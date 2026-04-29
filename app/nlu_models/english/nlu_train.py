"""
English NLU pipeline: intent + entities + continuous-learning filters.
"""

import re
from pathlib import Path

import spacy
from spacy.matcher import Matcher

from app.nlu_models.english.continuous_learning import apply_entity_blocklist, apply_entity_hints

BASE_DIR = Path(__file__).parent
NLU_MODEL = BASE_DIR / "models" / "nlu_model_en"
NER_MODEL = BASE_DIR / "models" / "ner_model_en"


def _load_model(path: Path, fallback_names: tuple[str, ...], lang: str):
    # Try local model first, excluding lemmatizer to avoid [E912] errors
    try:
        return spacy.load(path, exclude=["lemmatizer"]), True
    except Exception:
        pass
    
    # Try fallback models, also with lemmatizer excluded
    for name in fallback_names:
        try:
            return spacy.load(name, exclude=["lemmatizer"]), False
        except Exception:
            continue
    
    # Last resort: blank pipeline
    return spacy.blank(lang), False


_nlp_intent, _use_intent_model = _load_model(
    NLU_MODEL, ("en_core_web_md", "en_core_web_sm"), "en"
)

_nlp_ner, _use_ner_model = _load_model(
    NER_MODEL, ("en_core_web_md", "en_core_web_sm"), "en"
)

_intent_patterns: dict[str, list[str]] = {
    "greeting": [r"\b(hello|hi|hey|good morning|good evening)\b"],
    "ask_hours": [r"\b(hours|open|close|schedule|when)\b"],
    "ask_activity": [r"\b(activity|activities|sports|class|classes|offer)\b"],
    "ask_pricing": [r"\b(price|pricing|cost|fee|membership|tariff)\b"],
    "ask_location": [r"\b(where|location|room|pool|locker|reception)\b"],
    "reserve": [r"\b(book|reserve|reservation|sign up)\b"],
    "who_are_you": [r"\b(who are you|your name|robot|assistant)\b"],
    "cancel_booking": [r"\b(cancel|remove|delete|drop)\b"],
    "ask_available_slots": [r"\b(slot|available|availability|free time)\b"],
    "ask_my_bookings": [r"\b(my bookings|my reservations|what did i book)\b"],
    "ask_registered_activity_schedule": [r"\b(my (class|session|booking|reserved activity)|i am registered|i booked)\b.*\b(when|what time|schedule|start)\b|\b(when|what time|schedule|start)\b.*\b(my (class|session|booking|reserved activity)|i am registered|i booked)\b"],
    "ask_special_events": [r"\b(special event|event|tournament|competition)\b.*\b(ongoing|in progress|upcoming|coming|next|this week|soon)\b|\b(info|details|schedule)\b.*\b(tournament|event|competition)\b"],
}
_compiled_fallback = {
    intent: [re.compile(p, re.IGNORECASE) for p in patterns]
    for intent, patterns in _intent_patterns.items()
}


def _classify_regex(text: str) -> tuple[str, float]:
    scores = {
        intent: sum(1 for p in patterns if p.search(text))
        for intent, patterns in _compiled_fallback.items()
    }
    best = max(scores.items(), key=lambda item: item[1])[0]
    if scores[best] > 0:
        return best, round(scores[best] / len(_compiled_fallback[best]), 2)
    return "unknown", 0.0


_matcher = Matcher(_nlp_intent.vocab)
_matcher.add("SPORT", [[{"LOWER": {"IN": ["swimming", "yoga", "fitness", "tennis", "pilates", "zumba", "badminton"]}}]])
_matcher.add("LOCATION", [
    [{"LOWER": {"IN": ["pool", "reception", "lockers", "room", "court", "hall"]}}],
    [{"LOWER": "room"}, {"LOWER": {"IN": ["a", "b", "c", "d"]}}],
])


_question_number_words = {"how", "many"}


def _clean_numbers(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in values:
        if not isinstance(raw, str):
            continue
        value = raw.strip()
        if not value:
            continue
        low = value.lower().strip(" ?!.,;:\"'()[]{}")
        if not low or low in _question_number_words:
            continue
        is_numeric = bool(re.search(r"\d", low))
        if not is_numeric:
            continue
        if low in seen:
            continue
        seen.add(low)
        cleaned.append(value)
    return cleaned


def _extract_entities_matcher(doc) -> dict:
    matches = _matcher(doc)
    sports, locations = [], []

    filtered, last_end = [], -1
    for match_id, start, end in sorted(matches, key=lambda m: (m[1], -(m[2] - m[1]))):
        if start >= last_end:
            filtered.append((match_id, start, end))
            last_end = end

    for match_id, start, end in filtered:
        label = _nlp_intent.vocab.strings[match_id]
        text = doc[start:end].text
        if label == "SPORT":
            sports.append(text)
        elif label == "LOCATION":
            locations.append(text)

    times = [ent.text for ent in doc.ents if ent.label_ in ("DATE", "TIME")]
    numbers = _clean_numbers([tok.text for tok in doc if tok.like_num])

    return {
        "sports": list(dict.fromkeys(sports)),
        "locations": list(dict.fromkeys(locations)),
        "times": list(dict.fromkeys(times)),
        "numbers": numbers,
    }


def _extract_entities_ner(text: str) -> dict:
    if _nlp_ner is None:
        return {"sports": [], "locations": [], "times": [], "numbers": []}

    doc = _nlp_ner(text)
    result: dict[str, list] = {"sports": [], "locations": [], "times": [], "numbers": []}
    label_map = {
        "SPORT": "sports",
        "LOCATION": "locations",
        "DATE": "times",
        "TIME": "times",
        "NUMBER": "numbers",
    }
    for ent in doc.ents:
        key = label_map.get(ent.label_)
        if key:
            result[key].append(ent.text)

    dedup = {k: list(dict.fromkeys(v)) for k, v in result.items()}
    dedup["numbers"] = _clean_numbers(dedup.get("numbers", []))
    return dedup


def traiter_requete(text: str) -> dict:
    text = (text or "").strip()

    if _use_intent_model:
        doc = _nlp_intent(text)
        intent = max(doc.cats.items(), key=lambda item: item[1])[0]
        conf = round(doc.cats[intent], 2)
    else:
        intent, conf = _classify_regex(text.lower())
        doc = _nlp_intent(text)

    if _use_ner_model:
        entities = _extract_entities_ner(text)
    else:
        entities = _extract_entities_matcher(doc)

    entities = apply_entity_hints(text, entities)
    entities = apply_entity_blocklist(entities)

    return {"intent": intent, "confidence": conf, "entites": entities}


if __name__ == "__main__":
    tests = [
        "hello",
        "book swimming tomorrow at 9am",
        "where are the lockers",
        "what is the price for yoga",
        "cancel my booking",
    ]

    for phrase in tests:
        r = traiter_requete(phrase)
        print(f"\n{phrase}")
        print(f"intent: {r['intent']} ({r['confidence']:.0%})")
        print(r["entites"])
