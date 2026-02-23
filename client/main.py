# -*- coding: utf-8 -*-
"""
Exemple de client minimal pour Pepper (Python 2.7.18).
Envoie la transcription au serveur FastAPI et récupère la réponse du DialogManager.
"""

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
MODE = "phone"  # Options: "phone" or "pepper"
PHONE_URL = "http://192.168.1.11:8080/audio.wav"
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
LOG_FILE = os.path.join(LOG_DIR, "logs_{}.txt".format(datetime.datetime.now().strftime("%Y%m%d_%H%M%S")))

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
        """
        Logs state every 0.5s or immediately if an event/text is provided.
        """
        import datetime
        import time

        # Initialisation du timer interne
        if not hasattr(self, '_last_log_time'):
            self._last_log_time = 0

        current_time = time.time()
        
        # On logue si c'est un événement spécial OU si 0.5s sont passées
        is_event = event_name != "HEARTBEAT" or user_text != "" or pepper_answer != ""
        if not (is_event or (current_time - self._last_log_time) >= 0.5):
            return

        self._last_log_time = current_time
        
        try:
            # Récupération des états réels des flags (booléens)
            b_engaged = self.asr.is_engaged
            c_watching = self.asr.check_if_silent
            d_listening = self.asr.is_listening
            wake_idx   = self.asr.wake_chunk_index
            
            timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
            
            # Nettoyage du texte pour l'affichage en tableau
            u_text = user_text.replace("\n", " ")[:30]
            p_text = pepper_answer.replace("\n", " ")[:30]
            
            # On affiche T pour True et F pour False pour une lecture ultra-rapide
            line = "{} | {} | B = {} | C = {} | D = {} | Idx:{} | User:{} | Pepper:{}\n".format(
                timestamp,
                event_name.ljust(12),
                "T" if b_engaged else "F",
                "T" if c_watching else "F",
                "T" if d_listening else "F",
                str(wake_idx).zfill(3),
                u_text.ljust(15),
                p_text.ljust(15)
            )
            
            with open(log_file, "a") as f:
                f.write(line)
        except Exception:
            # On reste discret en cas d'erreur pour ne pas bloquer le robot
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
        #             if "chunk" in f.lower() and f.endswith(".wav"):
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