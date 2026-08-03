from backend.scout.validate import (
    address_issues,
    find_duplicates,
    name_issues,
    phone_issues,
    property_issues,
    validate_row,
)


def test_good_phone_has_no_issues():
    assert phone_issues("2094771234") == []


def test_555_numbers_are_caught():
    assert "phone_looks_fake" in phone_issues("209-555-0100")


def test_area_code_cannot_start_with_zero_or_one():
    assert "phone_invalid_area_code" in phone_issues("109-477-1234")
    assert "phone_invalid_area_code" in phone_issues("009-477-1234")


def test_service_codes_are_caught():
    assert "phone_service_code" in phone_issues("911-477-1234")


def test_repeated_and_sequential_digits_are_caught():
    assert "phone_repeated_digits" in phone_issues("2222222222")
    assert "phone_sequential" in phone_issues("123-456-7890")


def test_short_phone_is_caught():
    assert phone_issues("20947") == ["phone_wrong_length"]


def test_missing_phone_is_not_an_issue():
    assert phone_issues(None) == []
    assert phone_issues("") == []


def test_entity_owners_are_flagged_because_you_cannot_call_an_llc():
    assert name_issues("Stockton Holdings LLC") == ["owner_is_an_entity"]
    assert name_issues("Wells Fargo Bank") == ["owner_is_an_entity"]
    assert name_issues("The Gonzalez Family Trust") == ["owner_is_an_entity"]


def test_placeholder_names_are_flagged():
    for junk in ("OWNER", "Current Resident", "unknown", "N/A"):
        assert name_issues(junk) == ["name_is_placeholder"], junk


def test_a_real_person_name_passes():
    assert name_issues("Maria Gonzalez") == []


def test_po_boxes_are_flagged_since_you_cannot_buy_one():
    assert "address_is_po_box" in address_issues("P.O. Box 1234, Stockton CA")
    assert "address_is_po_box" in address_issues("PO BOX 99")


def test_address_without_a_street_number_is_flagged():
    assert "address_has_no_street_number" in address_issues("Main Street, Stockton")


def test_missing_address_is_flagged():
    assert address_issues("") == ["address_missing"]
    assert address_issues(None) == ["address_missing"]


def test_good_address_passes():
    assert address_issues("123 Main St, Stockton CA") == []


def test_future_year_built_is_implausible():
    assert "year_built_in_the_future" in property_issues({"year_built": 2099})


def test_ancient_year_built_is_implausible():
    assert "year_built_implausible" in property_issues({"year_built": 1200})


def test_sqft_inconsistent_with_bed_count():
    assert "sqft_too_small_for_bed_count" in property_issues({"beds": 4, "sqft": 400})


def test_zero_value_is_flagged():
    assert "value_is_zero" in property_issues({"estimated_value": 0})


def test_clean_row_is_ok():
    row = {
        "address": "123 Main St",
        "beds": 3,
        "sqft": 1400,
        "year_built": 1968,
        "contact": {"name": "Maria Gonzalez", "phone": "2094771234"},
    }
    result = validate_row(row)
    assert result["severity"] == "ok"
    assert result["issues"] == []
    assert result["confidence"] == 1.0


def test_row_with_no_address_is_rejected():
    result = validate_row({"address": "", "contact": {"phone": "2094771234"}})
    assert result["severity"] == "reject"


def test_a_fake_phone_flags_the_row_but_keeps_the_property():
    row = {"address": "123 Main St", "contact": {"phone": "209-555-0100"}}
    result = validate_row(row)

    assert result["severity"] == "suspect", (
        "the property is still real and skip trace can find a working number"
    )
    assert result["phone_usable"] is False


def test_a_usable_phone_is_marked_usable():
    row = {"address": "123 Main St", "contact": {"phone": "209-477-1234"}}
    result = validate_row(row)
    assert result["phone_usable"] is True
    assert result["severity"] == "ok"


def test_entity_owner_is_suspect_not_rejected():
    row = {
        "address": "123 Main St",
        "contact": {"name": "Acme Holdings LLC", "phone": "2094771234"},
    }
    result = validate_row(row)
    assert result["severity"] == "suspect"
    assert "owner_is_an_entity" in result["issues"]


def test_confidence_drops_as_issues_stack_up():
    clean = validate_row({"address": "1 A St", "contact": {"phone": "2094771234"}})
    messy = validate_row(
        {"address": "PO Box 5", "year_built": 2099, "contact": {"name": "OWNER", "phone": "2094771234"}}
    )
    assert messy["confidence"] < clean["confidence"]


def test_duplicate_apn_is_found():
    rows = [{"apn": "123-456-78"}, {"apn": "999-000-11"}, {"apn": "123-456-78"}]
    dupes = find_duplicates(rows)
    assert 2 in dupes
    assert "duplicate_apn_of_row_0" in dupes[2]


def test_duplicate_address_is_found_when_apn_is_missing():
    rows = [{"address": "123 Main St"}, {"address": "123 MAIN ST"}]
    assert 1 in find_duplicates(rows)


def test_distinct_rows_are_not_flagged():
    rows = [{"apn": "1", "address": "1 A St"}, {"apn": "2", "address": "2 B St"}]
    assert find_duplicates(rows) == {}
