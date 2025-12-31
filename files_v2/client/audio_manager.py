# -*- coding: utf-8 -*-
import time
import requests
import wave
import audioop
import os


class AudioSense:
    def __init__(self, phone_url):
        self.phone_url = phone_url
        self.hard_framerate = 16000

    def record_chunk(self, output_file, duration=2):
            """ Capture un segment audio depuis le téléphone """
            try:
                r = requests.get(self.phone_url, stream=True, timeout=5)
                with open(output_file, 'wb') as f:
                    start_time = time.time()
                    for chunk in r.iter_content(chunk_size=1024):
                        if chunk: f.write(chunk)
                        if time.time() - start_time > duration: break
                return True
            except Exception as e:
                print(u"Erreur Micro: {0}".format(str(e)).encode('utf-8'))
                return False
    
    def record_until_silence(self, output_file, silence_threshold, silence_limit, max_duration):
        """ 
        Enregistre en détectant dynamiquement les paramètres audio 
        du premier segment pour configurer l'analyse RMS.
        """
        temp_calib = "temp_calib.wav"
        try:
            # 1. On enregistre un micro-segment pour détecter le format
            if not self.record_chunk(temp_calib, duration=0.5):
                return False

            # 2. Extraction dynamique des paramètres (nchannels, sampwidth, framerate)
            wf_calib = wave.open(temp_calib, 'rb')
            try:
                self.nchannels = wf_calib.getnchannels()
                self.sampwidth = wf_calib.getsampwidth()
                self.framerate = wf_calib.getframerate()
            finally:
                wf_calib.close()
            
            # 3. Ouverture du flux pour la capture réelle
            r = requests.get(self.phone_url, stream=True, timeout=5)
            frames_accumulator = []
            last_voice_time = time.time()
            start_time = time.time()

            print(u"[AUDIO] Format détecté: {0}Hz, {1} channels. Écoute...".format(
                self.framerate, self.nchannels).encode('utf-8'))

            for chunk in r.iter_content(chunk_size=2048):
                if not chunk: continue
                frames_accumulator.append(chunk)
                
                # On utilise le sampwidth détecté dynamiquement
                rms = audioop.rms(chunk, self.sampwidth)
                current_time = time.time()
                
                if rms > silence_threshold:
                    last_voice_time = current_time
                
                if (current_time - last_voice_time) > silence_limit or \
                   (current_time - start_time) > max_duration:
                    break

            # 4. Écriture finale avec les paramètres détectés
            # out = wave.open(output_file, 'wb')
            # try:
            #     out.setnchannels(self.nchannels)
            #     out.setsampwidth(self.sampwidth)
            #     out.setframerate(self.framerate)
            #     # out.setframerate(self.hard_framerate)
            #     out.writeframes(b''.join(frames_accumulator))
            # finally:
            #     out.close()
                
            # if os.path.exists(temp_calib): os.remove(temp_calib)
            # return True

            raw_data = b''.join(frames_accumulator)
            self.save_resampled_wav(output_file, raw_data, original_rate=self.framerate)

            if os.path.exists(temp_calib): os.remove(temp_calib)
            return True
        
        except Exception as e:
            print(u"Erreur Record Silence dynamique: {0}".format(str(e)).encode('utf-8'))
            return False

    def merge_wavs(self, file_list, output_name):
        """ Fusionne les morceaux du buffer pour l'analyse """
        try:
            data = []
            nchannels, sampwidth, framerate = None, None, None
            for filename in file_list:
                if not os.path.exists(filename): continue
                w = wave.open(filename, 'rb')
                # Ignorer le chunk s'il ne contient aucune donnée audio (0 frames)
                if w.getnframes() == 0:
                    w.close()
                    continue

                try:
                    if nchannels is None:
                        nchannels = w.getnchannels()
                        sampwidth = w.getsampwidth()
                        framerate = w.getframerate()
                    data.append(w.readframes(w.getnframes()))
                finally:
                    w.close()

            out = wave.open(output_name, 'wb')
            try:
                out.setnchannels(nchannels)
                out.setsampwidth(sampwidth)
                out.setframerate(framerate)
                for frame in data: out.writeframes(frame)
            finally:
                out.close()
            return output_name
        except Exception as e:
            print("Erreur fusion: " + str(e))
            return file_list[-1]
    
    def is_silent(self, wav_file, threshold=800):
        """ 
        Vérifie si le fichier est trop silencieux (Compatible Python 2.7)
        """
        wf = None
        try:
            if not os.path.exists(wav_file):
                return True

            # En Python 2.7, on n'utilise pas 'with' pour wave.open
            wf = wave.open(wav_file, 'rb')
            
            # Récupérer les paramètres : (nchannels, sampwidth, framerate, nframes, ...)
            params = wf.getparams()
            sampwidth = params[1]
            nframes = params[3]
            
            frames = wf.readframes(nframes)
            
            if not frames:
                return True
            
            # Calcul de l'énergie RMS
            rms = audioop.rms(frames, sampwidth)
            
            # Optionnel : décommenter pour voir le niveau réel dans la console
            # print("Niveau sonore RMS : {0}".format(rms))
            
            return rms < threshold

        except Exception as e:
            print(u"Erreur analyse silence: {0}".format(str(e)).encode('utf-8'))
            return True
        finally:
            if wf is not None:
                wf.close()

    def save_resampled_wav(self, path, raw_data, original_rate=44100):
        """
        Convertit les données brutes vers 16000Hz 
        puis les sauvegarde dans un fichier WAV (Compatibilité Python 2.7).
        """
        target_rate = 16000
        nchannels = self.nchannels # Utilise la valeur détectée
        sampwidth = self.sampwidth # Utilise la valeur détectée
        
        # 1. Conversion des données
        resampled_data, _ = audioop.ratecv(
            raw_data, 
            sampwidth, 
            nchannels, 
            original_rate, 
            target_rate, 
            None
        )
        
        # 2. Écriture du fichier (Style Python 2.7 sans 'with')
        out = wave.open(path, 'wb')
        try:
            out.setnchannels(nchannels)
            out.setsampwidth(sampwidth)
            out.setframerate(target_rate)
            out.writeframes(resampled_data)
        finally:
            out.close()
            
        print(u"[AUDIO] Fichier {0} sauvegardé à 16000Hz.".format(path).encode('utf-8'))