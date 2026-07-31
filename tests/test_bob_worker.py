from backend.lib import db
from bob import worker
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


def test_seller_memory_is_built_from_what_calls_actually_learned():
    lead = {
        "id": "lead-1",
        "motivation_level": 8,
        "price_floor": 15000000,
        "timeline_urgency": "asap",
        "objections": ["needs to talk to sister"],
        "call_summary": "Wants out before the auction.",
        "call_attempts": 2,
    }

    memory = worker.build_seller_memory(lead)

    assert memory["motivation_level"] == 8
    assert memory["price_floor"] == 15000000
    assert memory["timeline_urgency"] == "asap"
    assert memory["objections"] == ["needs to talk to sister"]
    assert memory["call_summaries"] == ["Wants out before the auction."]


def test_seller_memory_is_empty_for_a_lead_never_called():
    memory = worker.build_seller_memory({"id": "lead-1"})
    assert memory["call_summaries"] == []
    assert "motivation_level" not in memory


def test_seller_memory_counts_attempts_when_no_summary_was_saved():
    memory = worker.build_seller_memory({"id": "lead-1", "call_attempts": 3})
    assert len(memory["call_summaries"]) == 3


def test_brief_is_stale_when_a_call_happened_after_it_was_written():
    from backend.lib.db import brief_is_stale

    assert brief_is_stale({
        "call_brief": {"objective": "x"},
        "call_brief_generated_at": "2026-07-01T00:00:00Z",
        "last_called_at": "2026-07-02T00:00:00Z",
    }) is True


def test_brief_is_fresh_when_written_after_the_last_call():
    from backend.lib.db import brief_is_stale

    assert brief_is_stale({
        "call_brief": {"objective": "x"},
        "call_brief_generated_at": "2026-07-03T00:00:00Z",
        "last_called_at": "2026-07-02T00:00:00Z",
    }) is False


def test_missing_brief_is_always_stale():
    from backend.lib.db import brief_is_stale

    assert brief_is_stale({"call_brief": None}) is True
    assert brief_is_stale({}) is True


def test_never_called_lead_with_a_brief_is_not_regenerated():
    from backend.lib.db import brief_is_stale

    assert brief_is_stale({"call_brief": {"objective": "x"}, "last_called_at": None}) is False
