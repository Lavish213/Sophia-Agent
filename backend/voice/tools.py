from __future__ import annotations

from datetime import datetime

from loguru import logger

from backend.lib import db


def format_offer_range(lead_id: str) -> dict:
    lead = db.get_lead_with_property(lead_id)
    if not lead:
        return {"available": False, "reason": "lead_not_found"}

    prop = lead.get("properties") or {}
    arv = prop.get("estimated_arv")
    mao = prop.get("mao")

    if not arv or not mao:
        return {"available": False, "reason": "not_enough_property_detail_yet"}

    low = int(mao * 0.9)
    high = int(mao * 1.05)
    return {
        "available": True,
        "low_dollars": low // 100,
        "high_dollars": high // 100,
    }


def book_appointment(lead_id: str, appointment_at_iso: str, notes: str | None = None) -> dict:
    try:
        datetime.fromisoformat(appointment_at_iso.replace("Z", "+00:00"))
    except ValueError:
        return {"success": False, "reason": "invalid_datetime_format"}

    db.update_lead_appointment(lead_id, appointment_at_iso)
    if notes:
        db.update_lead_fields(lead_id, {"operator_notes": notes})

    logger.info("appointment_booked lead_id={} at={}", lead_id, appointment_at_iso)

    from backend.alerts.owner import alert_appointment

    try:
        alert_appointment(lead_id, appointment_at_iso)
    except Exception as e:
        logger.error("appointment_alert_failed lead_id={} error={}", lead_id, str(e))

    return {"success": True}


def request_owner_callback(lead_id: str, reason: str) -> dict:
    db.update_lead_fields(lead_id, {
        "escalated": True,
        "priority_callback": True,
        "operator_notes": reason,
    })
    logger.info("owner_callback_requested lead_id={} reason={}", lead_id, reason)

    from backend.alerts.owner import alert_escalation

    try:
        alert_escalation(lead_id, reason)
    except Exception as e:
        logger.error("escalation_alert_failed lead_id={} error={}", lead_id, str(e))

    return {"success": True}


def send_details(lead_id: str, channel: str, note: str | None = None) -> dict:
    from backend.alerts.email import send_email
    from backend.alerts.sms import send_sms
    from backend.lib.config import get_settings

    settings = get_settings()
    lead = db.get_lead_with_property(lead_id)
    if not lead:
        return {"success": False, "reason": "lead_not_found"}

    detail = f" {note.strip()}" if note else ""
    results = {}

    if channel in ("text", "both"):
        if not lead.get("owner_phone"):
            results["text"] = {"success": False, "reason": "no_phone_on_file"}
        else:
            body = (
                f"Hey, it's Sophia with {settings.business_name}, following up like I said "
                f"on our call.{detail} Just reply here with any questions. "
                "Reply STOP to opt out."
            )
            results["text"] = send_sms(lead_id, body)

    if channel in ("email", "both"):
        if not lead.get("owner_email"):
            results["email"] = {"success": False, "reason": "no_email_on_file"}
        else:
            body = (
                f"Hi,\n\nThis is Sophia with {settings.business_name}, following up on our "
                f"call as promised.{detail}\n\nJust reply to this email with any questions.\n\n"
                f"Thanks,\nSophia\n{settings.business_name}"
            )
            results["email"] = send_email(lead_id, "Following up on our call", body)

    sent = [k for k, v in results.items() if v.get("success")]
    logger.info("send_details lead_id={} channel={} sent={}", lead_id, channel, sent)
    return {"success": bool(sent), "sent": sent, "results": results}


def mark_call_ended(lead_id: str, disposition: str) -> dict:
    valid = {"HOT", "WARM", "COLD", "DEAD"}
    if disposition not in valid:
        disposition = "WARM"

    if disposition == "HOT":
        db.update_lead_fields(lead_id, {"is_hot_lead": True})
    elif disposition == "DEAD":
        db.update_lead_fields(lead_id, {"callable": False, "stage": "dead"})

    logger.info("mark_call_ended lead_id={} disposition={}", lead_id, disposition)
    return {"success": True, "disposition": disposition}


def build_sophia_tool_schemas(lead_id: str | None, on_end_call):
    from pipecat.adapters.schemas.function_schema import FunctionSchema
    from pipecat.adapters.schemas.tools_schema import ToolsSchema
    from pipecat.frames.frames import EndWorkerFrame

    async def _get_offer_range_handler(params):
        if not lead_id:
            await params.result_callback({"available": False, "reason": "no_lead_on_file"})
            return
        await params.result_callback(format_offer_range(lead_id))

    async def _book_appointment_handler(params):
        if not lead_id:
            await params.result_callback({"success": False, "reason": "no_lead_on_file"})
            return
        appointment_at_iso = params.arguments.get("appointment_at_iso", "")
        notes = params.arguments.get("notes")
        await params.result_callback(book_appointment(lead_id, appointment_at_iso, notes))

    async def _request_owner_callback_handler(params):
        if not lead_id:
            await params.result_callback({"success": False, "reason": "no_lead_on_file"})
            return
        reason = params.arguments.get("reason", "")
        await params.result_callback(request_owner_callback(lead_id, reason))

    async def _send_details_handler(params):
        if not lead_id:
            await params.result_callback({"success": False, "reason": "no_lead_on_file"})
            return
        channel = params.arguments.get("channel", "text")
        note = params.arguments.get("note")
        await params.result_callback(send_details(lead_id, channel, note))

    async def _end_call_handler(params):
        await params.result_callback({"success": True})
        if on_end_call:
            on_end_call(params.arguments.get("disposition", "WARM"))
        await params.llm.push_frame(EndWorkerFrame())

    tools = [
        FunctionSchema(
            name="get_offer_range",
            description=(
                "Get a rough cash offer range for the property once enough details are known. "
                "Never quote a number without calling this first."
            ),
            properties={},
            required=[],
            handler=_get_offer_range_handler,
        ),
        FunctionSchema(
            name="book_appointment",
            description="Book a property walkthrough appointment with the owner.",
            properties={
                "appointment_at_iso": {
                    "type": "string",
                    "description": "The agreed appointment date and time as an ISO 8601 timestamp.",
                },
                "notes": {
                    "type": "string",
                    "description": "Any relevant notes about the appointment.",
                },
            },
            required=["appointment_at_iso"],
            handler=_book_appointment_handler,
        ),
        FunctionSchema(
            name="request_owner_callback",
            description=(
                "Flag this lead so Alanzo personally calls the owner back, for anything you "
                "can't or shouldn't handle yourself (legal questions, a firm price demand, "
                "anger, a request for a human)."
            ),
            properties={
                "reason": {
                    "type": "string",
                    "description": "Brief reason Alanzo needs to call back.",
                },
            },
            required=["reason"],
            handler=_request_owner_callback_handler,
        ),
        FunctionSchema(
            name="send_details",
            description=(
                "Send the seller a text or email during the call, when they ask for something "
                "in writing or ask you to follow up. Only use this if they asked for it."
            ),
            properties={
                "channel": {
                    "type": "string",
                    "enum": ["text", "email", "both"],
                    "description": "How the seller asked to be contacted.",
                },
                "note": {
                    "type": "string",
                    "description": "One short sentence about what they asked you to send.",
                },
            },
            required=["channel"],
            handler=_send_details_handler,
        ),
        FunctionSchema(
            name="end_call",
            description="End the call gracefully once the conversation has reached a natural close.",
            properties={
                "disposition": {
                    "type": "string",
                    "description": "One of HOT, WARM, COLD, DEAD describing how promising this lead is.",
                },
            },
            required=["disposition"],
            handler=_end_call_handler,
        ),
    ]

    return ToolsSchema(standard_tools=tools)
