import os
import time
import sys
import site
import wave

#Chargment des cudas dynamique - Code portable
def setup_cuda_path():
    """Ajoute dynamiquement les dossiers NVIDIA du venv au PATH Windows."""
    # 1. On récupère les chemins vers les site-packages de l'environnement actif
    package_paths = site.getsitepackages()
    
    for base_path in package_paths:
        # 2. On définit les sous-dossiers cibles
        nvidia_base = os.path.join(base_path, "nvidia")
        
        if os.path.exists(nvidia_base):
            # On cherche tous les dossiers 'bin' dans les sous-dossiers de nvidia
            # (cudnn/bin, cublas/bin, etc.)
            for root, dirs, files in os.walk(nvidia_base):
                if root.endswith("bin"):
                    if root not in os.environ["PATH"]:
                        os.environ["PATH"] = root + os.pathsep + os.environ["PATH"]
                        print(f"[ASR] DLL Path ajouté : {root}")

# Appeler la fonction avant d'importer faster_whisper
if sys.platform == "win32":
    setup_cuda_path()

from faster_whisper import WhisperModel

class ASRModule:
    def __init__(self, model_size="base", logprob_threshold=-1.0, nospeech_threshold=0.6):
        # On force l'utilisation du processeur (cpu) si vous n'avez pas de GPU NVIDIA
        print(f"[ASR] Chargement du modèle Whisper ({model_size})...")
        # "int8" permet de rendre le modèle encore plus léger
        self.model = WhisperModel(model_size,
                                  device="cuda",
                                #   device="cpu",
                                  compute_type="int8_float16")
                                #   compute_type="int8")
        
        self.logprob_threshold = logprob_threshold # Plus bas : modèle trop incertain
        self.nospeech_threshold = nospeech_threshold # Plus haut : Plus de tolérance au bruit
    
    def clean_audio_with_vad(self, file_path):
        
        if not os.path.exists(file_path):
            return False
        
        try:
            with wave.open(file_path, 'rb') as wf:
                sample_rate = wf.getframerate()
                n_channels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                frames = wf.readframes(wf.getnframes())

            # Le VAD nécessite obligatoirement du 16-bit PCM Mono
            if n_channels != 1 or sampwidth != 2:
                print("[VAD] Format incompatible (doit être Mono 16-bit)")
                return False

            frame_duration_ms = 30
            frame_size = int(sample_rate * (frame_duration_ms / 1000.0) * 2)

            voiced_frames = []
            for i in range(0, len(frames), frame_size):
                chunk = frames[i:i + frame_size]
                if len(chunk) < frame_size:
                    break
                if self.vad.is_speech(chunk, sample_rate):
                    voiced_frames.append(chunk)
            
            if not voiced_frames:
                print("[VAD] Aucun segment de voix détecté.")
                # On ne vide pas le fichier pour éviter que Whisper crash, 
                # mais on sait qu'il sera peu fiable.
                return False

            # On réécrit le fichier avec uniquement la voix
            with wave.open(file_path, 'wb') as wf:
                wf.setnchannels(n_channels)
                wf.setsampwidth(sampwidth)
                wf.setframerate(sample_rate)
                wf.writeframes(b"".join(voiced_frames))
            
            print(f"[VAD] Nettoyage terminé. Voix extraite de {file_path}")
            return True
        except Exception as e:
            print(f"[VAD] Erreur lors du nettoyage : {e}")
            return False

    def process_audio(self, audio_file_path):
        """ Detecte la langue et transcrit le fichier audio """
        if not os.path.exists(audio_file_path):
            print("error : Fichier introuvable")
            return {"error": "Fichier introuvable"}
        
        start_time = time.time()
        print(f"[ASR] Début de transcription pour: {audio_file_path}")

        segments_generator, info = self.model.transcribe(audio_file_path, beam_size=5)

        segments = list(segments_generator)
        full_text = ""
        avg_logprob = -99.0
        no_speech_prob = 1.0        
        
        if segments:
            full_text = " ".join([s.text for s in segments]).strip()
            avg_logprob = sum([s.avg_logprob for s in segments]) / len(segments)
            no_speech_prob = sum([s.no_speech_prob for s in segments]) / len(segments)
            
            print(f"[DEBUG ASR] Texte brut: '{full_text}'")
            print(f"[DEBUG ASR] Langue: {info.language} ({info.language_probability:.2f})")
            print(f"[DEBUG ASR] Métriques: logprob={avg_logprob:.2f}, no_speech={no_speech_prob:.2f}")
        else:
            print("[DEBUG ASR] Aucun segment détecté (silence total ?)")
        
        duration = time.time() - start_time

        is_reliable = True
        if avg_logprob < self.logprob_threshold or no_speech_prob > self.nospeech_threshold:
            print(f"[ASR] Alerte Confiance: logprob={avg_logprob:.2f}, no_speech={no_speech_prob:.2f}")
            is_reliable = False  

        return {
            "text": full_text if is_reliable else "ERROR_CONFIDENCE_LOW",
            "language": info.language,
            "language_probability": info.language_probability,
            "avg_logprob": round(avg_logprob, 2),
            "no_speech_prob": round(no_speech_prob, 2),
            "is_reliable": is_reliable,
            "processing_time": round(duration, 2)
        }


if __name__=="__main__":
    # 1. On récupère le dossier où se trouve speech.py (le dossier 'app')
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 2. On construit le chemin vers le fichier de test
    # Cela donnera : app/Audio_tests/audio_test.wav
    test_file = os.path.join(current_dir, "Audio_tests", "audio_test.wav")
    
    asr = ASRModule(model_size="small")

    result = asr.process_audio(test_file)

    print("-" * 30)
    print(f"Texte reconnu : {result['text']}")
    print(f"Langue        : {result['language']} ({round(result['language_probability']*100, 1)}%)")
    print(f"Temps calcul  : {result['processing_time']} secondes")
    print("-" * 30)