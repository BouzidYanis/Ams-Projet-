from typing import Dict, Any
import re
import os
import spacy


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
        "ask_available_slots": "ask_available_slots",
        "demander_mes_reservations": "ask_my_reservations",
        "inconnu": "unknown",
    }

    def __init__(self, **kwargs):
        # Chargement paresseux de modèles spaCy par langue.
        # Si aucun modèle disque n'est trouvé pour la langue, on retombe
        # sur le parser rule-based `matcher_parse` défini dans `app.nlu_train`.
        self.models = {}  # lang -> nlp
        # dossier racine pour les modèles locaux
        self.models_root = kwargs.get("models_root") or os.path.join(os.path.dirname(__file__), "nlu_models")
        # mapping simple langue code -> dossier (tel qu'organisé dans repo)
        self.lang_to_folder = {"fr": "francais", "en": "english"}

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

    def _find_spacy_model_path(self, lang: str) -> dict[str, str | None]:
        """Retourne les chemins vers `nlu_model` et `ner_model` lorsqu'ils existent.

        Renvoie un dict: {"nlu": path_or_None, "ner": path_or_None}
        """
        folder = self.lang_to_folder.get(lang, lang)
        base = os.path.join(self.models_root, folder)
        models_dir = os.path.join(base, "models")

        nlu_path = None
        ner_path = None

        # Cas classique : chaque langue contient un dossier `models/<model_name>/...`
        if os.path.isdir(models_dir):
            for name in os.listdir(models_dir):
                candidate = os.path.join(models_dir, name)
                if os.path.isdir(candidate) and os.path.exists(os.path.join(candidate, "meta.json")):
                    # Chercher si le nom du dossier indique son type
                    lname = name.lower()
                    if "nlu" in lname:
                        nlu_path = candidate
                    elif "ner" in lname:
                        ner_path = candidate
                    else:
                        # Si on n'a encore rien, utilitaire fallback
                        if not nlu_path:
                            nlu_path = candidate
                        elif not ner_path:
                            ner_path = candidate

        # Cas où le répertoire `models` est lui-même un modèle spaCy (export)
        if os.path.exists(os.path.join(models_dir, "meta.json")):
            # Utiliser comme nlu par défaut si absent
            if not nlu_path:
                nlu_path = models_dir

        # Rechercher dossiers spécifiques `nlu_model` / `ner_model` (structure fournie)
        nlu_dir_candidate = os.path.join(base, "nlu_model")
        ner_dir_candidate = os.path.join(base, "ner_model")
        if os.path.isdir(nlu_dir_candidate):
            # Peut contenir un sous-dossier `models` ou être lui-même un modèle
            if os.path.isdir(os.path.join(nlu_dir_candidate, "models")):
                # prendre premier modèle à l'intérieur
                for name in os.listdir(os.path.join(nlu_dir_candidate, "models")):
                    cand = os.path.join(nlu_dir_candidate, "models", name)
                    if os.path.isdir(cand) and os.path.exists(os.path.join(cand, "meta.json")):
                        nlu_path = cand
                        break
            elif os.path.exists(os.path.join(nlu_dir_candidate, "meta.json")):
                nlu_path = nlu_dir_candidate

        if os.path.isdir(ner_dir_candidate):
            if os.path.isdir(os.path.join(ner_dir_candidate, "models")):
                for name in os.listdir(os.path.join(ner_dir_candidate, "models")):
                    cand = os.path.join(ner_dir_candidate, "models", name)
                    if os.path.isdir(cand) and os.path.exists(os.path.join(cand, "meta.json")):
                        ner_path = cand
                        break
            elif os.path.exists(os.path.join(ner_dir_candidate, "meta.json")):
                ner_path = ner_dir_candidate

        return {"nlu": nlu_path, "ner": ner_path}

    def _load_model_for_lang(self, lang: str, model_type: str = "nlu"):
        """Charge et met en cache un modèle spaCy pour la langue et le type demandés.

        model_type: 'nlu' ou 'ner'
        Retourne None si indisponible.
        """
        assert model_type in ("nlu", "ner")

        cache = self.models.setdefault(lang, {})
        if model_type in cache and cache[model_type] is not None:
            return cache[model_type]

        paths = self._find_spacy_model_path(lang)
        path = paths.get(model_type)
        if not path:
            cache[model_type] = None
            return None

        try:
            nlp = spacy.load(path)
            cache[model_type] = nlp
            print(f"[NLU] Modèle spaCy chargé pour '{lang}' ({model_type}): {path}")
            return nlp
        except Exception as e:
            print(f"[NLU] Erreur chargement modèle spaCy pour '{lang}' ({model_type}): {e}")
            cache[model_type] = None
            return None

    def parse(self, text: str, lang: str = "fr") -> Dict[str, Any]:
        text_in = (text or "").strip()
        if not text_in:
            return {"intent": "unknown", "confidence": 0.0, "entities": {}, "raw_text": text}
        # Tenter d'utiliser les modèles spaCy pour la langue demandée
        nlu_nlp = self._load_model_for_lang(lang, "nlu")
        ner_nlp = self._load_model_for_lang(lang, "ner")

        if nlu_nlp or ner_nlp:
            try:
                raw_intent = None
                confidence = 0.0
                ent_sports = []
                ent_lieux = []
                ent_temps = []
                ent_nombres = []

                doc_nlu = None

                # Si on a un modèle NLU dédié, l'utiliser pour l'intent
                if nlu_nlp:
                    doc_nlu = nlu_nlp(text_in)
                    raw_intent = getattr(doc_nlu._, "intent", None)
                    confidence = getattr(doc_nlu._, "confidence", 0.0)
                    # certains modèles NLU exposent aussi des entités
                    for ent in doc_nlu.ents:
                        lab = ent.label_.upper()
                        if lab in ("ACTIVITY", "SPORT"):
                            ent_sports.append(ent.text)
                        elif lab in ("LOCATION", "LIEU"):
                            ent_lieux.append(ent.text)
                        elif lab in ("DATE", "TIME"):
                            ent_temps.append(ent.text)

                # Utiliser le modèle NER dédié si disponible pour extraire des entités plus précises
                if ner_nlp:
                    doc_ner = ner_nlp(text_in)
                    for ent in doc_ner.ents:
                        lab = ent.label_.upper()
                        if lab in ("ACTIVITY", "SPORT"):
                            ent_sports.append(ent.text)
                        elif lab in ("LOCATION", "LIEU"):
                            ent_lieux.append(ent.text)
                        elif lab in ("DATE", "TIME"):
                            ent_temps.append(ent.text)
                    # nombres via tokens
                    ent_nombres = [token.text for token in doc_ner if token.like_num]
                else:
                    # fallback nombres si pas de ner model
                    if doc_nlu is not None:
                        ent_nombres = [token.text for token in doc_nlu if token.like_num]

                # Si aucun intent détecté via modèle NLU -> fallback rule-based
                if not raw_intent:
                    result = matcher_parse(text_in)
                else:
                    result = {
                        "intent": raw_intent or "inconnu",
                        "confidence": float(confidence or 0.0),
                        "entites": {
                            "sports": list(dict.fromkeys(ent_sports)),
                            "lieux": list(dict.fromkeys(ent_lieux)),
                            "temps": ent_temps,
                            "nombres": ent_nombres,
                        },
                    }

            except Exception as e:
                print(f"[NLU] Erreur pendant parsing spaCy (fallback): {e}")
                result = matcher_parse(text_in)
        else:
            # Pas de modèle dispo -> fallback rule-based
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

    def parse_intents_confidences(self, text: str, lang: str = "fr") -> Dict[str, float]:
        """Retourne les scores de toutes les intents (ici un seul gagnant)."""
        result = self.parse(text, lang)
        intent = result["intent"]
        conf = result["confidence"]
        all_intents = {v: 0.0 for v in self._INTENT_MAP.values()}
        all_intents[intent] = conf
        return all_intents
    
    