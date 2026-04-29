"""
Review pending intent feedback for English pipeline.
"""

from app.test_model.english.continuous_learning import format_intents, pending_examples, validate_pending_item


def main() -> None:
    rows = pending_examples()
    if not rows:
        print("No pending feedback.")
        return

    print(f"{len(rows)} pending feedback item(s)")
    print(f"Available intents: {format_intents()}")

    idx = 0
    while idx < len(rows):
        item = rows[idx]
        text = item.get("text", "")
        pred = item.get("predicted_intent", "unknown")
        conf = float(item.get("confidence", 0.0))

        print("\n" + "-" * 72)
        print(f"[{idx}] phrase     : {text}")
        print(f"    prediction  : {pred} ({conf:.0%})")
        print("    actions     : [enter]=skip | keep | intent | del | quit")

        ans = input("    > ").strip()
        if ans == "":
            idx += 1
            continue

        low = ans.lower()
        if low in {"quit", "q", "exit"}:
            break

        if low == "del":
            validate_pending_item(idx, "unknown")
            rows.pop(idx)
            continue

        if low == "keep":
            validate_pending_item(idx, pred)
            rows.pop(idx)
            continue

        valid = validate_pending_item(idx, ans)
        if valid:
            rows.pop(idx)
        else:
            print("Invalid index or unknown intent.")
            idx += 1

    print("\nReview complete.")


if __name__ == "__main__":
    main()
