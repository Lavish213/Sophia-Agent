from backend.alerts import followup
from backend.lib import db


def _lead(**overrides):
    lead = {"id": "lead-1", "owner_phone": "2095551212", "owner_email": None, "appointment_at": None}
    lead.update(overrides)
    return lead


def test_no_disposition_does_nothing():
    result = followup.send_post_call_followup("lead-1", "call-1", None)
    assert result == {"sms": None, "email": None}


def test_lead_not_found_does_nothing(monkeypatch):
    monkeypatch.setattr(db, "get_lead_by_id", lambda lead_id: None)
    result = followup.send_post_call_followup("missing", "call-1", "HOT")
    assert result == {"sms": None, "email": None}


def test_no_answer_sends_sms_and_email(monkeypatch):
    lead = _lead(owner_email="seller@example.com", owner_name="Maria Gonzalez")
    monkeypatch.setattr(db, "get_lead_by_id", lambda lead_id: lead)
    sms_calls = []
    email_calls = []

    def _fake_send_sms(lead_id, body):
        sms_calls.append(body)
        return {"success": True}

    def _fake_send_email(lead_id, subject, body):
        email_calls.append((subject, body))
        return {"success": True}

    monkeypatch.setattr(followup, "send_sms", _fake_send_sms)
    monkeypatch.setattr(followup, "send_email", _fake_send_email)

    result = followup.send_post_call_followup("lead-1", "call-1", "no-answer")

    assert result["sms"]["success"] is True
    assert result["email"]["success"] is True
    assert "Sophia" in sms_calls[0]
    assert "Maria" in email_calls[0][1]


def test_no_answer_without_email_skips_email(monkeypatch):
    monkeypatch.setattr(db, "get_lead_by_id", lambda lead_id: _lead())
    monkeypatch.setattr(followup, "send_sms", lambda lead_id, body: {"success": True})
    result = followup.send_post_call_followup("lead-1", "call-1", "busy")
    assert result["email"] is None


def test_hot_disposition_sends_confirmation_when_appointment_booked(monkeypatch):
    monkeypatch.setattr(db, "get_lead_by_id", lambda lead_id: _lead(appointment_at="2026-08-01T15:00:00Z"))
    sms_calls = []
    monkeypatch.setattr(followup, "send_sms", lambda lead_id, body: sms_calls.append(body) or {"success": True})

    followup.send_post_call_followup("lead-1", "call-1", "HOT")

    assert "Confirming" in sms_calls[0]


def test_cold_disposition_sends_nothing(monkeypatch):
    monkeypatch.setattr(db, "get_lead_by_id", lambda lead_id: _lead())
    result = followup.send_post_call_followup("lead-1", "call-1", "COLD")
    assert result == {"sms": None, "email": None}


def test_dead_disposition_sends_nothing(monkeypatch):
    monkeypatch.setattr(db, "get_lead_by_id", lambda lead_id: _lead())
    result = followup.send_post_call_followup("lead-1", "call-1", "DEAD")
    assert result == {"sms": None, "email": None}
