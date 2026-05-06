# -*- coding: utf-8 -*-
"""
Exemple de client minimal pour Pepper (Python 2.7.18).
Envoie la transcription au serveur FastAPI et récupère la réponse du DialogManager.
"""
import textwrap
import qi
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
SERVER_URL = "http://localhost:8001"
# SERVER_URL = "http://192.168.1.74:8000"
# SERVER_URL = "http://10.60.55.34:8000"

# Base URL pour les pages web (tablette)
WEB_BASE_URL = "http://10.26.1.75:8001/"  # Ou "http://localhost:8000/" pour test

# URLs des pages web
WEB_NAVIGATION_URL = WEB_BASE_URL + "carte_navigation.html"
WEB_RESERVATION_URL = WEB_BASE_URL + "reservation.html"
WEB_SATISFACTION_URL = WEB_BASE_URL + "satisfaction.html"
# Shortcut pour compatibilité
WEB_URL = WEB_BASE_URL #C'est quoi ça Yanis ?

# 2. AUDIO SOURCE CONFIG
# MODE = "phone"  # Options: "phone" or "pepper"
MODE = "pepper"  # Options: "phone" or "pepper"

PHONE_URL = "http://10.126.3.205:8080/audio.wav"
#PHONE_URL = "http://10.60.55.196:8080/audio.wav"

# 3. ROBOT HARDWARE CONFIG
PEPPER_IP = "192.168.13.202"
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
               self.connector.robot_say("Application demarrée - Vous pouvez parlez")
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
    
        # Info utilisateur (ex: après reconnaissance faciale)
        self.current_user = None
        
        # Gestion du formulaire de satisfaction
        self.satisfaction_form_displayed = False
        self.satisfaction_form_timeout = None

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

            if MODE == "pepper":
                user_name = self._try_face_recognition()
                if user_name:
                    print(u"[MAIN] Utilisateur identifié : {}".format(user_name).encode('utf-8'))
                    # You can store this in the session to pass to the LLM later
                    self.current_user = user_name
            else :
                self.current_user = "Patrice SEBASTIANO"

            if MODE == "pepper":
                self.connector.robot_say(u"Bonjour {}. Comment puis-je vous aider aujourd'hui ?".format(self.current_user).encode('utf-8'))

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

        # --- ÉTAPE 3.5 : GESTION DU FORMULAIRE DE SATISFACTION ---
        # Si un formulaire est affiché et le timeout est dépassé, revenir en veille
        if self.satisfaction_form_displayed and self.satisfaction_form_timeout:
            if time.time() - self.satisfaction_form_timeout > 60:  # 60 secondes
                print(u"[MAIN] Formulaire inactif (1 min). Retour en veille.".encode('utf-8'))
                self._close_satisfaction_form()
                self._go_to_sleep()

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
        response = self.net.send_dialog_text(text, session_id=self.session_id, user_name=self.current_user)
        
        print("RESPONSE ", response)
        print("\n")
            
        
        if response:
            self.session_id = response.get("session_id")
            answer = response.get("text", "")
            actions = response.get("actions", {})
                   
            print(u"===> Robot : {}".format(answer).encode('utf-8'))
            self._log_state("PEPPER_REPLY", pepper_answer=answer)
            self._log_state("ACTIONS", pepper_answer=str(actions))
            
            print("PEPPER_REPLY", answer)
            print("\n")
            #Seulement sur le vrai pepper
            if MODE == "pepper":
                # Cette ligne bloque maintenant tout le script jusqu'à la fin du "parler"               
                self.handle_actions(actions)
                self.connector.robot_say(answer)
                
                if self.tablet:
                    self.tablet.hidePage()
                
                # Afficher le formulaire de satisfaction après la réponse
                self._show_satisfaction_form()
            else:
                # Simulation uniquement pour le mode phone
                time.sleep(len(answer) * 0.05)
                
                # Afficher le formulaire de satisfaction en mode test aussi
                self._show_satisfaction_form()
    
    def _go_to_sleep(self):
        """Réinitialise l'état en veille."""
        print(u"[MAIN] Timeout : Retour en veille.".encode('utf-8'))
        self.asr.is_engaged = False
        self.asr.is_listening = False
        self.asr.check_if_silent = False
        self.asr.last_transcript = ""
        self.session_id = None
        
        # Fermer le formulaire de satisfaction s'il est ouvert
        self._close_satisfaction_form()
    
    def _show_satisfaction_form(self):
        """Affiche le formulaire de satisfaction et attend 1 minute avant fermeture automatique."""
        if not self.session_id:
            print(u"[SATISFACTION] Pas de session ID, impossible d'afficher le formulaire.".encode('utf-8'))
            return
        
        # Construire l'URL avec la session ID
        satisfaction_url = "{}?session_id={}".format(WEB_SATISFACTION_URL, self.session_id)
        
        print(u"[SATISFACTION] Affichage du formulaire...".encode('utf-8'))
        self.satisfaction_form_displayed = True
        self.satisfaction_form_timeout = time.time()
        
        # Afficher le formulaire sur la tablette
        if MODE == "pepper":
            try:
                self.connector.robot_show_url(satisfaction_url)
                print(u"[SATISFACTION] Formulaire affiché: {}".format(satisfaction_url).encode('utf-8'))
            except Exception as e:
                print(u"[SATISFACTION] Erreur affichage du formulaire: {}".format(str(e)).encode('utf-8'))
        else:
            print(u"[SATISFACTION] URL du formulaire: {}".format(satisfaction_url).encode('utf-8'))
        
        if MODE == "pepper":
            self.connector.robot_say(u"Merci pour cette conversation. Pouvez-vous compléter le questionnaire sur la tablette ? Vous avez une minute.".encode('utf-8'))
    
    def _close_satisfaction_form(self):
        """Ferme le formulaire de satisfaction."""
        if self.satisfaction_form_displayed:
            print(u"[SATISFACTION] Fermeture du formulaire.".encode('utf-8'))
            self.satisfaction_form_displayed = False
            self.satisfaction_form_timeout = None
            
            # Masquer la page sur la tablette
            if MODE == "pepper":
                try:
                    if hasattr(self, 'tablet') and self.tablet:
                        self.tablet.hidePage()
                    print(u"[SATISFACTION] Formulaire fermé.".encode('utf-8'))
                except Exception as e:
                    print(u"[SATISFACTION] Erreur fermeture: {}".format(str(e)).encode('utf-8'))
    
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

    def handle_actions(self, actions):
        """
        Traite les actions retournées par le DialogManager.
        actions est un dict avec un champ 'type' et des données associées.
        """
        if not actions or not isinstance(actions, dict):
            return

        action_type = actions.get("type", "")
        print("[ACTION] Type: {}".format(action_type))

        if action_type == "face_recognition":
            # Lancer la reconnaissance faciale
            print("[ACTION] Reconnaissance faciale demandee")
            try:
                from reco_face import FaceRecoFlow
                flow = FaceRecoFlow(self.session)
                flow.start_face_detection()
                face_data = flow.wait_for_face(timeout_s=10)
                if face_data:
                    image_bytes, meta = flow.take_picture()
                    result = flow.call_verify_api(image_bytes, meta=meta)
                    print(result)
                    if result and result.get("matched"):
                        best = result.get("best_match", {})
                        nom = best.get("nom", "")
                        prenom = best.get("prenom", "")
                        if isinstance(nom, unicode):
                            nom = nom.encode("utf-8")
                        if isinstance(prenom, unicode):
                            prenom = prenom.encode("utf-8")
                        self.connector.robot_say(u"Bonjour {} {} !".format(prenom, nom))
                    else:
                        print("[ACTION] Visage non reconnu")
                else:
                    print("[ACTION] Aucun visage detecte")
                flow.stop_face_detection()
            except Exception as e:
                print("[TTS] Erreur reco faciale: " + repr(e))

        elif action_type == "booking_confirmed":
            # Réservation confirmée
            booking = actions.get("booking", {})
            print("[ACTION] Reservation confirmee: {}".format(booking))
            self.connector.robot_gesture("nod")

        elif action_type == "booking_slot_filling":
            # En attente d'info pour la réservation - afficher le formulaire
            missing = actions.get("missing_slot", "")
            print("[ACTION] Slot manquant: {}".format(missing))
            
            # Afficher la page de réservation avec session_id
            if self.dialog_session_id:
                reservation_url = "{}?session_id={}".format(WEB_RESERVATION_URL, self.dialog_session_id)
                self.connector.robot_show_url(reservation_url)
                print("[ACTION] Page de reservation affichee: {}".format(reservation_url))

        elif action_type == "navigate":
            # Instructions de navigation
            destination = actions.get("destination", "")
            instructions = actions.get("instructions", "")

            if self.nav and destination:
                try:
                    # Afficher la carte sur la tablette
                    self.nav.afficher_carte(destination)
                    print("[ACTION] Carte affichee pour: {}".format(
                        destination.encode("utf-8") if isinstance(destination, unicode) else destination))
                except Exception as e:
                    print("[ACTION] Erreur affichage carte: {}".format(e))

        elif action_type == "show_url":
            url = actions.get("url", "")
            if url:
                self.connector.robot_show_url(url)
        
        elif action_type == "show_web_form":
            # Afficher un formulaire web avec synchronisation
            form_type = actions.get("form_type", "reservation")
            if form_type == "reservation" and self.dialog_session_id:
                reservation_url = "{}?session_id={}".format(WEB_RESERVATION_URL, self.dialog_session_id)
                self.connector.robot_show_url(reservation_url)
                print("[ACTION] Formulaire web affiche: {}".format(reservation_url))


    def _try_face_recognition(self):
            """
            Lance la détection faciale et retourne (prenom, nom) ou (None, None).
            """
            try:
                from reco_face import FaceRecoFlow
                VERIFY_URL = SERVER_URL + "/v1/verify"

                print("[FACE] Lancement de la detection faciale...")
                self.leds.fadeRGB("FaceLeds", 0x00FFFF00, 0.3)

                flow = FaceRecoFlow(self.session, verify_url=VERIFY_URL)
                flow.start_face_detection()

                face_data = flow.wait_for_face(timeout_s=8)
                if not face_data:
                    flow.stop_face_detection()
                    return None, None

                image_bytes, meta = flow.take_picture()
                flow.stop_face_detection()

                result = flow.call_verify_api(image_bytes, meta=meta)
                print(result)
                if result and result.get("matched") and result.get("best_match"):
                    best = result["best_match"]
                    # FIX: s'assurer que prenom/nom sont des str bytes et non unicode
                    prenom = best.get("prenom", "") or ""
                    nom = best.get("nom", "") or ""

                    # Convertir en bytes UTF-8 pour l'affichage Python 2.7
                    prenom_b = prenom.encode("utf-8") if isinstance(prenom, unicode) else prenom
                    nom_b = nom.encode("utf-8") if isinstance(nom, unicode) else nom

                    # FIX: utiliser b"" concatenation pour le print, pas .format() avec unicode
                    print("[FACE] Personne reconnue: " + prenom_b + " " + nom_b)

                    # Retourner les unicode originaux (pas les bytes) pour l'usage ultérieur
                    return prenom, nom
                else:
                    print("[FACE] Personne non reconnue.")
                    return None, None

            except Exception as e:
                # FIX: triple protection contre UnicodeEncodeError
                try:
                    err_str = unicode(e).encode("utf-8")
                except Exception:
                    try:
                        err_str = str(e)
                    except Exception:
                        err_str = "erreur inconnue"
                print("[FACE] Erreur reconnaissance faciale: " + err_str)
                return None, None


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


