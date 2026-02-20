from typing import Dict, Any

from app.nlu_train import traiter_requete as matcher_parse


class NLU:

    # Mapping intent nlu_train → intent API
    _INTENT_MAP = {
        "salutation": "greeting",
        "demander_heure": "ask_hours",
        "demander_activite": "ask_activities",
        "demander_lieu": "navigate",
        "reserver": "book_activity",
        "qui": "who_are_you",
        "inconnu": "unknown",
    }

    def __init__(self, **kwargs):
        # Pas de modèle à charger, tout vient de nlu_train.py
        pass

    def _normalize_destination_key(self, raw: str) -> str:
        """Normalize a destination string to a key usable by the tablet map."""
        if raw is None:
            return ""
        s = str(raw).strip()
        if len(s) >= 2 and ((s[0] == s[-1] == "'") or (s[0] == s[-1] == '"')):
            s = s[1:-1].strip()
        s = s.lower().strip()
        s = " ".join(s.split())

        direct = {
            "salle a": "salle_a",
            "salle b": "salle_b",
            "salle c": "salle_c",
            "salle d": "salle_d",
            "salle natation": "natation",
            "salle de natation": "natation",
        }
        if s in direct:
            return direct[s]

        s = s.replace("-", "_").replace(" ", "_")
        return s

    def parse(self, text: str, lang: str = "fr") -> Dict[str, Any]:
        text_in = (text or "").strip().lower()
        if not text_in:
            return {"intent": "unknown", "confidence": 0.0, "entities": {}, "raw_text": text}

        # Tout passe par nlu_train.py
        result = matcher_parse(text_in)

        # Intent : mapper vers les noms utilisés par le DialogManager
        raw_intent = result.get("intent", "inconnu")
        intent = self._INTENT_MAP.get(raw_intent, raw_intent)
        confidence = result.get("confidence", 0.0)

        # Entities : restructurer pour l'API
        matcher_ents = result.get("entites", {})
        entities: Dict[str, list] = {}

        # Lieux → location (normalisés)
        for lieu in matcher_ents.get("lieux", []):
            normalized = self._normalize_destination_key(lieu)
            if normalized:
                entities.setdefault("location", []).append(normalized)

        # Sports → activity
        for sport in matcher_ents.get("sports", []):
            if sport:
                entities.setdefault("activity", []).append(sport)

        # Temps → time
        for t in matcher_ents.get("temps", []):
            if t:
                entities.setdefault("time", []).append(t)

        # Nombres → number
        for n in matcher_ents.get("nombres", []):
            if n:
                entities.setdefault("number", []).append(n)

        return {
            "intent": intent,
            "confidence": round(confidence, 2),
            "entities": entities,
            "raw_text": text,
        }

    def parse_intents_confidences(self, text: str) -> Dict[str, float]:
        """Retourne les scores de toutes les intents (ici un seul gagnant)."""
        result = self.parse(text)
        intent = result["intent"]
        conf = result["confidence"]
        all_intents = {v: 0.0 for v in self._INTENT_MAP.values()}
        all_intents[intent] = conf
        return all_intents
    
    