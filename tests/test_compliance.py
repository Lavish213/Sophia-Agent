from datetime import datetime

import pytz

import backend.lib.db as db
from backend.compliance.compliance import ComplianceEngine, is_calling_hours


def _lead(**overrides):
    lead = {
        "id": "lead-1",
        "owner_phone": "2095551212",
        "owner_phone_2": None,
        "opted_out": False,
        "dnc_blocked": False,
    }
    lead.update(overrides)
    return lead


def _daytime_pacific():
    pacific = pytz.timezone("America/Los_Angeles")
    return pacific.localize(datetime(2026, 7, 30, 14, 0))


def _nighttime_pacific():
    pacific = pytz.timezone("America/Los_Angeles")
    return pacific.localize(datetime(2026, 7, 30, 23, 30))


def test_calling_hours_true_at_2pm():
    assert is_calling_hours(_daytime_pacific()) is True


def test_calling_hours_false_at_11pm():
    assert is_calling_hours(_nighttime_pacific()) is False


def test_blocks_opted_out_lead(monkeypatch):
    monkeypatch.setattr(db, "get_lead_with_property", lambda lead_id: _lead(opted_out=True))
    result = ComplianceEngine().check_call_allowed("lead-1")
    assert result.allowed is False
    assert result.reason == "opted_out"


def test_blocks_dnc_blocked_lead(monkeypatch):
    monkeypatch.setattr(db, "get_lead_with_property", lambda lead_id: _lead(dnc_blocked=True))
    result = ComplianceEngine().check_call_allowed("lead-1")
    assert result.allowed is False
    assert result.reason == "dnc_blocked"


def test_blocks_lead_not_found(monkeypatch):
    monkeypatch.setattr(db, "get_lead_with_property", lambda lead_id: None)
    result = ComplianceEngine().check_call_allowed("missing")
    assert result.allowed is False
    assert result.reason == "lead_not_found"


def test_blocks_number_on_dnc_list(monkeypatch):
    monkeypatch.setattr(db, "get_lead_with_property", lambda lead_id: _lead())
    monkeypatch.setattr(db, "is_on_dnc_list", lambda phone: phone == "2095551212")
    import backend.compliance.compliance as compliance_module
    monkeypatch.setattr(compliance_module, "is_calling_hours", lambda: True)
    result = ComplianceEngine().check_call_allowed("lead-1")
    assert result.allowed is False
    assert result.reason == "dnc_list_match"


def test_allows_clean_lead_during_hours(monkeypatch):
    monkeypatch.setattr(db, "get_lead_with_property", lambda lead_id: _lead())
    monkeypatch.setattr(db, "is_on_dnc_list", lambda phone: False)
    import backend.compliance.compliance as compliance_module
    monkeypatch.setattr(compliance_module, "is_calling_hours", lambda: True)
    result = ComplianceEngine().check_call_allowed("lead-1")
    assert result.allowed is True


def test_fails_closed_on_exception(monkeypatch):
    def _raise(lead_id):
        raise RuntimeError("db unreachable")
    monkeypatch.setattr(db, "get_lead_with_property", _raise)
    result = ComplianceEngine().check_call_allowed("lead-1")
    assert result.allowed is False
    assert result.reason == "check_failed_blocking"


def test_sms_blocks_opted_out(monkeypatch):
    monkeypatch.setattr(db, "get_lead_with_property", lambda lead_id: _lead(opted_out=True))
    result = ComplianceEngine().check_sms_allowed("lead-1")
    assert result.allowed is False
    assert result.reason == "opted_out"
