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
    return {"success": True}


def request_owner_callback(lead_id: str, reason: str) -> dict:
    db.update_lead_fields(lead_id, {
        "escalated": True,
        "priority_callback": True,
        "operator_notes": reason,
    })
    logger.info("owner_callback_requested lead_id={} reason={}", lead_id, reason)
    return {"success": True}


def mark_call_ended(lead_id: str, disposition: str) -> dict:
    valid = {"HOT", "WARM", "COLD", "DEAD"}
    if disposition not in valid:
        disposition = "WARM"

    if disposition == "HOT":
        db.update_lead_fields(lead_id, {"is_hot_lead": True})
    elif disposition == "DEAD":
        db.update_lead_fields(lead_id, {"opted_out": False, "callable": False})

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
