from typing import Dict, Any, Callable, cast
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
        self.parsers: dict[str, Any] = {}
        self._parsers = self.parsers
        self._parser_modules = {
            "fr": "app.nlu_models.francais.nlu_train",
            "en": "app.nlu_models.english.nlu_train",
        }
        self.parsers["fr"] = self._load_language_parser("francais")
        self.parsers["en"] = self._load_language_parser("english")

        # Fallback historique si un parseur de langue n'est pas importable.
        self.fallback_parser = matcher_parse

    def _load_language_parser(self, folder_name: str):
        module_name = f"app.nlu_models.{folder_name}.nlu_train"
        try:
            return importlib.import_module(module_name)
        except Exception as exc:
            print(f"[NLU] Erreur import parseur pour '{folder_name[:2]}': {exc}")
            return None

    def _normalize_lang_code(self, lang: str | None) -> str:
        """Réduit les variantes de langue à une clé de parseur supportée."""
        if not lang:
            return "fr"
        normalized = str(lang).strip().lower().replace("_", "-")
        return normalized.split("-", 1)[0] or "fr"

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

        # Harmoniser les variantes anglaises et françaises vers les clés DB.
        s = s.replace("room ", "salle ")
        s = s.replace("room_", "salle_")

        direct = {
            "salle a": "salle_a",
            "salle b": "salle_b",
            "salle c": "salle_c",
            "salle d": "salle_d",
            "salle e": "salle_e",
            "salle f": "salle_f",
            "room a": "salle_a",
            "room b": "salle_b",
            "room c": "salle_c",
            "room d": "salle_d",
            "room e": "salle_e",
            "room f": "salle_f",
            "salle natation": "natation",
            "room natation": "natation",
            "salle de natation": "natation",
            "pool": "natation",
            "swimming pool": "natation",
        }
        if s in direct:
            return direct[s]

        match = re.fullmatch(r"(?:salle|room)[ _-]*([a-f])", s)
        if match:
            return f"salle_{match.group(1)}"

        s = s.replace("-", "_").replace(" ", "_")
        return s

    def _normalize_activity_name(self, raw: str) -> str:
        """Normalise une activité vers le libellé attendu par la base Mongo."""
        if raw is None:
            return ""

        s = str(raw).strip().strip("'\"")
        if not s:
            return ""

        key = re.sub(r"[\s_-]+", " ", s.lower())
        aliases = {
            "yoga": "Yoga",
            "pilates": "Pilates",
            "zumba": "Zumba",
            "fitness": "Fitness",
            "musculation": "Fitness",
            "cardio": "Fitness",
            "gym": "Fitness",
            "natation": "Natation",
            "swimming": "Natation",
            "pool": "Natation",
            "basket": "Basket",
            "basketball": "Basket",
            "football": "Football",
            "soccer": "Football",
            "futsal": "Futsal",
            "tennis": "Tennis",
            "ping pong": "Ping-Pong",
            "pingpong": "Ping-Pong",
            "table tennis": "Ping-Pong",
            "tennis de table": "Ping-Pong",
            "badminton": "Badminton",
            "volley": "Volley",
            "volleyball": "Volley",
            "handball": "Handball",
        }
        if key in aliases:
            return aliases[key]

        return s[:1].upper() + s[1:] if len(s) > 1 else s.upper()

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
                    normalized_activity = self._normalize_activity_name(sport)
                    if normalized_activity:
                        entities.setdefault("activity", []).append(normalized_activity)

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
        lang_key = self._normalize_lang_code(lang)
        parser_module = self.parsers.get(lang_key)
        parser = parser_module or self.fallback_parser

        try:
            parse_fn = cast(Callable[[str], Dict[str, Any]], getattr(parser_module, "traiter_requete", None))
            if callable(parse_fn):
                result = parse_fn(text_in)
            else:
                result = parser(text_in)
        except Exception as exc:
            print(f"[NLU] Erreur pendant parsing pour '{lang_key}': {exc}")
            result = self.fallback_parser(text_in)

        # Intent : mapper vers les noms utilisés par le DialogManager
        raw_intent = result.get("intent", "inconnu")
        intent = self._INTENT_MAP.get(raw_intent, raw_intent)
        confidence = result.get("confidence", 0.0)

        # Entities : normaliser les clés FR/EN vers l'API
        matcher_ents = result.get("entites") or result.get("entities") or {}
        entities = self._normalize_entities(matcher_ents)

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
    
    