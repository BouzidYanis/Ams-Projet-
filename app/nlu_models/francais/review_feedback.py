"""
Revision manuelle des feedbacks pending.

Usage:
    python review_feedback.py
"""

from app.nlu_models.francais.continuous_learning import (
    format_intents,
    pending_examples,
    validate_pending_item,
)


def main() -> None:
    rows = pending_examples()
    if not rows:
        print("Aucun feedback pending.")
        return

    print(f"{len(rows)} feedback(s) pending a reviser")
    print(f"Intents disponibles: {format_intents()}")

    idx = 0
    while idx < len(rows):
        item = rows[idx]
        text = item.get("text", "")
        pred = item.get("predicted_intent", "inconnu")
        conf = float(item.get("confidence", 0.0))

        print("\n" + "-" * 72)
        print(f"[{idx}] phrase    : {text}")
        print(f"    prediction : {pred} ({conf:.0%})")
        print("    actions    : [enter]=skip | keep | intent | del | quit")

        ans = input("    > ").strip()

        if ans == "":
            idx += 1
            continue

        low = ans.lower()
        if low in {"quit", "q", "exit"}:
            break

        if low == "del":
            # Supprime en validant avec intent 'inconnu' pour garder une trace exploitable.
            validate_pending_item(idx, "inconnu")
            rows.pop(idx)
            continue

        if low == "keep":
            validate_pending_item(idx, pred)
            rows.pop(idx)
            continue

        # Sinon, on interprete la saisie comme intent corrige.
        valid = validate_pending_item(idx, ans)
        if valid:
            rows.pop(idx)
        else:
            print("Index invalide ou intent inconnu.")
            idx += 1

    print("\nRevision terminee.")


if __name__ == "__main__":
    main()
