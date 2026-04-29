"""
Training dataset for spaCy TextCategorizer (English).
"""

INTENTS = [
    "greeting",
    "ask_hours",
    "ask_activity",
    "ask_pricing",
    "ask_location",
    "reserve",
    "who_are_you",
    "cancel_booking",
    "ask_available_slots",
    "ask_my_bookings",
    "ask_registered_activity_schedule",
    "ask_special_events",
    "unknown",
]


def cats(positive: str) -> dict:
    return {intent: 1.0 if intent == positive else 0.0 for intent in INTENTS}


TRAINING_DATA: list[tuple[str, dict]] = [
    ("hello", {"cats": cats("greeting")}),
    ("hi", {"cats": cats("greeting")}),
    ("good morning", {"cats": cats("greeting")}),
    ("good evening", {"cats": cats("greeting")}),
    ("hey there", {"cats": cats("greeting")}),
    ("hello, I need help", {"cats": cats("greeting")}),

    ("what are your opening hours", {"cats": cats("ask_hours")}),
    ("when does the center open", {"cats": cats("ask_hours")}),
    ("when do you close", {"cats": cats("ask_hours")}),
    ("pool schedule", {"cats": cats("ask_hours")}),
    ("are you open on sunday", {"cats": cats("ask_hours")}),
    ("what time is the first class", {"cats": cats("ask_hours")}),

    ("what activities do you offer", {"cats": cats("ask_activity")}),
    ("which sports are available", {"cats": cats("ask_activity")}),
    ("do you have yoga classes", {"cats": cats("ask_activity")}),
    ("what can I do here", {"cats": cats("ask_activity")}),
    ("do you offer swimming", {"cats": cats("ask_activity")}),
    ("available group classes", {"cats": cats("ask_activity")}),

    ("how much does it cost", {"cats": cats("ask_pricing")}),
    ("what is the price for yoga", {"cats": cats("ask_pricing")}),
    ("membership fees", {"cats": cats("ask_pricing")}),
    ("pricing for tennis", {"cats": cats("ask_pricing")}),
    ("how much is a single session", {"cats": cats("ask_pricing")}),
    ("student discount price", {"cats": cats("ask_pricing")}),

    ("where are the lockers", {"cats": cats("ask_location")}),
    ("where is the reception", {"cats": cats("ask_location")}),
    ("how do I get to the pool", {"cats": cats("ask_location")}),
    ("where is room B", {"cats": cats("ask_location")}),
    ("where are the changing rooms", {"cats": cats("ask_location")}),
    ("show me the way to yoga room", {"cats": cats("ask_location")}),

    ("I want to book a yoga class", {"cats": cats("reserve")}),
    ("book swimming for tomorrow", {"cats": cats("reserve")}),
    ("reserve room A", {"cats": cats("reserve")}),
    ("book a fitness session", {"cats": cats("reserve")}),
    ("I want to reserve for monday morning", {"cats": cats("reserve")}),
    ("book a slot tonight", {"cats": cats("reserve")}),

    ("who are you", {"cats": cats("who_are_you")}),
    ("what is your name", {"cats": cats("who_are_you")}),
    ("are you a robot", {"cats": cats("who_are_you")}),
    ("introduce yourself", {"cats": cats("who_are_you")}),
    ("what is your role", {"cats": cats("who_are_you")}),
    ("who am I talking to", {"cats": cats("who_are_you")}),

    ("cancel my booking", {"cats": cats("cancel_booking")}),
    ("I want to cancel my reservation", {"cats": cats("cancel_booking")}),
    ("remove my yoga booking", {"cats": cats("cancel_booking")}),
    ("cancel tomorrow class", {"cats": cats("cancel_booking")}),
    ("I cannot come, cancel it", {"cats": cats("cancel_booking")}),
    ("please cancel my slot", {"cats": cats("cancel_booking")}),

    ("what slots are available", {"cats": cats("ask_available_slots")}),
    ("any free time for yoga", {"cats": cats("ask_available_slots")}),
    ("show available slots for tennis", {"cats": cats("ask_available_slots")}),
    ("is there any place left tonight", {"cats": cats("ask_available_slots")}),
    ("free slots this week", {"cats": cats("ask_available_slots")}),
    ("availability on saturday morning", {"cats": cats("ask_available_slots")}),

    ("my bookings", {"cats": cats("ask_my_bookings")}),
    ("show my reservations", {"cats": cats("ask_my_bookings")}),
    ("what did I book", {"cats": cats("ask_my_bookings")}),
    ("list my upcoming classes", {"cats": cats("ask_my_bookings")}),
    ("check my booked sessions", {"cats": cats("ask_my_bookings")}),
    ("my active bookings", {"cats": cats("ask_my_bookings")}),

    ("what time is my yoga class", {"cats": cats("ask_registered_activity_schedule")}),
    ("when is my booked swimming session", {"cats": cats("ask_registered_activity_schedule")}),
    ("what is the schedule of the class I booked", {"cats": cats("ask_registered_activity_schedule")}),
    ("I am registered for pilates, what time does it start", {"cats": cats("ask_registered_activity_schedule")}),
    ("when does my reserved activity start", {"cats": cats("ask_registered_activity_schedule")}),
    ("what is the time of my booking", {"cats": cats("ask_registered_activity_schedule")}),
    ("when is my next reserved class", {"cats": cats("ask_registered_activity_schedule")}),
    ("schedule for my registered badminton class", {"cats": cats("ask_registered_activity_schedule")}),

    ("is there a tournament in progress", {"cats": cats("ask_special_events")}),
    ("what special events are coming soon", {"cats": cats("ask_special_events")}),
    ("I want info about the next tournament", {"cats": cats("ask_special_events")}),
    ("which event is coming up", {"cats": cats("ask_special_events")}),
    ("any competition this week", {"cats": cats("ask_special_events")}),
    ("special events schedule", {"cats": cats("ask_special_events")}),
    ("are there upcoming tournaments", {"cats": cats("ask_special_events")}),
    ("details about upcoming sport events", {"cats": cats("ask_special_events")}),

    ("what is the weather", {"cats": cats("unknown")}),
    ("tell me a joke", {"cats": cats("unknown")}),
    ("thanks", {"cats": cats("unknown")}),
    ("ok", {"cats": cats("unknown")}),
    ("write me a poem", {"cats": cats("unknown")}),
    ("what time is it in tokyo", {"cats": cats("unknown")}),
]
