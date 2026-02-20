# -*- coding: utf-8 -*-
"""
Module pour capturer l'audio depuis les microphones de Pepper
et l'envoyer au serveur ASR pour transcription.
"""

import qi
import time
import os
import requests
import paramiko  # pour récupérer le fichier depuis le robot via SCP/SFTP


class PepperAudioCapture:
    """Capture audio depuis les microphones de Pepper via ALAudioRecorder."""

    def __init__(self, session, asr_url="http://localhost:8000/v1/asr",
                 robot_ip="192.168.13.230", robot_user="nao", robot_pass="nao"):
        self.session = session
        self.asr_url = asr_url
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
            local_file = self._download_file(remote_file, filename)
            return local_file

        except Exception as e:
            print("[PepperAudio] Erreur enregistrement: {}".format(e))
            try:
                self.audio_recorder.stopMicrophonesRecording()
            except Exception:
                pass
            return None

    def _download_file(self, remote_file, local_filename):
        """Télécharge un fichier depuis le robot via SFTP."""
        local_path = os.path.join("/tmp", local_filename)

        transport = paramiko.Transport((self.robot_ip, 22))
        transport.connect(username=self.robot_user, password=self.robot_pass)
        sftp = paramiko.SFTPClient.from_transport(transport)

        try:
            sftp.get(remote_file, local_path)
            print("[PepperAudio] Fichier téléchargé: {}".format(local_path))
            return local_path
        finally:
            sftp.close()
            transport.close()

    def send_to_asr(self, filepath):
        """
        Envoie un fichier audio au serveur ASR et retourne la transcription.

        Returns:
            dict avec 'text', 'language', etc. ou None en cas d'erreur.
        """
        if not filepath or not os.path.exists(filepath):
            print("[PepperAudio] Fichier introuvable: {}".format(filepath))
            return None

        try:
            with open(filepath, "rb") as f:
                files = {"file": (os.path.basename(filepath), f, "audio/wav")}
                resp = requests.post(self.asr_url, files=files, timeout=30)

            if resp.ok:
                result = resp.json()
                print("[PepperAudio] ASR: {} ({})".format(
                    result.get("text", ""), result.get("language", "??")))
                return result
            else:
                print("[PepperAudio] Erreur ASR HTTP {}: {}".format(
                    resp.status_code, resp.text))
                return None

        except Exception as e:
            print("[PepperAudio] Erreur envoi ASR: {}".format(e))
            return None

    def record_and_transcribe(self, duration=3):
        """Raccourci : enregistre puis transcrit."""
        filepath = self.record_chunk(duration=duration)
        if filepath:
            result = self.send_to_asr(filepath)
            # Nettoyage
            try:
                os.remove(filepath)
            except Exception:
                pass
            return result
        return None