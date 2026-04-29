"""
Training dataset for English NER.
Labels: SPORT, LOCATION, DATE, TIME, NUMBER.
"""

ENTITY_LABELS = ["SPORT", "LOCATION", "DATE", "TIME", "NUMBER"]


def e(text: str, span: str, label: str) -> tuple[int, int, str]:
    start = text.index(span)
    return (start, start + len(span), label)


def entities(*items) -> dict:
    return {"entities": list(items)}


def build_training_data() -> list[tuple[str, dict]]:
    data: list[tuple[str, dict]] = []

    samples = [
        (
            "book a swimming class tomorrow at 9am",
            [e("book a swimming class tomorrow at 9am", "swimming", "SPORT"),
             e("book a swimming class tomorrow at 9am", "tomorrow", "DATE"),
             e("book a swimming class tomorrow at 9am", "9am", "TIME")],
        ),
        (
            "yoga on monday morning in room B",
            [e("yoga on monday morning in room B", "yoga", "SPORT"),
             e("yoga on monday morning in room B", "monday", "DATE"),
             e("yoga on monday morning in room B", "morning", "TIME"),
             e("yoga on monday morning in room B", "room B", "LOCATION")],
        ),
        (
            "reserve room A for tomorrow",
            [e("reserve room A for tomorrow", "room A", "LOCATION"),
             e("reserve room A for tomorrow", "tomorrow", "DATE")],
        ),
        (
            "cancel my tennis booking on saturday at 2pm",
            [e("cancel my tennis booking on saturday at 2pm", "tennis", "SPORT"),
             e("cancel my tennis booking on saturday at 2pm", "saturday", "DATE"),
             e("cancel my tennis booking on saturday at 2pm", "2pm", "TIME")],
        ),
        (
            "where are the lockers",
            [e("where are the lockers", "lockers", "LOCATION")],
        ),
        (
            "fitness class for 2 people",
            [e("fitness class for 2 people", "fitness", "SPORT"),
             e("fitness class for 2 people", "2", "NUMBER")],
        ),
        (
            "book 3 slots for pilates tonight",
            [e("book 3 slots for pilates tonight", "3", "NUMBER"),
             e("book 3 slots for pilates tonight", "pilates", "SPORT"),
             e("book 3 slots for pilates tonight", "tonight", "DATE")],
        ),
        (
            "show me the way to the pool",
            [e("show me the way to the pool", "pool", "LOCATION")],
        ),
        (
            "is badminton available this weekend",
            [e("is badminton available this weekend", "badminton", "SPORT"),
             e("is badminton available this weekend", "this weekend", "DATE")],
        ),
        (
            "zumba class at 6:30pm",
            [e("zumba class at 6:30pm", "zumba", "SPORT"),
             e("zumba class at 6:30pm", "6:30pm", "TIME")],
        ),
    ]

    for text, ents in samples:
        data.append((text, entities(*ents)))

    return data


NER_TRAINING_DATA = build_training_data()
