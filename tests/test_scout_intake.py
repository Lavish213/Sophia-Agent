from backend.lib import db
from backend.scout import intake


def test_normalize_phone_handles_common_formats():
    assert intake.normalize_phone("(209) 555-1212") == "+12095551212"
    assert intake.normalize_phone("209-555-1212") == "+12095551212"
    assert intake.normalize_phone("+12095551212") == "+12095551212"
    assert intake.normalize_phone("12095551212") == "+12095551212"


def test_normalize_phone_rejects_junk():
    assert intake.normalize_phone(None) is None
    assert intake.normalize_phone("") is None
    assert intake.normalize_phone("555") is None


def test_phone_variants_includes_e164_and_bare():
    variants = intake.phone_variants("2095551212")
    assert "+12095551212" in variants
    assert "2095551212" in variants


def test_intake_lead_requires_some_identity():
    result = intake.intake_lead("web_form")
    assert result["success"] is False
    assert result["reason"] == "no_identity"


def _no_existing(monkeypatch):
    monkeypatch.setattr(db, "get_lead_by_owner_phone", lambda phone: None)
    monkeypatch.setattr(db, "get_lead_by_owner_email", lambda email: None)


def test_intake_lead_creates_property_contact_and_lead(monkeypatch):
    _no_existing(monkeypatch)
    captured = {}

    def _fake_upsert(data):
        captured["property"] = data
        return "prop-1"

    def _fake_contact(data):
        captured["contact"] = data

    updates = {}
    monkeypatch.setattr(db, "upsert_property", _fake_upsert)
    monkeypatch.setattr(db, "insert_contact", _fake_contact)
    monkeypatch.setattr(db, "get_or_create_lead", lambda pid: {"id": "lead-1"})
    monkeypatch.setattr(db, "update_lead_fields", lambda lid, f: updates.update(f))

    result = intake.intake_lead(
        "web_form",
        address="123 Main St",
        owner_name="Maria Gonzalez",
        owner_phone="(209) 555-1212",
        owner_email="Maria@Example.COM",
    )

    assert result["success"] is True
    assert result["created"] is True
    assert result["lead_id"] == "lead-1"
    assert captured["property"]["address"] == "123 Main St"
    assert captured["property"]["source"] == "web_form"
    assert captured["property"]["distress_score"] == 80
    assert captured["contact"]["phone"] == "+12095551212"
    assert updates["owner_phone"] == "+12095551212"
    assert updates["owner_email"] == "maria@example.com"


def test_intake_lead_dedupes_against_existing_lead_in_other_format(monkeypatch):
    existing = {"id": "lead-9", "property_id": "prop-9", "owner_phone": "2095551212"}

    def _by_phone(phone):
        return existing if phone == "2095551212" else None

    monkeypatch.setattr(db, "get_lead_by_owner_phone", _by_phone)
    monkeypatch.setattr(db, "get_lead_by_owner_email", lambda email: None)
    updates = {}
    monkeypatch.setattr(db, "update_lead_fields", lambda lid, f: updates.update(f))

    def _boom(*args, **kwargs):
        raise AssertionError("should not create a duplicate property")

    monkeypatch.setattr(db, "upsert_property", _boom)

    result = intake.intake_lead("inbound_call", owner_phone="+12095551212", notes="Called in")

    assert result["success"] is True
    assert result["created"] is False
    assert result["lead_id"] == "lead-9"
    assert updates["operator_notes"] == "Called in"


def test_intake_lead_without_address_uses_placeholder_and_synthetic_apn(monkeypatch):
    _no_existing(monkeypatch)
    captured = {}
    monkeypatch.setattr(db, "upsert_property", lambda d: captured.update(d) or "prop-2")
    monkeypatch.setattr(db, "insert_contact", lambda d: None)
    monkeypatch.setattr(db, "get_or_create_lead", lambda pid: {"id": "lead-2"})
    monkeypatch.setattr(db, "update_lead_fields", lambda lid, f: None)

    result = intake.intake_lead("inbound_call", owner_phone="2095551212")

    assert result["success"] is True
    assert "Address needed" in captured["address"]
    assert captured["apn"] == "inbound_call:+12095551212"
    assert captured["distress_score"] == 70


def test_intake_lead_appends_note_without_clobbering(monkeypatch):
    existing = {"id": "lead-3", "property_id": "p", "operator_notes": "First note"}
    monkeypatch.setattr(db, "get_lead_by_owner_phone", lambda phone: existing)
    monkeypatch.setattr(db, "get_lead_by_owner_email", lambda email: None)
    updates = {}
    monkeypatch.setattr(db, "update_lead_fields", lambda lid, f: updates.update(f))

    intake.intake_lead("inbound_sms", owner_phone="2095551212", notes="Second note")

    assert updates["operator_notes"] == "First note\nSecond note"


def test_intake_lead_does_not_duplicate_identical_note(monkeypatch):
    existing = {"id": "lead-4", "property_id": "p", "operator_notes": "Same note"}
    monkeypatch.setattr(db, "get_lead_by_owner_phone", lambda phone: existing)
    monkeypatch.setattr(db, "get_lead_by_owner_email", lambda email: None)
    updates = {}
    monkeypatch.setattr(db, "update_lead_fields", lambda lid, f: updates.update(f))

    intake.intake_lead("inbound_sms", owner_phone="2095551212", notes="Same note")

    assert updates.get("operator_notes", "Same note") == "Same note"
