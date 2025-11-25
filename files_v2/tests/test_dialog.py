import requests
import json

# Test rapide d'intégration (exige le serveur en local)
SERVER = "http://localhost:8000"

def test_flow():
    r = requests.post(SERVER + "/v1/respond", json={"text":"Bonjour", "lang":"fr"})
    assert r.status_code == 200
    data = r.json()
    assert "text" in data
    sid = data["session_id"]

    r2 = requests.post(SERVER + "/v1/respond", json={"text":"Quels sont les horaires ?", "session_id": sid, "lang":"fr"})
    assert r2.status_code == 200
    data2 = r2.json()
    assert "ouvert" in data2["text"].lower() or "heures" in data2["text"].lower()