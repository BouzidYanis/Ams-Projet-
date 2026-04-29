# -*- coding: utf-8 -*-
"""
Module pour créer une session de connectino avec le robot le controler
 - Enregrister l'audio
 - Enregrister la video
 - Faire dire des choses
"""

import time
import os
import paramiko  # pour récupérer le fichier depuis le robot via SCP/SFTP
import qi
from affichage_dynamique import PepperWebDisplayService
from nav import Navigation
from Queue import Queue

TMP_DIR = "/tmp/pepper"

# Configuration
PEPPER_IP = "192.168.13.230"
PEPPER_PORT = 9559

#Copier tel quel de chez Yanis
WEB_BASE_URL = "http://10.126.5.245:5500/"  # Ou "http://localhost:8000/" pour test
WEB_URL = WEB_BASE_URL

class PepperConnector:
    """
    Gère la session Qi et centralise l'accès aux services du robot.
    """
    def __init__(self, ip=PEPPER_IP, port=PEPPER_PORT):
        self.ip = ip
        self.port = port
        self.session = qi.Session()
        
        # Core Services
        self.tts = None
        self.motion = None
        self.posture = None
        self.leds = None
        self.memory = None
        
        # Specialized Services
        self.tablet = None
        self.nav = None
        self.audio = None
        
        # Behavioral Services (To be disabled)
        self.basic_awareness = None
        self.autonomous_life = None

    def connect(self):
        """Établit la connexion et initialise les services."""
        connection_url = "tcp://{}:{}".format(self.ip, self.port)
        
        # --- 1. CRITICAL SERVICES (The "Must-Haves") ---
        try:
            self.session.connect(connection_url)
            print(u"[CONNEXION] Connecté à Pepper sur {}".format(connection_url))
            
            # Initialization of core services
            self.tts = self.session.service("ALAnimatedSpeech")
            self.memory = self.session.service("ALMemory")
            self.motion = self.session.service("ALMotion")
            self.posture = self.session.service("ALRobotPosture")
            self.leds = self.session.service("ALLeds")
            
            # Configure Language
            tts_config = self.session.service("ALTextToSpeech")
            tts_config.setLanguage("French")

        except RuntimeError as e:
            print(u"[ERREUR CRITIQUE] Connexion échouée: {}".format(e))
            return False

        # --- 2. OPTIONAL CONFIGURATION (The "Nice-to-Haves") ---
        # We put these in separate try/except so if one fails, the others still try to run.
        
        # Disable Basic Awareness (Stop Pepper from moving his head to everyone)
        try:
            self.basic_awareness = self.session.service("ALBasicAwareness")
            self.basic_awareness.stopAwareness()
            print("[INIT] Basic Awareness désactivée.")
        except Exception as e:
            print("[INIT] Info: ALBasicAwareness non disponible ou déjà stoppé.")

        # Pause Native ASR (Important so the robot doesn't "listen" to itself)
        try:
            asr_native = self.session.service("ALSpeechRecognition")
            asr_native.pause(True)
            print("[INIT] ASR natif mis en pause.")
        except Exception as e:
            print("[INIT] Info: ASR natif non disponible sur ce modèle.")

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

        # If we reached this point, the connection is solid!
        return True

    def robot_say(self, text):
        """
        Fait parler le robot de manière synchrone (bloquante).
        Gère l'encodage UTF-8 et attend la fin de l'élocution.
        """
        if not text:
            return

        # 1. GESTION DE L'ENCODAGE (Python 2.7 Safety)
        # On s'assure d'envoyer des bytes UTF-8 à NAOqi
        if isinstance(text, unicode):
            text_bytes = text.encode("utf-8")
        else:
            text_bytes = text

        print("[TTS] " + text_bytes)

        try:
            # 2. EXECUTION SYNCHRONE
            # .post lance la tâche en arrière-plan et retourne un ID
            # .wait(id, 0) bloque le script jusqu'à ce que cet ID soit terminé
            if self.tts:
                say_id = self.tts.post.say(text_bytes)
                self.tts.wait(say_id, 0) 
            else:
                print("[TTS] Erreur: Service TTS non initialisé.")
                
        except Exception as e:
            # Triple protection pour l'affichage de l'erreur en console
            try:
                err_msg = str(e)
            except:
                err_msg = "Erreur de communication Qi"
            print("[TTS] Erreur lors de l'appel: " + err_msg)

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

    def get_session(self):
        """Renvoie la session pour PepperAudioCapture."""
        return self.session

class PepperAudioCapture:
    def __init__(self, session):
        self.session = session
        self.audio_device = session.service("ALAudioDevice")
        self.audio_queue = Queue() # Le réservoir de bits bruts
        
        # Nom du module pour ALAudioDevice
        self.module_name = "PepperLiveStream"
        
        # On enregistre l'objet lui-même comme service pour recevoir l'audio
        # Note: 'self' doit avoir la méthode processRemote
        try:
            self.session.registerService(self.module_name, self)
        except RuntimeError:
            print("Module deja enregistre")

    def processRemote(self, nbOfChannels, nbrOfSamplesByChannel, timestamp, buffer):
        """
        Callback appele par Pepper (PUSH).
        buffer contient les bits bruts.
        """
        # On pousse les bits bruts dans la file
        self.audio_queue.put(bytes(buffer))

    def stream_generator(self):
        """
        Le generateur utilise par AudioInputs (PULL).
        """
        # 1. On s'abonne aux micros
        # 16000Hz, micro FRONT (3), interleaved (0)
        self.audio_device.setClientPreferences(self.module_name, 16000, 3, 0)
        self.audio_device.subscribe(self.module_name)
        
        print("[PepperAudio] Stream started...")
        
        try:
            while True:
                # 2. On attend et on yield les bits bruts des que processRemote les remplit
                chunk = self.audio_queue.get()
                yield chunk
        finally:
            # 3. Securite : on se desabonne si le stream s'arrete
            self.audio_device.unsubscribe(self.module_name)
            print("[PepperAudio] Stream stopped.")

# class PepperAudioCapture:
#     """Capture audio depuis les microphones de Pepper via ALAudioRecorder."""
#     def __init__(self, session, robot_ip="192.168.13.230", robot_user="nao", robot_pass="nao"):
#         self.session = session
#         self.robot_ip = robot_ip
#         self.robot_user = robot_user
#         self.robot_pass = robot_pass

#         self.audio_recorder = session.service("ALAudioRecorder")
#         self.audio_device = session.service("ALAudioDevice")

#         # Chemin d'enregistrement sur le robot
#         self.remote_path = "/home/nao/recordings/"

#     def record_chunk(self, filename="chunk.wav", duration=3, sample_rate=16000, channels=(0, 0, 1, 0)):
#         """
#         Enregistre un chunk audio depuis les micros de Pepper.

#         Args:
#             filename: nom du fichier WAV
#             duration: durée en secondes
#             sample_rate: fréquence d'échantillonnage (16000 Hz recommandé pour Whisper)
#             channels: tuple (front, rear, left, right) — (0,0,1,0) = micro gauche seul
        
#         Returns:
#             Chemin local du fichier téléchargé, ou None en cas d'erreur.
#         """
#         remote_file = self.remote_path + filename
#         local_path = os.path.join(TMP_DIR, filename)

#         try:
#             # Démarrer l'enregistrement
#             # Paramètres : nom_fichier, sample_rate, channels_config
#             self.audio_recorder.startMicrophonesRecording(
#                 remote_file,        # chemin sur le robot
#                 "wav",              # format
#                 sample_rate,        # fréquence d'échantillonnage
#                 channels            # (front, rear, left, right)
#             )

#             time.sleep(duration)

#             # Arrêter l'enregistrement
#             self.audio_recorder.stopMicrophonesRecording()

#             # Télécharger le fichier depuis le robot via SFTP
#             transport = paramiko.Transport((self.ip, 22))
#             transport.connect(username=self.user, password=self.password)
#             sftp = paramiko.SFTPClient.from_transport(transport)
#             sftp.get(remote_file, local_path)
#             sftp.close()
#             transport.close()
#             return local_path

#         except Exception as e:
#             print("[PepperAudio] Erreur enregistrement: {}".format(e))
#             try:
#                 self.audio_recorder.stopMicrophonesRecording()
#             except Exception:
#                 pass
#             return None      



