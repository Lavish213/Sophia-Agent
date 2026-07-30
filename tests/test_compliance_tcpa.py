from datetime import datetime

import pytz

from backend.compliance.compliance import ComplianceEngine, is_calling_hours
from backend.lib import db
from backend.lib.config import get_settings

_PACIFIC = pytz.timezone("America/Los_Angeles")


def _lead(**overrides):
    lead = {
        "id": "lead-1",
        "owner_phone": "+12095551212",
        "opted_out": False,
        "dnc_blocked": False,
    }
    lead.update(overrides)
    return lead


def _at(hour, minute=0, month=6, day=15):
    return _PACIFIC.localize(datetime(2026, month, day, hour, minute))


def test_calling_hours_allows_midday():
    assert is_calling_hours(_at(13)) is True


def test_calling_hours_blocks_early_morning():
    assert is_calling_hours(_at(6)) is False


def test_calling_hours_blocks_late_night():
    assert is_calling_hours(_at(22)) is False


def test_calling_hours_boundaries_are_inclusive_start_exclusive_end():
    settings = get_settings()
    assert is_calling_hours(_at(settings.calling_hours_start)) is True
    assert is_calling_hours(_at(settings.calling_hours_end)) is False


def test_calling_hours_converts_a_utc_timestamp_to_pacific():
    utc_3am_pacific = pytz.utc.localize(datetime(2026, 6, 15, 10, 0))
    assert is_calling_hours(utc_3am_pacific) is False


def test_sms_is_blocked_outside_calling_hours(monkeypatch):
    monkeypatch.setattr(db, "get_lead_with_property", lambda lid: _lead())
    monkeypatch.setattr(db, "is_on_dnc_list", lambda phone: False)
    monkeypatch.setattr(
        "backend.compliance.compliance.is_calling_hours_for_phone", lambda phone, now=None: False
    )

    result = ComplianceEngine().check_sms_allowed("lead-1")

    assert result.allowed is False, "texting at 3am is a TCPA violation just like calling"
    assert result.reason == "outside_hours"


def test_sms_is_blocked_for_a_dnc_listed_number(monkeypatch):
    monkeypatch.setattr(db, "get_lead_with_property", lambda lid: _lead())
    monkeypatch.setattr(
        "backend.compliance.compliance.is_calling_hours_for_phone", lambda phone, now=None: True
    )
    monkeypatch.setattr(db, "is_on_dnc_list", lambda phone: True)

    result = ComplianceEngine().check_sms_allowed("lead-1")

    assert result.allowed is False, "a DNC-listed number must not be texted"
    assert result.reason == "dnc_list_match"


def test_sms_allowed_in_the_clear_case(monkeypatch):
    monkeypatch.setattr(db, "get_lead_with_property", lambda lid: _lead())
    monkeypatch.setattr(db, "is_on_dnc_list", lambda phone: False)
    monkeypatch.setattr(
        "backend.compliance.compliance.is_calling_hours_for_phone", lambda phone, now=None: True
    )

    result = ComplianceEngine().check_sms_allowed("lead-1")

    assert result.allowed is True


def test_sms_still_blocks_opted_out_lead(monkeypatch):
    monkeypatch.setattr(db, "get_lead_with_property", lambda lid: _lead(opted_out=True))
    result = ComplianceEngine().check_sms_allowed("lead-1")
    assert result.reason == "opted_out"


def test_compliance_fails_closed_when_the_database_errors(monkeypatch):
    def _boom(lead_id):
        raise RuntimeError("supabase unreachable")

    monkeypatch.setattr(db, "get_lead_with_property", _boom)

    assert ComplianceEngine().check_call_allowed("lead-1").allowed is False
    assert ComplianceEngine().check_sms_allowed("lead-1").allowed is False


def test_call_checks_the_secondary_phone_against_dnc(monkeypatch):
    lead = _lead(owner_phone="+12095551212", owner_phone_2="+12095559999")
    monkeypatch.setattr(db, "get_lead_with_property", lambda lid: lead)
    monkeypatch.setattr(
        "backend.compliance.compliance.is_calling_hours_for_phone", lambda phone, now=None: True
    )
    monkeypatch.setattr(db, "is_on_dnc_list", lambda phone: phone == "+12095559999")

    result = ComplianceEngine().check_call_allowed("lead-1")

    assert result.allowed is False
    assert result.reason == "dnc_list_match"
