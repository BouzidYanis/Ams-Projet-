```markdown
# Serveur de dialogue (LLM) - Robot d'accueil Salle multisports

Cette version du serveur de dialogue utilise un LLM configurable (FastChat ou HuggingFace TGI) pour générer des réponses conversationnelles
à partir de l'historique de la session.

Principales caractéristiques :
- Backend LLM configurable via `configs/llm_config.json` : `fastchat` (OpenAI-like) ou `hf_tgi` (HuggingFace Text-Generation-Inference).
- Conversation memory par session (user/assistant messages).
- Prompting : system prompt + conversation history.
- Endpoints REST simples pour intégration avec NAOqi / ROS (après ASR -> envoyer transcript).

Installation rapide :
1. Créer un environnement Python 3.10+ :
   python -m venv venv
   source venv/bin/activate

2. Installer dépendances :
   pip install -r requirements.txt

3. Configurer LLM :
   - Si tu as FastChat/Chat-Completion API (ex: modèle Vicuna ou Llama-derivé) : modifie `configs/llm_config.json` :
     backend: "fastchat"
     endpoint: "http://<host>:<port>"  (ex: http://localhost:8000)
     model: "<nom_du_model>"
   - Si tu as HuggingFace TGI : backend "hf_tgi", endpoint ex: http://localhost:8080

4. Lancer le serveur :
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

Endpoints :
- POST /v1/parse
  Payload: {"text": "...", "lang": "fr"}
  Retour: {intent, confidence, entities}

- POST /v1/respond
  Payload: {"text": "...", "lang":"fr", "session_id":"... (optionnel)"}
  Retour: { "text": "<réponse>", "actions": {...}, "session_id": "..." }

- GET /v1/session/{session_id}/reset
  Réinitialiser la session.

Exemple d'usage (curl) :
1) Début de conversation
   curl -X POST http://localhost:8000/v1/respond -H "Content-Type: application/json" -d '{"text":"Bonjour", "lang":"fr"}'
2) Réutiliser session_id renvoyé pour la suite (garder l'historique côté serveur).

Notes et recommandations :
- FastChat : si tu utilises le serveur FastChat officiel, il propose un endpoint OpenAI-compatible
  /v1/chat/completions (vérifie l'URL et le port de ton déploiement FastChat).
- HuggingFace TGI : si tu exposes TGI localement (ex: text-generation-inference) utilise backend "hf_tgi".
- Pour la production : sécuriser l'API (auth, TLS), stocker sessions dans Redis, et logs/booking dans une BDD.
- Tu peux affiner le system_prompt dans `configs/llm_config.json` pour personnaliser le comportement du robot.

Ce dépôt est prévu pour être un point de départ : si tu veux je peux
- ajouter un backend "transformers local" (ex: via accelerate + transformers) pour inference locale,
- fournir des exemples d'installation FastChat/Vicuna ou TGI,
- connecter la gestion des réservations à une base SQLite/Postgres.

```

curl -s "https://generativelanguage.googleapis.com/v1beta/models?key=AIzaSyCMsuEISK-UD4przCm3kCfS2RJ65BWZfY0" | jq '.models[].name'