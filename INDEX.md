# 📚 INDEX - Synchronisation Réservation Pepper

Bienvenue! Ce document vous guide dans la structure et l'utilisation du système de réservation synchronisé.

## 🚀 Démarrage Rapide (5 min)

### 1️⃣ Installation des dépendances
```bash
pip install -r requirements.txt
```

### 2️⃣ Vérifier l'installation
```bash
python validate_setup.py
```

### 3️⃣ Démarrer les services
```bash
python start.py
# Choisir: 1 (Backend) ou 3 (Tests)
```

### 4️⃣ Tester
```bash
# Terminal 2, pendant que le backend tourne:
python test_reservation_sync.py
```

---

## 📂 Architecture des Fichiers

### 🎯 **Fichier Principal**
| Fichier | Usage |
|---------|-------|
| **reservation.html** | Page web du formulaire (tablette) |
| **app/main.py** | Backend FastAPI + WebSocket |
| **client/main2.py** | Orchestrateur robot Pepper |

### ⚙️ **Configuration**
| Fichier | Usage |
|---------|-------|
| **config.py** | Configuration centralisée (URLs, ports, etc.) |
| **start.py** | Démarrage facile (menu interactif) |
| **start.sh** | Démarrage Bash (Linux/Mac) |

### 🧪 **Tests & Validation**
| Fichier | Usage |
|---------|-------|
| **test_reservation_sync.py** | Tests WebSocket et HTTP |
| **validate_setup.py** | Vérification installation |

### 📖 **Documentation**

#### Pour Comprendre le Système
| Fichier | Cible |
|---------|-------|
| **README_RESERVATION.md** | Vue d'ensemble complète |
| **ARCHITECTURE.md** | Diagrammes et flux détaillé |
| **RESERVATION_SYNC.md** | Guide intégration WebSocket |

#### Pour Déboguer
| Fichier | Contenu |
|---------|---------|
| **TROUBLESHOOTING.md** | FAQ et problèmes courants |
| **CHANGES_SUMMARY.md** | Modifications effectuées |

---

## 🎯 Parcours par Rôle

### 👨‍💻 **Je suis développeur**
1. Lire: [ARCHITECTURE.md](ARCHITECTURE.md) - Comprendre le flux
2. Lancer: `python start.py` → Backend
3. Examiner: `app/main.py` (ConnectionManager + WebSocket)
4. Tester: `python test_reservation_sync.py`
5. Customiser: Éditer `reservation.html` et `app/dialog_manager.py`

### 🛠️ **Je dois déployer en production**
1. Éditer: `config.py` - Adapter URLs et ports
2. Vérifier: `python validate_setup.py`
3. Lancer: `python start.py` → Backend sur serveur
4. Configurer: URLs dans `client/main2.py` pour robot
5. Monitorez: Logs dans `logs/*.log`

### 🤔 **Quelque chose ne marche pas**
1. Consulter: [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
2. Vérifier: `python validate_setup.py`
3. Tester endpoint: `python test_reservation_sync.py`
4. Déboguer: `DEBUG=True python -m uvicorn app.main:app --reload`

### 📚 **Je dois former quelqu'un**
1. Commencer par: [README_RESERVATION.md](README_RESERVATION.md)
2. Montrer: Les diagrammes dans [ARCHITECTURE.md](ARCHITECTURE.md)
3. Démontrer: `python test_reservation_sync.py`
4. Pratiquer: Éditer `reservation.html` ensemble

---

## 📋 Checklist de Compréhension

### Niveau 1: Basique
- [ ] J'ai lu README_RESERVATION.md
- [ ] J'ai lancé le backend avec `start.py`
- [ ] J'ai vu le formulaire se remplir dans les tests
- [ ] J'ai compris le flux: Robot → NLU → DialogManager → WebSocket → Tablette

### Niveau 2: Intermédiaire
- [ ] Je comprends le rôle de ConnectionManager
- [ ] Je sais où les slots sont stockés (session["booking_slots"])
- [ ] Je peux tracer une requête du robot à la tablette
- [ ] Je peux expliquer pourquoi WebSocket vs HTTP simple

### Niveau 3: Avancé
- [ ] Je peux modifier dialog_manager.py pour ajouter un nouveau slot
- [ ] Je peux customiser le design de reservation.html
- [ ] Je peux déboguer un problème de synchronisation
- [ ] Je peux déployer le système en production

---

## 🎓 Concepts Clés

### SessionStore
Stocke l'historique et l'état par session_id
```python
session = {
    "history": [...],           # Messages du dialogue
    "booking_slots": {          # Données extraites
        "salle": "A",
        "jour": "21/04/2026",
        "heure": "10:00"
    }
}
```

### ConnectionManager
Gère les WebSocket connectées
```python
manager = ConnectionManager()
# Pour chaque session_id, ensemble de WebSocket clients
# Broadcast envoie le message à tous
await manager.broadcast_slots(session_id, slots)
```

### Dialog Flow
```
Utilisateur parle
    ↓ [ASR]
Texte reconnu
    ↓ [NLU]
Entités extraites
    ↓ [DialogManager]
Slots remplis + Réponse LLM
    ↓ [WebSocket]
Tablette mise à jour
    ↓ [Utilisateur]
Complète formulaire
```

---

## 🔍 Où Chercher Quoi

### "Comment ajouter un champ au formulaire?"
→ Voir: [TROUBLESHOOTING.md](TROUBLESHOOTING.md#q-comment-ajouter-un-champ)

### "Comment changer les couleurs?"
→ Voir: `reservation.html` section `<style>`

### "Où sont les valeurs par défaut?"
→ Voir: `config.py` (section CONFIGURATION)

### "Comment déboguer les slots?"
→ Lancer: `DEBUG=True python -m uvicorn app.main:app`

### "Comment tester sans robot?"
→ Lancer: `python test_reservation_sync.py`

### "Comment savoir si tout fonctionne?"
→ Lancer: `python validate_setup.py`

### "Où sont les réservations sauvegardées?"
→ MongoDB (si configuré) ou base données définie dans `app/reservation.py`

---

## 🚨 SOS - Aide Rapide

```
Problem                     | Solution
---------------------------|------------------------------------------
"WebSocket non connecté"    | Vérifier backend tourne: curl localhost:8000
"Formulaire reste vide"     | Débugage: grep "[WS]" logs/*.log
"Port déjà utilisé"         | Tuer processus: lsof -i :8000
"Import errors"             | Installer: pip install -r requirements.txt
"MongoDB erreur"            | C'est optionnel - test sans
"Page blanche"              | F12 console → voir erreurs JavaScript
```

---

## 📞 Support

### Ressources
- 📖 [FastAPI Docs](https://fastapi.tiangolo.com/)
- 🔗 [WebSocket MDN](https://developer.mozilla.org/docs/Web/API/WebSocket)
- 🤖 [NAOqi Docs](https://doc.aldebaran.com/)

### Fichiers de Log
```bash
# En continu
tail -f logs/*.log

# Filtrer par type
grep ERROR logs/*.log
grep "\[WS\]" logs/*.log
grep DEBUG logs/*.log
```

### Tester les Endpoints
```bash
# Health check
curl http://localhost:8000/

# Page réservation
curl -I http://localhost:8000/reservation.html

# Récupérer slots
curl http://localhost:8000/v1/session/test/slots

# Dialogue
curl -X POST http://localhost:8000/v1/respond \
  -H "Content-Type: application/json" \
  -d '{"text":"Bonjour","session_id":"test"}'
```

---

## 📊 État du Projet

### ✅ Complété
- [x] Page HTML avec formulaire
- [x] WebSocket synchronisation
- [x] Backend FastAPI + routes
- [x] Client robot intégration
- [x] Tests automatisés
- [x] Documentation complète
- [x] Scripts de démarrage
- [x] Validation installation

### ⏳ Futur (Nice to Have)
- [ ] Animation remplissage champs
- [ ] Multi-langue
- [ ] Thème customisable
- [ ] Offline mode (PWA)
- [ ] Historique réservations
- [ ] Admin dashboard

---

## 🎬 Prochaines Étapes

### Immédiat
```bash
python validate_setup.py  # Vérifier install
python start.py           # Lancer
# Choisir: 1 (Backend)
```

### Court terme
- Éditer `config.py` avec vos URLs
- Tester avec `test_reservation_sync.py`
- Montrer à l'équipe

### Moyen terme
- Déployer en production
- Intégrer avec votre système de réservation
- Customiser le design

---

## 👨‍🏫 Format d'Apprentissage

### 10 min: Comprendre
1. [README_RESERVATION.md](README_RESERVATION.md) - Vue générale
2. Lancer backend: `python start.py`

### 20 min: Explorer
1. Ouvrir [ARCHITECTURE.md](ARCHITECTURE.md) - Voir diagrammes
2. Examiner `reservation.html` - Code HTML
3. Lancer tests: `python test_reservation_sync.py`

### 30 min: Approfondir
1. Lire `app/main.py` - WebSocket setup
2. Lire `client/main2.py` - Robot integration
3. Tracer un appel end-to-end

### 1h: Maîtriser
1. [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - FAQ
2. [CHANGES_SUMMARY.md](CHANGES_SUMMARY.md) - Mods details
3. Écrire un slot personnalisé

---

## 🎉 Félicitations!

Vous avez maintenant un système complet de :
- ✨ Dialogue conversationnel
- 📱 Formulaire synchronisé en temps réel
- 🤖 Intégration robot Pepper
- 🔌 WebSocket performant
- 📊 Architecture scalable

**Enjoy!** 🚀

---

**Dernière mise à jour:** 2026-04-09
**Prêt pour:** Production ✅
