import pytest

from backend.alerts import followup
from backend.lib import db


@pytest.fixture(autouse=True)
def _no_prior_reply(monkeypatch):
    monkeypatch.setattr(db, "lead_has_replied_by_sms", lambda lead_id: False)


def _lead(**overrides):
    lead = {
        "id": "lead-1",
        "owner_phone": "2095551212",
        "owner_email": None,
        "appointment_at": None,
        "properties": {"owner_name": "Maria Gonzalez", "address": "123 Main St"},
    }
    lead.update(overrides)
    return lead


def test_no_disposition_does_nothing():
    result = followup.send_post_call_followup("lead-1", "call-1", None)
    assert result == {"sms": None, "email": None}


def test_lead_not_found_does_nothing(monkeypatch):
    monkeypatch.setattr(db, "get_lead_with_property", lambda lead_id: None)
    result = followup.send_post_call_followup("missing", "call-1", "HOT")
    assert result == {"sms": None, "email": None}


def test_no_answer_sends_sms_and_email(monkeypatch):
    lead = _lead(owner_email="seller@example.com")
    monkeypatch.setattr(db, "get_lead_with_property", lambda lead_id: lead)
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
    assert "Maria" in sms_calls[0]
    assert "123 Main St" in sms_calls[0]
    assert "Maria" in email_calls[0][1]


def test_no_answer_without_email_skips_email(monkeypatch):
    monkeypatch.setattr(db, "get_lead_with_property", lambda lead_id: _lead())
    monkeypatch.setattr(followup, "send_sms", lambda lead_id, body: {"success": True})
    result = followup.send_post_call_followup("lead-1", "call-1", "busy")
    assert result["email"] is None


def test_hot_disposition_sends_confirmation_when_appointment_booked(monkeypatch):
    monkeypatch.setattr(db, "get_lead_with_property", lambda lead_id: _lead(appointment_at="2026-08-01T15:00:00Z"))
    sms_calls = []
    monkeypatch.setattr(followup, "send_sms", lambda lead_id, body: sms_calls.append(body) or {"success": True})

    followup.send_post_call_followup("lead-1", "call-1", "HOT")

    assert "all set for" in sms_calls[0]
    assert "Aug 1" in sms_calls[0]


def test_cold_disposition_sends_nothing(monkeypatch):
    monkeypatch.setattr(db, "get_lead_with_property", lambda lead_id: _lead())
    result = followup.send_post_call_followup("lead-1", "call-1", "COLD")
    assert result == {"sms": None, "email": None}


def test_dead_disposition_sends_nothing(monkeypatch):
    monkeypatch.setattr(db, "get_lead_with_property", lambda lead_id: _lead())
    result = followup.send_post_call_followup("lead-1", "call-1", "DEAD")
    assert result == {"sms": None, "email": None}


def test_placeholder_address_is_not_read_aloud_to_the_seller(monkeypatch):
    lead = _lead(properties={"owner_name": "", "address": "Address needed - inbound_call from +1209"})
    monkeypatch.setattr(db, "get_lead_with_property", lambda lead_id: lead)
    sms_calls = []
    monkeypatch.setattr(followup, "send_sms", lambda lid, body: sms_calls.append(body) or {"success": True})

    followup.send_post_call_followup("lead-1", "call-1", "no-answer")

    assert "Address needed" not in sms_calls[0]
    assert "your property" in sms_calls[0]


def test_missing_owner_name_still_reads_naturally(monkeypatch):
    lead = _lead(properties={"owner_name": None, "address": "123 Main St"})
    monkeypatch.setattr(db, "get_lead_with_property", lambda lead_id: lead)
    sms_calls = []
    monkeypatch.setattr(followup, "send_sms", lambda lid, body: sms_calls.append(body) or {"success": True})

    followup.send_post_call_followup("lead-1", "call-1", "no-answer")

    assert sms_calls[0].startswith("Hey, it's Sophia")


def test_voicemail_disposition_texts_about_the_voicemail(monkeypatch):
    monkeypatch.setattr(db, "get_lead_with_property", lambda lead_id: _lead())
    sms_calls = []
    monkeypatch.setattr(followup, "send_sms", lambda lid, body: sms_calls.append(body) or {"success": True})

    followup.send_post_call_followup("lead-1", "call-1", "voicemail")

    assert "voicemail" in sms_calls[0]
    assert "Maria" in sms_calls[0]


def test_appointment_formatting_survives_bad_timestamps():
    assert followup.format_appointment(None) == ""
    assert followup.format_appointment("not-a-date") == ""
    assert "Aug 1" in followup.format_appointment("2026-08-01T15:00:00Z")


def test_first_text_always_carries_an_opt_out(monkeypatch):
    for disposition in ("no-answer", "voicemail", "HOT"):
        monkeypatch.setattr(db, "get_lead_with_property", lambda lead_id: _lead())
        sms_calls = []
        monkeypatch.setattr(followup, "send_sms", lambda lid, body: sms_calls.append(body) or {"success": True})
        monkeypatch.setattr(followup, "send_email", lambda lid, s, b: {"success": True})

        followup.send_post_call_followup("lead-1", "call-1", disposition)

        assert sms_calls, f"{disposition} sent no text"
        assert "STOP" in sms_calls[0], f"{disposition} text has no opt-out"


def test_opt_out_footer_drops_once_the_seller_has_replied(monkeypatch):
    monkeypatch.setattr(db, "get_lead_with_property", lambda lead_id: _lead())
    monkeypatch.setattr(db, "lead_has_replied_by_sms", lambda lead_id: True)
    sms_calls = []
    monkeypatch.setattr(followup, "send_sms", lambda lid, body: sms_calls.append(body) or {"success": True})

    followup.send_post_call_followup("lead-1", "call-1", "voicemail")

    assert "STOP" not in sms_calls[0], (
        "once someone texts back it is a conversation, and a compliance footer on every reply "
        "is the clearest tell that nobody is really there"
    )


def test_texts_are_short_enough_to_read_as_human():
    lead = _lead()
    for body in (followup._no_answer_sms_body(lead), followup._voicemail_sms_body(lead)):
        assert len(body) < 175, f"{len(body)} chars reads like a marketing blast"


def test_outreach_texts_end_with_a_question():
    lead = _lead()
    for body in (followup._no_answer_sms_body(lead), followup._voicemail_sms_body(lead)):
        assert body.rstrip().endswith("?"), "a text that does not ask anything does not get a reply"
