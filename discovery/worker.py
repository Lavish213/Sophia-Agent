from __future__ import annotations

import time

from loguru import logger

from backend.lib import db
from backend.lib.config import get_settings
from backend.scout.reddit import fetch_matches


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
