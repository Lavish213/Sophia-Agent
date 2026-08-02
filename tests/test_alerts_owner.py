from backend.alerts import owner
from backend.lib import db
from backend.lib.config import get_settings


def _lead(**overrides):
    lead = {
        "id": "lead-1",
        "owner_phone": "+12095551212",
        "call_summary": "Behind on payments, wants out before the auction.",
        "properties": {"address": "123 Main St"},
    }
    lead.update(overrides)
    return lead


def test_no_owner_phone_configured_is_reported_not_crashed(monkeypatch):
    monkeypatch.delenv("OWNER_PHONE", raising=False)
    get_settings.cache_clear()
    try:
        result = owner.notify_owner("anything")
        assert result["success"] is False
        assert result["reason"] == "no_owner_phone"
    finally:
        get_settings.cache_clear()


def test_hot_lead_alert_names_the_property_and_the_seller(monkeypatch):
    monkeypatch.setattr(db, "get_lead_with_property", lambda lid: _lead())
    sent = {}
    monkeypatch.setattr(owner, "notify_owner", lambda body: sent.update(body=body) or {"success": True})

    owner.alert_hot_lead("lead-1")

    assert "HOT" in sent["body"]
    assert "123 Main St" in sent["body"]
    assert "+12095551212" in sent["body"]
    assert "auction" in sent["body"]


def test_escalation_alert_carries_the_reason(monkeypatch):
    monkeypatch.setattr(db, "get_lead_with_property", lambda lid: _lead())
    sent = {}
    monkeypatch.setattr(owner, "notify_owner", lambda body: sent.update(body=body) or {"success": True})

    owner.alert_escalation("lead-1", "asked to speak to a human")

    assert "Callback requested" in sent["body"]
    assert "asked to speak to a human" in sent["body"]


def test_appointment_alert_states_when(monkeypatch):
    monkeypatch.setattr(db, "get_lead_with_property", lambda lid: _lead())
    sent = {}
    monkeypatch.setattr(owner, "notify_owner", lambda body: sent.update(body=body) or {"success": True})

    owner.alert_appointment("lead-1", "2026-08-01T15:00:00Z")

    assert "Walkthrough booked" in sent["body"]
    assert "Aug 1" in sent["body"]


def test_placeholder_address_falls_back_to_the_phone(monkeypatch):
    lead = _lead(properties={"address": "Address needed - inbound_call from +1209"})
    monkeypatch.setattr(db, "get_lead_with_property", lambda lid: lead)
    sent = {}
    monkeypatch.setattr(owner, "notify_owner", lambda body: sent.update(body=body) or {"success": True})

    owner.alert_hot_lead("lead-1")

    assert "Address needed" not in sent["body"]


def test_alert_on_a_missing_lead_does_not_crash(monkeypatch):
    monkeypatch.setattr(db, "get_lead_with_property", lambda lid: None)
    assert owner.alert_hot_lead("missing")["reason"] == "lead_not_found"
    assert owner.alert_escalation("missing", "x")["reason"] == "lead_not_found"


def test_alerts_are_truncated_to_one_reasonable_message(monkeypatch):
    lead = _lead(call_summary="x" * 2000)
    monkeypatch.setattr(db, "get_lead_with_property", lambda lid: lead)
    sent = {}
    monkeypatch.setattr(owner, "notify_owner", lambda body: sent.update(body=body) or {"success": True})

    owner.alert_hot_lead("lead-1")

    assert len(sent["body"]) <= 600
