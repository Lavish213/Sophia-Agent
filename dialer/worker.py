from __future__ import annotations

import time

from loguru import logger

from backend.lib.config import get_settings
from backend.voice.outbound import place_outbound_call
from dialer.concurrency import has_capacity

_COMPLIANCE_SKIP_REASONS = {
    "outside_hours", "dnc_blocked", "opted_out",
    "dnc_list_match", "lead_not_found", "check_failed_blocking",
}


def _fetch_due_leads() -> list[dict]:
    from backend.lib import db

    settings = get_settings()
    return db.get_leads_for_outbound(
        min_score=0,
        limit=settings.dialer_batch_size,
        reattempt_hours=settings.outbound_reattempt_hours,
    )


def run_once() -> dict:
    logger.info("dialer_run_once_starting")

    results = {"attempted": 0, "placed": 0, "skipped_capacity": 0, "skipped_compliance": 0, "errors": 0}

    leads = _fetch_due_leads()
    logger.info("dialer_leads_due count={}", len(leads))

    for lead in leads:
        lead_id = lead.get("id")
        if not lead_id:
            continue

        if not has_capacity():
            results["skipped_capacity"] += 1
            logger.info("dialer_at_capacity remaining_leads={}", len(leads) - results["attempted"])
            break

        results["attempted"] += 1

        try:
            result = place_outbound_call(lead_id)
            if result["success"]:
                results["placed"] += 1
            elif result["reason"] in _COMPLIANCE_SKIP_REASONS:
                results["skipped_compliance"] += 1
            else:
                results["errors"] += 1
        except Exception as e:
            results["errors"] += 1
            logger.error("dialer_lead_failed lead_id={} error={}", lead_id, str(e))

    logger.info("dialer_run_once_complete results={}", results)
    return results


def run_loop() -> None:
    settings = get_settings()
    logger.info("dialer_starting interval={}min", settings.dialer_interval_minutes)
    while True:
        try:
            run_once()
        except Exception as e:
            logger.error("dialer_loop_error error={}", str(e))
        time.sleep(settings.dialer_interval_minutes * 60)
