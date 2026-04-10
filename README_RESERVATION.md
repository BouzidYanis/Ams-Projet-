# 🤖 Système de Dialogue Pepper avec Réservation Synchronisée

Un système complet de dialogue conversationnel pour un robot d'accueil Pepper, avec synchronisation WebSocket pour un formulaire de réservation sur tablette.

## 🎯 Fonctionnalités

- ✨ **ASR (Automatic Speech Recognition)** - Transcription audio via Faster-Whisper
- 🧠 **NLU (Natural Language Understanding)** - Compréhension du langage naturel avec spaCy
- 💬 **Dialogue Manager** - Gestion intelligente des conversations avec LLM  
- 📅 **Slot Filling** - Extraction automatique (salle, date, heure, activité)
- 📱 **Synchronisation WebSocket** - Mise à jour du formulaire en temps réel
- 🗺️ **Navigation** - Instructions directionnelles
- 👤 **Reconnaissance Faciale** - Identification des utilisateurs

## 🏗️ Architecture

```
┌─────────────────────┐
│   Robot Pepper      │
│  (Micro + Haut-p.)  │
└──────────┬──────────┘
           │ Audio
           ↓
┌─────────────────────────────────┐
│   Backend FastAPI (Port 8000)   │
├─────────────────────────────────┤
│  • ASR Module                   │
│  • NLU (spaCy)                  │
│  • DialogManager + LLM          │
│  • Session Store                │
│  • WebSocket Manager            │
└──────────┬──────────────────────┘
           │ JSON + WebSocket
           ↓
┌─────────────────────┐
│  Tablette Pepper    │
│  reservation.html   │
│  (Synchronisée)     │
└─────────────────────┘
```

## 🚀 Installation

### Prérequis
- Python 3.8+
- pip / conda
- NAOqi SDK (pour Pepper)
- MongoDB (optionnel, pour réservations)

### 1. Cloner et installer

```bash
git clone <repo>
cd Ams-Projet-
pip install -r requirements.txt
```

### 2. Configurer

Éditer `client/main2.py` ou créer `.env`:
```bash
# Backend
BACKEND_URL=http://localhost:8000
WEBSOCKET_URL=ws://localhost:8000

# Robot
PEPPER_IP=192.168.13.202
PEPPER_PORT=9559

# Tablette
TABLET_WEB_BASE_URL=http://10.126.8.40:5500/
# Ou pour test local:
# TABLET_WEB_BASE_URL=http://localhost:8000/
```

### 3. Démarrer les services

**Terminal 1: Backend**
```bash
cd app
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

**Terminal 2: Client Robot (local)**
```bash
cd client
python main2.py
```

**Terminal 3: Serveur web (optionnel, si pas de serveur externe)**
```bash
cd ..
python -m http.server 5500 --bind 10.126.8.40
```

## 📋 Endpoints API

### ASR (Transcription)
```http
POST /v1/asr
Content-Type: multipart/form-data

Réponse:
{
  "text": "Je veux réserver la salle A pour le 21 avril à 10h",
  "language": "fr",
  "confidence": 0.95
}
```

### Dialogue
```http
POST /v1/respond
Content-Type: application/json

{
  "text": "Je veux réserver la salle A pour le 21 avril à 10h",
  "session_id": "session_123",
  "user_name": "Jean Dupont"
}

Réponse:
{
  "text": "Très bien! Je réserve la salle A pour le 21 avril. À quelle heure?",
  "actions": {"type": "booking_slot_filling"},
  "session_id": "session_123"
}
```

### Slots (Récupération)
```http
GET /v1/session/{session_id}/slots

Réponse:
{
  "session_id": "session_123",
  "slots": {
    "salle": "A",
    "jour": "2026-04-21",
    "heure": "10:00",
    "activite": "Fitness"
  },
  "in_progress": true
}
```

### WebSocket (Synchronisation temps réel)
```javascript
// Frontend (reservation.html)
const ws = new WebSocket('ws://localhost:8000/ws/reservation/session_123');

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log('Slots reçus:', data.slots);
    // Mise à jour du formulaire...
};
```

## 📱 Utilisation

### Flux Utilisateur Typique

```
1️⃣ Utilisateur (à Pepper):
   "Bonjour, je veux réserver une salle pour demain"

2️⃣ Pepper reconnaît et envoie au serveur

3️⃣ DialogManager extrait les slots et demande:
   Pepper: "Quelle activité désirez-vous?"
   → Page de réservation s'affiche sur tablette

4️⃣ Utilisateur parle ou remplit le formulaire

5️⃣ Les champs se remplissent en temps réel
   📅 Jour: 22/04/2026
   🏋️ Activité: Fitness
   ...

6️⃣ Une fois complet, l'utilisateur clique "Réserver"

7️⃣ Réservation confirmée dans la BD
   Pepper: "Confirmation! Salle réservée."
```

## 🔧 Fichiers Clés

| Fichier | Rôle |
|---------|------|
| `app/main.py` | Backend FastAPI principal |
| `app/dialog_manager.py` | Logique de dialogue + slot filling |
| `app/nlu.py` | Module NLU avec spaCy |
| `app/speech.py` | Transcription audio (Whisper) |
| `reservation.html` | Page web de réservation synchronisée |
| `client/main2.py` | Orchestrateur robot Pepper |
| `config.py` | Configuration globale |

## 🧪 Tests

### Test simple (HTTP)
```bash
python test_reservation_sync.py
```

### Test WebSocket
```bash
python test_reservation_sync.py
# Attend la connexion WebSocket et teste la sync
```

### Curl direct
```bash
# Test ASR
curl -X POST -F "file=@audio.wav" http://localhost:8000/v1/asr

# Test dialogue
curl -X POST http://localhost:8000/v1/respond \
  -H "Content-Type: application/json" \
  -d '{"text": "Bonjour", "session_id": "test123"}'

# Récupérer slots
curl http://localhost:8000/v1/session/test123/slots
```

## 🐛 Débogage

### Activer logs verbeux
```python
# Dans config.py
DEBUG = True
VERBOSE_LOGGING = True
```

### Vérifier WebSocket
```bash
# Terminal Linux
websocat ws://localhost:8000/ws/reservation/test

# Terminal Windows
wscat -c ws://localhost:8000/ws/reservation/test
```

### Logs de la tablette
Ouvrir DevTools (F12) sur la tablette:
```javascript
// Console
> console.log('WebSocket state:', ws.readyState);
> console.log('Slots reçus:', lastSlotsData);
```

## 🔐 Sécurité

❌ **À faire en prod**:
- [ ] Auth OAuth/JWT pour les réservations
- [ ] HTTPS + WSS (WebSocket Secure)
- [ ] Rate limiting sur les endpoints
- [ ] Validation stricte des inputs
- [ ] Chiffrer session storage

✅ **Déjà configuré**:
- CORS middleware
- Gestion des WebSockets propre
- Erreur handling robuste

## 📚 Documentation Supplémentaire

- [RESERVATION_SYNC.md](RESERVATION_SYNC.md) - Détails synchronisation
- [README.md](README.md) - Documentation générale (exis tante)

## 🤝 Contribution

Pour ajouter une nouvelle action:

1. Dans `dialog_manager.py`: définir l'action
2. Dans `client/main2.py`: implémenter le traitement
3. Tester avec `test_reservation_sync.py`

## 📝 Licence

À définir

## 👥 Contact

Support Pepper: [contact info]

---

**🚀 Prêt à démarrer?** 
```bash
python config.py  # Voir la configuration
python -m uvicorn app.main:app --reload  # Démarrer
```
