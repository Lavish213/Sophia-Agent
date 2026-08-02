from datetime import UTC, datetime, timedelta

from backend.api.routes.workers import classify

_NOW = datetime(2026, 8, 2, 12, 0, tzinfo=UTC)


def _run(minutes_ago, status="ok", results=None, error=None):
    return {
        "started_at": (_NOW - timedelta(minutes=minutes_ago)).isoformat(),
        "status": status,
        "results": results or {},
        "error": error,
        "duration_ms": 1200,
    }


def test_worker_that_never_ran_is_flagged():
    result = classify("dialer", None, _NOW)
    assert result["state"] == "never_run"


def test_recent_run_is_ok():
    assert classify("dialer", _run(3), _NOW)["state"] == "ok"


def test_slightly_overdue_is_late_not_dead():
    assert classify("dialer", _run(18), _NOW)["state"] == "late"


def test_long_overdue_worker_is_stale():
    result = classify("dialer", _run(120), _NOW)
    assert result["state"] == "stale", "a dialer silent for 2 hours is the case this page exists for"


def test_errored_run_beats_recency():
    assert classify("bob", _run(1, status="error", error="boom"), _NOW)["state"] == "error"


def test_minutes_since_is_computed():
    assert classify("bob", _run(45), _NOW)["minutes_since"] == 45


def test_unparseable_timestamp_does_not_crash():
    run = {"started_at": "not-a-date", "status": "ok", "results": {}}
    result = classify("bob", run, _NOW)
    assert result["minutes_since"] is None


def test_results_are_passed_through_for_display():
    result = classify("dialer", _run(2, results={"placed": 7}), _NOW)
    assert result["results"]["placed"] == 7
