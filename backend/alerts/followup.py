from __future__ import annotations

from loguru import logger

from backend.alerts.email import send_email
from backend.alerts.sms import send_sms
from backend.lib import db
from backend.lib.config import get_settings

_NO_ANSWER_DISPOSITIONS = {"no-answer", "busy", "failed"}
_CONVERSATION_DISPOSITIONS = {"HOT", "WARM", "COLD", "DEAD"}


def _no_answer_sms_body() -> str:
    settings = get_settings()
    return (
        f"Hey, this is Sophia with {settings.business_name} — tried giving you a call "
        "about your property but couldn't reach you. No worries, just call or text "
        "this number back whenever works. Reply STOP to stop texts."
    )


def _no_answer_email_body(first_name: str) -> str:
    settings = get_settings()
    return (
        f"Hi {first_name},\n\n"
        f"This is Sophia with {settings.business_name}. I tried reaching you by phone "
        "about your property but wasn't able to connect. If you're open to a quick "
        "conversation about a potential cash offer, feel free to call or text this "
        f"number back, or just reply to this email.\n\nThanks,\nSophia"
    )


def _conversation_sms_body(lead: dict) -> str | None:
    settings = get_settings()
    if lead.get("appointment_at"):
        return (
            f"Hey, it's Sophia with {settings.business_name} — great talking with you! "
            "Confirming our walkthrough, talk soon. Reply STOP to stop texts."
        )
    return (
        f"Hey, it's Sophia with {settings.business_name} — thanks for chatting with me. "
        "I'll follow up soon, and feel free to reach out anytime before then. "
        "Reply STOP to stop texts."
    )


def send_post_call_followup(lead_id: str, call_id: str, disposition: str | None) -> dict:
    if not disposition:
        return {"sms": None, "email": None}

    lead = db.get_lead_by_id(lead_id)
    if not lead:
        return {"sms": None, "email": None}

    results: dict = {"sms": None, "email": None}

    if disposition in _NO_ANSWER_DISPOSITIONS:
        if lead.get("owner_phone"):
            results["sms"] = send_sms(lead_id, _no_answer_sms_body())
        if lead.get("owner_email"):
            first_name = (lead.get("owner_name") or "there").split(" ")[0]
            results["email"] = send_email(lead_id, "Tried to reach you", _no_answer_email_body(first_name))
        return results

    if disposition in ("HOT", "WARM"):
        body = _conversation_sms_body(lead)
        if body and lead.get("owner_phone"):
            results["sms"] = send_sms(lead_id, body)
        return results

    logger.debug("no_followup_needed lead_id={} disposition={}", lead_id, disposition)
    return results
