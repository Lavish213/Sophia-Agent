from __future__ import annotations

from xml.sax.saxutils import escape

from loguru import logger

from backend.lib.config import get_settings

MACHINE_ANSWERS = {
    "machine_start",
    "machine_end_beep",
    "machine_end_silence",
    "machine_end_other",
}

READY_FOR_MESSAGE = {"machine_end_beep", "machine_end_silence", "machine_end_other"}

_UNUSABLE_ANSWERS = {"fax", "unknown"}


def is_machine(answered_by: str | None) -> bool:
    return (answered_by or "").strip().lower() in MACHINE_ANSWERS


def is_human(answered_by: str | None) -> bool:
    return (answered_by or "").strip().lower() in {"human", ""}


def should_leave_voicemail(answered_by: str | None) -> bool:
    return (answered_by or "").strip().lower() in READY_FOR_MESSAGE


def is_unusable(answered_by: str | None) -> bool:
    return (answered_by or "").strip().lower() in _UNUSABLE_ANSWERS


def _spoken_phone(phone: str) -> str:
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        return phone
    return f"{' '.join(digits[:3])}, {' '.join(digits[3:6])}, {' '.join(digits[6:])}"


def build_voicemail_script(lead: dict | None, attempt_number: int = 1) -> str:
    settings = get_settings()
    callback = _spoken_phone(settings.agent_phone or settings.signalwire_phone or "")
    first_name = ""
    if lead:
        owner_name = (lead.get("properties") or {}).get("owner_name") or ""
        first_name = owner_name.split(" ")[0] if owner_name else ""

    greeting = f"Hi {first_name}," if first_name else "Hi there,"

    if attempt_number >= 3:
        return (
            f"{greeting} it's {settings.agent_name} with {settings.business_name} again. "
            "I won't keep bugging you. If you ever want to talk about your property, "
            f"give me a call back at {callback}. Otherwise I'll leave you be. Take care."
        )

    if attempt_number == 2:
        return (
            f"{greeting} it's {settings.agent_name} with {settings.business_name}, "
            "just following up on my last message about your property. "
            f"If you're open to hearing what we could offer, call or text me at {callback}. "
            "Thanks."
        )

    return (
        f"{greeting} this is {settings.agent_name} with {settings.business_name}. "
        "We buy houses here in San Joaquin County, and I was reaching out to see if you'd "
        "ever consider an offer on your property. No pressure at all, and no obligation. "
        f"If you want to talk it through, call or text me at {callback}. "
        "Thanks, and have a good one."
    )


def build_voicemail_laml(script: str) -> str:
    settings = get_settings()
    voice_attr = f' voice="{escape(settings.voicemail_voice)}"' if settings.voicemail_voice else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f"<Response><Say{voice_attr}>{escape(script)}</Say><Hangup/></Response>"
    )


def build_hangup_laml() -> str:
    return '<?xml version="1.0" encoding="UTF-8"?><Response><Hangup/></Response>'


def voicemail_allowed(lead: dict | None) -> bool:
    already_left = (lead or {}).get("voicemail_count") or 0
    return already_left < get_settings().max_voicemails_per_lead


def record_voicemail_left(call_id: str | None, lead_id: str | None, script: str, lead: dict | None = None) -> None:
    from backend.lib import db

    if call_id:
        db.update_call_fields(call_id, {"call_disposition": "voicemail", "voicemail_left": True})
    if call_id and lead_id:
        db.insert_call_event(call_id, lead_id, "voicemail_left", {"script": script})
    if lead_id:
        db.update_lead_call_outcome(lead_id, "voicemail")
        already_left = (lead or {}).get("voicemail_count") or 0
        db.update_lead_fields(lead_id, {"voicemail_count": already_left + 1})
    logger.info("voicemail_left call_id={} lead_id={}", call_id, lead_id)
