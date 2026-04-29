from typing import Dict, Any
import importlib
import re

from app.nlu_train import traiter_requete as matcher_parse


class NLU:

    # Mapping intent NLU embarqué → intent API
    _INTENT_MAP = {
        # français
        "salutation": "greeting",
        "demander_heure": "ask_hours",
        "demander_activite": "ask_activities",
        "demander_lieu": "navigate",
        "reserver": "book_activity",
        "qui": "who_are_you",
        "ask_available_slots": "ask_available_slots",
        "demander_mes_reservations": "ask_my_reservations",
        "ask_pricing": "ask_pricing",
        "cancel_booking": "cancel_booking",
        "demander_horaire_activite_inscrite": "ask_registered_activity_schedule",
        "demander_evenements_speciaux": "ask_special_events",
        # english
        "greeting": "greeting",
        "ask_hours": "ask_hours",
        "ask_activity": "ask_activities",
        "ask_pricing": "ask_pricing",
        "ask_location": "navigate",
        "reserve": "book_activity",
        "who_are_you": "who_are_you",
        "ask_my_bookings": "ask_my_reservations",
        "ask_registered_activity_schedule": "ask_registered_activity_schedule",
        "ask_special_events": "ask_special_events",
        "inconnu": "unknown",
        "unknown": "unknown",
    }

    def __init__(self, **kwargs):
        # Chargement paresseux des parseurs par langue.
        self._parsers = {}
        self._parser_modules = {
            "fr": "app.nlu_models.francais.nlu_train",
            "en": "app.nlu_models.english.nlu_train",
        }

    def _normalize_destination_key(self, raw: str) -> str:
        """Normalize a destination string to a key usable by the tablet map."""
        if raw is None:
            return ""
        s = str(raw).strip()
        if len(s) >= 2 and ((s[0] == s[-1] == "'") or (s[0] == s[-1] == '"')):
            s = s[1:-1].strip()
        s = s.lower().strip()
        # Supprimer la ponctuation finale (., !, ?, etc.)
        s = re.sub(r'[^\w\s]$', '', s).strip()
        s = " ".join(s.split())

        direct = {
            "salle a": "salle_a",
            "salle b": "salle_b",
            "salle c": "salle_c",
            "salle d": "salle_d",
            "salle e": "salle_e",
            "salle f": "salle_f",
            "salle natation": "natation",
            "salle de natation": "natation",
        }
        if s in direct:
            return direct[s]

        s = s.replace("-", "_").replace(" ", "_")
        return s

    def _load_parser_for_lang(self, lang: str):
        if lang in self._parsers:
            return self._parsers[lang]

        module_name = self._parser_modules.get(lang)
        if not module_name:
            self._parsers[lang] = None
            return None

        try:
            module = importlib.import_module(module_name)
            parser = getattr(module, "traiter_requete", None)
            self._parsers[lang] = parser
            return parser
        except Exception as e:
            print(f"[NLU] Erreur import parseur pour '{lang}': {e}")
            self._parsers[lang] = None
            return None

    def _normalize_entities(self, raw_entities: Dict[str, Any]) -> Dict[str, list]:
        entities: Dict[str, list] = {}

        for sport_key in ("sports", "sport", "activity", "activities"):
            for sport in raw_entities.get(sport_key, []) or []:
                if sport:
                    entities.setdefault("activity", []).append(sport)

        for location_key in ("lieux", "lieu", "locations", "location"):
            for lieu in raw_entities.get(location_key, []) or []:
                normalized = self._normalize_destination_key(lieu)
                if normalized:
                    entities.setdefault("location", []).append(normalized)

        for time_key in ("temps", "time", "times"):
            for t in raw_entities.get(time_key, []) or []:
                if t:
                    entities.setdefault("time", []).append(t)

        for number_key in ("nombres", "number", "numbers"):
            for n in raw_entities.get(number_key, []) or []:
                if n:
                    entities.setdefault("number", []).append(n)

        # Déduplication
        for key, values in list(entities.items()):
            seen = set()
            unique = []
            for value in values:
                low = str(value).strip().lower()
                if not low or low in seen:
                    continue
                seen.add(low)
                unique.append(value)
            entities[key] = unique

        return entities

    def parse(self, text: str, lang: str = "fr") -> Dict[str, Any]:
        text_in = (text or "").strip()
        if not text_in:
            return {"intent": "unknown", "confidence": 0.0, "entities": {}, "raw_text": text}
        parser = self._load_parser_for_lang(lang)
        if parser is None:
            result = matcher_parse(text_in)
        else:
            try:
                result = parser(text_in)
            except Exception as e:
                print(f"[NLU] Erreur pendant parsing '{lang}' (fallback): {e}")
                result = matcher_parse(text_in)

        # Intent : mapper vers les noms utilisés par le DialogManager
        raw_intent = result.get("intent", "inconnu")
        intent = self._INTENT_MAP.get(raw_intent, raw_intent)
        confidence = result.get("confidence", 0.0)

        # Entities : normaliser les clés FR/EN vers l'API
        entities = self._normalize_entities(result.get("entites", {}))

        return {
            "intent": intent,
            "confidence": round(confidence, 2),
            "entities": entities,
            "raw_text": text,
        }

    def parse_intents_confidences(self, text: str, lang: str = "fr") -> Dict[str, float]:
        """Retourne les scores de toutes les intents (ici un seul gagnant)."""
        result = self.parse(text, lang)
        intent = result["intent"]
        conf = result["confidence"]
        all_intents = {v: 0.0 for v in self._INTENT_MAP.values()}
        all_intents[intent] = conf
        return all_intents
    
    