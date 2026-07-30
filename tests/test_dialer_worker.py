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
