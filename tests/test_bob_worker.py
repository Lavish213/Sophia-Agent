from backend.lib import db
from bob.worker import run_once


def _lead(lead_id="lead-1"):
    return {
        "id": lead_id,
        "initial_trust_score": 5.0,
        "properties": {"distress_type": "pre_foreclosure", "address": "123 Main St"},
    }


def test_run_once_processes_leads_and_saves_briefs(monkeypatch):
    saved_briefs = {}
    decision_records = []

    monkeypatch.setattr(db, "get_leads_needing_brief", lambda batch_size: [_lead()])
    monkeypatch.setattr(db, "load_intel_packet", lambda lead_id: None)
    monkeypatch.setattr(db, "get_seller_memory", lambda lead_id: {})
    monkeypatch.setattr(db, "save_call_brief", lambda lead_id, brief: saved_briefs.__setitem__(lead_id, brief))
    monkeypatch.setattr(db, "save_decision_record", lambda record: decision_records.append(record))

    results = run_once()

    assert results["processed"] == 1
    assert results["briefs_created"] == 1
    assert results["errors"] == 0
    assert "lead-1" in saved_briefs
    assert saved_briefs["lead-1"]["missing_box"] == "right_person"
    assert len(decision_records) == 1


def test_run_once_skips_leads_without_id(monkeypatch):
    monkeypatch.setattr(db, "get_leads_needing_brief", lambda batch_size: [{"properties": {}}])
    results = run_once()
    assert results["processed"] == 0


def test_run_once_counts_errors_without_raising(monkeypatch):
    monkeypatch.setattr(db, "get_leads_needing_brief", lambda batch_size: [_lead()])
    monkeypatch.setattr(db, "load_intel_packet", lambda lead_id: (_ for _ in ()).throw(RuntimeError("db down")))
    results = run_once()
    assert results["processed"] == 1
    assert results["errors"] == 1
    assert results["briefs_created"] == 0


def test_run_once_handles_empty_batch(monkeypatch):
    monkeypatch.setattr(db, "get_leads_needing_brief", lambda batch_size: [])
    results = run_once()
    assert results == {"processed": 0, "briefs_created": 0, "errors": 0}
