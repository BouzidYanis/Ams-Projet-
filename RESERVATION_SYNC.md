# 📅 Synchronisation Réservation - Guide d'Intégration

## Overview

Cette fonctionnalité permet une synchronisation en **temps réel** entre le dialogue du robot et une page web de réservation. Quand l'utilisateur demande une réservation au robot, les informations extraites (salle, date, heure, activité) remplissent *automatiquement* le formulaire web sur la tablette du robot.

## Architecture

```
┌─────────────┐         ┌──────────────┐         ┌─────────────┐
│   Robot     │         │   Backend    │         │  Tablette   │
│  (Pepper)   │──ASR──→ │  (FastAPI)   │◄─WebSocket─→ (HTML) │
│             │         │  DialogMgr   │         │ Formulaire  │
└─────────────┘         └──────────────┘         └─────────────┘
                              ↓
                        Dialog Manager
                      (NLU + Slot filling)
```

## Fichiers Modifiés/Créés

| Fichier | Rôle |
|---------|------|
| **app/main.py** | Backend FastAPI avec support WebSocket |
| **reservation.html** | Page web avec formulaire synchronisé |
| **test_reservation_sync.py** | Tests unitaires |

## Flux de Utilisation

### 1️⃣ Utilisateur parle au robot:
```
"Je veux réserver la salle A pour le 21 avril 2026 à 10h"
```

### 2️⃣ Backend traite:
- **NLU** extrait: `salle=A`, `jour=21/04/2026`, `heure=10:00`
- **DialogManager** remplit les slots
- Stocke dans session: `booking_slots = {...}`

### 3️⃣ WebSocket envoie au frontend:
```json
{
  "slots": {
    "salle": "A",
    "jour": "21/04/2026",
    "heure": "10:00"
  },
  "message": "Formulaire mis à jour"
}
```

### 4️⃣ Page web se met à jour:
- Les champs du formulaire se remplissent
- Indicateurs visuels ✓ apparaissent
- Bouton "Réserver" devient actif

## Intégration dans le Client (main2.py)

### Afficher la page de réservation:
```python
# Dans PepperOrchestrator, quand une réservation est en cours:
def handle_actions(self, actions):
    if actions.get("type") == "booking_slot_filling":
        session_id = self.dialog_session_id
        url = f"{WEB_URL}?session_id={session_id}"
        self.robot_show_url(url)  # Affiche la page de réservation
```

### Configuration (main2.py):
```python
WEB_URL = "http://10.126.8.40:5500/reservation.html"
# ou localement:
WEB_URL = "http://localhost:8000/reservation.html"
```

## Endpoints API

### WebSocket: `/ws/reservation/{session_id}`
**Établit une connexion pour la synchronisation en temps réel.**

```bash
ws://localhost:8000/ws/reservation/session_123
```

### GET: `/v1/session/{session_id}/slots`
**Récupère les slots actuels (fallback HTTP).**

```bash
curl http://localhost:8000/v1/session/session_123/slots

# Réponse:
{
  "session_id": "session_123",
  "slots": {
    "salle": "A",
    "activite": "Fitness",
    "jour": "2026-04-21",
    "heure": "10:00"
  },
  "in_progress": true
}
```

### POST: `/v1/reserver_salle`
**Soumet la réservation finale.**

```bash
curl -X POST http://localhost:8000/v1/reserver_salle \
  -H "Content-Type: application/json" \
  -d '{
    "utilisateur_id": "user_123",
    "salle": "A",
    "creneau": {
      "jour": "2026-04-21",
      "heure_debut": "10:00",
      "heure_fin": "11:00"
    }
  }'
```

## Formats de Date/Heure Supportés

La page web convertit automatiquement les formats:

| Format | Exemple | Converti en |
|--------|---------|------------|
| ISO | `2026-04-21` | `2026-04-21` |
| DD/MM/YYYY | `21/04/2026` | `2026-04-21` |
| Texte | `21 avril 2026` | `2026-04-21` |
| Heure HH:MM | `10:30` | `10:30` |
| Heure textuelle | `10 h 30` | `10:30` |

## Éléments Visuels

### Indicateurs Remplis:
```
✓ (cercle vert) = Champ rempli automatiquement
```

### Couleurs:
- **Purple gradient** = Thème principal
- **Green (#28a745)** = Champs remplis
- **Blue (#667eea)** = Focus/Actif

### États:
1. **Déconnecté** (point rouge pulsant en haut-droit)
2. **Connecté** (point vert fixe en haut-droit)

## Tests

### Test HTTP simple:
```bash
python3 test_reservation_sync.py
```

### Test WebSocket en direct:
```bash
# Terminal 1: Lancer le serveur
python3 -m uvicorn app.main:app --reload

# Terminal 2: Lancer les tests
python3 test_reservation_sync.py
```

## Débogage

### Logs du backend:
```bash
# Cherchez les messages:
[WS] Client connecté: session_123
[WS] Slots envoyés au frontend: {...}
[DEBUG] Slots actuels: {...}
```

### Logs du frontend (console browser):
```javascript
// Ouvrir F12 / DevTools de la tablette
console.log('WebSocket connecté');
console.log('Slots reçus:', data);
```

### Vérifier la connexion WebSocket:
```bash
curl -i -N \
  -H "Connection: Upgrade" \
  -H "Upgrade: websocket" \
  http://localhost:8000/ws/reservation/test_session
```

## Cas d'Usage Avancés

### 1. Pré-remplir avec le nom reconnu:
```python
# Dans client/main2.py:
user_name = recognize_face()  # Donne "Jean Dupont"
response = send_to_dialog(text, user_name=user_name)
```

### 2. Faire défiler le formulaire pour voir tous les champs:
La page web utilise du responsive design et scroll si nécessaire.

### 3. Gérer les salles multiples:
Le NLU peut extraire plusieurs salles; la page affichera la première.

## Troubleshooting

| Problème | Solution |
|----------|----------|
| WebSocket "Connection refused" | Vérifier que le backend court sur le bon port |
| Formulaire ne se met pas à jour | Vérifier les logs WebSocket du backend |
| Page blanche | Ouvrir console (F12) et vérifier les erreurs JS |
| CORS errors | Backend inclut middleware CORS - devrait être OK |

## Prochaines Étapes

1. **Intégrer dans main2.py** - afficher la page au moment opportun
2. **Ajouter validation côté client** - vérifier format avant submission
3. **Multi-langue** - adapter le formulaire selon la langue détectée
4. **Animations** - transitions quand les champs se remplissent
5. **Confirmations** - pop-up ou animation quand réservation réussit

---

**Questions?** Vérifier les logs et les tests.
