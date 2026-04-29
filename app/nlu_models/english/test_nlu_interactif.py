"""
Interactive test for English NLU pipeline.
"""

import spacy

from app.test_model.english.continuous_learning import (
    add_blocked_entity,
    add_entity_hint,
    entity_blocklist_count,
    entity_hints_count,
    format_intents,
    is_valid_intent,
    log_interaction,
    pending_count,
    validated_count,
)
from app.test_model.english.nlu_train import traiter_requete


try:
    _INTENT_MODEL = spacy.load("models/nlu_model_en")
except OSError:
    _INTENT_MODEL = None


def _top_intents(phrase: str, top_k: int = 3) -> list[tuple[str, float]]:
    if _INTENT_MODEL is None:
        return []
    doc = _INTENT_MODEL(phrase)
    ordered = sorted(doc.cats.items(), key=lambda x: x[1], reverse=True)
    return [(intent, float(score)) for intent, score in ordered[:top_k]]


def show_result(phrase: str, result: dict) -> None:
    print("\n" + "-" * 60)
    print(f"Phrase      : {phrase}")
    print(f"Intent      : {result['intent']}")
    print(f"Confidence  : {result['confidence']:.0%}")
    print("Entities:")

    entities = result.get("entites", {})
    has_values = False
    for key, values in entities.items():
        if values:
            has_values = True
            print(f"  - {key}: {values}")
    if not has_values:
        print("  (none)")


def ask_intent_feedback(phrase: str, intent: str, confidence: float, entities: dict) -> None:
    top3 = _top_intents(phrase, top_k=3)
    if top3:
        print("Top intents  : " + " | ".join(f"{i}:{s:.0%}" for i, s in top3))

    answer = input("Prediction correct? (y/n/s) ").strip().lower()

    if answer in {"y", "yes"}:
        log_interaction(phrase, intent, confidence, top3, entities=entities, corrected_intent=intent)
        print("Feedback     : validated and added")
        return

    if answer in {"n", "no"}:
        print(f"Available intents: {format_intents()}")
        correction = input("Correct intent: ").strip()
        if not is_valid_intent(correction):
            log_interaction(phrase, intent, confidence, top3, entities=entities, corrected_intent=None)
            print("Invalid intent -> saved to pending")
            return

        log_interaction(phrase, intent, confidence, top3, entities=entities, corrected_intent=correction)
        print("Feedback     : corrected and added")
        return

    log_interaction(phrase, intent, confidence, top3, entities=entities, corrected_intent=None)
    print("Feedback     : saved to pending")


def ask_entity_feedback(result: dict) -> None:
    entities = result.get("entites", {})
    values = []
    for key, vals in entities.items():
        for value in vals or []:
            values.append((key, value))

    if not values:
        return

    answer = input("Entities correct? (y/n) ").strip().lower()
    if answer not in {"n", "no"}:
        return

    action = input("Action: block false positive (b) or add missing (a)? ").strip().lower()

    if action in {"a", "add"}:
        print("Entity types: sports, locations, times, numbers")
        key = input("Entity type: ").strip().lower()
        value = input("Missing value: ").strip()
        if add_entity_hint(key, value):
            print(f"Entity hint added: {key} = {value}")
        else:
            print("Could not add hint (invalid/empty/already exists).")
        return

    print("Detected entities:")
    for idx, (key, value) in enumerate(values, start=1):
        print(f"  {idx}. {key} = {value}")

    choice = input("Number to block (or empty to cancel): ").strip()
    if not choice or not choice.isdigit():
        return

    index = int(choice) - 1
    if index < 0 or index >= len(values):
        print("Out of range.")
        return

    key, value = values[index]
    if add_blocked_entity(key, value):
        print(f"Entity blocked: {key} = {value}")
    else:
        print("Entity already blocked or invalid.")


def main() -> None:
    print("=" * 60)
    print("Interactive English NLU test")
    print("Exit commands: quit, exit, q")
    print(f"Validated feedback: {validated_count()} | pending: {pending_count()}")
    print(f"Blocked entities : {entity_blocklist_count()}")
    print(f"Entity hints     : {entity_hints_count()}")
    print("=" * 60)

    while True:
        try:
            phrase = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if not phrase:
            continue

        if phrase.lower() in {"quit", "exit", "q"}:
            print("Bye.")
            break

        result = traiter_requete(phrase)
        show_result(phrase, result)
        ask_intent_feedback(phrase, result["intent"], float(result["confidence"]), result.get("entites", {}))
        ask_entity_feedback(result)


if __name__ == "__main__":
    main()
