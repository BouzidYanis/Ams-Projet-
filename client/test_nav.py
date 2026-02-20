# -*- coding: utf-8 -*-
# filepath: /media/ybouzid/Y2_3_Dat1/projet/pweb/Api_robot/Ams-Projet-/client/test_nav.py
# je veux que le robot envoie une requette POST http://localhost:8000/v1/respond   -H "Content-Type: application/json"   -d '{"text":"je cherche la salle a"}'

import qi
import sys
import time
import requests
import json
from nav import Navigation

# Configuration
PEPPER_IP = "192.168.13.230"
PEPPER_PORT = 9559
API_URL = "http://localhost:8000/v1/respond"
WEB_BASE_URL = "http://10.126.8.40:5500/"

def main():
    try:
        # 1. Envoi de la requête POST au serveur de dialogue
        print("Envoi de la requête POST à {}...".format(API_URL))
        payload = {"text": "je cherche la salle a"}
        headers = {"Content-Type": "application/json"}
        response = requests.post(API_URL, json=payload, headers=headers)
        response.raise_for_status()

        data = response.json()
        print("Réponse du serveur :")
        print(json.dumps(data, indent=2, ensure_ascii=False))

        response_text = data.get("text", "")
        actions = data.get("actions", {})
        session_id = data.get("session_id", "")

        # 2. Connexion à Pepper
        print("\nConnexion à Pepper ({})...".format(PEPPER_IP))
        session = qi.Session()
        session.connect("tcp://{}:{}".format(PEPPER_IP, PEPPER_PORT))
        print("Connecté !")

        # 3. Initialisation de la navigation
        nav = Navigation(WEB_BASE_URL, session)

        # 4. Si le serveur a renvoyé une action de navigation, afficher la carte
        if actions.get("type") == "navigate":
            destination_key = actions.get("destination_key", "")
            print("Navigation vers : {} ({})".format(actions.get("destination", ""), destination_key))
            nav.afficher_carte(destination_key)
            session.service("ALTextToSpeech").say(response_text)

        # 6. Laisser la carte affichée quelques secondes
        time.sleep(10)

        # 7. Masquer la page
        nav.web_display.hidePage()
        print("Terminé.")

    except requests.exceptions.RequestException as e:
        print("Erreur lors de la requête HTTP : {}".format(e))
        sys.exit(1)
    except Exception as e:
        print("Erreur : {}".format(e))
        sys.exit(1)

if __name__ == "__main__":
    main()