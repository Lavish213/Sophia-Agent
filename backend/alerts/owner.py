from __future__ import annotations

from loguru import logger

from backend.lib import db
from backend.lib.config import get_settings


def _property_label(lead: dict) -> str:
    address = (lead.get("properties") or {}).get("address") or ""
    if not address or address.startswith("Address needed"):
        return lead.get("owner_phone") or "an unknown caller"
    return address


def notify_owner(body: str) -> dict:
    settings = get_settings()

    if not settings.owner_phone:
        logger.warning("owner_alert_skipped reason=no_owner_phone")
        return {"success": False, "reason": "no_owner_phone"}

    from signalwire.rest import Client as SignalwireClient

    try:
        client = SignalwireClient(
            settings.signalwire_project_id,
            settings.signalwire_token,
            signalwire_space_url=settings.signalwire_space,
        )
        message = client.messages.create(
            to=settings.owner_phone,
            from_=settings.signalwire_phone,
            body=body,
        )
        logger.info("owner_alert_sent sid={}", message.sid)
        return {"success": True, "message_sid": message.sid}
    except Exception as e:
        logger.error("owner_alert_failed error={}", str(e))
        return {"success": False, "reason": str(e)}


def alert_hot_lead(lead_id: str) -> dict:
    lead = db.get_lead_with_property(lead_id)
    if not lead:
        return {"success": False, "reason": "lead_not_found"}

    phone = lead.get("owner_phone") or "no number on file"
    body = (
        f"HOT lead — {_property_label(lead)}. "
        f"Seller {phone}. "
        f"{lead.get('call_summary') or 'See the dashboard for the call summary.'}"
    )
    return notify_owner(body[:600])


def alert_escalation(lead_id: str, reason: str) -> dict:
    lead = db.get_lead_with_property(lead_id)
    if not lead:
        return {"success": False, "reason": "lead_not_found"}

    phone = lead.get("owner_phone") or "no number on file"
    body = (
        f"Callback requested — {_property_label(lead)}. "
        f"Seller {phone}. Reason: {reason}"
    )
    return notify_owner(body[:600])


def alert_appointment(lead_id: str, appointment_at: str) -> dict:
    lead = db.get_lead_with_property(lead_id)
    if not lead:
        return {"success": False, "reason": "lead_not_found"}

    from backend.alerts.followup import format_appointment

    when = format_appointment(appointment_at) or appointment_at
    body = f"Walkthrough booked — {_property_label(lead)} on {when}."
    return notify_owner(body[:600])
