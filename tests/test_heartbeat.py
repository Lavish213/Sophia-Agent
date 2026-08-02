import pytest

from backend.lib import db, heartbeat


def test_successful_run_is_recorded_with_results(monkeypatch):
    monkeypatch.setattr(db, "start_worker_run", lambda w: "run-1")
    captured = {}
    monkeypatch.setattr(
        db,
        "finish_worker_run",
        lambda rid, status, results, ms, err: captured.update(
            run_id=rid, status=status, results=results, error=err
        ),
    )

    with heartbeat.record_run("dialer") as results:
        results.update({"placed": 3})

    assert captured["status"] == "ok"
    assert captured["results"] == {"placed": 3}
    assert captured["error"] is None


def test_failing_run_is_recorded_and_reraised(monkeypatch):
    monkeypatch.setattr(db, "start_worker_run", lambda w: "run-1")
    captured = {}
    monkeypatch.setattr(
        db,
        "finish_worker_run",
        lambda rid, status, results, ms, err: captured.update(status=status, error=err),
    )

    with pytest.raises(RuntimeError), heartbeat.record_run("bob"):
        raise RuntimeError("supabase down")

    assert captured["status"] == "error"
    assert "supabase down" in captured["error"]


def test_worker_still_runs_when_heartbeat_cannot_be_written(monkeypatch):
    def _boom(worker):
        raise RuntimeError("no db")

    monkeypatch.setattr(db, "start_worker_run", _boom)

    ran = {"yes": False}
    with heartbeat.record_run("discovery"):
        ran["yes"] = True

    assert ran["yes"] is True, "monitoring must never be what stops the work"


def test_finish_failure_does_not_break_the_worker(monkeypatch):
    monkeypatch.setattr(db, "start_worker_run", lambda w: "run-1")

    def _boom(*args, **kwargs):
        raise RuntimeError("write failed")

    monkeypatch.setattr(db, "finish_worker_run", _boom)

    with heartbeat.record_run("bob") as results:
        results.update({"processed": 1})
