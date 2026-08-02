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
    assert memory["timeline_mentioned"] == "asap"
    assert memory["objections_raised"] == ["needs to talk to sister"]
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


def _lead_after(**facts):
    lead = {"call_attempts": facts.pop("attempts", 1), "call_summary": "spoke with them"}
    lead.update(facts)
    return lead


def test_memory_uses_the_key_names_bob_actually_reads():
    memory = worker.build_seller_memory(
        _lead_after(timeline_urgency="asap", objections=["needs sister"], property_condition="roof")
    )

    assert "timeline_mentioned" in memory, "checkbox_selector reads timeline_mentioned"
    assert "objections_raised" in memory, "brief_generator reads objections_raised"
    assert "hot_topics" in memory, "checkbox_selector reads hot_topics"


def test_scalar_facts_are_wrapped_for_list_readers():
    memory = worker.build_seller_memory(_lead_after(property_condition="roof leaks"))
    assert memory["hot_topics"] == ["roof leaks"]


def test_checkbox_ladder_advances_as_sophia_learns():
    from bob.checkbox_selector import select_missing_checkbox

    prop = {"address": "123 Main St"}
    steps = [
        ({}, "right_person"),
        (_lead_after(occupancy="owner occupied"), "condition"),
        (_lead_after(occupancy="owner occupied", property_condition="roof"), "timeline"),
        (
            _lead_after(occupancy="owner occupied", property_condition="roof", timeline_urgency="asap"),
            "motivation",
        ),
        (
            _lead_after(
                occupancy="owner occupied",
                property_condition="roof",
                timeline_urgency="asap",
                motivation_level=8,
            ),
            "next_step",
        ),
    ]

    for lead, expected in steps:
        memory = worker.build_seller_memory(lead)
        assert select_missing_checkbox({}, memory, lead, prop) == expected, (
            f"ladder stalled at {expected}; bob would ask the same question on every call"
        )


def test_occupancy_learned_on_a_call_counts_even_when_property_data_is_silent():
    from bob.checkbox_selector import select_missing_checkbox

    lead = _lead_after(occupancy="tenant occupied")
    memory = worker.build_seller_memory(lead)

    assert select_missing_checkbox({}, memory, lead, {"address": "1 A St"}) != "occupancy"


def test_creative_finance_is_allowed_where_the_whitelist_says_it_should_be():
    from bob.avoidances_builder import build_avoidances

    cases = [
        ("preforeclosure", {"distress_type": "pre_foreclosure"}),
        ("unknown", {"free_and_clear": True}),
        ("unknown", {"absentee_owner": True}),
    ]
    for label, prop in cases:
        avoid = build_avoidances({}, label, 1, property_row=prop)
        assert "creative finance discussion" not in avoid, (
            f"{label}/{prop} is on the creative-finance whitelist but Bob still blocked it"
        )


def test_creative_finance_still_blocked_where_it_is_not_appropriate():
    from bob.avoidances_builder import build_avoidances

    avoid = build_avoidances({}, "probate", 1, property_row={"distress_type": "probate"})
    assert "creative finance discussion" in avoid


def test_pricing_and_legal_advice_are_always_avoided():
    from bob.avoidances_builder import build_avoidances

    for label in ("preforeclosure", "probate", "unknown", ""):
        avoid = build_avoidances({}, label, 1, property_row={})
        assert "pricing" in avoid
        assert "legal advice" in avoid


def test_the_ladder_matches_the_documented_priority_order():
    from bob.checkbox_selector import select_missing_checkbox
    from bob.contracts import CHECKBOX_PRIORITY

    prop = {"address": "1 A St"}
    known: dict = {"call_attempts": 1, "call_summary": "spoke"}
    satisfies = {
        "occupancy": ("occupancy", "owner occupied"),
        "condition": ("property_condition", "roof leaks"),
        "timeline": ("timeline_urgency", "asap"),
        "motivation": ("motivation_level", 8),
    }

    seen = []
    for _ in range(len(CHECKBOX_PRIORITY) + 1):
        box = select_missing_checkbox({}, worker.build_seller_memory(known), known, prop)
        seen.append(box)
        if box not in satisfies:
            break
        field, value = satisfies[box]
        known[field] = value

    for box in seen:
        assert box in CHECKBOX_PRIORITY, (
            f"{box} is not in contracts.CHECKBOX_PRIORITY — the ladder and the documented "
            "order have drifted apart"
        )

    positions = [CHECKBOX_PRIORITY.index(b) for b in seen]
    assert positions == sorted(positions), f"ladder went backwards: {seen}"
