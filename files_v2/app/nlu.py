import json
import os
from typing import Dict, Any
import re

# Optional: spaCy usage placeholder (commented). Install spaCy models separately if you want ML parsing.
# import spacy
# nlp_fr = spacy.load("fr_core_news_sm")
# nlp_en = spacy.load("en_core_web_sm")

INTENTS_FILE = os.path.join(os.path.dirname(__file__), "..", "configs", "intents.json")

class NLU:
    def __init__(self):
        with open(INTENTS_FILE, "r", encoding="utf-8") as f:
            self.intents = json.load(f)
        # build simple keyword index
        self.keyword_map = []
        for intent_name, spec in self.intents.items():
            kws = spec.get("keywords", [])
            self.keyword_map.append((intent_name, kws, spec))

    def parse(self, text: str, lang: str = "fr") -> Dict[str, Any]:
        text_low = text.lower()
        # simple rule-based match by keywords
        best_intent = "unknown"
        best_score = 0.0
        entities = {}

        for intent_name, keywords, spec in self.keyword_map:
            score = 0
            for kw in keywords:
                if kw in text_low:
                    score += 1
            # also check regex entities
            if score > best_score:
                best_intent = intent_name
                best_score = float(score) / max(1, len(keywords))

        # extract simple entities (time, date, activity, location)
        # time regex (HH:MM or matin/après-midi)
        time_match = re.search(r"((?:[01]?\d|2[0-3])[:h][0-5]\d)|matin|après-?midi|soir", text_low)
        if time_match:
            entities["time"] = time_match.group(0)
        # activity
        for act in ["fitness", "basket", "natation", "tennis", "futsal", "yoga"]:
            if act in text_low:
                entities.setdefault("activity", act)
                break
        # location (vestiaire, bureau, terrain, salle)
        for loc in ["vestiaire", "vestiaires", "bureau", "terrain", "salle", "accueil", "secrétariat"]:
            if loc in text_low:
                entities.setdefault("location", loc)
                break

        # confidence basic heuristic
        confidence = best_score if best_score > 0 else 0.0

        return {"intent": best_intent, "confidence": confidence, "entities": entities}