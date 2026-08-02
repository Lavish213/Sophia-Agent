from backend.lib import db
from backend.scout import ingest


def _row(**overrides):
    row = {
        "apn": "123-456-78",
        "address": "123 Main St",
        "city": "Stockton",
        "state": "CA",
        "zip": "95202",
        "estimated_value": 30000000,
    }
    row.update(overrides)
    return row


def _stub(monkeypatch, property_id="prop-1", lead=None):
    captured: dict = {"contacts": [], "lead_updates": {}}

    def _fake_upsert(data):
        captured["property"] = data
        return property_id

    monkeypatch.setattr(db, "upsert_property", _fake_upsert)
    monkeypatch.setattr(db, "insert_contact", lambda d: captured["contacts"].append(d))
    monkeypatch.setattr(db, "get_or_create_lead", lambda pid: lead or {"id": "lead-1"})
    monkeypatch.setattr(
        db, "update_lead_fields", lambda lid, f: captured["lead_updates"].update(f)
    )
    return captured


def test_distress_score_is_written_as_an_integer(monkeypatch):
    captured = _stub(monkeypatch)
    result = ingest.ingest_property_row(_row())

    score = captured["property"]["distress_score"]
    assert isinstance(score, int), "a non-int score is what crashed every row in the old repo"
    assert result["distress_score"] == score


def test_contact_is_stripped_before_the_property_upsert(monkeypatch):
    captured = _stub(monkeypatch)
    row = _row(contact={"name": "Maria", "phone": "2095551212", "email": "m@example.com"})

    ingest.ingest_property_row(row)

    assert "contact" not in captured["property"], "contact must never reach the properties table"
    assert captured["contacts"][0]["phone"] == "+12095551212"


def test_contact_details_are_promoted_onto_the_lead(monkeypatch):
    captured = _stub(monkeypatch)
    row = _row(contact={"phone": "2095551212", "phone_2": "2095559999", "email": "m@example.com"})

    ingest.ingest_property_row(row)

    assert captured["lead_updates"]["owner_phone"] == "+12095551212"
    assert captured["lead_updates"]["owner_phone_2"] == "+12095559999"
    assert captured["lead_updates"]["owner_email"] == "m@example.com"


def test_existing_lead_contact_details_are_not_overwritten(monkeypatch):
    existing = {"id": "lead-1", "owner_phone": "2095550000", "owner_email": "old@example.com"}
    captured = _stub(monkeypatch, lead=existing)
    row = _row(contact={"phone": "2095551212", "email": "new@example.com"})

    ingest.ingest_property_row(row)

    assert "owner_phone" not in captured["lead_updates"]
    assert "owner_email" not in captured["lead_updates"]


def test_row_without_contact_creates_no_contact_row(monkeypatch):
    captured = _stub(monkeypatch)
    ingest.ingest_property_row(_row())
    assert captured["contacts"] == []


def test_contact_with_only_blank_values_is_skipped(monkeypatch):
    captured = _stub(monkeypatch)
    ingest.ingest_property_row(_row(contact={"name": "Maria", "phone": "", "email": ""}))
    assert captured["contacts"] == []


def test_failed_property_upsert_returns_cleanly_without_a_lead(monkeypatch):
    monkeypatch.setattr(db, "upsert_property", lambda d: None)

    def _should_not_run(*args, **kwargs):
        raise AssertionError("must not create a lead without a property")

    monkeypatch.setattr(db, "get_or_create_lead", _should_not_run)

    result = ingest.ingest_property_row(_row())

    assert result["property_id"] is None
    assert result["lead_id"] is None


def test_csv_batch_counts_processed_and_created(monkeypatch):
    _stub(monkeypatch)
    result = ingest.ingest_csv_rows([_row(apn="1"), _row(apn="2"), _row(apn="3")])
    assert result["processed"] == 3
    assert result["leads_created"] == 3
    assert result["errors"] == 0


def test_one_bad_row_does_not_abort_the_whole_import(monkeypatch):
    calls = {"n": 0}

    def _flaky_upsert(data):
        calls["n"] += 1
        if data.get("apn") == "bad":
            raise RuntimeError("malformed row")
        return "prop-1"

    monkeypatch.setattr(db, "upsert_property", _flaky_upsert)
    monkeypatch.setattr(db, "insert_contact", lambda d: None)
    monkeypatch.setattr(db, "get_or_create_lead", lambda pid: {"id": "lead-1"})
    monkeypatch.setattr(db, "update_lead_fields", lambda lid, f: None)

    result = ingest.ingest_csv_rows([_row(apn="1"), _row(apn="bad"), _row(apn="3")])

    assert result["processed"] == 2
    assert result["errors"] == 1
    assert calls["n"] == 3, "the importer must keep going after a bad row"


def test_empty_csv_is_not_an_error(monkeypatch):
    result = ingest.ingest_csv_rows([])
    assert result == {"processed": 0, "leads_created": 0, "errors": 0}


def test_ingest_does_not_mutate_the_caller_row_beyond_expected_keys(monkeypatch):
    _stub(monkeypatch)
    row = _row(contact={"phone": "2095551212"})

    ingest.ingest_property_row(row)

    assert "contact" not in row, "contact is popped, so the caller sees it consumed"
    assert row["apn"] == "123-456-78"


def test_csv_phones_are_normalized_like_every_other_source(monkeypatch):
    captured = _stub(monkeypatch)
    row = _row(contact={"phone": "(209) 555-1212", "email": "  Maria@Example.COM "})

    ingest.ingest_property_row(row)

    assert captured["contacts"][0]["phone"] == "+12095551212", (
        "a CSV lead stored in raw format will not dedupe against the same person calling in"
    )
    assert captured["lead_updates"]["owner_phone"] == "+12095551212"
    assert captured["lead_updates"]["owner_email"] == "maria@example.com"


def test_unparseable_csv_phone_is_kept_rather_than_dropped(monkeypatch):
    captured = _stub(monkeypatch)
    ingest.ingest_property_row(_row(contact={"phone": "ext 4471"}))

    assert captured["contacts"][0]["phone"] == "ext 4471"
