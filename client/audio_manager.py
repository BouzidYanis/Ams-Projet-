# -*- coding: utf-8 -*-
import time
import requests
import wave
import audioop
import os

import webrtcvad
import collections
from pydub import AudioSegment
import io
from PepperOrchestrator import PepperAudioCapture  # Spécialiste pour Pepper

TMP_DIR = "/tmp/pepper"
if not os.path.exists(TMP_DIR):
    os.makedirs(TMP_DIR)

VAD_FRAME_SIZE = 320 # 10ms à 16000Hz (16kHz * 0.01s * 2 bytes) = 320 bytes
VAD_AGGRESIVENESS_3 = 3  # 0-3, plus c'est élevé, plus le VAD est strict
SILENT_FRAMES_RUN = 2

SILENCHE_THRESHOLD = 800

# =================================================================
# 1. HARDWARE WRAPPER (The Switcher)
# =================================================================
class AudioInputs:
    """ 
    Fait le pont entre la logique AudioSense et les sources matérielles.
    """
    def __init__(self, mode="pepper", pepper_specialist=None, phone_url=None):
        self.mode = mode  # "pepper" ou "phone"
        self.pepper = pepper_specialist
        self.phone_url = phone_url

    def get_stream(self):
        """ 
        Générateur universel de flux audio (bits bruts).
        """
        if self.mode == "phone":
            return self._get_phone_stream()
        elif self.mode == "pepper":
            return self._get_pepper_stream()
        else:
            raise ValueError("[Inputs] Mode inconnu")
    
    def _get_phone_stream(self):
        """ Flux venant de l'URL du téléphone (souvent 44.1kHz). """
        try:
            r = requests.get(self.phone_url, stream=True, timeout=5)
            for chunk in r.iter_content(chunk_size=1024):
                if chunk: yield chunk
        except Exception as e:
            print("[Inputs] Erreur Flux Phone: " + str(e))

    def _get_pepper_stream(self):
        """ 
        Consomme le générateur de PepperAudioCapture.
        """
        if self.pepper:
            # IMPORTANT: On appelle la méthode pour récupérer l'objet générateur
            return self.pepper.stream_generator() 
        else:
            print("[Inputs] Erreur: pepper_specialist (PepperAudioCapture) est None")
            return None

    # def record_chunk(self, filename, duration=2):
    #     """ Porte d'entrée unique pour capturer un fichier WAV. """
    #     if self.mode == "pepper" and self.pepper:
    #         # On appelle le spécialiste Pepper (PepperAudioCapture)
    #         return self.pepper.record_chunk(filename, duration)
    #     elif self.mode == "phone":
    #         # On utilise la logique directe pour le téléphone
    #         return self._record_from_phone(filename, duration)
    #     else:
    #         print("[Inputs] Erreur: Mode inconnu ou spécialiste manquant.")
    #         return None
        
    #Je n'ai pas fait un module dédié car ici on utilise juste requests
    # def _record_from_phone(self, filename, duration):
    #     local_path = os.path.join(TMP_DIR, filename)
    #     try:
    #         r = requests.get(self.phone_url, stream=True, timeout=5)
    #         with open(local_path, 'wb') as f:
    #             start = time.time()
    #             for chunk in r.iter_content(chunk_size=1024):
    #                 if chunk: f.write(chunk)
    #                 if time.time() - start > duration: break
    #         return local_path
    #     except Exception as e:
    #         print("Erreur Micro Phone: " + str(e))
    #         return None

    # def _record_from_phone(self, filename, min_duration=2):
    #     local_path = os.path.join(TMP_DIR, filename)
        
    #     # Paramètres VAD (16000Hz obligatoire pour WebRTC VAD)
    #     sample_rate = 16000
    #     frame_duration_ms = 30 
    #     # Calcul dynamique du nombre de bytes par frame
    #     frame_size = int(sample_rate * (frame_duration_ms / 1000.0) * 2) # = 960
        
    #     try:
    #         r = requests.get(self.phone_url, stream=True, timeout=5)
    #         full_audio_data = b""
    #         silence_window = collections.deque(maxlen=20) # ~600ms de fenêtre
            
    #         print("[VAD] En attente de parole (Frame size: {} bytes)...".format(frame_size))
    #         start_time = time.time()
    #         triggered = False

    #         # On itère avec la taille de frame exacte
    #         for chunk in r.iter_content(chunk_size=frame_size):
    #             if len(chunk) < frame_size: 
    #                 continue
                
    #             # IMPORTANT: Si le flux est du MP3, vad.is_speech va planter.
    #             # Cette méthode suppose que self.phone_url envoie du RAW PCM 16bit 16kHz.
    #             is_speech = self.vad.is_speech(chunk, sample_rate)
                
    #             if not triggered:
    #                 if is_speech:
    #                     triggered = True
    #                     print("[VAD] Début de phrase détecté !")
    #                     full_audio_data += chunk
    #             else:
    #                 full_audio_data += chunk
    #                 silence_window.append(int(is_speech))
                    
    #                 elapsed = time.time() - start_time
    #                 if elapsed > min_duration:
    #                     # Si la moyenne de parole dans la fenêtre tombe sous 10%
    #                     if sum(silence_window) < 2: 
    #                         print("[VAD] Fin de phrase détectée.")
    #                         break
                
    #             if time.time() - start_time > 15: # Timeout sécurité
    #                 break

    #         if not full_audio_data:
    #             return None

    #         # Exportation finale
    #         audio = AudioSegment(
    #             data=full_audio_data,
    #             sample_width=2,
    #             frame_rate=sample_rate,
    #             channels=1
    #         )
    #         audio.export(local_path, format="wav")
    #         return local_path

    #     except Exception as e:
    #         print("[VAD Error] " + str(e))
    #         return None
       

class AudioSense:
    def __init__(self, audio_input):
        """
        audio_inputs: Instance de AudioInputs (le wrapper)
        """
        self.audio_inputs = audio_input
        self.stream = self.audio_inputs.get_stream()
        self.vad = webrtcvad.Vad(VAD_AGGRESIVENESS_3)
        
        # --- State maintained across multiple record_chunk calls ---
        self.resample_state = None       # Smooths the wave between chunks
        self.vad_buffer = b""            # The "slicer" bucket for VAD frames
        self.leftover_audio = b""        # Bits received after the "cut" frame
        
        # Audio specs
        self.target_rate = 16000
        self.sampwidth = 2
        self.nchannels = 1

    # # --- INPUT METHODS ---
    # def record_chunk(self, output_file, duration=2):
    #     #print("record_chunk")
    #     """
    #     Remplace record_from_phone et record_from_pepper.
    #     Délègue directement au wrapper hardware.
    #     """
    #     return  self.audio_inputs.record_chunk(output_file, duration)
    
    def _save_wav(self, path, data):
        wf = wave.open(path, 'wb')
        try:
            wf.setnchannels(self.nchannels)
            wf.setsampwidth(self.sampwidth)
            wf.setframerate(self.target_rate)
            wf.writeframes(data)
        finally:
            wf.close()
        return path
    
    def record_chunk(self, output_file, duration=2):
        local_path = os.path.join(TMP_DIR, output_file)
        input_rate = 44100 if self.audio_inputs.mode == "phone" else 16000
        vad_frame_size = VAD_FRAME_SIZE
        
        # On commence avec les restes du chunk précédent
        full_audio_accumulated = self.leftover_audio
        self.leftover_audio = b"" # On vide pour ce cycle
        
        start_time = time.time()
        silent_frames_run = 0

        for raw_bits in self.stream:
            # 1. Resample
            resampled, self.resample_state = audioop.ratecv(
                raw_bits, self.sampwidth, self.nchannels, 
                input_rate, self.target_rate, self.resample_state
            )
            
            # On ajoute au flux total et au seau VAD
            full_audio_accumulated += resampled
            self.vad_buffer += resampled
            
            # 2. Scanning for the cut
            while len(self.vad_buffer) >= vad_frame_size:
                frame = self.vad_buffer[:vad_frame_size]
                is_speech = self.vad.is_speech(frame, self.target_rate)
                
                # On retire la frame du seau VAD
                self.vad_buffer = self.vad_buffer[vad_frame_size:]
                
                if not is_speech:
                    silent_frames_run += 1
                else:
                    silent_frames_run = 0

                # 3. La Coupe (The Snipping)
                elapsed = time.time() - start_time
                if elapsed >= duration and silent_frames_run >= SILENT_FRAMES_RUN:
                    cut_point = len(full_audio_accumulated) - len(self.vad_buffer)
                    
                    actual_chunk_data = full_audio_accumulated[:cut_point]
                    self.leftover_audio = full_audio_accumulated[cut_point:]
                    
                    # print("[VAD] Snipped at {:.2f}s. Leftover: {} bytes".format(elapsed, len(self.leftover_audio)))
                    return self._save_wav(local_path, actual_chunk_data)

            # Sécurité
            if (time.time() - start_time) > 10: break

        return self._save_wav(local_path, full_audio_accumulated)
        
    def record_until_silence(self, output_file, silence_threshold=SILENCHE_THRESHOLD, silence_limit=2, max_duration=10):
        #print("record_until_silence")
        """ 
        Utilise exclusivement record_chunk pour être compatible 
        avec Pepper ET le Téléphone.
        """
        chunks = []
        last_voice_time = time.time()
        start_time = time.time()
        
        print(u"[AUDIO] Écoute active...".encode('utf-8'))

        try:
            while (time.time() - start_time) < max_duration:
                # 1. Nom temporaire pour ce segment
                tmp_name = "chunk_{0}.wav".format(len(chunks))
                
                full_path = self.record_chunk(tmp_name, duration=1)
                print("full_path", full_path)
                # 2. Capture (Auto-géré par AudioInputs)
                if full_path:
                    # Calibration au premier passage
                    if len(chunks) == 0:
                        self._calibrate_params(full_path)
                        print(u"[AUDIO] Format: {0}Hz, {1}ch".format(self.framerate, self.nchannels).encode('utf-8'))

                    chunks.append(full_path)

                    # 3. Analyse du silence sur le dernier chunk
                    if not self.is_silent(full_path, silence_threshold):
                        last_voice_time = time.time()
                    
                    # 4. Sortie si silence trop long
                    if (time.time() - last_voice_time) > silence_limit:
                        print(u"[AUDIO] Fin de parole détectée.".encode('utf-8'))
                        break
                else:
                    break

            # 5. Fusion de tous les segments
            final_path = self.merge_wavs(chunks, output_file)
            
            # Nettoyage
            for c in chunks:
                try: os.remove(c)
                except: pass
                
            return final_path

        except Exception as e:
            print(u"Erreur record_until_silence: {0}".format(str(e)).encode('utf-8'))
            return None

    def _calibrate_params(self, wav_file):
        """Extrait les paramètres audio du premier WAV reçu."""
        wf = wave.open(wav_file, 'rb')
        try:
            self.nchannels = wf.getnchannels()
            self.sampwidth = wf.getsampwidth()
            self.framerate = wf.getframerate()
        finally:
            wf.close()
    
    #Detect silence with simple RMS threshold
    # def is_silent(self, wav_file, threshold=800):
    #     if not os.path.exists(wav_file): return True
    #     wf = wave.open(wav_file, 'rb')
    #     try:
    #         params = wf.getparams()
    #         frames = wf.readframes(params[3])
    #         if not frames: return True
    #         return audioop.rms(frames, params[1]) < threshold
    #     finally:
    #         wf.close()

    #Detect silence with VAD
    def is_silent(self, wav_file, speech_ratio_threshold=0.15):
        """
        Scans the WAV file using WebRTC VAD.
        Returns True if the ratio of speech frames is below the threshold.
        """
        if not os.path.exists(wav_file): 
            return True
            
        wf = wave.open(wav_file, 'rb')
        try:
            # We must use 16000Hz for WebRTC VAD
            rate = wf.getframerate()
            if rate not in [8000, 16000, 32000, 48000]:
                # If the file isn't VAD-compatible, fallback to RMS
                params = wf.getparams()
                frames = wf.readframes(params[3])
                return audioop.rms(frames, params[1]) < 800

            # VAD settings: 30ms frames are most stable
            frame_duration_ms = 30
            # n_bytes = sample_rate * duration_sec * sampwidth * channels
            n = int(rate * (frame_duration_ms / 1000.0) * 2 * 1) 
            
            frames_count = 0
            speech_frames = 0
            
            while True:
                chunk = wf.readframes(int(rate * frame_duration_ms / 1000.0))
                if not chunk or len(chunk) < n:
                    break
                
                frames_count += 1
                if self.vad.is_speech(chunk, rate):
                    speech_frames += 1
            
            if frames_count == 0: 
                return True
                
            actual_ratio = float(speech_frames) / frames_count
            
            # Debug log (optional)
            # print("[VAD_CHECK] Speech Ratio: {:.2f} (Threshold: {})".format(actual_ratio, speech_ratio_threshold))
            
            # If less than 15% of the file is speech, treat as silent/noise
            return actual_ratio < speech_ratio_threshold

        finally:
            wf.close()
    
    def merge_wavs(self, file_list, output_name):
        #print("merge_wavs")
        """ 
        Fusionne les morceaux, resample à 16000Hz si nécessaire, et sauvegarde.
        """
        if not file_list: return None
        
        try:
            combined_data = b""
            nchannels, sampwidth, framerate = None, None, None
            
            # 1. Collecter les données brutes de TOUS les morceaux
            for filename in file_list:
                if not os.path.exists(filename): continue
                w = wave.open(filename, 'rb')
                try:
                    if nchannels is None:
                        nchannels = w.getnchannels()
                        sampwidth = w.getsampwidth()
                        framerate = w.getframerate()
                    
                    combined_data += w.readframes(w.getnframes())
                finally:
                    w.close()

            if not combined_data: return None

            # 2. Resampling UNIQUE sur la totalité des données fusionnées
            final_rate = framerate
            if framerate != 16000:
                # On applique le resampling ici, une seule fois pour tout le bloc
                combined_data = self.resample_wav(combined_data, framerate)
                final_rate = 16000

            # 3. Sauvegarde finale du fichier complet
            out_path = os.path.join("/tmp", output_name)
            out = wave.open(out_path, 'wb')
            try:
                out.setnchannels(nchannels)
                out.setsampwidth(sampwidth)
                out.setframerate(final_rate)
                out.writeframes(combined_data)
            finally:
                out.close()
                
            print(u"[AUDIO] Export final: {} ({}Hz)".format(out_path, final_rate).encode('utf-8'))
            return out_path

        except Exception as e:
            print("Erreur merge/resample: " + str(e))
            return None

    # def merge_wavs(self, file_list, output_name):
    #     #print("merge_wavs")
    #     """ 
    #     Fusionne les morceaux, resample à 16000Hz si nécessaire, et sauvegarde.
    #     """
    #     if not file_list: return None
        
    #     try:
    #         combined_data = b""
    #         nchannels, sampwidth, framerate = None, None, None
            
    #         # 1. Collecter les données et les paramètres
    #         #print("file_list", file_list)
    #         for filename in file_list:
    #             if not os.path.exists(filename): continue
    #             w = wave.open(filename, 'rb')
    #             try:
    #                 if nchannels is None:
    #                     nchannels = w.getnchannels()
    #                     sampwidth = w.getsampwidth()
    #                     framerate = w.getframerate()
                    
    #                 combined_data += w.readframes(w.getnframes())
    #             finally:
    #                 w.close()

    #         # 2. Vérifier si un resampling est nécessaire (ex: Phone à 44100Hz)
    #         final_rate = framerate
    #         if framerate != 16000:
    #             combined_data = self.resample_wav(combined_data, framerate)
    #             final_rate = 16000

    #         # 3. Sauvegarde finale
    #         out_path = os.path.join("/tmp", output_name)
    #         out = wave.open(out_path, 'wb')
    #         try:
    #             out.setnchannels(nchannels)
    #             out.setsampwidth(sampwidth)
    #             out.setframerate(final_rate)
    #             out.writeframes(combined_data)
    #         finally:
    #             out.close()
                
    #         print(u"[AUDIO] Export final: {} ({}Hz)".format(out_path, final_rate).encode('utf-8'))
    #         return out_path

    #     except Exception as e:
    #         print("Erreur merge/resample: " + str(e))
    #         return None
    
    def resample_wav(self, raw_data, original_rate):
        print("resample_wav")
        """
        Convertit les données brutes vers 16000Hz via audioop.
        """
        target_rate = 16000
        if original_rate == target_rate:
            return raw_data
            
        print(u"[AUDIO] Resampling: {}Hz -> {}Hz".format(original_rate, target_rate).encode('utf-8'))
        
        # Note: audioop.ratecv nécessite l'état du convertisseur (None au début)
        resampled_data, _ = audioop.ratecv(
            raw_data, 
            self.sampwidth, 
            self.nchannels, 
            original_rate, 
            target_rate, 
            None
        )
        return resampled_data
    
# =================================================================
# MAIN TEST BLOCK (Python 2.7 compatible)
# =================================================================
if __name__ == "__main__":
    # --- CONFIGURATION TEST ---
    PHONE_URL = "http://192.168.1.11:8080/audio.wav" 
    
    # Initialisation
    inputs = AudioInputs(mode="phone", phone_url=PHONE_URL)
    sense = AudioSense(inputs)
    
    print "--- DEBUT DU TEST EN CONTINU ---"
    print "Le script va creer des fichiers WAV des qu'un silence est detecte."
    print "Appuyez sur CTRL+C pour arreter."
    print "-" * 40

    try:
        # On ouvre le flux une seule fois pour tout le test
        
        counter = 0
        while True:
            # Python 2.7 format style
            filename = "live_test_{0:03d}.wav".format(counter)
            
            # On demande un chunk d'au moins 1.5 seconde
            chunk_path = sense.record_chunk(filename, duration=1.5)
            
            if chunk_path:
                size = os.path.getsize(chunk_path)
                print "[CHUNK SAVED] {0} ({1} bytes)".format(filename, size)
                counter += 1
            else:
                print "[!] Probleme de flux, nouvelle tentative..."
                time.sleep(1)

    except KeyboardInterrupt:
        print "\n--- ARRET DU TEST ---"
        print "Test termine. {0} chunks generes dans {1}".format(counter, TMP_DIR)
    except Exception as e:
        print "\n[ERREUR CRITIQUE] {0}".format(str(e))