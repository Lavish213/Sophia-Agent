from dataclasses import dataclass

import signalwire.rest

from backend.alerts.sms import handle_inbound_sms, send_sms
from backend.compliance.compliance import ComplianceEngine, ComplianceResult
from backend.lib import db


def _lead(**overrides):
    lead = {"id": "lead-1", "owner_phone": "2095551212"}
    lead.update(overrides)
    return lead


def test_send_sms_lead_not_found(monkeypatch):
    monkeypatch.setattr(db, "get_lead_by_id", lambda lead_id: None)
    result = send_sms("missing", "hey there")
    assert result["success"] is False
    assert result["reason"] == "lead_not_found"


def test_send_sms_no_phone(monkeypatch):
    monkeypatch.setattr(db, "get_lead_by_id", lambda lead_id: _lead(owner_phone=None))
    result = send_sms("lead-1", "hey there")
    assert result["success"] is False
    assert result["reason"] == "no_phone_on_file"


def test_send_sms_blocked_by_compliance(monkeypatch):
    monkeypatch.setattr(db, "get_lead_by_id", lambda lead_id: _lead())
    monkeypatch.setattr(
        ComplianceEngine, "check_sms_allowed",
        lambda self, lead_id: ComplianceResult(allowed=False, reason="opted_out"),
    )
    result = send_sms("lead-1", "hey there")
    assert result["success"] is False
    assert result["reason"] == "opted_out"


@dataclass
class _FakeMessage:
    sid: str = "SM123"


class _FakeMessages:
    def create(self, **kwargs):
        _FakeMessages.last_kwargs = kwargs
        return _FakeMessage()


class _FakeSignalwireClient:
    def __init__(self, *args, **kwargs):
        self.messages = _FakeMessages()


def test_send_sms_success(monkeypatch):
    monkeypatch.setattr(db, "get_lead_by_id", lambda lead_id: _lead())
    monkeypatch.setattr(
        ComplianceEngine, "check_sms_allowed",
        lambda self, lead_id: ComplianceResult(allowed=True, reason="ok"),
    )
    monkeypatch.setattr(signalwire.rest, "Client", _FakeSignalwireClient)
    recorded = {}
    monkeypatch.setattr(
        db, "insert_sms_message",
        lambda lead_id, direction, body, signalwire_message_sid=None, status="queued": recorded.update(
            lead_id=lead_id, direction=direction, body=body, sid=signalwire_message_sid,
        ),
    )

    result = send_sms("lead-1", "hey there")

    assert result["success"] is True
    assert result["message_sid"] == "SM123"
    assert recorded["direction"] == "outbound"
    assert recorded["sid"] == "SM123"


def test_handle_inbound_sms_no_match(monkeypatch):
    monkeypatch.setattr(db, "get_lead_by_owner_phone", lambda phone: None)
    action = handle_inbound_sms("2095551212", "STOP")
    assert action == "unmatched"


def test_handle_inbound_sms_stop_opts_out(monkeypatch):
    monkeypatch.setattr(db, "get_lead_by_owner_phone", lambda phone: _lead())
    monkeypatch.setattr(db, "insert_sms_message", lambda *a, **k: None)
    captured = {}
    monkeypatch.setattr(db, "update_lead_fields", lambda lead_id, fields: captured.update(fields))

    action = handle_inbound_sms("2095551212", "  Stop  ")

    assert action == "opted_out"
    assert captured["opted_out"] is True


def test_handle_inbound_sms_start_opts_back_in(monkeypatch):
    monkeypatch.setattr(db, "get_lead_by_owner_phone", lambda phone: _lead())
    monkeypatch.setattr(db, "insert_sms_message", lambda *a, **k: None)
    captured = {}
    monkeypatch.setattr(db, "update_lead_fields", lambda lead_id, fields: captured.update(fields))

    action = handle_inbound_sms("2095551212", "START")

    assert action == "opted_in"
    assert captured["opted_out"] is False


def test_handle_inbound_sms_other_text_just_logged(monkeypatch):
    monkeypatch.setattr(db, "get_lead_by_owner_phone", lambda phone: _lead())
    logged = {}
    monkeypatch.setattr(db, "insert_sms_message", lambda lead_id, direction, body, status="queued": logged.update(direction=direction, body=body))

    action = handle_inbound_sms("2095551212", "Is this a good time to call back?")

    assert action == "logged"
    assert logged["direction"] == "inbound"
