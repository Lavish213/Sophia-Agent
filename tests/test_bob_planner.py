from bob.avoidances_builder import build_avoidances
from bob.brief_generator import generate_call_brief
from bob.checkbox_selector import select_missing_checkbox
from bob.escalation_rules import build_escalation_rules
from bob.objective_selector import get_objective
from bob.worker import get_situation_label


def test_checkbox_right_person_first_when_no_prior_calls():
    box = select_missing_checkbox({}, {"call_summaries": []}, {}, {"address": "123 Main St"})
    assert box == "right_person"


def test_checkbox_property_confirmed_when_no_address():
    memory = {"call_summaries": [{"x": 1}]}
    box = select_missing_checkbox({}, memory, {}, {})
    assert box == "property_confirmed"


def test_checkbox_progresses_to_next_step_when_all_known():
    memory = {
        "call_summaries": [{"x": 1}],
        "hot_topics": ["roof"],
        "timeline_mentioned": True,
        "motivation_level": 7,
    }
    prop = {"address": "123 Main St", "vacant": True}
    box = select_missing_checkbox({}, memory, {}, prop)
    assert box == "next_step"


def test_objective_maps_checkbox():
    assert "owner" in get_objective("right_person")


def test_objective_falls_back_to_phase():
    assert get_objective("unknown_box", phase="QUALIFY") == "ask if they would be open to a quick walkthrough"


def test_avoidances_always_includes_pricing_and_legal():
    avoid = build_avoidances({}, "unknown", 0)
    assert "pricing" in avoid
    assert "legal advice" in avoid


def test_avoidances_adds_situation_specific():
    avoid = build_avoidances({}, "pre_foreclosure", 0)
    assert "foreclosure guidance" in avoid


def test_avoidances_creative_finance_allowed_for_free_and_clear():
    intel = {"property_profile": {"distress_type": "free_and_clear"}}
    avoid = build_avoidances(intel, "unknown", 0)
    assert "creative finance discussion" not in avoid


def test_avoidances_blocks_creative_finance_by_default():
    avoid = build_avoidances({}, "unknown", 0)
    assert "creative finance discussion" in avoid


def test_escalation_always_includes_dnc_and_legal():
    rules = build_escalation_rules({}, "unknown", {})
    assert "stop calling or DNC request" in rules
    assert "legal or lawsuit threat" in rules


def test_escalation_high_motivation_triggers_human_takeover():
    rules = build_escalation_rules({}, "unknown", {"motivation_level": 9})
    assert any("human takeover" in r for r in rules)


def test_get_situation_label_matches_distress_type():
    assert get_situation_label({"distress_type": "pre_foreclosure"}) == "preforeclosure"
    assert get_situation_label({"distress_type": "unknown"}) == "unknown"


def test_generate_call_brief_first_call_returns_verify_phase():
    brief = generate_call_brief(
        lead_id="lead-1",
        lead={},
        prop={"distress_type": "pre_foreclosure"},
        intel_packet={},
        seller_memory={},
        situation_label="preforeclosure",
    )
    assert brief is not None
    assert brief.phase == "VERIFY"
    assert brief.missing_box == "right_person"
    assert brief.mood == "distressed"
    assert "foreclosure guidance" in brief.avoid


def test_generate_call_brief_returns_none_on_internal_error(monkeypatch):
    import bob.brief_generator as bg
    monkeypatch.setattr(bg, "select_missing_checkbox", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    brief = generate_call_brief("lead-1", {}, {}, {}, {})
    assert brief is None
