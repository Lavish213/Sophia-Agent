from __future__ import annotations

from loguru import logger

from bob.avoidances_builder import build_avoidances
from bob.checkbox_selector import select_missing_checkbox
from bob.contracts import CallBrief
from bob.escalation_rules import build_escalation_rules
from bob.objective_selector import get_objective

_OPENER_HINTS: dict[str, str] = {
    "preforeclosure": "seller may be stressed — open light and stay calm",
    "pre_foreclosure": "seller may be stressed — open light and stay calm",
    "inherited_property": "acknowledge any loss naturally before qualifying",
    "inherited": "acknowledge any loss naturally before qualifying",
    "probate": "acknowledge any loss naturally before qualifying",
    "tired_landlord": "lead with simplicity and no hassle",
    "divorce": "neutral tone — do not reference the other party",
    "vacant_property": "property is likely a pain point — lead with that",
    "distressed_seller": "follow their emotion first before any questions",
    "stale_listing": "their listing has sat a while — lead with that, not with price",
    "expired_listing": "listing just expired — they are likely frustrated with agents",
}

_SITUATION_MOOD: dict[str, str] = {
    "preforeclosure": "distressed",
    "pre_foreclosure": "distressed",
    "inherited_property": "guarded",
    "inherited": "guarded",
    "probate": "guarded",
    "divorce": "guarded",
}


def _derive_phase(missing_box: str, call_count: int) -> str:
    if missing_box in ("right_person", "property_confirmed"):
        return "VERIFY"
    if missing_box in ("occupancy", "condition", "timeline", "motivation"):
        return "LIGHT_DISCOVERY"
    if missing_box == "next_step":
        return "QUALIFY"
    return "LIGHT_DISCOVERY"


def _derive_mood(
    intel_packet: dict,
    seller_memory: dict,
    situation_label: str,
    initial_trust: float,
    is_outbound: bool,
    call_count: int,
) -> str:
    sit = (situation_label or "").lower()
    for key, mood in _SITUATION_MOOD.items():
        if key in sit:
            return mood

    motivation = seller_memory.get("motivation_level")
    if motivation is not None and int(motivation) >= 8:
        return "motivated"

    objections = seller_memory.get("objections_raised") or []
    if objections and call_count > 0:
        return "skeptical"

    if initial_trust >= 6.5 and not is_outbound:
        return "open"

    if is_outbound and call_count == 0:
        return "guarded"

    flags = (intel_packet or {}).get("conflict_flags") or []
    if flags:
        return "skeptical"

    return "guarded"


def _derive_confidence(packet_state: str) -> float:
    return {
        "bob_enriched": 0.90,
        "operator_locked": 0.95,
        "system_assembled": 0.65,
        "conflicted": 0.50,
    }.get(packet_state or "", 0.40)


def generate_call_brief(
    lead_id: str,
    lead: dict,
    prop: dict,
    intel_packet: dict,
    seller_memory: dict,
    situation_label: str = "unknown",
    initial_trust: float = 5.0,
    is_outbound: bool = True,
) -> CallBrief | None:
    try:
        call_summaries = seller_memory.get("call_summaries") or []
        call_count = len(call_summaries)

        missing_box = select_missing_checkbox(intel_packet, seller_memory, lead, prop)
        phase = _derive_phase(missing_box, call_count)
        objective = get_objective(missing_box, phase)
        avoid = build_avoidances(intel_packet, situation_label, call_count, property_row=prop)
        escalation_rules = build_escalation_rules(intel_packet, situation_label, seller_memory)
        mood = _derive_mood(intel_packet, seller_memory, situation_label, initial_trust, is_outbound, call_count)

        sit = (situation_label or "").lower()
        opener_hint = next((hint for key, hint in _OPENER_HINTS.items() if key in sit), None)

        packet_state = (intel_packet or {}).get("packet_state", "system_assembled")
        confidence = _derive_confidence(packet_state)

        brief = CallBrief(
            lead_id=lead_id,
            phase=phase,
            objective=objective,
            missing_box=missing_box,
            mood=mood,
            avoid=avoid,
            escalation_rules=escalation_rules,
            opener_hint=opener_hint,
            confidence=confidence,
            source="bob" if packet_state == "bob_enriched" else "system",
        )

        logger.info(
            "brief_generated lead_id={} phase={} box={} mood={} confidence={:.2f}",
            lead_id, phase, missing_box, mood, confidence,
        )
        return brief

    except Exception as e:
        logger.error("brief_generator_failed lead_id={} error={}", lead_id, str(e))
        return None
