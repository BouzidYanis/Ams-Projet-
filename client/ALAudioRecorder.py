# -*- coding: utf-8 -*-
"""
Module pour capturer l'audio depuis les microphones de Pepper
en live streaming (ALAudioDevice) et l'envoyer au serveur ASR.
Plus besoin de SCP/SFTP !
"""

import qi
import time
import os
import wave
import requests


class SoundReceiverModule(object):
    """
    Module enregistré auprès de qi pour recevoir le flux audio en temps réel.
    La méthode processRemote est appelée par ALAudioDevice à chaque buffer.
    DOIT être un objet new-style (hérite de object).
    """
    def __init__(self):
        self.audio_buffer = []
        self.is_recording = False

    def processRemote(self, nbOfChannels, nbrOfSamplesByChannel, timeStamp, inputBuffer):
        """Callback appelé par Pepper à chaque chunk audio."""
        if self.is_recording:
            self.audio_buffer.append(bytes(inputBuffer))


class PepperAudioCapture:
    """Capture audio depuis les microphones de Pepper via ALAudioDevice (live streaming)."""

    def __init__(self, session, asr_url="http://localhost:8000/v1/asr"):
        self.session = session
        self.asr_url = asr_url

        self.audio_device = session.service("ALAudioDevice")

        # Créer et enregistrer le module audio comme service qi
        self.module_name = "SoundReceiverModule_{}".format(int(time.time()))
        self.collector = SoundReceiverModule()
        self.service_id = self.session.registerService(
            self.module_name, self.collector
        )

        self.sample_rate = 16000

    def record_chunk(self, filename="chunk.wav", duration=3, sample_rate=16000,
                     channels=(0, 0, 1, 0)):
        """
        Enregistre un chunk audio en live streaming depuis les micros de Pepper.

        Args:
            filename: nom du fichier WAV local
            duration: durée en secondes
            sample_rate: fréquence d'échantillonnage (16000 Hz recommandé pour Whisper)
            channels: non utilisé ici (ALAudioDevice utilise setClientPreferences)

        Returns:
            Chemin local du fichier WAV, ou None en cas d'erreur.
        """
        self.sample_rate = sample_rate
        local_path = os.path.join("/tmp", filename)

        try:
            # Réinitialiser le buffer
            self.collector.audio_buffer = []
            self.collector.is_recording = True

            # Configurer les préférences audio :
            #   - module_name : identifiant du module enregistré
            #   - sample_rate : 16000 Hz (idéal pour Whisper)
            #   - channel : 3 = micro avant (0=all, 1=left, 2=right, 3=front, 4=rear)
            #   - deinterleaved : 0 = données entrelacées
            self.audio_device.setClientPreferences(
                self.module_name,
                sample_rate,
                3,   # Front microphone (changez selon vos besoins)
                0    # Interleaved
            )
            self.audio_device.subscribe(self.module_name)

            print("[PepperAudio] Enregistrement en cours ({} secondes)...".format(duration))
            time.sleep(duration)

            # Arrêter la capture
            self.audio_device.unsubscribe(self.module_name)
            self.collector.is_recording = False

            # Assembler les buffers et sauvegarder en WAV
            raw_data = b"".join(self.collector.audio_buffer)

            if not raw_data:
                print("[PepperAudio] ERREUR: Aucune donnée audio reçue !")
                print("[PepperAudio] Vérifiez le réseau/firewall entre le robot et cette machine.")
                return None

            wf = wave.open(local_path, 'wb')
            try:
                wf.setnchannels(1)        # Mono
                wf.setsampwidth(2)        # 16-bit PCM
                wf.setframerate(sample_rate)
                wf.writeframes(raw_data)
            finally:
                wf.close()

            size_kb = os.path.getsize(local_path) / 1024.0
            print("[PepperAudio] Fichier sauvegardé: {} ({:.1f} KB)".format(
                local_path, size_kb))
            return local_path

        except Exception as e:
            print("[PepperAudio] Erreur enregistrement: {}".format(e))
            try:
                self.audio_device.unsubscribe(self.module_name)
            except Exception:
                pass
            self.collector.is_recording = False
            return None

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
                text = result.get("text", "")
                lang = result.get("language", "??")
                if isinstance(text, unicode):
                    text = text.encode("utf-8")
                if isinstance(lang, unicode):
                    lang = lang.encode("utf-8")
                print("[PepperAudio] ASR: {} ({})".format(text, lang))
                return result
            else:
                print("[PepperAudio] Erreur ASR HTTP {}: {}".format(
                    resp.status_code, resp.text.encode("utf-8") if isinstance(resp.text, unicode) else resp.text))
                return None

        except Exception as e:
            print("[PepperAudio] Erreur envoi ASR: {}".format(
                str(e).encode("utf-8") if isinstance(str(e), unicode) else str(e)))
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

    def shutdown(self):
        """Nettoyage : désenregistrer le service."""
        try:
            self.audio_device.unsubscribe(self.module_name)
        except Exception:
            pass
        try:
            self.session.unregisterService(self.service_id)
        except Exception:
            pass