from backend.lib import db
from dialer import worker


def _lead(lead_id="lead-1"):
    return {"id": lead_id, "owner_phone": "2095551212"}


def test_run_once_places_calls_when_capacity_and_allowed(monkeypatch):
    monkeypatch.setattr(worker, "_fetch_due_leads", lambda: [_lead("lead-1"), _lead("lead-2")])
    monkeypatch.setattr(worker, "has_capacity", lambda: True)
    monkeypatch.setattr(worker, "place_outbound_call", lambda lead_id: {"success": True, "call_sid": "CA1"})

    results = worker.run_once()

    assert results["attempted"] == 2
    assert results["placed"] == 2
    assert results["skipped_capacity"] == 0


def test_run_once_stops_when_capacity_hit(monkeypatch):
    monkeypatch.setattr(worker, "_fetch_due_leads", lambda: [_lead("lead-1"), _lead("lead-2"), _lead("lead-3")])
    capacity_calls = {"count": 0}

    def _fake_capacity():
        capacity_calls["count"] += 1
        return capacity_calls["count"] <= 1

    monkeypatch.setattr(worker, "has_capacity", _fake_capacity)
    monkeypatch.setattr(worker, "place_outbound_call", lambda lead_id: {"success": True, "call_sid": "CA1"})

    results = worker.run_once()

    assert results["attempted"] == 1
    assert results["placed"] == 1
    assert results["skipped_capacity"] == 1


def test_run_once_counts_compliance_skips_separately_from_errors(monkeypatch):
    monkeypatch.setattr(worker, "_fetch_due_leads", lambda: [_lead("lead-1"), _lead("lead-2")])
    monkeypatch.setattr(worker, "has_capacity", lambda: True)

    responses = iter([
        {"success": False, "reason": "outside_hours"},
        {"success": False, "reason": "no_phone_on_file"},
    ])
    monkeypatch.setattr(worker, "place_outbound_call", lambda lead_id: next(responses))

    results = worker.run_once()

    assert results["skipped_compliance"] == 1
    assert results["errors"] == 1
    assert results["placed"] == 0


def test_run_once_handles_exceptions_without_crashing(monkeypatch):
    monkeypatch.setattr(worker, "_fetch_due_leads", lambda: [_lead("lead-1")])
    monkeypatch.setattr(worker, "has_capacity", lambda: True)

    def _raise(lead_id):
        raise RuntimeError("signalwire down")

    monkeypatch.setattr(worker, "place_outbound_call", _raise)

    results = worker.run_once()

    assert results["errors"] == 1


def test_run_once_skips_leads_without_id(monkeypatch):
    monkeypatch.setattr(worker, "_fetch_due_leads", lambda: [{"owner_phone": "2095551212"}])
    monkeypatch.setattr(worker, "has_capacity", lambda: True)
    results = worker.run_once()
    assert results["attempted"] == 0


def test_run_once_empty_batch(monkeypatch):
    monkeypatch.setattr(worker, "_fetch_due_leads", lambda: [])
    results = worker.run_once()
    assert results["attempted"] == 0
    assert results["placed"] == 0


def test_max_concurrent_zero_is_a_kill_switch(monkeypatch):
    from backend.lib.config import get_settings
    from dialer.concurrency import has_capacity

    monkeypatch.setenv("MAX_CONCURRENT_OUTBOUND", "0")
    get_settings.cache_clear()
    try:
        monkeypatch.setattr(db, "count_active_calls", lambda **kwargs: 0)
        assert has_capacity() is False, (
            "setting MAX_CONCURRENT_OUTBOUND=0 is the documented way to stop all outbound "
            "calling without a redeploy; it must hold even with no calls in flight"
        )
    finally:
        get_settings.cache_clear()


def test_kill_switch_stops_the_worker_placing_any_call(monkeypatch):
    from backend.lib.config import get_settings

    monkeypatch.setenv("MAX_CONCURRENT_OUTBOUND", "0")
    get_settings.cache_clear()
    try:
        monkeypatch.setattr(worker, "_fetch_due_leads", lambda: [{"id": "l1"}, {"id": "l2"}])
        monkeypatch.setattr(db, "count_active_calls", lambda **kwargs: 0)

        def _should_not_dial(lead_id):
            raise AssertionError("placed a call while the kill switch was on")

        monkeypatch.setattr(worker, "place_outbound_call", _should_not_dial)

        results = worker._run_once_inner()

        assert results["placed"] == 0
    finally:
        get_settings.cache_clear()
