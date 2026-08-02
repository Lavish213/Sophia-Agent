from __future__ import annotations


def select_missing_checkbox(intel_packet: dict, seller_memory: dict, lead: dict, prop: dict) -> str:
    call_summaries = seller_memory.get("call_summaries") or []
    timeline_mentioned = seller_memory.get("timeline_mentioned")
    motivation_level = seller_memory.get("motivation_level")

    distress = (prop.get("distress_type") or "").lower()
    occupancy_known = (
        bool(seller_memory.get("occupancy_known"))
        or "vacant" in distress
        or prop.get("vacant") is True
    )

    call_count = len(call_summaries)
    owner_confirmed = call_count > 0

    if not owner_confirmed:
        return "right_person"

    address = prop.get("address") or lead.get("address")
    if not address:
        return "property_confirmed"

    if not occupancy_known:
        return "occupancy"

    property_issues = seller_memory.get("hot_topics") or []
    if not property_issues:
        return "condition"

    if not timeline_mentioned:
        return "timeline"

    if motivation_level is None:
        return "motivation"

    return "next_step"
