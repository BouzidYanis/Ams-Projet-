"""
nlu_train.py
============
Pipeline NLU combinant :
    - TextCategorizer (models/nlu_model)  → intent
    - NER entraîné   (models/ner_model)   → entités SPORT / LIEU / DATE / HEURE / NOMBRE
    - Fallback regex                      → si les modèles ne sont pas encore entraînés

Les deux modèles sont chargés une seule fois au démarrage.
"""

import re
from pathlib import Path

import spacy
from spacy.tokens import Doc

from app.nlu_models.francais.continuous_learning import apply_entity_blocklist, apply_entity_hints

# ─────────────────────────────────────────────────────────────────
# Chemins des modèles
# ─────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
NLU_MODEL  = BASE_DIR / "models" / "nlu_model"
NER_MODEL  = BASE_DIR / "models" / "ner_model"

# ─────────────────────────────────────────────────────────────────
# Extensions Doc
# ─────────────────────────────────────────────────────────────────
if not Doc.has_extension("intent"):
    Doc.set_extension("intent", default=None)
if not Doc.has_extension("confidence"):
    Doc.set_extension("confidence", default=0.0)

# ─────────────────────────────────────────────────────────────────
# Chargement des modèles
# ─────────────────────────────────────────────────────────────────
def _load_spacy_model(path: Path, fallback_name: str | None = None):
    """Charge un modèle spaCy en évitant les crashs de lemmatizer/config.

    Si le modèle sérialisé est cassé ou si `fr_core_news_md` ne peut pas être
    initialisé (tables de lemmatisation manquantes), on retombe sur un pipeline
    français minimal qui suffit pour le matcher et le vocabulaire.
    """
    try:
        return spacy.load(path, exclude=["lemmatizer"]), True
    except Exception as exc:
        print(f"[NLU] ⚠ Chargement impossible de {path}: {exc}")

    if fallback_name:
        try:
            # Le parser a seulement besoin d'un vocab; le reste du pipeline est optionnel.
            return spacy.load(fallback_name, exclude=["lemmatizer"]), False
        except Exception as exc:
            print(f"[NLU] ⚠ Fallback {fallback_name} impossible: {exc}")

    return spacy.blank("fr"), False


_nlp_intent, _USE_INTENT_MODEL = _load_spacy_model(NLU_MODEL, "fr_core_news_md")
if _USE_INTENT_MODEL:
    print("[NLU] ✓ Modèle intent chargé")
else:
    print("[NLU] ⚠ Modèle intent absent → fallback regex")

_nlp_ner, _USE_NER_MODEL = _load_spacy_model(NER_MODEL, "fr_core_news_md")
if _USE_NER_MODEL:
    print("[NLU] ✓ Modèle NER chargé")
else:
    print("[NLU] ⚠ Modèle NER absent → fallback Matcher")

# ─────────────────────────────────────────────────────────────────
# Fallback regex (intent) — utilisé si NLU_MODEL absent
# ─────────────────────────────────────────────────────────────────
_INTENT_PATTERNS: dict[str, list[str]] = {
    "salutation":               [r"\b(bonjour|salut|hello|bonsoir|hey|coucou)\b"],
    "demander_heure":           [r"\b(horaire|heure|quand|ouvre|ferme|ouvert|planning)\b"],
    "demander_activite":        [r"\b(activité|sport|cours|séance|discipline|propose)\b"],
    "ask_pricing":              [r"\b(tarif|prix|coût|combien|abonnement|forfait)\b"],
    "demander_lieu":            [r"\b(où|situé|trouve|vestiaire|salle|accueil|toilette|casier)\b"],
    "reserver":                 [r"\b(réserver|réservation|inscrire|inscription|prendre.*cours)\b"],
    "qui":                      [r"\b(qui (es-tu|êtes-vous)|ton nom|présente-toi|robot|ia)\b"],
    "cancel_booking":           [r"\b(annuler|annulation|supprimer|résilier|désister|déprogrammer)\b"],
    "ask_available_slots":      [r"\b(créneaux?|disponible|disponibilité|libre|slots?)\b"],
    "demander_mes_reservations": [r"\b(mes.*réservations?|voir.*réservations?|j'ai.*réservé)\b"],
    "demander_horaire_activite_inscrite": [r"\b(mon cours|ma séance|activité inscrite|cours réservé|inscrit.*(à|au))\b.*\b(heure|horaire|quand)\b|\b(heure|horaire|quand)\b.*\b(mon cours|ma séance|activité inscrite|cours réservé|inscrit.*(à|au))\b"],
    "demander_evenements_speciaux": [r"\b(événement|événements|tournoi|tournois|compétition|spécial|spéciaux)\b.*\b(en cours|à venir|prochain|bientôt|cette semaine)\b|\b(y a-t-il|infos?|programme)\b.*\b(événement|tournoi|compétition)\b"],
}
_compiled_fallback = {
    intent: [re.compile(p, re.IGNORECASE) for p in patterns]
    for intent, patterns in _INTENT_PATTERNS.items()
}

def _classify_regex(text: str) -> tuple[str, float]:
    scores = {
        intent: sum(1 for p in patterns if p.search(text))
        for intent, patterns in _compiled_fallback.items()
    }
    best = max(scores, key=lambda intent: scores[intent])
    if scores[best] > 0:
        return best, round(scores[best] / len(_compiled_fallback[best]), 2)
    return "inconnu", 0.0


# ─────────────────────────────────────────────────────────────────
# Fallback Matcher spaCy (entités) — utilisé si NER_MODEL absent
# ─────────────────────────────────────────────────────────────────
from spacy.matcher import Matcher as _Matcher

_matcher = _Matcher(_nlp_intent.vocab)

_matcher.add("SPORT", [
    [{"LOWER": {"IN": ["natation", "nage", "aquagym"]}}],
    [{"LOWER": {"IN": ["tennis", "badminton", "squash", "ping-pong"]}}],
    [{"LOWER": {"IN": ["fitness", "musculation", "cardio", "gym"]}}],
    [{"LOWER": {"IN": ["yoga", "pilates", "stretching"]}}],
    [{"LOWER": {"IN": ["zumba", "danse", "aerobic"]}}],
    [{"LOWER": {"IN": ["football", "basket", "volley", "handball"]}}],
    [{"LOWER": {"IN": ["running", "jogging", "athlétisme"]}}],
])

_matcher.add("LIEU", [
    [{"LOWER": {"IN": ["vestiaire", "vestiaires", "casier", "casiers"]}}],
    [{"LOWER": {"IN": ["piscine", "bassin"]}}],
    [{"LOWER": {"IN": ["accueil", "réception", "entrée"]}}],
    [{"LOWER": {"IN": ["toilette", "toilettes", "wc"]}}],
    [{"LOWER": {"IN": ["secrétariat", "bureau"]}}],
    [{"LOWER": "salle"}, {"LOWER": {"IN": ["a", "b", "c", "d", "e", "f"]}}],
    [{"LOWER": "salle"}, {"LIKE_NUM": True}],
    [{"LOWER": "salle"}, {"LOWER": "de"}, {"LOWER": {"IN": ["sport", "natation", "fitness", "musculation"]}}],
    [{"LOWER": {"IN": ["salle", "terrain", "court"]}}],
])

_QUESTION_NUMBER_WORDS = {
    "combien",
    "quel",
    "quelle",
    "quels",
    "quelles",
}

_NUMBER_WORDS = {
    "zero", "zéro", "un", "une", "deux", "trois", "quatre", "cinq",
    "six", "sept", "huit", "neuf", "dix", "onze", "douze", "treize",
    "quatorze", "quinze", "seize", "vingt", "trente", "quarante",
    "cinquante", "soixante", "cent", "mille",
}


def _clean_nombres(values: list[str]) -> list[str]:
    """Garde uniquement les vrais nombres et retire les faux positifs."""
    cleaned: list[str] = []
    seen: set[str] = set()

    for raw in values:
        if not isinstance(raw, str):
            continue

        value = raw.strip()
        if not value:
            continue

        low = value.lower().strip(" ?!.,;:\"'()[]{}")
        if not low or low in _QUESTION_NUMBER_WORDS:
            continue

        is_numeric = bool(re.search(r"\d", low))
        is_number_word = low in _NUMBER_WORDS

        if not is_numeric and not is_number_word:
            continue

        if low in seen:
            continue
        seen.add(low)
        cleaned.append(value)

    return cleaned

def _extract_entities_matcher(doc) -> dict:
    """Extraction par Matcher (fallback)."""
    matches = _matcher(doc)
    sports, lieux = [], []

    filtered, last_end = [], -1
    for match_id, start, end in sorted(matches, key=lambda m: (m[1], -(m[2] - m[1]))):
        if start >= last_end:
            filtered.append((match_id, start, end))
            last_end = end

    for match_id, start, end in filtered:
        label = _nlp_intent.vocab.strings[match_id]
        text  = doc[start:end].text
        if label == "SPORT":
            sports.append(text)
        elif label == "LIEU":
            lieux.append(text)

    temps   = [ent.text for ent in doc.ents if ent.label_ in ("DATE", "TIME")]
    nombres = _clean_nombres([tok.text for tok in doc if tok.like_num])

    return {
        "sports":  list(set(sports)),
        "lieux":   list(set(lieux)),
        "temps":   temps,
        "nombres": nombres,
    }


# ─────────────────────────────────────────────────────────────────
# Extraction NER entraîné
# ─────────────────────────────────────────────────────────────────
def _extract_entities_ner(text: str) -> dict:
    """Extraction par le modèle NER entraîné."""
    doc = _nlp_ner(text)
    result: dict[str, list] = {
        "sports": [], "lieux": [], "temps": [], "nombres": []
    }
    label_map = {
        "SPORT":  "sports",
        "LIEU":   "lieux",
        "DATE":   "temps",
        "HEURE":  "temps",
        "NOMBRE": "nombres",
    }
    for ent in doc.ents:
        key = label_map.get(ent.label_)
        if key:
            result[key].append(ent.text)

    # Dédupliquer + nettoyer les nombres bruités
    dedup = {k: list(set(v)) for k, v in result.items()}
    dedup["nombres"] = _clean_nombres(dedup.get("nombres", []))
    return dedup


# ─────────────────────────────────────────────────────────────────
# Point d'entrée public
# ─────────────────────────────────────────────────────────────────
def traiter_requete(texte: str) -> dict:
    """
    Analyse le texte et retourne :
        {
            "intent":     str,
            "confidence": float,
            "entites": {
                "sports":  list[str],
                "lieux":   list[str],
                "temps":   list[str],
                "nombres": list[str],
            }
        }
    """
    text = (texte or "").strip()

    # ── Intent ───────────────────────────────────────────────────
    if _USE_INTENT_MODEL:
        doc    = _nlp_intent(text)
        intent = max(doc.cats, key=lambda label: doc.cats[label])
        conf   = round(doc.cats[intent], 2)
    else:
        intent, conf = _classify_regex(text.lower())
        doc = _nlp_intent(text)   # pour le Matcher fallback

    # ── Entités ───────────────────────────────────────────────────
    if _USE_NER_MODEL:
        entites = _extract_entities_ner(text)
    else:
        entites = _extract_entities_matcher(doc)

    entites = apply_entity_hints(text, entites)
    entites = apply_entity_blocklist(entites)

    return {
        "intent":     intent,
        "confidence": conf,
        "entites":    entites,
    }


# ─────────────────────────────────────────────────────────────────
# Tests si exécuté directement
# ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    tests = [
        "Bonjour !",
        "réserver un cours de natation demain à 9h",
        "yoga lundi matin en salle B",
        "annuler mon tennis samedi à 14h",
        "combien coûte l'abonnement fitness",
        "où sont les vestiaires",
        "créneaux disponibles pour le squash",
        "mes réservations de la semaine",
        "qui es-tu",
    ]

    print("=" * 65)
    print("  TEST NLU COMBINÉ (intent + NER)")
    print("=" * 65)

    for phrase in tests:
        r = traiter_requete(phrase)
        print(f"\n« {phrase} »")
        print(f"  intent   : {r['intent']}  ({r['confidence']:.0%})")
        for k, v in r["entites"].items():
            if v:
                print(f"  {k:<8} : {v}")