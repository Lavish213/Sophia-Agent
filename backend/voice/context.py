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


def build_caller_awareness_str(lead: dict | None, direction: str, is_new_contact: bool = False) -> str:
    if direction == "inbound" and (lead is None or is_new_contact):
        return (
            "This is an inbound call from a number that has never been contacted before. "
            "You do not know who this is or which property they are calling about. "
            "Do not pretend to recognize them, and do not claim you called them. "
            "Ask who you're speaking with and how you can help."
        )

    lead = lead or {}
    lines = []

    attempts = lead.get("call_attempts") or 0
    voicemails = lead.get("voicemail_count") or 0
    last_outcome = lead.get("last_call_outcome")

    if direction == "inbound":
        lines.append("This person is calling you back.")
        if voicemails:
            lines.append(
                f"You left them {voicemails} voicemail(s), so they are most likely returning that. "
                "Thank them for calling back."
            )
        elif attempts:
            lines.append(f"You have tried reaching them {attempts} time(s) before.")
    else:
        if attempts:
            lines.append(f"This is outbound attempt number {attempts + 1} for this lead.")
        if voicemails:
            lines.append(
                f"You have already left {voicemails} voicemail(s), "
                "so do not re-introduce yourself from scratch."
            )

    if last_outcome:
        lines.append(f"The last call ended as: {last_outcome}.")

    if lead.get("opted_out"):
        lines.append(
            "This person previously opted out of texts. Do not offer to text them unless they ask."
        )

    if not lines:
        lines.append("You have not spoken with this person before.")

    return " ".join(lines)


def build_call_brief_str(lead: dict | None) -> str:
    brief = (lead or {}).get("call_brief")
    if not isinstance(brief, dict) or not brief:
        return ""

    lines = []

    objective = brief.get("objective")
    if objective:
        lines.append(f"Your objective on this call: {objective}")

    missing_box = brief.get("missing_box")
    if missing_box:
        lines.append(f"The single most important thing to find out is their {missing_box.replace('_', ' ')}.")

    mood = brief.get("mood")
    if mood:
        lines.append(f"Match this tone: {mood}.")

    opener_hint = brief.get("opener_hint")
    if opener_hint:
        lines.append(f"Suggested way in: {opener_hint}")

    avoid = brief.get("avoid") or []
    if avoid:
        lines.append("Do not bring up: " + "; ".join(str(a) for a in avoid) + ".")

    escalation_rules = brief.get("escalation_rules") or []
    if escalation_rules:
        lines.append("Escalate to Alanzo if: " + "; ".join(str(r) for r in escalation_rules) + ".")

    return " ".join(lines)


def preload_call_context(caller_phone: str) -> dict:
    from backend.scout.intake import find_existing_lead, intake_lead

    lead = find_existing_lead(caller_phone) if caller_phone else None
    is_new_contact = False

    if not lead and caller_phone:
        result = intake_lead(
            "inbound_call",
            owner_phone=caller_phone,
            notes="Created automatically from an inbound call.",
        )
        if result["success"] and result["lead_id"]:
            lead = db.get_lead_with_property(result["lead_id"])
            is_new_contact = result.get("created", False)
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
            "caller_awareness_str": build_caller_awareness_str(None, "inbound", True),
        }

    owner_name = lead.get("properties", {}).get("owner_name") if lead.get("properties") else None
    first_name = (owner_name or "").split(" ")[0] if owner_name else "there"

    return {
        "lead": lead,
        "lead_id": lead["id"],
        "owner_first_name": first_name or "there",
        "property_context_str": build_property_context_str(lead),
        "caller_awareness_str": build_caller_awareness_str(lead, "inbound", is_new_contact),
        "call_brief_str": build_call_brief_str(lead),
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
            "caller_awareness_str": build_caller_awareness_str(None, "outbound"),
        }

    owner_name = (lead.get("properties") or {}).get("owner_name")
    first_name = (owner_name or "").split(" ")[0] if owner_name else "there"

    return {
        "lead": lead,
        "lead_id": lead["id"],
        "owner_first_name": first_name or "there",
        "property_context_str": build_property_context_str(lead),
        "caller_awareness_str": build_caller_awareness_str(lead, "outbound"),
        "call_brief_str": build_call_brief_str(lead),
    }
