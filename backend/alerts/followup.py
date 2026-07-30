from __future__ import annotations

from datetime import datetime

from loguru import logger

from backend.alerts.email import send_email
from backend.alerts.sms import send_sms
from backend.lib import db
from backend.lib.config import get_settings

_NO_ANSWER_DISPOSITIONS = {"no-answer", "busy", "failed"}
_CONVERSATION_DISPOSITIONS = {"HOT", "WARM", "COLD", "DEAD"}
_VOICEMAIL_DISPOSITIONS = {"voicemail"}


def _first_name(lead: dict) -> str:
    owner_name = (lead.get("properties") or {}).get("owner_name") or ""
    return owner_name.split(" ")[0] if owner_name else ""


def _greeting(lead: dict) -> str:
    name = _first_name(lead)
    return f"Hey {name}," if name else "Hey,"


def _property_reference(lead: dict) -> str:
    address = (lead.get("properties") or {}).get("address") or ""
    if not address or address.startswith("Address needed"):
        return "your property"
    return address


def _no_answer_sms_body(lead: dict) -> str:
    settings = get_settings()
    return (
        f"{_greeting(lead)} it's Sophia with {settings.business_name}. Tried reaching you about "
        f"{_property_reference(lead)} but couldn't get through. Call or text back whenever works "
        "— no rush. Reply STOP to opt out."
    )


def _no_answer_email_body(lead: dict) -> str:
    settings = get_settings()
    name = _first_name(lead) or "there"
    return (
        f"Hi {name},\n\n"
        f"This is Sophia with {settings.business_name}. I tried reaching you by phone about "
        f"{_property_reference(lead)} but wasn't able to connect.\n\n"
        "We buy houses in San Joaquin County as-is — no agents, no commissions, and no repairs "
        "on your end. If you're open to a quick conversation about what we could offer, just "
        "reply to this email or call or text me back.\n\n"
        "If you'd rather not hear from us, reply to this email and let me know and I'll take "
        f"you off the list.\n\nThanks,\nSophia\n{settings.business_name}"
    )


def _voicemail_sms_body(lead: dict) -> str:
    settings = get_settings()
    return (
        f"{_greeting(lead)} it's Sophia with {settings.business_name} — just left you a voicemail "
        f"about {_property_reference(lead)}. No pressure, but if you're curious what we'd offer, "
        "just text me back here. Reply STOP to opt out."
    )


def format_appointment(appointment_at: str | None) -> str:
    if not appointment_at:
        return ""
    try:
        parsed = datetime.fromisoformat(appointment_at.replace("Z", "+00:00"))
    except ValueError:
        return ""
    return parsed.strftime("%A %b %-d at %-I:%M %p")


def _conversation_sms_body(lead: dict) -> str | None:
    settings = get_settings()
    if lead.get("appointment_at"):
        when = format_appointment(lead.get("appointment_at"))
        when_phrase = f" for {when}" if when else ""
        return (
            f"{_greeting(lead)} it's Sophia with {settings.business_name} — great talking with you. "
            f"You're all set{when_phrase}. If anything changes just text me here. "
            "Reply STOP to opt out."
        )
    return (
        f"{_greeting(lead)} it's Sophia with {settings.business_name} — thanks for chatting. "
        "I'll follow up soon, and you can reach me right here anytime before then. "
        "Reply STOP to opt out."
    )


def send_post_call_followup(lead_id: str, call_id: str, disposition: str | None) -> dict:
    if not disposition:
        return {"sms": None, "email": None}

    lead = db.get_lead_with_property(lead_id)
    if not lead:
        return {"sms": None, "email": None}

    results: dict = {"sms": None, "email": None}

    if disposition in _VOICEMAIL_DISPOSITIONS:
        if lead.get("owner_phone"):
            results["sms"] = send_sms(lead_id, _voicemail_sms_body(lead))
        return results

    if disposition in _NO_ANSWER_DISPOSITIONS:
        if lead.get("owner_phone"):
            results["sms"] = send_sms(lead_id, _no_answer_sms_body(lead))
        if lead.get("owner_email"):
            results["email"] = send_email(lead_id, "Tried to reach you", _no_answer_email_body(lead))
        return results

    if disposition in ("HOT", "WARM"):
        body = _conversation_sms_body(lead)
        if body and lead.get("owner_phone"):
            results["sms"] = send_sms(lead_id, body)
        return results

    logger.debug("no_followup_needed lead_id={} disposition={}", lead_id, disposition)
    return results
