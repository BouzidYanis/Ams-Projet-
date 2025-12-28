import os
import time
import sys
import site


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
    def __init__(self, model_size="base"):
        # On force l'utilisation du processeur (cpu) si vous n'avez pas de GPU NVIDIA
        print(f"[ASR] Chargement du modèle Whisper ({model_size})...")
        # "int8" permet de rendre le modèle encore plus léger
        self.model = WhisperModel(model_size,
                                  device="cuda",
                                  compute_type="float16")

    def process_audio(self, audio_file_path):
        """ Detecte la langue et transcrit le fichier audio """
        if not os.path.exists(audio_file_path):
            return {"error": "Fichier introuvable"}
        
        start_time = time.time()

        segments, info = self.model.transcribe(audio_file_path, beam_size=5)

        text = " ".join([segment.text for segment in segments]).strip()

        duration = time.time() - start_time

        return {
            "text" : text,
            "language" : info.language,
            "language_probability" : info.language_probability,
            "processing_time" : round(duration, 2)
        }


if __name__=="__main__":
    asr = ASRModule(model_size="small")

    test_file = r"Audio_tests\audio_test.wav"
    result = asr.process_audio(test_file)

    print("-" * 30)
    print(f"Texte reconnu : {result['text']}")
    print(f"Langue        : {result['language']} ({round(result['language_probability']*100, 1)}%)")
    print(f"Temps calcul  : {result['processing_time']} secondes")
    print("-" * 30)