from __future__ import annotations

from loguru import logger

from backend.compliance.compliance import ComplianceEngine
from backend.lib import db
from backend.lib.config import get_settings

_STOP_KEYWORDS = {"stop", "stopall", "unsubscribe", "cancel", "end", "quit"}
_START_KEYWORDS = {"start", "yes", "unstop"}


def send_sms(lead_id: str, body: str) -> dict:
    lead = db.get_lead_by_id(lead_id)
    if not lead:
        return {"success": False, "reason": "lead_not_found"}

    if not lead.get("owner_phone"):
        return {"success": False, "reason": "no_phone_on_file"}

    compliance_result = ComplianceEngine().check_sms_allowed(lead_id)
    if not compliance_result.allowed:
        logger.info("sms_blocked lead_id={} reason={}", lead_id, compliance_result.reason)
        return {"success": False, "reason": compliance_result.reason}

    settings = get_settings()

    from signalwire.rest import Client as SignalwireClient

    client = SignalwireClient(
        settings.signalwire_project_id,
        settings.signalwire_token,
        signalwire_space_url=settings.signalwire_space,
    )

    message = client.messages.create(
        to=lead["owner_phone"],
        from_=settings.signalwire_phone,
        body=body,
    )

    db.insert_sms_message(lead_id, "outbound", body, signalwire_message_sid=message.sid, status="sent")
    logger.info("sms_sent lead_id={} sid={}", lead_id, message.sid)
    return {"success": True, "message_sid": message.sid}


def _normalize_body(body: str) -> str:
    return body.strip().lower()


def handle_inbound_sms(from_number: str, body: str) -> str:
    lead = db.get_lead_by_owner_phone(from_number)
    normalized = _normalize_body(body)

    if not lead:
        logger.info("inbound_sms_no_lead_match from={}", from_number)
        return "unmatched"

    db.insert_sms_message(lead["id"], "inbound", body, status="received")

    if normalized in _STOP_KEYWORDS:
        db.update_lead_fields(lead["id"], {"opted_out": True})
        logger.info("sms_opt_out lead_id={} phone={}", lead["id"], from_number)
        return "opted_out"

    if normalized in _START_KEYWORDS:
        db.update_lead_fields(lead["id"], {"opted_out": False})
        logger.info("sms_opt_in lead_id={} phone={}", lead["id"], from_number)
        return "opted_in"

    return "logged"
