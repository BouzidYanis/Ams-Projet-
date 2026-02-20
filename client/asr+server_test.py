# -*- coding: utf-8 -*-
import threading
import Queue
import collections
import time
import os

# Import de tes modules existants
from network_client import NetworkClient
from audio_manager import AudioSense

# --- CONFIGURATION ---
# --- CONFIGURATION ---
# SERVER_URL = "http://192.168.1.74:8000"
# SERVER_URL = "http://10.60.55.34:8000"
SERVER_URL = "http://localhost:8000"

PHONE_URL = "http://192.168.1.11:8080/audio.wav"
# PHONE_URL = "http://10.60.55.196:8080/audio.wav"

WAKE_WORDS = [u"pepper", u"bonjour"]
CONVERSATION_TIMEOUT = 10 

class PepperTestOrchestrator:
    def __init__(self):
        self.net = NetworkClient(SERVER_URL, timeout=50)
        self.audio = AudioSense(PHONE_URL)
        
        # État
        self.is_engaged = False
        self.last_interaction = 0
        self.audio_queue = Queue.Queue()
        self.buffer_size = 2
        self.buffer_files = collections.deque(maxlen=self.buffer_size)
        self.is_running = True

    def contains_wake_words(self, text):
        if not text: return False
        text_unicode = text if isinstance(text, unicode) else text.decode('utf-8', 'ignore')
        text_lower = text_unicode.lower()
        for word in WAKE_WORDS:
            if word in text_lower: return True
        return False

    def audio_capture_loop(self):
        """ BRAS A : Capture continue pour la veille """
        print(u"[AUDIO] Démarrage capture de veille...".encode('utf-8'))
        count = 0
        while self.is_running:
            if not self.is_engaged:
                name = "chunk_{}.wav".format(count % 10)
                if self.audio.record_chunk(name, duration=2):
                    self.audio_queue.put(name)
                    count += 1
            else:
                # En mode engagé, on pause cette boucle pour laisser record_until_silence travailler
                time.sleep(0.5)

    def audio_analysis_loop(self):
        """ BRAS B : Analyse ASR uniquement """
        print(u"[ANALYSE] Prêt (Mode Test ASR)...".encode('utf-8'))
        
        while self.is_running:
            # --- MODE CONVERSATION (ÉCOUTE ACTIVE) ---
            if self.is_engaged:
                # Nettoyage de la queue de veille
                while not self.audio_queue.empty():
                    try: 
                        self.audio_queue.get_nowait()
                        self.audio_queue.task_done()
                    except: break
                
                conv_file = "test_conversation.wav"
                
                # APPEL CORRIGÉ : On passe les 4 arguments requis par ta fonction
                # (output_file, silence_threshold, silence_limit, max_duration)
                if self.audio.record_until_silence(conv_file, 400, 3, 10):
                    print(u"[INFO] Silence détecté ou fin de phrase.".encode('utf-8'))
                    
                    result_asr = self.net.send_asr_file(conv_file)
                    if result_asr:
                        text = result_asr.get("text", "")
                        lang = result_asr.get("language", "??")
                        print(u"--- [ASR] L'utilisateur a dit ({0}): {1}".format(lang, text).encode('utf-8'))
                        self.last_interaction = time.time() 

                # Check Timeout pour repasser en veille
                if (time.time() - self.last_interaction > CONVERSATION_TIMEOUT):
                    print(u"--- [LOG] Timeout : Retour en mode veille ---".encode('utf-8'))
                    self.is_engaged = False
                
                time.sleep(0.1)

            # --- MODE VEILLE (RECHERCHE MOT-CLÉ) ---
            else:
                try:
                    new_chunk = self.audio_queue.get(timeout=1)
                    self.buffer_files.append(new_chunk)

                    if len(self.buffer_files) == self.buffer_size:
                        merged = self.audio.merge_wavs(list(self.buffer_files), "test_veille.wav")
                        
                        if merged and not self.audio.is_silent(merged):
                            result_asr = self.net.send_asr_file(merged)
                            if result_asr:
                                text = result_asr.get("text", "")
                                if self.contains_wake_words(text):
                                    print(u"===> [LOG] Mot-clé détecté : '{0}' ! PASSAGE EN MODE ACTIF".format(text).encode('utf-8'))
                                    self.is_engaged = True
                                    self.last_interaction = time.time()
                                    self.buffer_files.clear()
                    
                    self.audio_queue.task_done()
                except Queue.Empty:
                    continue

    def start(self):
        t1 = threading.Thread(target=self.audio_capture_loop)
        t2 = threading.Thread(target=self.audio_analysis_loop)
        t1.daemon = True
        t2.daemon = True
        t1.start()
        t2.start()
        try:
            while True: time.sleep(1)
        except KeyboardInterrupt:
            self.is_running = False
            print(u"\nArrêt du test...".encode('utf-8'))

if __name__ == "__main__":
    print(u"=== TEST ASR (SANS LLM) ===".encode('utf-8'))
    test = PepperTestOrchestrator()
    test.start()
