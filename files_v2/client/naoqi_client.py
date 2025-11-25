"""
Exemple de client minimal que le robot (NAOqi/ROS) peut utiliser.
Supposons que le robot envoie la transcription (ASR) au serveur et récupère la réponse.
"""

import requests

SERVER = "http://localhost:8000"

def send_user_text(text, session_id=None, lang="fr"):
    payload = {"text": text, "lang": lang}
    if session_id:
        payload["session_id"] = session_id
    r = requests.post(f"{SERVER}/v1/respond", json=payload, timeout=5)
    r.raise_for_status()
    return r.json()

if __name__ == "__main__":
    # exemple
    resp = send_user_text("Bonjour", None)
    print("Response:", resp)
    # Réutiliser session_id pour suivre la conversation
    sid = resp["session_id"]
    resp2 = send_user_text("Quels sont les horaires ?", sid)
    print(resp2)