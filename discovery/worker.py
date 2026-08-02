from __future__ import annotations

import time

from loguru import logger

from backend.lib import db
from backend.lib.config import get_settings
from backend.scout import skiptrace
from backend.scout.reddit import fetch_matches
from backend.scout.stale_listings import run_stale_listing_pass


def run_skiptrace_pass() -> dict:
    results = {"attempted": 0, "enriched": 0}
    if not skiptrace.is_configured():
        return results

    settings = get_settings()
    leads = db.get_leads_needing_skiptrace(limit=settings.skiptrace_batch_size)

    for lead in leads:
        results["attempted"] += 1
        try:
            outcome = skiptrace.enrich_lead(lead["id"])
            if outcome.get("success"):
                results["enriched"] += 1
        except Exception as e:
            logger.error("skiptrace_pass_failed lead_id={} error={}", lead.get("id"), str(e))

    logger.info("skiptrace_pass_complete results={}", results)
    return results


def run_once() -> dict:
    logger.info("discovery_run_once_starting")

    matches = fetch_matches()
    results = {"fetched": len(matches), "new_matches": 0, "errors": 0}

    for match in matches:
        try:
            if db.get_reddit_match_by_reddit_id(match["reddit_id"]):
                continue
            db.insert_reddit_match(match)
            results["new_matches"] += 1
        except Exception as e:
            results["errors"] += 1
            logger.error("discovery_match_failed reddit_id={} error={}", match.get("reddit_id"), str(e))

    results["skiptrace"] = run_skiptrace_pass()
    results["stale_listings"] = run_stale_listing_pass()

    logger.info("discovery_run_once_complete results={}", results)
    return results


def run_loop() -> None:
    settings = get_settings()
    logger.info("discovery_starting interval={}min", settings.reddit_poll_interval_minutes)
    while True:
        try:
            run_once()
        except Exception as e:
            logger.error("discovery_loop_error error={}", str(e))
        time.sleep(settings.reddit_poll_interval_minutes * 60)
