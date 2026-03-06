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

TMP_DIR = "/tmp/pepper"

# Configuration
PEPPER_IP = "192.168.13.230"
PEPPER_PORT = 9559

class PepperConnector:
    """
    Gère la session Qi et centralise l'accès aux services du robot.
    """
    def __init__(self, ip=PEPPER_IP, port=PEPPER_PORT):
        self.ip = ip
        self.port = port
        self.session = qi.Session()
        self.tts = None
        self.tablet = None
        self.memory = None

    def connect(self):
        """Établit la connexion et initialise les services de base."""
        connection_url = "tcp://{}:{}".format(self.ip, self.port)
        try:
            self.session.connect(connection_url)
            print(u"[CONNEXION] Connecté à Pepper sur {}".format(connection_url))
            
            # Initialisation des services communs pour la production
            self.tts = self.session.service("ALAnimatedSpeech")
            self.memory = self.session.service("ALMemory")
            return True
        except RuntimeError as e:
            print(u"[ERREUR] Impossible de se connecter: {}".format(e))
            return False

    def say(self, text):
        """Méthode utilitaire pour faire parler Pepper."""
        if self.tts:
            self.tts.say(text)

    def get_session(self):
        """Renvoie la session pour PepperAudioCapture."""
        return self.session


class PepperAudioCapture:
    """Capture audio depuis les microphones de Pepper via ALAudioRecorder."""
    def __init__(self, session, robot_ip="192.168.13.230", robot_user="nao", robot_pass="nao"):
        self.session = session
        self.robot_ip = robot_ip
        self.robot_user = robot_user
        self.robot_pass = robot_pass

        self.audio_recorder = session.service("ALAudioRecorder")
        self.audio_device = session.service("ALAudioDevice")

        # Chemin d'enregistrement sur le robot
        self.remote_path = "/home/nao/recordings/"

    def record_chunk(self, filename="chunk.wav", duration=3, sample_rate=16000, channels=(0, 0, 1, 0)):
        """
        Enregistre un chunk audio depuis les micros de Pepper.

        Args:
            filename: nom du fichier WAV
            duration: durée en secondes
            sample_rate: fréquence d'échantillonnage (16000 Hz recommandé pour Whisper)
            channels: tuple (front, rear, left, right) — (0,0,1,0) = micro gauche seul
        
        Returns:
            Chemin local du fichier téléchargé, ou None en cas d'erreur.
        """
        remote_file = self.remote_path + filename
        local_path = os.path.join(TMP_DIR, filename)

        try:
            # Démarrer l'enregistrement
            # Paramètres : nom_fichier, sample_rate, channels_config
            self.audio_recorder.startMicrophonesRecording(
                remote_file,        # chemin sur le robot
                "wav",              # format
                sample_rate,        # fréquence d'échantillonnage
                channels            # (front, rear, left, right)
            )

            time.sleep(duration)

            # Arrêter l'enregistrement
            self.audio_recorder.stopMicrophonesRecording()

            # Télécharger le fichier depuis le robot via SFTP
            transport = paramiko.Transport((self.ip, 22))
            transport.connect(username=self.user, password=self.password)
            sftp = paramiko.SFTPClient.from_transport(transport)
            sftp.get(remote_file, local_path)
            sftp.close()
            transport.close()
            return local_path

        except Exception as e:
            print("[PepperAudio] Erreur enregistrement: {}".format(e))
            try:
                self.audio_recorder.stopMicrophonesRecording()
            except Exception:
                pass
            return None      



