from __future__ import annotations

from loguru import logger

from backend.lib import db


def _format_cents(cents: int | None) -> str | None:
    if cents is None:
        return None
    return f"${cents / 100:,.0f}"


def build_property_context_str(lead: dict) -> str:
    prop = lead.get("properties") or {}
    lines = []

    address = prop.get("address")
    if address:
        lines.append(f"Property address: {address}.")

    distress_type = prop.get("distress_type")
    if distress_type and distress_type != "unknown":
        lines.append(f"Known situation: {distress_type.replace('_', ' ')}.")

    arv = _format_cents(prop.get("estimated_arv"))
    mao = _format_cents(prop.get("mao"))
    if arv and mao:
        lines.append(f"Estimated after-repair value is around {arv}, rough offer range would land near {mao}.")

    motivation = lead.get("motivation_level")
    if motivation is not None:
        lines.append(f"Motivation level from prior calls: {motivation}/10.")

    price_floor = _format_cents(lead.get("price_floor"))
    if price_floor:
        lines.append(f"Owner has previously mentioned a price floor around {price_floor}.")

    timeline = lead.get("timeline_urgency")
    if timeline:
        lines.append(f"Timeline urgency from prior calls: {timeline}.")

    call_summary = lead.get("call_summary")
    if call_summary:
        lines.append(f"Summary of most recent prior call: {call_summary}")

    if not lines:
        return "No prior information on this caller. Greet naturally and find out why they're calling."

    return " ".join(lines)


def preload_call_context(caller_phone: str) -> dict:
    from backend.scout.intake import find_existing_lead, intake_lead

    lead = find_existing_lead(caller_phone) if caller_phone else None

    if not lead and caller_phone:
        result = intake_lead(
            "inbound_call",
            owner_phone=caller_phone,
            notes="Created automatically from an inbound call.",
        )
        if result["success"] and result["lead_id"]:
            lead = db.get_lead_with_property(result["lead_id"])
            logger.info("preload_call_context_created_lead phone={} lead_id={}", caller_phone, result["lead_id"])

    if not lead:
        logger.info("preload_call_context_no_match phone={}", caller_phone)
        return {
            "lead": None,
            "lead_id": None,
            "owner_first_name": "there",
            "property_context_str": (
                "No property on file for this caller. Greet naturally and find out why they're calling."
            ),
        }

    owner_name = lead.get("properties", {}).get("owner_name") if lead.get("properties") else None
    first_name = (owner_name or "").split(" ")[0] if owner_name else "there"

    return {
        "lead": lead,
        "lead_id": lead["id"],
        "owner_first_name": first_name or "there",
        "property_context_str": build_property_context_str(lead),
    }


def preload_outbound_context(lead_id: str) -> dict:
    lead = db.get_lead_with_property(lead_id)

    if not lead:
        logger.warning("preload_outbound_context_lead_not_found lead_id={}", lead_id)
        return {
            "lead": None,
            "lead_id": lead_id,
            "owner_first_name": "there",
            "property_context_str": (
                "No property on file. Greet naturally and confirm you're speaking with the property owner."
            ),
        }

    owner_name = (lead.get("properties") or {}).get("owner_name")
    first_name = (owner_name or "").split(" ")[0] if owner_name else "there"

    return {
        "lead": lead,
        "lead_id": lead["id"],
        "owner_first_name": first_name or "there",
        "property_context_str": build_property_context_str(lead),
    }
