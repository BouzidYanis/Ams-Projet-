# -*- coding: utf-8 -*-
import requests
import json
import sys

# Configuration du serveur
# URL = "http://192.168.1.74:8000/v1/respond"
# URL = "http://10.60.55.34:8000/v1/respond"
URL = "http://127.0.0.1:8000/v1/respond"

def test_chat():
    session_id = None
    print(u"--- Test Interaction DialogManager ---")
    print(u"Connecté à : {0}".format(URL))
    print(u"(Tapez 'quit' pour sortir)\n")

    while True:
        try:
            # Récupération de l'input utilisateur
            user_input = raw_input("Vous: ").decode('utf-8')
            if user_input.lower() in ['quit', 'exit']:
                break

            # Préparation du payload pour le point de terminaison FastAPI
            payload = {
                "text": user_input,
                "session_id": session_id,
                "lang": "fr"
            }

            # Envoi de la requête au serveur
            r = requests.post(URL, json=payload, timeout=60)

            if r.status_code == 200:
                data = r.json()
                # On récupère le session_id pour maintenir le contexte dans le DialogManager
                session_id = data.get("session_id")
                response_text = data.get("text")
                
                print(u"Robot: {0}".format(response_text).encode('utf-8'))
                print(u"[SID: {0}]".format(session_id))
            else:
                print(u"Erreur {0}: {1}".format(r.status_code, r.text))

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(u"Erreur de connexion: {0}".format(str(e)))

if __name__ == "__main__":
    test_chat()