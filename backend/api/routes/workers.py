from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter

from backend.lib import db
from backend.lib.config import get_settings

router = APIRouter()

EXPECTED_WORKERS = ("bob", "dialer", "discovery")


def expected_interval_minutes(worker: str) -> int:
    settings = get_settings()
    return {
        "bob": settings.bob_worker_interval_minutes,
        "dialer": settings.dialer_interval_minutes,
        "discovery": settings.reddit_poll_interval_minutes,
    }.get(worker, 15)


def classify(worker: str, run: dict | None, now: datetime | None = None) -> dict:
    interval = expected_interval_minutes(worker)
    reference = now or datetime.now(UTC)

    if not run:
        return {
            "worker": worker,
            "state": "never_run",
            "interval_minutes": interval,
            "last_run": None,
            "minutes_since": None,
            "results": {},
            "error": None,
        }

    started = run.get("started_at")
    minutes_since = None
    if started:
        try:
            parsed = datetime.fromisoformat(str(started).replace("Z", "+00:00"))
            minutes_since = int((reference - parsed).total_seconds() / 60)
        except ValueError:
            minutes_since = None

    if run.get("status") == "error":
        state = "error"
    elif minutes_since is not None and minutes_since > interval * 3:
        state = "stale"
    elif minutes_since is not None and minutes_since > interval * 1.5:
        state = "late"
    else:
        state = "ok"

    return {
        "worker": worker,
        "state": state,
        "interval_minutes": interval,
        "last_run": started,
        "minutes_since": minutes_since,
        "results": run.get("results") or {},
        "error": run.get("error"),
        "duration_ms": run.get("duration_ms"),
    }


@router.get("/workers/health")
async def workers_health():
    try:
        runs = {r["worker"]: r for r in db.get_latest_worker_runs()}
    except Exception:
        runs = {}

    statuses = [classify(w, runs.get(w)) for w in EXPECTED_WORKERS]
    overall = "ok"
    if any(s["state"] in ("error", "stale", "never_run") for s in statuses):
        overall = "degraded"
    elif any(s["state"] == "late" for s in statuses):
        overall = "late"

    return {"overall": overall, "workers": statuses}
