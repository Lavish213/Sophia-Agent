from backend.lib import db
from backend.voice.context import build_property_context_str, preload_call_context, preload_outbound_context


def _lead(**overrides):
    lead = {
        "id": "lead-1",
        "motivation_level": None,
        "price_floor": None,
        "timeline_urgency": None,
        "call_summary": None,
        "properties": {
            "address": "123 Main St, Stockton, CA",
            "distress_type": "pre_foreclosure",
            "estimated_arv": 20000000,
            "mao": 11500000,
            "owner_name": "Maria Gonzalez",
        },
    }
    lead.update(overrides)
    return lead


def test_context_str_includes_address_and_offer_range():
    text = build_property_context_str(_lead())
    assert "123 Main St" in text
    assert "$200,000" in text
    assert "$115,000" in text


def test_context_str_includes_prior_call_facts():
    lead = _lead(
        motivation_level=8,
        price_floor=15000000,
        timeline_urgency="asap",
        call_summary="Wants to sell fast, divorce.",
    )
    text = build_property_context_str(lead)
    assert "8/10" in text
    assert "$150,000" in text
    assert "asap" in text
    assert "divorce" in text


def test_context_str_handles_no_data():
    text = build_property_context_str({"properties": {}})
    assert "No prior information" in text


def test_preload_call_context_creates_lead_for_unknown_caller(monkeypatch):
    monkeypatch.setattr(db, "get_lead_by_owner_phone", lambda phone: None)
    monkeypatch.setattr(db, "get_lead_by_owner_email", lambda email: None)
    captured = {}
    monkeypatch.setattr(db, "upsert_property", lambda data: captured.update(data) or "prop-new")
    monkeypatch.setattr(db, "insert_contact", lambda data: None)
    monkeypatch.setattr(db, "get_or_create_lead", lambda pid: {"id": "lead-new"})
    monkeypatch.setattr(db, "update_lead_fields", lambda lid, fields: None)
    monkeypatch.setattr(
        db, "get_lead_with_property", lambda lid: {"id": "lead-new", "properties": {}}
    )

    ctx = preload_call_context("2095551212")

    assert ctx["lead_id"] == "lead-new"
    assert captured["source"] == "inbound_call"


def test_preload_call_context_no_phone_stays_anonymous(monkeypatch):
    ctx = preload_call_context("")
    assert ctx["lead"] is None
    assert ctx["lead_id"] is None
    assert ctx["owner_first_name"] == "there"


def test_preload_call_context_found(monkeypatch):
    monkeypatch.setattr(db, "get_lead_by_owner_phone", lambda phone: _lead())
    ctx = preload_call_context("2095551212")
    assert ctx["lead_id"] == "lead-1"
    assert ctx["owner_first_name"] == "Maria"
    assert "123 Main St" in ctx["property_context_str"]


def test_preload_call_context_empty_phone_skips_lookup(monkeypatch):
    called = {"count": 0}
    def _lookup(phone):
        called["count"] += 1
    monkeypatch.setattr(db, "get_lead_by_owner_phone", _lookup)
    ctx = preload_call_context("")
    assert called["count"] == 0
    assert ctx["lead"] is None


def test_preload_outbound_context_found(monkeypatch):
    monkeypatch.setattr(db, "get_lead_with_property", lambda lead_id: _lead())
    ctx = preload_outbound_context("lead-1")
    assert ctx["owner_first_name"] == "Maria"


def test_preload_outbound_context_missing_lead(monkeypatch):
    monkeypatch.setattr(db, "get_lead_with_property", lambda lead_id: None)
    ctx = preload_outbound_context("missing")
    assert ctx["lead"] is None
    assert ctx["lead_id"] == "missing"
