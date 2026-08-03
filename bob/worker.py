from __future__ import annotations

import time

from loguru import logger

from backend.lib import db
from backend.lib.config import get_settings
from backend.lib.heartbeat import record_run
from bob.brief_generator import generate_call_brief
from bob.decision_logger import log_decision
from bob.prioritizer import score_lead, waiting_on_a_human

_SITUATION_LABELS: dict[str, str] = {
    "preforeclosure": "preforeclosure",
    "pre_foreclosure": "preforeclosure",
    "probate": "probate",
    "inherited": "inherited_property",
    "vacant": "vacant_property",
    "landlord": "tired_landlord",
    "divorce": "divorce",
    "tax": "tax_delinquent",
    "code": "code_violation",
    "stale_listing": "stale_listing",
    "expired_listing": "expired_listing",
}


_LEAD_FIELD_TO_MEMORY_KEY = {
    "motivation_level": "motivation_level",
    "price_floor": "price_floor",
    "next_best_action": "next_best_action",
    "timeline_urgency": "timeline_mentioned",
    "objections": "objections_raised",
    "property_condition": "hot_topics",
    "occupancy": "occupancy_known",
}


def build_seller_memory(lead: dict) -> dict:
    memory: dict = {}

    for lead_field, memory_key in _LEAD_FIELD_TO_MEMORY_KEY.items():
        value = lead.get(lead_field)
        if value is None:
            continue
        if memory_key in ("hot_topics", "objections_raised") and not isinstance(value, list):
            value = [value]
        memory[memory_key] = value

    summary = lead.get("call_summary")
    attempts = lead.get("call_attempts") or 0
    if summary:
        memory["call_summaries"] = [summary]
    else:
        memory["call_summaries"] = [""] * attempts

    return memory


def get_situation_label(prop: dict) -> str:
    distress = (prop.get("distress_type") or "").lower()
    for key, label in _SITUATION_LABELS.items():
        if key in distress:
            return label
    return "unknown"


def _run_once_inner() -> dict:
    settings = get_settings()
    logger.info("bob_worker_run_once_starting")

    leads = db.get_leads_needing_brief(settings.bob_batch_size)
    logger.info("bob_worker_leads_to_process count={}", len(leads))

    results = {"processed": 0, "briefs_created": 0, "errors": 0}

    for lead in leads:
        lead_id = lead.get("id")
        if not lead_id:
            continue

        results["processed"] += 1
        prop = lead.get("properties") or {}

        try:
            intel_packet = db.load_intel_packet(lead_id) or {}
            seller_memory = build_seller_memory(lead)
            situation_label = get_situation_label(prop)
            initial_trust = float(lead.get("initial_trust_score") or 5.0)

            brief = generate_call_brief(
                lead_id=lead_id,
                lead=lead,
                prop=prop,
                intel_packet=intel_packet,
                seller_memory=seller_memory,
                situation_label=situation_label,
                initial_trust=initial_trust,
                is_outbound=True,
            )

            if not brief:
                results["errors"] += 1
                continue

            brief_dict = brief.to_dict()
            db.save_call_brief(lead_id, brief_dict)

            priority, reasons = score_lead(lead)
            db.update_lead_fields(lead_id, {
                "call_priority": priority,
                "priority_reasons": reasons,
                "waiting_on_human": waiting_on_a_human(lead),
            })

            log_decision(
                lead_id=lead_id,
                decision_type="call_brief",
                inputs={
                    "situation_label": situation_label,
                    "call_count": len(seller_memory.get("call_summaries") or []),
                    "packet_state": intel_packet.get("packet_state", "missing"),
                },
                output=brief_dict,
                reason_codes=[f"missing:{brief.missing_box}", f"phase:{brief.phase}", f"mood:{brief.mood}"],
                confidence=brief.confidence,
            )

            results["briefs_created"] += 1
            logger.info(
                "brief_saved lead_id={} phase={} box={} mood={}",
                lead_id, brief.phase, brief.missing_box, brief.mood,
            )

        except Exception as e:
            results["errors"] += 1
            logger.error("bob_worker_lead_failed lead_id={} error={}", lead_id, str(e))

    logger.info("bob_worker_run_once_complete results={}", results)
    return results


def run_loop() -> None:
    settings = get_settings()
    logger.info("bob_worker_starting interval={}min", settings.bob_worker_interval_minutes)
    while True:
        try:
            run_once()
        except Exception as e:
            logger.error("bob_worker_loop_error error={}", str(e))
        time.sleep(settings.bob_worker_interval_minutes * 60)


def run_once() -> dict:
    with record_run("bob") as results:
        outcome = _run_once_inner()
        results.update(outcome)
        return outcome
