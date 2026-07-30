from __future__ import annotations

_CHECKBOX_OBJECTIVES: dict[str, str] = {
    "right_person": "confirm you are speaking with the property owner",
    "property_confirmed": "confirm which property they are calling about",
    "occupancy": "learn if the property is occupied rented or vacant",
    "condition": "learn what repairs or issues the property has",
    "timeline": "learn how soon they are looking to make a move",
    "motivation": "learn what is making them consider selling",
    "next_step": "set a walkthrough or confirm the next contact",
}

_PHASE_OBJECTIVES: dict[str, str] = {
    "VERIFY": "confirm ownership and open the conversation",
    "LIGHT_DISCOVERY": "learn the situation with one natural question",
    "QUALIFY": "ask if they would be open to a quick walkthrough",
    "NEXT_STEP": "book the walkthrough or confirm callback time",
    "WRAP": "confirm next steps and end warmly",
}


def get_objective(missing_box: str, phase: str | None = None) -> str:
    if missing_box in _CHECKBOX_OBJECTIVES:
        return _CHECKBOX_OBJECTIVES[missing_box]
    if phase and phase in _PHASE_OBJECTIVES:
        return _PHASE_OBJECTIVES[phase]
    return "understand their situation with one natural question"
