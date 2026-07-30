from dataclasses import dataclass

import signalwire.rest

from backend.compliance.compliance import ComplianceEngine, ComplianceResult
from backend.lib import db
from backend.voice.outbound import place_outbound_call


def _lead(**overrides):
    lead = {"id": "lead-1", "owner_phone": "2095551212", "properties": {}}
    lead.update(overrides)
    return lead


def test_lead_not_found(monkeypatch):
    monkeypatch.setattr(db, "get_lead_with_property", lambda lead_id: None)
    result = place_outbound_call("missing")
    assert result["success"] is False
    assert result["reason"] == "lead_not_found"


def test_no_phone_on_file(monkeypatch):
    monkeypatch.setattr(db, "get_lead_with_property", lambda lead_id: _lead(owner_phone=None))
    result = place_outbound_call("lead-1")
    assert result["success"] is False
    assert result["reason"] == "no_phone_on_file"


def test_blocked_by_compliance(monkeypatch):
    monkeypatch.setattr(db, "get_lead_with_property", lambda lead_id: _lead())
    monkeypatch.setattr(
        ComplianceEngine, "check_call_allowed",
        lambda self, lead_id: ComplianceResult(allowed=False, reason="outside_hours"),
    )
    result = place_outbound_call("lead-1")
    assert result["success"] is False
    assert result["reason"] == "outside_hours"


@dataclass
class _FakeCall:
    sid: str = "CA123"


class _FakeCalls:
    def create(self, **kwargs):
        _FakeCalls.last_kwargs = kwargs
        return _FakeCall()


class _FakeSignalwireClient:
    def __init__(self, *args, **kwargs):
        self.calls = _FakeCalls()


def test_places_call_when_allowed(monkeypatch):
    monkeypatch.setattr(db, "get_lead_with_property", lambda lead_id: _lead())
    monkeypatch.setattr(
        ComplianceEngine, "check_call_allowed",
        lambda self, lead_id: ComplianceResult(allowed=True, reason="ok"),
    )
    monkeypatch.setattr(signalwire.rest, "Client", _FakeSignalwireClient)
    recorded = {}
    monkeypatch.setattr(db, "insert_call", lambda data: recorded.update(data) or "call-row-1")

    result = place_outbound_call("lead-1")

    assert result["success"] is True
    assert result["call_sid"] == "CA123"
    assert _FakeCalls.last_kwargs["to"] == "2095551212"
    assert recorded["signalwire_call_id"] == "CA123"
    assert recorded["direction"] == "outbound"


def test_places_call_includes_status_callback(monkeypatch):
    monkeypatch.setattr(db, "get_lead_with_property", lambda lead_id: _lead())
    monkeypatch.setattr(
        ComplianceEngine, "check_call_allowed",
        lambda self, lead_id: ComplianceResult(allowed=True, reason="ok"),
    )
    monkeypatch.setattr(signalwire.rest, "Client", _FakeSignalwireClient)
    monkeypatch.setattr(db, "insert_call", lambda data: "call-row-1")

    place_outbound_call("lead-1")

    assert "status_callback" in _FakeCalls.last_kwargs
    assert _FakeCalls.last_kwargs["status_callback"].endswith("/api/voice/status")
