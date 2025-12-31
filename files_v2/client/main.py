# -*- coding: utf-8 -*-
"""
Exemple de client minimal pour Pepper (Python 2.7.18).
Envoie la transcription au serveur FastAPI et récupère la réponse du DialogManager.
"""

import threading
import Queue
import collections
import time
import os


from network_client import NetworkClient
from audio_manager import AudioSense
from robot_controller import PepperRobot

# --- CONFIGURATION ---
SERVER_URL = "http://192.168.1.74:8000"
PHONE_URL = "http://192.168.1.38:8080/audio.wav"

PEPPER_IP = "127.0.0.1"
PEPPER_PORT = 9559

WAKE_WORDS = [u"pepper", u"bonjour"]

SLOW_TIMEOUT = 50
CONVERSATION_TIMEOUT = 15

class PepperOrchestrator:
    def __init__(self):
        self.net = NetworkClient(SERVER_URL, timeout=SLOW_TIMEOUT)
        self.audio = AudioSense(PHONE_URL)
        
        # Quand on aura le robot
        # self.robot = PepperRobot(PEPPER_IP, PEPPER_PORT)

        # Etat de la conversation
        self.is_engaged = False
        self.session_id = None
        self.last_interaction = 0

        self.audio_queue = Queue.Queue()
        self.buffer_size = 2
        self.buffer_files = collections.deque(maxlen=self.buffer_size)
        self.is_running = True
    
    def clear_audio_files(self):
        count = 0
        while True:
            chunk_name = "chunk_{}.wav".format(count)
            if os.path.exists(chunk_name):
                try:
                    os.remove(chunk_name)
                except Exception as e:
                    print(u"Erreur suppression {0}: {1}".format(chunk_name, e).encode('utf-8'))
                count += 1
            else:
                break
        
        if os.path.exists("analysis_buffer.wav"):
            try:
                os.remove("analysis_buffer.wav")
            except:
                pass

    def contains_wake_words(self, text):
        if not text:
            return False
        
        text_unicode = text if isinstance(text, unicode) else text.decode('utf-8', 'ignore')
        text_lower = text_unicode.lower()

        for word in WAKE_WORDS:
            if word in text_lower:
                return True
        return False

    def audio_capture_loop(self):
        """ BRAS A : Capture continue (uniquement en veille) """
        print(u"[AUDIO] Démarrage capture...".encode('utf-8'))
        count = 0
        while self.is_running:
            if not self.is_engaged:
                name = "chunk_{}.wav".format(count % 10)
                if self.audio.record_chunk(name, duration=2):
                    self.audio_queue.put(name)
                    count += 1
            else:
                # En mode engagé, on laisse record_until_silence gérer le flux
                time.sleep(0.5)

    def audio_analysis_loop(self):
        """ BRAS B : Analyse et dialogue """
        print(u"[ANALYSE] Prêt...".encode('utf-8'))
        
        while self.is_running:
            if self.is_engaged:
                # 1. Nettoyage pré-écoute
                while not self.audio_queue.empty():
                    try: self.audio_queue.get_nowait()
                    except: break
                
                # 2. Capture active (Paramètres calés sur tes tests ASR)
                conv_file = "conversation_input.wav"
                if self.audio.record_until_silence(conv_file, 400, 3, 10):
                    print(u"[INFO] Silence détecté.".encode('utf-8'))
                    result_asr = self.net.send_asr_file(conv_file)
                    
                    if result_asr:
                        text = result_asr.get("text", "")
                        is_reliable = result_asr.get("is_reliable", True)
                        lang = result_asr.get("language", "fr")

                        if not is_reliable or text == "ERROR_CONFIDENCE_LOW":
                            self.handle_dialog("[SYSTEM_ERROR_UNRELIABLE_AUDIO]", lang=lang)
                        elif text.strip():
                            print(u"===> Reçu: {0}".format(text).encode('utf-8'))
                            self.handle_dialog(text, lang=lang)

                # 3. Timeout
                if (time.time() - self.last_interaction > CONVERSATION_TIMEOUT):
                    print(u"--- [LOG] Timeout : Retour en veille ---".encode('utf-8'))
                    self.is_engaged = False
                    self.session_id = None
                
                time.sleep(0.1)

            else:
                # MODE VEILLE
                try:
                    new_chunk = self.audio_queue.get(timeout=1)
                    self.buffer_files.append(new_chunk)

                    if len(self.buffer_files) == self.buffer_size:
                        merged = self.audio.merge_wavs(list(self.buffer_files), "analysis_buffer.wav")
                        if merged and not self.audio.is_silent(merged):
                            result_asr = self.net.send_asr_file(merged)
                            if result_asr and self.contains_wake_words(result_asr.get("text", "")):
                                print(u"===> [LOG] Réveil détecté !".encode('utf-8'))
                                self.is_engaged = True
                                self.last_interaction = time.time()
                                self.handle_dialog(result_asr.get("text"), lang=result_asr.get("language", "fr"))
                    
                    self.audio_queue.task_done()
                except Queue.Empty:
                    continue

    def handle_dialog(self, text, lang="fr"):
        self.last_interaction = time.time()
        
        if text == "[SYSTEM_ERROR_UNRELIABLE_AUDIO]":
            msg_for_llm = u"L'audio est mauvais. Demande poliment de répéter en répondant UNIQUEMENT en {0}.".format(lang)
        else:
            msg_for_llm = text

        response = self.net.send_dialog_text(msg_for_llm, session_id=self.session_id, lang=lang)
        if response:
            self.session_id = response.get("session_id")
            print("Robot: " + response["text"].encode('utf-8'))
            # self.robot.say(response["text"]) # Activer plus tard

        if response:
            self.session_id = response.get("session_id")
            print("Robot: " + response["text"].encode('utf-8'))
            
            # self.robot.say(response["text"])

            # Nettoyage
            self.buffer_files.clear()
            while not self.audio_queue.empty():
                try: self.audio_queue.get_nowait()
                except: pass

    def start(self):
        t1 = threading.Thread(target=self.audio_capture_loop)
        t2 = threading.Thread(target=self.audio_analysis_loop)
        t1.daemon = True
        t2.daemon = True
        t1.start()
        t2.start()

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        self.is_running = False
        print(u"Arrêt de l'orchestrateur...".encode('utf-8'))
        self.clear_audio_files()

if __name__=="__main__":

    print(u"--- Session Pepper Modulaire ---".encode('utf-8'))
    orchestrator = PepperOrchestrator()
    orchestrator.start()
