# -*- coding: utf-8 -*-
"""
Exemple de client minimal pour Pepper (Python 2.7.18).
Envoie la transcription au serveur FastAPI et récupère la réponse du DialogManager.
"""
import textwrap
import io
import time
import datetime
import os
import shutil

from ASREngine import ASREngine
from audio_manager import AudioSense, AudioInputs
from network_client import NetworkClient
from PepperOrchestrator import PepperConnector, PepperAudioCapture


# =================================================================
# --- CONFIGURATION HUB ---
# =================================================================

# 1. NETWORK CONFIG (Choose your active server)
SERVER_URL = "http://localhost:8000"
# SERVER_URL = "http://192.168.1.74:8000"
# SERVER_URL = "http://10.60.55.34:8000"

# 2. AUDIO SOURCE CONFIG
#MODE = "phone"  # Options: "phone" or "pepper"
MODE = "pepper"  # Options: "phone" or "pepper"

PHONE_URL = "http://10.126.8.53:8080/audio.wav"
# PHONE_URL = "http://10.60.55.196:8080/audio.wav"

# 3. ROBOT HARDWARE CONFIG
PEPPER_IP = "192.168.1.10"
# PEPPER_IP = "127.0.0.1" # For local simulation (Choregraphe)
PEPPER_PORT = 9559

# 4. DIALOG & TIMING SETTINGS
WAKE_WORDS = [u"pepper", u"bonjour"]
SILENCE_DELAY = 3.0
CONVERSATION_TIMEOUT = 15
SLOW_TIMEOUT = 50
TRANSCRIPT_BATCH_SIZE = 5 

# 5. Logging
LOG_DIR = "client"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# Le nom du fichier est fixé au démarrage du script
LOG_FILE = os.path.join(LOG_DIR, "logs_{}.log".format(datetime.datetime.now().strftime("%Y%m%d_%H%M%S")))

# 2. Création immédiate du fichier avec son header
with open(LOG_FILE, "w") as f:
    f.write("TIMESTAMP | EVENT | ARM B | ARM C | ARM D | WAKE_IDX | USER_TEXT | PEPPER_ANSWER\n")
    f.write("-" * 115 + "\n")

print("[LOGGING] Fichier initialisé : {}".format(LOG_FILE))
# Stockage !Attention, elle doit être la même dans les modules : ASREngine, PepperOrchestrator, audio_manager
TMP_DIR = "/tmp/pepper"

# --- INITIALISATION DOSSIER ---
if os.path.exists(TMP_DIR):
    # On nettoie les vieux résidus d'un crash précédent
    shutil.rmtree(TMP_DIR)

try:
    os.makedirs(TMP_DIR)
    print(u"[MAIN] Dossier temporaire prêt : {}".format(TMP_DIR).encode('utf-8'))
except Exception as e:
    print(u"[MAIN] Erreur création dossier : {}".format(str(e)).encode('utf-8'))

# =================================================================

class PepperAppMain():
    def __init__(self):
        print(u"[MAIN] Initialisation du système...".encode('utf-8'))
        
        # 1. Network & Hardware Setup
        self.net = NetworkClient(SERVER_URL, timeout=SLOW_TIMEOUT)
        
        # Setup Audio Inputs based on MODE
        self.pepper_spec = None
        if MODE == "pepper":
            self.connector = PepperConnector(PEPPER_IP, PEPPER_PORT)
            if self.connector.connect():
               self.pepper_spec = PepperAudioCapture(self.connector.get_session())
            pass
            
        self.audio_inputs = AudioInputs(mode=MODE, pepper_specialist=self.pepper_spec, phone_url=PHONE_URL)
        self.audio_sense = AudioSense(self.audio_inputs)

        # 2. ASR Engine Setup (The 4-Arm Engine)
        self.asr = ASREngine(
            audio_manager=self.audio_sense, 
            network_client=self.net, 
            wake_words=WAKE_WORDS, 
            silence_delay=SILENCE_DELAY,
            transcript_batch_size=TRANSCRIPT_BATCH_SIZE
        )

        # 3. App State
        self.is_running = True
        self.last_interaction = time.time()
        self.session_id = None
    
    def start(self):
        """Démarre le moteur ASR et la boucle de contrôle principale."""
        self.asr.start()
        
        print(u"[MAIN] Pepper est en veille. Dites 'Pepper' pour commencer.".encode('utf-8'))
        
        try:
            while self.is_running:
                self._update_logic()
                time.sleep(0.1)
        except KeyboardInterrupt:
            self.stop()
    
    def _update_logic(self):
        """Boucle de décision principale."""

        # --- ÉTAPE 1 : RÉVEIL (Via Arm B) ---
        # Here, the activation is done directly in Arm B inside asr object
        if self.asr.is_engaged and not self.asr.is_listening and not self.asr.check_if_silent:
            print(u"[MAIN] Réveil ! Activation de l'oreille (Arm D).".encode('utf-8'))
            self.asr.is_listening = True
            self.last_interaction = time.time()
            self._log_state("WAKE_WORD")

        # --- ÉTAPE 2 : TRAITEMENT DU TEXTE (Via Arm D) ---
        if self.asr.is_engaged and self.asr.committed_transcript.strip():
            captured_text = self.asr.committed_transcript.strip()

            self._log_state("TRANSCRIPT", user_text=captured_text)
            self.asr.committed_transcript = "" 
            

            # Détection d'erreur ou audio trop court
            if "ERROR_CONFIDENCE_LOW" in captured_text or len(captured_text) < 3:
                print(u"[MAIN] Audio illisible. Demande de répétition...".encode('utf-8'))
                # On envoie un message système caché au LLM
                error_prompt = u"[SYSTEM_NOTE: L'utilisateur a parlé mais l'audio était inaudible. Demande-lui poliment de répéter.]"
                self.handle_dialog(error_prompt)
            else:
                print(u"===> Utilisateur : {}".format(captured_text).encode('utf-8'))
                self.handle_dialog(captured_text)
            
            # --- PHASE 4 : THE HANDOVER ---
            # Pepper a fini de parler. On relance D et C en parallèle.
            print(u"[MAIN] Pepper a fini. Écoute + Surveillance silence...".encode('utf-8'))
            self.asr.check_if_silent = True   # Arm C surveille
            self.last_interaction = time.time()
            self._log_state("HANDOVER") # Optionnel: pour voir quand Pepper repasse en mode attente

        # --- ÉTAPE 3 : GESTION DU TIMEOUT (Si Arm C ne détecte rien) ---
        if self.asr.is_engaged and self.asr.check_if_silent:
            # Si Arm C n'a pas encore détecté de bruit (check_if_silent est tjs True)
            # et que le temps imparti est dépassé :
            if (time.time() - self.last_interaction) > CONVERSATION_TIMEOUT:
                print(u"[MAIN] Personne ne parle. Retour en veille.".encode('utf-8'))
                self._log_state("SLEEP_TIMEOUT")
                self._go_to_sleep()
        
        self._log_state()
    
    def handle_dialog(self, text):
        """Fait le pont avec le Network Client (Futur DialogEngine)."""
        # On coupe l'écoute pendant que le serveur réfléchit et que Pepper parle
        self.asr.is_listening = False 
        
        # Peut etre à rajouter plus tard
        # if text == "[SYSTEM_ERROR_UNRELIABLE_AUDIO]":
        #     msg_for_llm = u"L'audio est mauvais. Demande poliment de répéter en répondant UNIQUEMENT en {0}.".format(lang)
        # else:
        #     msg_for_llm = text

        print(u"[LLM] Envoi au DialogManager...".encode('utf-8'))
        response = self.net.send_dialog_text(text, session_id=self.session_id)
        
        if response:
            self.session_id = response.get("session_id")
            answer = response.get("text", "")
            print(u"===> Robot : {}".format(answer).encode('utf-8'))
            self._log_state("PEPPER_REPLY", pepper_answer=answer)

            # Ici on appellera self.connector.say(answer) quand le robot sera là
            # Pour l'instant, on simule le temps de parole
            time.sleep(len(answer) * 0.05)
    
    def _go_to_sleep(self):
        """Réinitialise l'état en veille."""
        print(u"[MAIN] Timeout : Retour en veille.".encode('utf-8'))
        self.asr.is_engaged = False
        self.asr.is_listening = False
        self.asr.check_if_silent = False
        self.asr.last_transcript = ""
        self.session_id = None
    
    def _log_state(self, event_name="HEARTBEAT", user_text="", pepper_answer="", log_file=LOG_FILE):
        # Setup widths - Time compressed, Committed added
        W_TS, W_EV, W_B, W_C, W_D, W_IDX, W_U, W_P, W_COM = 8, 15, 3, 3, 3, 8, 25, 25, 25
        
        if not hasattr(self, '_log_line_count'): self._log_line_count = 0
        if not hasattr(self, '_last_log_time'): self._last_log_time = 0

        is_event = event_name != "HEARTBEAT" or user_text != "" or pepper_answer != ""
        if not (is_event or (time.time() - self._last_log_time) >= 0.5): 
            return
        self._last_log_time = time.time()

        def safe_unicode(text):
            """Force conversion to unicode without crashing on accents"""
            if text is None: return u""
            try:
                if isinstance(text, str):
                    return text.decode('utf-8')
                return unicode(text)
            except:
                # Fallback for weird characters
                return unicode(repr(text))

        def get_header():
            h = "| {0} | {1} | {2}|{3}|{4} | {5} | {6} | {7} | {8} |".format(
                "TIME".ljust(W_TS), "EVENT".ljust(W_EV), "B".center(W_B),
                "C".center(W_C), "D".center(W_D), "W_IDX".center(W_IDX),
                "USER_TEXT".ljust(W_U), "PEPPER_ANS".ljust(W_P), "COMMITTED".ljust(W_COM))
            sep = "-" * len(h)
            return "\n" + sep + "\n" + h + "\n" + sep + "\n"

        output = u""
        if self._log_line_count % 30 == 0:
            output += get_header()
        
        # Process all text inputs safely
        u_clean = safe_unicode(user_text).replace("\n", " ")
        p_clean = safe_unicode(pepper_answer).replace("\n", " ")
        c_clean = safe_unicode(getattr(self.asr, 'committed_transcript', "")).replace("\n", " ")
        
        u_lines = textwrap.wrap(u_clean, width=W_U)
        p_lines = textwrap.wrap(p_clean, width=W_P)
        c_lines = textwrap.wrap(c_clean, width=W_COM)
        max_lines = max(len(u_lines), len(p_lines), len(c_lines), 1)

        for i in range(max_lines):
            ts = datetime.datetime.now().strftime("%H:%M:%S") if i == 0 else " " * W_TS
            display_event = (event_name if i == 0 else "").ljust(W_EV)

            if i == 0:
                b = ("T" if getattr(self.asr, 'is_engaged', False) else "F").center(W_B)
                c = ("T" if getattr(self.asr, 'check_if_silent', False) else "F").center(W_C)
                d = ("T" if getattr(self.asr, 'is_listening', False) else "F").center(W_D)
                idx = str(getattr(self.asr, 'wake_chunk_index', 0)).zfill(3).center(W_IDX)
            else:
                b, c, d, idx = " ".center(W_B), " ".center(W_C), " ".center(W_D), " ".center(W_IDX)
            
            u_txt = (u_lines[i] if i < len(u_lines) else u"").ljust(W_U)
            p_txt = (p_lines[i] if i < len(p_lines) else u"").ljust(W_P)
            com_txt = (c_lines[i] if i < len(c_lines) else u"").ljust(W_COM)

            line = u"| {0} | {1} | {2}|{3}|{4} | {5} | {6} | {7} | {8} |\n".format(
                ts, display_event, b, c, d, idx, u_txt, p_txt, com_txt)
            output += line

        if is_event:
            output += u"-" * (len(line) - 1) + u"\n"
        
        self._log_line_count += 1
        
        # Write only to file, never to console terminal
        try:
            with open(log_file, "ab") as f:
                f.write(output.encode('utf-8', 'replace'))
        except:
            pass

    def stop(self):
        """Nettoyage partiel : on garde les fichiers assemblés pour debug."""
        import os
        self.is_running = False
        
        # 1. On demande à l'ASR de s'arrêter
        self.asr.stop()
        
        # print(u"[MAIN] Nettoyage sélectif du dossier {}...".format(TMP_DIR).encode('utf-8'))
        # try:
        #     if os.path.exists(TMP_DIR):
        #         files = os.listdir(TMP_DIR)
        #         for f in files:
        #             # On supprime uniquement les chunks individuels (ex: chunk_001.wav)
        #             # On GARDE les fichiers qui contiennent 'merged' ou 'wake'
        #             if "chunk" in sf.lower() and f.endswith(".wav"):
        #                 os.remove(os.path.join(TMP_DIR, f))
                
        #         print(u"[MAIN] Chunks supprimés. Merged files conservés dans {}".format(TMP_DIR).encode('utf-8'))
            
        #     print(u"[MAIN] Nettoyage terminé.".encode('utf-8'))
        # except Exception as e:
        #     print("Erreur nettoyage: " + str(e))
            
        print(u"[MAIN] Système arrêté proprement.".encode('utf-8'))

    

if __name__ == "__main__":
    app = PepperAppMain()
    try:
        app.start()
    except KeyboardInterrupt:
        print(u"\n[SIGINT] Interruption détectée...".encode('utf-8'))
        app.stop()
    except Exception as e:
        print(u"\n[FATAL] Erreur inattendue: {}".format(e).encode('utf-8'))
        app.stop()