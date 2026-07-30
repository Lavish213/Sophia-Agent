from backend.lib import db
from backend.scout.convert import convert_reddit_match_to_lead


def _match(**overrides):
    match = {
        "id": "match-1",
        "reddit_id": "p1",
        "url": "https://reddit.com/r/Stockton/p1",
        "intent_label": "hot",
        "lead_id": None,
    }
    match.update(overrides)
    return match


def test_match_not_found(monkeypatch):
    monkeypatch.setattr(db, "get_reddit_match_by_id", lambda match_id: None)
    result = convert_reddit_match_to_lead("missing", "123 Main St", "2095551212")
    assert result["success"] is False
    assert result["reason"] == "match_not_found"


def test_already_converted(monkeypatch):
    monkeypatch.setattr(db, "get_reddit_match_by_id", lambda match_id: _match(lead_id="lead-1"))
    result = convert_reddit_match_to_lead("match-1", "123 Main St", "2095551212")
    assert result["success"] is False
    assert result["reason"] == "already_converted"


def test_successful_conversion_creates_property_contact_lead_and_links(monkeypatch):
    monkeypatch.setattr(db, "get_reddit_match_by_id", lambda match_id: _match())
    captured = {}

    def _fake_upsert_property(data):
        captured["property"] = data
        return "prop-1"

    def _fake_insert_contact(data):
        captured["contact"] = data

    def _fake_get_or_create_lead(property_id):
        return {"id": "lead-1"}

    lead_updates = {}

    def _fake_update_lead_fields(lead_id, fields):
        lead_updates.update(fields)

    linked = {}

    def _fake_link(match_id, lead_id):
        linked.update(match_id=match_id, lead_id=lead_id)

    monkeypatch.setattr(db, "upsert_property", _fake_upsert_property)
    monkeypatch.setattr(db, "insert_contact", _fake_insert_contact)
    monkeypatch.setattr(db, "get_or_create_lead", _fake_get_or_create_lead)
    monkeypatch.setattr(db, "update_lead_fields", _fake_update_lead_fields)
    monkeypatch.setattr(db, "link_reddit_match_to_lead", _fake_link)

    result = convert_reddit_match_to_lead(
        "match-1", "123 Main St", "2095551212", owner_name="Maria Gonzalez", owner_email="maria@example.com",
    )

    assert result["success"] is True
    assert result["lead_id"] == "lead-1"
    assert captured["property"]["distress_score"] == 75
    assert captured["property"]["source"] == "reddit"
    assert captured["contact"]["phone"] == "2095551212"
    assert lead_updates["owner_phone"] == "2095551212"
    assert lead_updates["owner_email"] == "maria@example.com"
    assert "reddit.com" in lead_updates["operator_notes"]
    assert linked == {"match_id": "match-1", "lead_id": "lead-1"}


def test_intent_label_maps_to_reasonable_distress_score(monkeypatch):
    monkeypatch.setattr(db, "get_reddit_match_by_id", lambda match_id: _match(intent_label="cold"))
    captured = {}
    monkeypatch.setattr(db, "upsert_property", lambda data: captured.update(data) or "prop-1")
    monkeypatch.setattr(db, "insert_contact", lambda data: None)
    monkeypatch.setattr(db, "get_or_create_lead", lambda property_id: {"id": "lead-1"})
    monkeypatch.setattr(db, "update_lead_fields", lambda lead_id, fields: None)
    monkeypatch.setattr(db, "link_reddit_match_to_lead", lambda match_id, lead_id: None)

    convert_reddit_match_to_lead("match-1", "123 Main St", "2095551212")

    assert captured["distress_score"] == 35
