# -*- coding: utf-8 -*-
"""
Client principal pour Pepper (Python 2.7).
Flux : Micro Pepper → ASR → DialogManager → Actions (TTS, tablette, navigation, etc.)
"""

import qi
import sys
import time
import os
import requests
import json

from ALAudioRecorder import PepperAudioCapture
from affichage_dynamique import PepperWebDisplayService
from nav import Navigation

# ─── CONFIGURATION ───
PEPPER_IP = "192.168.13.213"
PEPPER_PORT = 9559

# Le serveur FastAPI (NLU + Dialog + ASR)
SERVER_URL = "http://localhost:8001"
ASR_URL = SERVER_URL + "/v1/asr"
RESPOND_URL = SERVER_URL + "/v1/respond"
WEB_URL = "http://10.126.8.40:5500/"

# Paramètres audio
RECORD_DURATION = 5          # secondes d'écoute par tour
SAMPLE_RATE = 16000

# Paramètres conversation
CONVERSATION_TIMEOUT = 30    # secondes sans interaction avant retour en veille
WAKE_WORDS = [u"pepper", u"bonjour", u"salut", u"hello"]
BYE_WORDS = [u"au revoir", u"aurevoir", u"à bientôt", u"a bientot", u"bye", u"goodbye", u"bonne journée", u"bonne soirée", u"ciao", u"adieu"]

REQUEST_TIMEOUT = 60


class PepperOrchestrator:
    """Orchestre la boucle principale du robot Pepper."""

    def __init__(self):
        # 1. Connexion au robot
        print("[INIT] Connexion a Pepper ({}:{})...".format(PEPPER_IP, PEPPER_PORT))
        self.session = qi.Session()
        try:
            self.session.connect("tcp://{}:{}".format(PEPPER_IP, PEPPER_PORT))
        except RuntimeError as e:
            print("[ERREUR] Impossible de se connecter a Pepper: {}".format(e))
            sys.exit(1)
        print("[INIT] Connecte !")

        # 2. Services NAOqi
        self.tts = self.session.service("ALTextToSpeech")
        self.tts.setLanguage("French")
        self.motion = self.session.service("ALMotion")
        self.posture = self.session.service("ALRobotPosture")
        self.leds = self.session.service("ALLeds")
        self.memory = self.session.service("ALMemory")

        # 2b. Désactiver la veille autonome pour éviter que Pepper
        #     réponde tout seul aux phrases comme "au revoir", "bonjour", etc.
        # try:
        #     self.autonomous_life = self.session.service("ALAutonomousLife")
        #     self.autonomous_life.setState("disabled")
        #     print("[INIT] Autonomous Life desactivee.")
        # except Exception as e:
        #     print("[INIT] Impossible de desactiver Autonomous Life: {}".format(e))

        # Désactiver aussi le dialogue natif de Pepper
        try:
            self.basic_awareness = self.session.service("ALBasicAwareness")
            self.basic_awareness.stopAwareness()
            print("[INIT] Basic Awareness desactivee.")
        except Exception as e:
            print("[INIT] Impossible de desactiver Basic Awareness: {}".format(e))

        # Désactiver ALSpeechRecognition natif (si actif)
        try:
            asr_native = self.session.service("ALSpeechRecognition")
            asr_native.pause(True)
            print("[INIT] ASR natif mis en pause.")
        except Exception as e:
            print("[INIT] ASR natif non disponible: {}".format(e))

        
        # 3. Module audio (micro Pepper → WAV local)
        self.audio = PepperAudioCapture(
            self.session,
            asr_url=ASR_URL,
        )

        # 4. Tablette
        try:
            self.tablet = PepperWebDisplayService(self.session)
        except Exception as e:
            print("[INIT] Tablette non disponible: {}".format(e))
            self.tablet = None

        # 4. Navigation
        try:
            self.nav = Navigation(WEB_URL, self.session)
        except Exception as e:
            print("[INIT] Navigation non disponible: {}".format(e))
            self.nav = None

        # 5. Etat conversation
        self.is_engaged = False
        self.dialog_session_id = None
        self.last_interaction = 0
        self.is_running = True

    # ─── COMMUNICATION SERVEUR ───

    def send_to_asr(self, filepath):
        """Envoie le fichier WAV au serveur ASR et retourne le dict résultat."""
        if not filepath or not os.path.exists(filepath):
            return None
        try:
            with open(filepath, "rb") as f:
                files = {"file": (os.path.basename(filepath), f, "audio/wav")}
                resp = requests.post(ASR_URL, files=files, timeout=REQUEST_TIMEOUT)
            if resp.ok:
                result = resp.json()
                text = result.get("text", "")
                lang = result.get("language", "??")
                if isinstance(text, unicode):
                    text_log = text.encode("utf-8")
                else:
                    text_log = text
                if isinstance(lang, unicode):
                    lang_log = lang.encode("utf-8")
                else:
                    lang_log = lang
                print("[ASR] Transcription: '{}' (langue: {})".format(text_log, lang_log))
                return result
            else:
                print("[ASR] Erreur HTTP {}: {}".format(resp.status_code, resp.text[:200]))
                return None
        except Exception as e:
            err_msg = str(e)
            if isinstance(err_msg, unicode):
                err_msg = err_msg.encode("utf-8")
            print("[ASR] Erreur envoi: {}".format(err_msg))
            return None

    def send_to_dialog(self, text, lang="fr"):
        """Envoie le texte transcrit au DialogManager et retourne la réponse."""
        payload = {
            "text": text,
            "lang": lang,
            "session_id": self.dialog_session_id,
        }
        try:
            resp = requests.post(RESPOND_URL, json=payload, timeout=REQUEST_TIMEOUT)
            if resp.ok:
                data = resp.json()
                self.dialog_session_id = data.get("session_id", self.dialog_session_id)
                return data
            else:
                print("[DIALOG] Erreur HTTP {}: {}".format(resp.status_code, resp.text[:200]))
                return None
        except Exception as e:
            err_msg = str(e)
            if isinstance(err_msg, unicode):
                err_msg = err_msg.encode("utf-8")
            print("[DIALOG] Erreur envoi: {}".format(err_msg))
            return None

    # ─── ACTIONS DU ROBOT ───

    def robot_say(self, text):
        """Fait parler le robot. Gère l'encodage Python 2.7."""
        if not text:
            return
        if isinstance(text, unicode):
            text_for_tts = text.encode("utf-8")
        else:
            text_for_tts = text
        print("[TTS] {}".format(text_for_tts))
        try:
            self.tts.say(text_for_tts)
        except Exception as e:
            print("[TTS] Erreur: {}".format(e))

    def robot_gesture(self, gesture_name):
        """Lance un geste/animation sur le robot."""
        try:
            if gesture_name == "wave":
                self.motion.setAngles("RShoulderPitch", -0.5, 0.2)
                time.sleep(0.5)
                self.motion.setAngles("RShoulderPitch", 1.0, 0.2)
            elif gesture_name == "nod":
                self.motion.setAngles("HeadPitch", 0.3, 0.3)
                time.sleep(0.3)
                self.motion.setAngles("HeadPitch", -0.1, 0.3)
                time.sleep(0.3)
                self.motion.setAngles("HeadPitch", 0.0, 0.2)
        except Exception as e:
            print("[GESTURE] Erreur: {}".format(e))

    def robot_show_url(self, url):
        """Affiche une URL sur la tablette."""
        if self.tablet:
            try:
                self.tablet.showUrl(url)
            except Exception as e:
                print("[TABLET] Erreur: {}".format(e))

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
                    if result and result.get("matched"):
                        best = result.get("best_match", {})
                        nom = best.get("nom", "")
                        prenom = best.get("prenom", "")
                        if isinstance(nom, unicode):
                            nom = nom.encode("utf-8")
                        if isinstance(prenom, unicode):
                            prenom = prenom.encode("utf-8")
                        self.robot_say("Bonjour {} {} !".format(prenom, nom))
                    else:
                        print("[ACTION] Visage non reconnu")
                else:
                    print("[ACTION] Aucun visage detecte")
                flow.stop_face_detection()
            except Exception as e:
                print("[ACTION] Erreur reco faciale: {}".format(e))

        elif action_type == "booking_confirmed":
            # Réservation confirmée
            booking = actions.get("booking", {})
            print("[ACTION] Reservation confirmee: {}".format(booking))
            self.robot_gesture("nod")

        elif action_type == "booking_slot_filling":
            # En attente d'info pour la réservation (le texte est déjà dit)
            missing = actions.get("missing_slot", "")
            print("[ACTION] Slot manquant: {}".format(missing))

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
                self.robot_show_url(url)

    # ─── DETECTION WAKE WORD ───

    def contains_wake_word(self, text):
        """Vérifie si le texte contient un mot de réveil."""
        if not text:
            return False
        if isinstance(text, str):
            text = text.decode("utf-8", "ignore")
        text_lower = text.lower()
        for word in WAKE_WORDS:
            if word in text_lower:
                return True
        return False
    
    def contains_bye_word(self, text):
        """Vérifie si le texte contient un mot d'au revoir."""
        if not text:
            return False
        if isinstance(text, str):
            text = text.decode("utf-8", "ignore")
        text_lower = text.lower()
        for word in BYE_WORDS:
            if word in text_lower:
                return True
        return False

    def disengage(self):
        """Désengager la conversation et retourner en mode veille."""
        print("\n[BYE] Desengagement de la conversation.")
        self.robot_say("Au revoir ! N'hésitez pas à revenir si vous avez besoin d'aide.")
        self.robot_gesture("wave")

        # Cacher la tablette
        if self.tablet:
            try:
                self.tablet.hidePage()
            except Exception:
                pass

        # Remettre les LEDs en blanc (veille)
        try:
            self.leds.fadeRGB("FaceLeds", 0x00FFFFFF, 0.5)
        except Exception:
            pass

        self.is_engaged = False
        self.dialog_session_id = None
        self.last_interaction = 0

    # ─── ENREGISTREMENT + NETTOYAGE ───

    def record_audio(self, duration=RECORD_DURATION):
        """Enregistre l'audio et retourne le chemin du fichier."""
        filepath = self.audio.record_chunk(
            filename="pepper_input.wav",
            duration=duration,
            sample_rate=SAMPLE_RATE,
            channels=(0, 0, 1, 0),
        )
        return filepath

    def cleanup_file(self, filepath):
        """Supprime le fichier temporaire."""
        if filepath:
            try:
                os.remove(filepath)
            except Exception:
                pass

    # ─── BOUCLE PRINCIPALE ───

    def run_idle_mode(self):
        """
        Mode veille : écoute en continu, attend un wake word.
        Retourne True si un wake word est détecté, False si on doit arrêter.
        """
        print("\n[VEILLE] En attente de wake word ({})...".format(
            ", ".join([w.encode("utf-8") for w in WAKE_WORDS])))
        self.leds.fadeRGB("FaceLeds", 0x00FFFFFF, 0.5)  # Blanc = veille

        filepath = self.record_audio(duration=3)
        if not filepath:
            return False

        # Envoyer au ASR
        result = self.send_to_asr(filepath)
        self.cleanup_file(filepath)

        if result:
            text = result.get("text", "")
            if self.contains_wake_word(text):
                print("[VEILLE] Wake word detecte !")
                self.is_engaged = True
                self.last_interaction = time.time()
                self.dialog_session_id = None  # Nouvelle session

                # Envoyer aussi le premier message au dialog
                self.process_user_input(text, result.get("language", "fr"))
                return True

        return False

    def run_engaged_mode(self):
        """
        Mode engagé : conversation active avec l'utilisateur.
        """
        # Vérifier le timeout
        if time.time() - self.last_interaction > CONVERSATION_TIMEOUT:
            print("\n[TIMEOUT] Retour en veille apres {} secondes d'inactivite.".format(
                CONVERSATION_TIMEOUT))
            self.robot_say("Si vous avez besoin de moi, n'hésitez pas à m'appeler.")
            self.is_engaged = False
            self.dialog_session_id = None
            return

        # Indiquer visuellement qu'on écoute
        self.leds.fadeRGB("FaceLeds", 0x0000FF00, 0.3)  # Vert = écoute
        print("\n[ECOUTE] Parlez maintenant ({} secondes)...".format(RECORD_DURATION))

        filepath = self.record_audio(duration=RECORD_DURATION)

        # Remettre LEDs en bleu = traitement
        self.leds.fadeRGB("FaceLeds", 0x000000FF, 0.3)

        if not filepath:
            print("[ERREUR] Enregistrement echoue.")
            return

        # 1. ASR
        asr_result = self.send_to_asr(filepath)
        self.cleanup_file(filepath)

        if not asr_result:
            print("[ERREUR] ASR n'a pas repondu.")
            return

        text = asr_result.get("text", "")
        lang = asr_result.get("language", "fr")
        is_reliable = asr_result.get("is_reliable", True)

        # Vérifier la fiabilité
        if not is_reliable or not text.strip():
            print("[ASR] Transcription non fiable ou vide.")
            self.robot_say("Je n'ai pas bien entendu, pouvez-vous répéter ?")
            self.last_interaction = time.time()
            return

        # Vérifier si l'utilisateur dit au revoir AVANT d'envoyer au DialogManager
        if self.contains_bye_word(text):
            self.disengage()
            return

        # 2. Envoyer au DialogManager
        self.process_user_input(text, lang)

    def process_user_input(self, text, lang="fr"):
        """Envoie le texte au DialogManager et traite la réponse."""
        self.last_interaction = time.time()

        if isinstance(text, unicode):
            text_log = text.encode("utf-8")
        else:
            text_log = text
        print("\n[USER] {}".format(text_log))

        dialog_result = self.send_to_dialog(text, lang=lang)

        if not dialog_result:
            self.robot_say("Désolé, je n'arrive pas à contacter le serveur.")
            return

        # Extraire la réponse et les actions
        response_text = dialog_result.get("text", "")
        actions = dialog_result.get("actions", {})

        # 3. Exécuter les actions
        self.handle_actions(actions)

        # 4. Faire parler le robot
        self.robot_say(response_text)

        self.tablet.hidePage()

        

    # ─── POINT D'ENTREE ───

    def start(self):
        """Boucle principale du robot."""
        print("\n" + "=" * 60)
        print("  PEPPER - ROBOT D'ACCUEIL MULTISPORT")
        print("  Serveur: {}".format(SERVER_URL))
        print("=" * 60)

        # Posture initiale
        try:
            self.posture.goToPosture("StandInit", 0.5)
        except Exception as e:
            print("[INIT] Erreur posture: {}".format(e))

        self.robot_say("Je suis prêt. Dites bonjour pour commencer.")

        try:
            while self.is_running:
                if self.is_engaged:
                    self.run_engaged_mode()
                else:
                    self.run_idle_mode()

                # Petite pause pour ne pas surcharger
                time.sleep(0.2)

        except KeyboardInterrupt:
            print("\n\n[ARRET] Interruption clavier.")
        finally:
            self.stop()

    # ...existing code...
    def stop(self):
        """Arrêt propre."""
        self.is_running = False
        print("[ARRET] Nettoyage...")
        self.robot_say("Au revoir !")

        # Nettoyage audio
        self.audio.shutdown()

        # Nettoyage fichiers
        self.cleanup_file("/tmp/pepper_input.wav")

        # LEDs éteintes
        try:
            self.leds.fadeRGB("FaceLeds", 0x00000000, 0.5)
        except Exception:
            pass

        # Réactiver la veille autonome
        try:
            self.autonomous_life.setState("solitary")
            print("[ARRET] Autonomous Life reactivee.")
        except Exception:
            pass

        try:
            self.basic_awareness.startAwareness()
        except Exception:
            pass

        print("[ARRET] Termine.")


if __name__ == "__main__":
    print("--- Demarrage du client Pepper ---")
    orchestrator = PepperOrchestrator()
    orchestrator.start()