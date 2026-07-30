from __future__ import annotations

from loguru import logger

from backend.compliance.compliance import ComplianceEngine
from backend.lib import db
from backend.lib.config import get_settings


def place_outbound_call(lead_id: str) -> dict:
    lead = db.get_lead_with_property(lead_id)
    if not lead:
        return {"success": False, "reason": "lead_not_found"}

    if not lead.get("owner_phone"):
        return {"success": False, "reason": "no_phone_on_file"}

    compliance_result = ComplianceEngine().check_call_allowed(lead_id)
    if not compliance_result.allowed:
        logger.info("outbound_call_blocked lead_id={} reason={}", lead_id, compliance_result.reason)
        return {"success": False, "reason": compliance_result.reason}

    settings = get_settings()

    from signalwire.rest import Client as SignalwireClient

    client = SignalwireClient(
        settings.signalwire_project_id,
        settings.signalwire_token,
        signalwire_space_url=settings.signalwire_space,
    )

    public_url = settings.public_url.rstrip("/")
    webhook_url = f"{public_url}/api/voice/outbound/{lead_id}"
    status_callback_url = f"{public_url}/api/voice/status"

    call = client.calls.create(
        to=lead["owner_phone"],
        from_=settings.signalwire_phone,
        url=webhook_url,
        status_callback=status_callback_url,
        machine_detection="DetectMessageEnd",
        machine_detection_timeout=settings.machine_detection_timeout_seconds,
    )

    db.insert_call({
        "lead_id": lead_id,
        "direction": "outbound",
        "signalwire_call_id": call.sid,
    })

    logger.info("outbound_call_placed lead_id={} call_sid={}", lead_id, call.sid)
    return {"success": True, "call_sid": call.sid}
