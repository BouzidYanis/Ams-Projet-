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
# SERVER_URL = "http://192.168.1.74:8000"
# SERVER_URL = "http://10.60.55.34:8000"
SERVER_URL = "http://localhost:8000"

PHONE_URL = "http://192.168.1.11:8080/audio.wav"
# PHONE_URL = "http://10.60.55.196:8080/audio.wav"


WAKE_WORDS = [u"pepper", u"bonjour"]
TRANSCRIPT_BATCH_SIZE = 1
SILENCE_DELAY = 3 

TMP_DIR = "/tmp/pepper"

class ASREngine:
    def __init__(self, audio_manager, network_client, wake_words=WAKE_WORDS, silence_delay=SILENCE_DELAY,
                 transcript_batch_size = TRANSCRIPT_BATCH_SIZE):
        self.audio = audio_manager
        self.net = network_client
        self.wake_words = wake_words
        
        # Flags de contrôle (Pilotés par le Main)
        self.is_running = True
        self.is_engaged = False      # True = Mode conversation
        self.is_listening = False    # True = Arm D transcrit (Le robot ne parle pas)
        self.check_if_silent = False # True = Arm C guette la fin de la réponse utilisateur
        
        # Paramètres de timing
        self.transcript_batch_size = transcript_batch_size
        self.silence_delay = silence_delay
        
        # Multi-Queues (Fan-out) pour éviter que les bras ne se volent les données
        self.queues = {
            "B": Queue.Queue(), # Wake Detector
            "C": Queue.Queue(), # Silence/Gatekeeper
            "D": Queue.Queue()  # Transcriber
        }
        
        # Buffer pour Arm B et Index de synchronisation
        self.buffer_window = collections.deque(maxlen=3)
        self.wake_chunk_index = -1
        self.committed_transcript = ""

    def start(self):
        """Démarre les quatre bras de traitement audio."""
        threads = [
            threading.Thread(target=self._arm_a_capture, name="Arm-A"),
            threading.Thread(target=self._arm_b_wake_detector, name="Arm-B"),
            threading.Thread(target=self._arm_c_silence_detector, name="Arm-C"),
            threading.Thread(target=self._arm_d_transcriber, name="Arm-D")
        ]
        
        for t in threads:
            t.daemon = True
            t.start()

    # --- BRAS A: PRODUCTEUR ---
    def _arm_a_capture(self):
        """Enregistre les chunks et supprime ceux plus vieux de 50s."""
        count = 0
        while self.is_running:
            name = "chunk_{}.wav".format(count)
            # On récupère le chemin RÉEL (ex: /tmp/chunk_0.wav)
            full_path = self.audio.record_chunk(name, duration=1)
            
            # print("Arm A : Captured chunk {}, path: {}".format(name, full_path))


            if full_path:
                payload = (count, full_path)
                for q in self.queues.values():
                    q.put(payload)
                
                # --- NETTOYAGE AUTO ---
                # Supprime le chunk d'il y a 50 secondes
                old_idx = count - 50
                if old_idx >= 0:
                    old_name = os.path.join(TMP_DIR, "chunk_{}.wav".format(old_idx))
                    if os.path.exists(old_name):
                        try: os.remove(old_name)
                        except: pass
                
                count += 1


    # --- BRAS B: VEILLEUR (WAKE WORD) ---
    def _arm_b_wake_detector(self):
        """Surveille les wake-words et marque l'index de départ pour Arm-D."""
        while self.is_running:
            if not self.is_engaged:
                try:
                    idx, name = self.queues["B"].get(timeout=1)
                    # On stocke (index, nom) dans le buffer glissant
                    
                    # 1. NEW SILENCE CHECK: 
                    # If it's just room noise, don't waste battery/bandwidth
                    if self.audio.is_silent(name):
                        self.queues["B"].task_done()
                        continue
                                       
                    res = self.net.send_asr_file(name)
                        
                    if res and self._contains_wake_word(res.get("text", "")):
                        print(u"[ARM-B] Wake word détecté !".encode('utf-8'))
                        # L'index de réveil est le premier chunk du buffer (le début du "Pepper")
                        self.wake_chunk_index = idx
                        self.is_engaged = True
                        self.is_listening = True # On active l'oreille (Arm D)
                                        
                    self.queues["B"].task_done()
                except Queue.Empty: pass
            else:
                if self.buffer_window: self.buffer_window.clear()
                time.sleep(0.5)

    # --- BRAS C: LE GARDIEN (DETECTEUR DE SILENCE) ---
    def _arm_c_silence_detector(self):
        """Vérifie si l'utilisateur continue de parler après une réponse du robot."""
        while self.is_running:
            try:
                idx, name = self.queues["C"].get(timeout=0.5)
                
                if self.check_if_silent:
                    # Si on détecte du bruit, l'utilisateur est en train de répondre
                    if not self.audio.is_silent(name):
                        print(u"[ARM-C] Bruit détecté, l'utilisateur répond.".encode('utf-8'))
                        
                        # On laisse Arm-D continuer son travail
                        self.wake_chunk_index = idx
                        self.check_if_silent = False
                        self.is_listening = True
                    else:
                        # Si c'est silencieux, on vérifie si on a dépassé le délai
                        # Note: Main gère le timeout global, Arm C gère l'absence de réponse immédiate
                        pass 
                
                self.queues["C"].task_done()
            except Queue.Empty: pass
    
    # --- BRAS D: LE TRANSCRIPTEUR (L'OREILLE) ---
    def _arm_d_transcriber(self):
        """
        Bras D: Batch de transcription + Flush sur silence.
        """
        batch = []
        active_transcript_list = [] 
        consecutive_silence = 0

        while self.is_running:
            try:
                                
                if self.is_listening and self.is_engaged:
                    idx, name = self.queues["D"].get(timeout=0.5)
                    # #Clean up when handed over from other arms (B and C)
                    # if idx < self.wake_chunk_index:
                    #     # On ignore et on vide par précaution
                    #     batch = []
                    #     active_transcript_list = []
                    #     consecutive_silence = 0
                    #     self.queues["D"].task_done()
                    #     continue
                    print("D : Received chunk {} with name {}".format(idx, name))
                    if idx >= self.wake_chunk_index:
                        # 1. Analyse du chunk individuel (1s)
                        if self.audio.is_silent(name):
                            consecutive_silence += 1
                        else:
                            consecutive_silence = 0
                        
                        batch.append(name)
                        print("D : batch content :", batch)
                        # 2. CAS A : Le batch est plein (ex: 5s) -> On transcrit
                        if len(batch) >= self.transcript_batch_size:
                            filename = "D_batch_{}s_{}.wav".format(self.transcript_batch_size, idx)
                            merged = self.audio.merge_wavs(batch, filename)
                            
                            res = self.net.send_asr_file(merged)
                            if res and res.get("text"):
                                active_transcript_list.append(res.get("text"))
                            
                            batch = [] # On repart sur un nouveau batch

                        # 3. CAS B : Seuil de silence atteint -> On flush et on arrête
                        if consecutive_silence >= self.silence_delay:
                            # S'il reste des morceaux dans le batch actuel, on les envoie
                            # if batch:
                            #     filename = "D_flush_{}.wav".format(idx)
                            #     merged = self.audio.merge_wavs(batch, filename)
                            #     res = self.net.send_asr_file(merged)
                            #     if res and res.get("text"):
                            #         active_transcript_list.append(res.get("text"))
                            
                            # On concatène tout et on envoie au Main
                            if active_transcript_list:
                                self.committed_transcript = " ".join(active_transcript_list).strip()
                            
                            # NETTOYAGE & ARRÊT
                            batch = []
                            active_transcript_list = []
                            consecutive_silence = 0
                            self.is_listening = False # On arrête l'écoute (Arm D & C s'arrêtent)

                    self.queues["D"].task_done()
            except Queue.Empty:
                pass
    
    def stop(self):
        """Arrête le moteur et vide les queues."""
        self.is_running = False
        for q in self.queues.values():
            while not q.empty():
                try:
                    q.get_nowait()
                    q.task_done()
                except: break
        print(u"[ASR] Stop & Queues vidées.".encode('utf-8'))
    
    def _contains_wake_word(self, text):
        """Vérifie la présence d'un mot-clé dans la transcription."""
        if not text: return False
        t = text.lower()
        for w in self.wake_words:
            if w in t: return True
        return False