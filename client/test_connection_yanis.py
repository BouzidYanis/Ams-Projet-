# -- coding: utf-8 --
"""
Test simple : enregistre l'audio depuis les micros de Pepper,
l'envoie au serveur ASR et affiche la transcription.
"""

import qi
import sys
import time
from ALAudioRecorder import PepperAudioCapture

# Configuration
PEPPER_IP = "192.168.13.230"
PEPPER_PORT = 9559
ASR_URL = "http://localhost:8000/v1/asr"


def main():
    # 1. Connexion à Pepper
    print("Connexion à Pepper ({}:{})...".format(PEPPER_IP, PEPPER_PORT))
    session = qi.Session()
    try:
        session.connect("tcp://{}:{}".format(PEPPER_IP, PEPPER_PORT))
    except RuntimeError as e:
        print("Erreur de connexion à Pepper: {}".format(e))
        sys.exit(1)
    print("Connecté !")

    # 2. Initialiser le module audio
    audio = PepperAudioCapture(
        session,
        asr_url=ASR_URL,
        robot_ip=PEPPER_IP,
        robot_user="nao",
        robot_pass="nao"
    )

    # 3. Faire dire au robot qu'il écoute
    tts = session.service("ALTextToSpeech")
    tts.setLanguage("French")

    print("\n" + "=" * 50)
    print("TEST DE TRANSCRIPTION AUDIO")
    print("=" * 50)

    try:
        while True:
            # Demander à l'utilisateur de parler
            raw_input("\nAppuyez sur Entrée pour commencer l'enregistrement (Ctrl+C pour quitter)...")

            tts.say("Je vous écoute.")
            print("\n[INFO] Enregistrement en cours (5 secondes)... Parlez maintenant !")

            # 4. Enregistrer un chunk audio
            duration = 5
            filepath = audio.record_chunk(
                filename="test_transcription.wav",
                duration=duration,
                sample_rate=16000,
                channels=(0, 0, 1, 0)  # micro gauche
            )

            if not filepath:
                print("[ERREUR] L'enregistrement a échoué.")
                continue

            print("[OK] Fichier audio enregistré: {}".format(filepath))

            # 5. Envoyer au serveur ASR
            print("[INFO] Envoi au serveur ASR ({})...".format(ASR_URL))
            result = audio.send_to_asr(filepath)

            if result:
                text = result.get("text", "")
                language = result.get("language", "??")

                print("\n" + "-" * 40)
                print("TRANSCRIPTION : \"{}\"".format(text))
                print("LANGUE        : {}".format(language))
                print("-" * 40)

                # 6. Le robot répète ce qu'il a compris
                if text.strip():
                    tts.say("Vous avez dit : {}".format(text.encode("utf-8")))
                else:
                    tts.say("Je n'ai rien compris, pouvez-vous répéter ?")
                    print("[WARNING] Transcription vide.")
            else:
                print("[ERREUR] Pas de réponse du serveur ASR.")
                tts.say("Désolé, le serveur de transcription n'a pas répondu.")

            # 7. Nettoyage du fichier temporaire
            import os
            try:
                os.remove(filepath)
            except Exception:
                pass

    except KeyboardInterrupt:
        print("\n\nArrêt du test.")
        tts.say("Au revoir !")


if __name__ == "__main__":
    main()