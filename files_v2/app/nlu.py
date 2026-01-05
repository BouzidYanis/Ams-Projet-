import os
from pathlib import Path
from typing import Dict, Any
import spacy


class NLU:
    # Default gazetteers (runtime fallback if entity_ruler is present but empty)
    _DEFAULT_ACTIVITIES = ["yoga", "fitness", "basket", "basketball", "tennis", "futsal", "natation"]
    _DEFAULT_LOCATIONS = ["salle", "salle de sport", "vestiaire", "terrain", "accueil", "secrétariat"]

    def __init__(
        self,
        intent_model_path: str | None = None,
        entity_model_path: str | None = None,
        threshold: float | None = None,
        debug: bool | None = None,
    ):
        base_dir = Path(__file__).resolve().parent

        intent_path = Path(intent_model_path) if intent_model_path else (base_dir / "intent_model")
        entity_path = Path(entity_model_path) if entity_model_path else (base_dir / "entity_model")

        # Allow override via env vars
        intent_path = Path(os.getenv("INTENT_MODEL_PATH", str(intent_path)))
        entity_path = Path(os.getenv("ENTITY_MODEL_PATH", str(entity_path)))

        thr_env = os.getenv("NLU_INTENT_THRESHOLD")
        self.threshold = threshold if threshold is not None else (float(thr_env) if thr_env else 0.4)

        dbg_env = os.getenv("NLU_DEBUG")
        self.debug = debug if debug is not None else (dbg_env == "1")

        self.intent_nlp = spacy.load(str(intent_path))
        self.entity_nlp = spacy.load(str(entity_path))

        self._ensure_entity_ruler_patterns()

    def _ensure_entity_ruler_patterns(self) -> None:
        if "entity_ruler" not in getattr(self.entity_nlp, "pipe_names", []):
            if self.debug:
                print("[NLU] entity_model has no entity_ruler pipe")
            return

        ruler = self.entity_nlp.get_pipe("entity_ruler")

        # Some saved models end up with an empty ruler; inject defaults.
        if getattr(ruler, "patterns", None) and len(ruler.patterns) > 0:
            if self.debug:
                print(f"[NLU] entity_ruler patterns loaded: {len(ruler.patterns)}")
            return

        patterns = []
        for a in self._DEFAULT_ACTIVITIES:
            patterns.append({"label": "ACTIVITY", "pattern": a})
        for l in self._DEFAULT_LOCATIONS:
            patterns.append({"label": "LOCATION", "pattern": l})

        ruler.add_patterns(patterns)

        if self.debug:
            print("[NLU] Injected default EntityRuler patterns:", len(ruler.patterns))
            print("[NLU] entity_model pipes:", self.entity_nlp.pipe_names)

    def parse(self, text: str) -> Dict[str, Any]:
        text_in = (text or "").strip()
        if not text_in:
            return {"intent": "unknown", "confidence": 0.0, "entities": {}, "raw_text": text}

        # Intent
        doc_intent = self.intent_nlp(text_in)
        intent = "unknown"
        confidence = 0.0

        if getattr(doc_intent, "cats", None):
            intent = max(doc_intent.cats, key=doc_intent.cats.get)
            confidence = float(doc_intent.cats.get(intent, 0.0))

        if confidence < self.threshold:
            intent = "unknown"

        # Entities
        doc_entities = self.entity_nlp(text_in)
        entities: Dict[str, list[str]] = {}

        for ent in doc_entities.ents:
            entities.setdefault(ent.label_.lower(), []).append(ent.text)

        return {
            "intent": intent,
            "confidence": round(confidence, 2),
            "entities": entities,
            "raw_text": text,
        }
