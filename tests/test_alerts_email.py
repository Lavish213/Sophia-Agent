from dataclasses import dataclass, field

import sendgrid

from backend.alerts.email import send_email
from backend.lib import db


def _lead(**overrides):
    lead = {"id": "lead-1", "owner_email": "seller@example.com", "opted_out": False, "email_opted_out": False}
    lead.update(overrides)
    return lead


def test_send_email_lead_not_found(monkeypatch):
    monkeypatch.setattr(db, "get_lead_by_id", lambda lead_id: None)
    result = send_email("missing", "Subject", "Body")
    assert result["success"] is False
    assert result["reason"] == "lead_not_found"


def test_send_email_no_email_on_file(monkeypatch):
    monkeypatch.setattr(db, "get_lead_by_id", lambda lead_id: _lead(owner_email=None))
    result = send_email("lead-1", "Subject", "Body")
    assert result["success"] is False
    assert result["reason"] == "no_email_on_file"


def test_send_email_blocked_by_opt_out(monkeypatch):
    monkeypatch.setattr(db, "get_lead_by_id", lambda lead_id: _lead(opted_out=True))
    result = send_email("lead-1", "Subject", "Body")
    assert result["success"] is False
    assert result["reason"] == "opted_out"


def test_send_email_blocked_by_email_opt_out(monkeypatch):
    monkeypatch.setattr(db, "get_lead_by_id", lambda lead_id: _lead(email_opted_out=True))
    result = send_email("lead-1", "Subject", "Body")
    assert result["success"] is False
    assert result["reason"] == "opted_out"


@dataclass
class _FakeResponse:
    status_code: int = 202
    headers: dict = field(default_factory=lambda: {"X-Message-Id": "msg-123"})


class _FakeSendGridClient:
    def __init__(self, api_key):
        pass

    def send(self, message):
        return _FakeResponse()


def test_send_email_success(monkeypatch):
    monkeypatch.setattr(db, "get_lead_by_id", lambda lead_id: _lead())
    monkeypatch.setattr(sendgrid, "SendGridAPIClient", _FakeSendGridClient)
    recorded = {}
    monkeypatch.setattr(
        db, "insert_email_message",
        lambda lead_id, direction, subject, body, provider_message_id=None, status="queued": recorded.update(
            lead_id=lead_id, subject=subject, provider_message_id=provider_message_id,
        ),
    )

    result = send_email("lead-1", "Quick question about your property", "Hey, this is Sophia...")

    assert result["success"] is True
    assert result["message_id"] == "msg-123"
    assert recorded["subject"] == "Quick question about your property"
