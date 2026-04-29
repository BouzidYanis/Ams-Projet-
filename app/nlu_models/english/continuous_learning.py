"""
Continuous learning loop for English NLU + NER.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.nlu_models.english.training_data import INTENTS

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
PENDING_FILE = DATA_DIR / "feedback_pending.jsonl"
VALIDATED_FILE = DATA_DIR / "feedback_validated.jsonl"
ENTITY_BLOCKLIST_FILE = DATA_DIR / "entity_blocklist.json"
ENTITY_HINTS_FILE = DATA_DIR / "entity_hints.json"

ENTITY_KEYS = ("sports", "locations", "times", "numbers")


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_jsonl(path: Path, item: dict) -> None:
    _ensure_data_dir()
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def overwrite_jsonl(path: Path, rows: list[dict]) -> None:
    _ensure_data_dir()
    with path.open("w", encoding="utf-8") as f:
        for item in rows:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def log_interaction(
    text: str,
    predicted_intent: str,
    confidence: float,
    top_intents: list[tuple[str, float]],
    entities: Optional[dict] = None,
    corrected_intent: Optional[str] = None,
    source: str = "interactive",
) -> None:
    item = {
        "timestamp": _utc_now_iso(),
        "source": source,
        "text": text.strip(),
        "predicted_intent": predicted_intent,
        "confidence": round(float(confidence), 4),
        "top_intents": [
            {"intent": intent, "score": round(float(score), 4)}
            for intent, score in top_intents
        ],
        "entities": entities or {},
        "corrected_intent": corrected_intent,
    }

    if corrected_intent is None:
        _append_jsonl(PENDING_FILE, item)
    else:
        if corrected_intent not in INTENTS:
            raise ValueError(f"Invalid intent: {corrected_intent}")
        _append_jsonl(VALIDATED_FILE, item)


def pending_count() -> int:
    return len(read_jsonl(PENDING_FILE))


def validated_count() -> int:
    return len(read_jsonl(VALIDATED_FILE))


def pending_examples() -> list[dict]:
    return read_jsonl(PENDING_FILE)


def validated_examples() -> list[dict]:
    return read_jsonl(VALIDATED_FILE)


def validate_pending_item(index: int, corrected_intent: str) -> bool:
    if corrected_intent not in INTENTS:
        raise ValueError(f"Invalid intent: {corrected_intent}")

    rows = read_jsonl(PENDING_FILE)
    if index < 0 or index >= len(rows):
        return False

    item = rows.pop(index)
    item["corrected_intent"] = corrected_intent
    item["validated_at"] = _utc_now_iso()

    overwrite_jsonl(PENDING_FILE, rows)
    _append_jsonl(VALIDATED_FILE, item)
    return True


def validated_to_training_data() -> list[tuple[str, dict]]:
    rows = validated_examples()
    data: list[tuple[str, dict]] = []

    for row in rows:
        text = (row.get("text") or "").strip()
        intent = row.get("corrected_intent")
        if not text or intent not in INTENTS:
            continue

        cats = {k: 1.0 if k == intent else 0.0 for k in INTENTS}
        data.append((text, {"cats": cats}))

    return data


def is_valid_intent(intent: str) -> bool:
    return intent in INTENTS


def format_intents() -> str:
    return ", ".join(INTENTS)


def _default_entity_blocklist() -> dict[str, list[str]]:
    return {k: [] for k in ENTITY_KEYS}


def load_entity_blocklist() -> dict[str, list[str]]:
    _ensure_data_dir()
    if not ENTITY_BLOCKLIST_FILE.exists():
        data = _default_entity_blocklist()
        save_entity_blocklist(data)
        return data

    try:
        with ENTITY_BLOCKLIST_FILE.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError):
        raw = {}

    data = _default_entity_blocklist()
    for key in ENTITY_KEYS:
        values = raw.get(key, [])
        if isinstance(values, list):
            seen: set[str] = set()
            clean_values: list[str] = []
            for value in values:
                if not isinstance(value, str):
                    continue
                v = value.strip()
                if not v:
                    continue
                low = v.lower()
                if low in seen:
                    continue
                seen.add(low)
                clean_values.append(v)
            data[key] = clean_values

    save_entity_blocklist(data)
    return data


def save_entity_blocklist(data: dict[str, list[str]]) -> None:
    _ensure_data_dir()
    payload = {k: data.get(k, []) for k in ENTITY_KEYS}
    with ENTITY_BLOCKLIST_FILE.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def add_blocked_entity(entity_key: str, value: str) -> bool:
    key = (entity_key or "").strip()
    val = (value or "").strip()
    if key not in ENTITY_KEYS or not val:
        return False

    data = load_entity_blocklist()
    existing = {x.lower() for x in data[key]}
    if val.lower() in existing:
        return False

    data[key].append(val)
    save_entity_blocklist(data)
    return True


def apply_entity_blocklist(entities: dict) -> dict:
    data = load_entity_blocklist()
    cleaned: dict[str, list] = {}

    for key, values in entities.items():
        if key not in ENTITY_KEYS:
            cleaned[key] = values
            continue

        blocked = {x.lower() for x in data.get(key, [])}
        result_values: list = []
        for value in values or []:
            if not isinstance(value, str):
                continue
            v = value.strip()
            if not v:
                continue
            if v.lower() in blocked:
                continue
            result_values.append(v)

        seen: set[str] = set()
        unique_values: list[str] = []
        for v in result_values:
            low = v.lower()
            if low in seen:
                continue
            seen.add(low)
            unique_values.append(v)

        cleaned[key] = unique_values

    return cleaned


def entity_blocklist_count() -> int:
    data = load_entity_blocklist()
    return sum(len(v) for v in data.values())


def _default_entity_hints() -> dict[str, list[str]]:
    return {k: [] for k in ENTITY_KEYS}


def load_entity_hints() -> dict[str, list[str]]:
    _ensure_data_dir()
    if not ENTITY_HINTS_FILE.exists():
        data = _default_entity_hints()
        save_entity_hints(data)
        return data

    try:
        with ENTITY_HINTS_FILE.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError):
        raw = {}

    data = _default_entity_hints()
    for key in ENTITY_KEYS:
        values = raw.get(key, [])
        if isinstance(values, list):
            seen: set[str] = set()
            clean_values: list[str] = []
            for value in values:
                if not isinstance(value, str):
                    continue
                v = value.strip()
                if not v:
                    continue
                low = v.lower()
                if low in seen:
                    continue
                seen.add(low)
                clean_values.append(v)
            data[key] = clean_values

    save_entity_hints(data)
    return data


def save_entity_hints(data: dict[str, list[str]]) -> None:
    _ensure_data_dir()
    payload = {k: data.get(k, []) for k in ENTITY_KEYS}
    with ENTITY_HINTS_FILE.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def add_entity_hint(entity_key: str, value: str) -> bool:
    key = (entity_key or "").strip()
    val = (value or "").strip()
    if key not in ENTITY_KEYS or not val:
        return False

    data = load_entity_hints()
    existing = {x.lower() for x in data[key]}
    if val.lower() in existing:
        return False

    data[key].append(val)
    save_entity_hints(data)
    return True


def apply_entity_hints(text: str, entities: dict) -> dict:
    hints = load_entity_hints()
    text_low = (text or "").lower()

    merged: dict[str, list] = {}
    for key in ENTITY_KEYS:
        base_vals = entities.get(key, []) or []
        base_clean = [v for v in base_vals if isinstance(v, str) and v.strip()]

        seen = {v.lower() for v in base_clean}
        out = list(base_clean)

        for hint in hints.get(key, []):
            h = hint.strip()
            if not h:
                continue
            if h.lower() in text_low and h.lower() not in seen:
                out.append(h)
                seen.add(h.lower())

        merged[key] = out

    for key, values in entities.items():
        if key not in merged:
            merged[key] = values

    return merged


def entity_hints_count() -> int:
    data = load_entity_hints()
    return sum(len(v) for v in data.values())


def _find_case_insensitive_span(text: str, value: str) -> tuple[int, int] | None:
    pattern = re.compile(re.escape(value), re.IGNORECASE)
    match = pattern.search(text)
    if not match:
        return None
    return match.start(), match.end()


def validated_to_ner_training_data() -> list[tuple[str, dict]]:
    rows = validated_examples()
    label_map = {
        "sports": "SPORT",
        "locations": "LOCATION",
        "times": "DATE",
        "numbers": "NUMBER",
    }

    dataset: list[tuple[str, dict]] = []
    seen_rows: set[str] = set()

    for row in rows:
        text = (row.get("text") or "").strip()
        entities = row.get("entities") or {}
        if not text or not isinstance(entities, dict):
            continue

        spans: list[tuple[int, int, str]] = []
        occupied: list[tuple[int, int]] = []

        for key, label in label_map.items():
            values = entities.get(key, [])
            if not isinstance(values, list):
                continue

            for value in values:
                if not isinstance(value, str):
                    continue
                v = value.strip()
                if not v:
                    continue

                found = _find_case_insensitive_span(text, v)
                if not found:
                    continue
                start, end = found

                overlaps = any(not (end <= s or start >= e) for s, e in occupied)
                if overlaps:
                    continue

                spans.append((start, end, label))
                occupied.append((start, end))

        if not spans:
            continue

        row_key = json.dumps([text, sorted(spans)], ensure_ascii=False)
        if row_key in seen_rows:
            continue
        seen_rows.add(row_key)

        dataset.append((text, {"entities": sorted(spans, key=lambda x: (x[0], x[1]))}))

    return dataset
