from backend.lib import db
from backend.lib.config import get_settings
from backend.scout import skiptrace


def _configure(monkeypatch, key="test-key"):
    monkeypatch.setenv("BATCHDATA_API_KEY", key)
    get_settings.cache_clear()


def test_not_configured_without_key(monkeypatch):
    monkeypatch.delenv("BATCHDATA_API_KEY", raising=False)
    get_settings.cache_clear()
    try:
        assert skiptrace.is_configured() is False
        assert skiptrace.skip_trace_address("123 Main St", "Stockton", "CA", "95202") == {}
        assert skiptrace.enrich_lead("lead-1")["reason"] == "not_configured"
    finally:
        get_settings.cache_clear()


def test_extract_contacts_empty():
    result = skiptrace.extract_contacts(None)
    assert result == {"phones": [], "emails": [], "name": None}


def test_extract_contacts_persons_shape():
    payload = {
        "persons": [
            {
                "name": {"first": "Maria", "last": "Gonzalez"},
                "phoneNumbers": [
                    {"number": "209-555-1212", "type": "Landline"},
                    {"number": "(209) 555-3434", "type": "Mobile"},
                ],
                "emails": [{"email": "Maria@Example.COM"}],
            }
        ]
    }
    contacts = skiptrace.extract_contacts(payload)
    assert contacts["name"] == "Maria Gonzalez"
    assert contacts["phones"][0]["phone"] == "+12095553434"
    assert contacts["phones"][0]["is_mobile"] is True
    assert contacts["emails"] == ["maria@example.com"]


def test_extract_contacts_flat_shape_with_string_entries():
    payload = {
        "firstName": "Bob",
        "lastName": "Smith",
        "phones": ["2095551212"],
        "emails": ["bob@example.com"],
    }
    contacts = skiptrace.extract_contacts(payload)
    assert contacts["name"] == "Bob Smith"
    assert contacts["phones"][0]["phone"] == "+12095551212"
    assert contacts["emails"] == ["bob@example.com"]


def test_extract_contacts_dedupes_and_skips_invalid():
    payload = {
        "persons": [
            {"phoneNumbers": [{"number": "2095551212"}, {"number": "+12095551212"}, {"number": "555"}]}
        ]
    }
    contacts = skiptrace.extract_contacts(payload)
    assert len(contacts["phones"]) == 1


def test_extract_contacts_sorts_mobile_first_and_dnc_last():
    payload = {
        "persons": [
            {
                "phoneNumbers": [
                    {"number": "2095551111", "type": "Landline"},
                    {"number": "2095552222", "type": "Mobile", "dnc": True},
                    {"number": "2095553333", "type": "Mobile"},
                ]
            }
        ]
    }
    phones = skiptrace.extract_contacts(payload)["phones"]
    assert phones[0]["phone"] == "+12095553333"
    assert phones[-1]["dnc"] is True


def test_enrich_lead_skips_lead_that_already_has_phone(monkeypatch):
    _configure(monkeypatch)
    try:
        monkeypatch.setattr(
            db, "get_lead_with_property", lambda lid: {"id": lid, "owner_phone": "+12095551212"}
        )
        assert skiptrace.enrich_lead("lead-1")["reason"] == "already_has_phone"
    finally:
        get_settings.cache_clear()


def test_enrich_lead_skips_placeholder_address(monkeypatch):
    _configure(monkeypatch)
    try:
        lead = {"id": "lead-1", "properties": {"address": "Address needed - inbound_call from +1209"}}
        monkeypatch.setattr(db, "get_lead_with_property", lambda lid: lead)
        assert skiptrace.enrich_lead("lead-1")["reason"] == "no_usable_address"
    finally:
        get_settings.cache_clear()


def test_enrich_lead_writes_phone_back(monkeypatch):
    _configure(monkeypatch)
    try:
        lead = {
            "id": "lead-1",
            "property_id": "prop-1",
            "properties": {"address": "123 Main St", "city": "Stockton", "state": "CA", "zip": "95202"},
        }
        monkeypatch.setattr(db, "get_lead_with_property", lambda lid: lead)
        monkeypatch.setattr(
            skiptrace,
            "skip_trace_address",
            lambda a, c, s, z: {"persons": [{"phoneNumbers": [{"number": "2095553434", "type": "Mobile"}]}]},
        )
        monkeypatch.setattr(skiptrace, "is_phone_blocked", lambda phone: False)
        updates = {}
        monkeypatch.setattr(db, "update_lead_fields", lambda lid, f: updates.update(f))
        monkeypatch.setattr(db, "insert_contact", lambda d: None)

        result = skiptrace.enrich_lead("lead-1")

        assert result["success"] is True
        assert updates["owner_phone"] == "+12095553434"
    finally:
        get_settings.cache_clear()


def test_enrich_lead_blocks_dnc_phone_and_records_it(monkeypatch):
    _configure(monkeypatch)
    try:
        lead = {
            "id": "lead-1",
            "property_id": "prop-1",
            "properties": {"address": "123 Main St", "city": "Stockton", "state": "CA", "zip": "95202"},
        }
        monkeypatch.setattr(db, "get_lead_with_property", lambda lid: lead)
        monkeypatch.setattr(
            skiptrace,
            "skip_trace_address",
            lambda a, c, s, z: {"persons": [{"phoneNumbers": [{"number": "2095553434"}]}]},
        )
        monkeypatch.setattr(skiptrace, "is_phone_blocked", lambda phone: True)
        recorded = {}
        monkeypatch.setattr(db, "add_to_dnc_list", lambda p, r: recorded.update(phone=p, reason=r))

        def _should_not_update(lid, fields):
            raise AssertionError("must not write a blocked phone onto the lead")

        monkeypatch.setattr(db, "update_lead_fields", _should_not_update)

        result = skiptrace.enrich_lead("lead-1")

        assert result["success"] is False
        assert result["reason"] == "phone_blocked"
        assert recorded["phone"] == "+12095553434"
    finally:
        get_settings.cache_clear()


def test_enrich_lead_rejects_all_dnc_results(monkeypatch):
    _configure(monkeypatch)
    try:
        lead = {
            "id": "lead-1",
            "property_id": "prop-1",
            "properties": {"address": "123 Main St", "city": "Stockton", "state": "CA", "zip": "95202"},
        }
        monkeypatch.setattr(db, "get_lead_with_property", lambda lid: lead)
        monkeypatch.setattr(
            skiptrace,
            "skip_trace_address",
            lambda a, c, s, z: {"persons": [{"phoneNumbers": [{"number": "2095553434", "dnc": True}]}]},
        )
        assert skiptrace.enrich_lead("lead-1")["reason"] == "no_usable_phone"
    finally:
        get_settings.cache_clear()


def test_is_phone_blocked_fails_closed_on_error(monkeypatch):
    _configure(monkeypatch)
    try:
        def _boom(url, body):
            raise RuntimeError("network down")

        monkeypatch.setattr(skiptrace, "_post", _boom)
        assert skiptrace.is_phone_blocked("+12095551212") is True
    finally:
        get_settings.cache_clear()
