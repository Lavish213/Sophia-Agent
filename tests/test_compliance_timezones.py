from datetime import datetime

import pytz

from backend.compliance import timezones
from backend.compliance.compliance import is_calling_hours_for_phone

_UTC = pytz.utc


def _utc(hour, minute=0, month=6, day=15):
    return _UTC.localize(datetime(2026, month, day, hour, minute))


def test_local_san_joaquin_number_maps_to_pacific():
    assert timezones.timezone_for_phone("+12095551212") == "America/Los_Angeles"


def test_new_york_number_maps_to_eastern():
    assert timezones.timezone_for_phone("+12125551212") == "America/New_York"


def test_arizona_is_its_own_zone_because_it_skips_dst():
    assert timezones.timezone_for_phone("+16025551212") == "America/Phoenix"


def test_area_code_parsing_handles_formats():
    assert timezones.area_code("(209) 555-1212") == "209"
    assert timezones.area_code("12095551212") == "209"
    assert timezones.area_code("209-555-1212") == "209"


def test_area_code_rejects_junk():
    assert timezones.area_code(None) is None
    assert timezones.area_code("555") is None
    assert timezones.timezone_for_phone("555") is None


def test_unknown_area_code_falls_back_to_both_coasts():
    assert timezones.zones_to_check("+19995551212") == timezones.STRICT_FALLBACK_ZONES


def test_known_area_code_checks_only_its_own_zone():
    assert timezones.zones_to_check("+12095551212") == ("America/Los_Angeles",)


def test_absentee_owner_on_the_east_coast_is_not_called_at_11pm_their_time():
    late_eastern = _utc(3)
    assert is_calling_hours_for_phone("+12125551212", late_eastern) is False


def test_the_same_moment_is_fine_for_a_local_pacific_number():
    eight_pm_pacific = _utc(3)
    assert is_calling_hours_for_phone("+12095551212", eight_pm_pacific) is True


def test_east_coast_owner_can_be_called_during_their_business_day():
    noon_eastern = _utc(16)
    assert is_calling_hours_for_phone("+12125551212", noon_eastern) is True


def test_pacific_number_blocked_before_8am_local():
    seven_am_pacific = _utc(14)
    assert is_calling_hours_for_phone("+12095551212", seven_am_pacific) is False


def test_unknown_number_is_blocked_when_either_coast_is_out_of_hours():
    eight_pm_pacific_eleven_eastern = _utc(3)
    assert is_calling_hours_for_phone("+19995551212", eight_pm_pacific_eleven_eastern) is False


def test_unknown_number_allowed_only_in_the_overlap():
    noon_pacific_three_eastern = _utc(19)
    assert is_calling_hours_for_phone("+19995551212", noon_pacific_three_eastern) is True


def test_missing_phone_uses_the_strict_fallback():
    assert is_calling_hours_for_phone(None, _utc(3)) is False
    assert is_calling_hours_for_phone(None, _utc(19)) is True


def test_dst_shift_is_handled_by_the_timezone_database():
    january_evening = _utc(3, month=1, day=15)
    assert is_calling_hours_for_phone("+12125551212", january_evening) is False


def test_no_area_code_is_claimed_by_two_timezones():
    seen: dict[str, str] = {}
    for zone_set, name in (
        (timezones._PACIFIC_CODES, "pacific"),
        (timezones._MOUNTAIN_CODES, "mountain"),
        (timezones._ARIZONA_CODES, "arizona"),
        (timezones._CENTRAL_CODES, "central"),
        (timezones._EASTERN_CODES, "eastern"),
    ):
        for code in zone_set:
            assert code not in seen, f"area code {code} is in both {seen.get(code)} and {name}"
            seen[code] = name


def test_area_codes_are_all_well_formed():
    for code in timezones._AREA_CODE_TIMEZONES:
        assert len(code) == 3 and code.isdigit()
        assert code[0] != "0" and code[0] != "1"
