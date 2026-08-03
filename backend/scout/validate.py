from __future__ import annotations

import re
from datetime import UTC, datetime

_NON_DIGITS = re.compile(r"\D")

_FAKE_PHONE_PREFIXES = ("555",)
_SERVICE_CODES = {"211", "311", "411", "511", "611", "711", "811", "911"}

_NON_PERSON_TOKENS = (
    " llc", " l.l.c", " inc", " corp", " company", " trust", " bank",
    " holdings", " properties", " partners", " lp", " llp", " foundation",
)
_PLACEHOLDER_NAMES = {
    "owner", "current owner", "unknown", "n/a", "na", "none", "occupant",
    "resident", "current resident", "tbd", "test",
}

_PO_BOX = re.compile(r"\b(p\.?\s*o\.?\s*box|post office box)\b", re.IGNORECASE)
_HAS_STREET_NUMBER = re.compile(r"^\s*\d")


def phone_issues(phone: str | None) -> list[str]:
    if not phone:
        return []

    digits = _NON_DIGITS.sub("", phone)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]

    if len(digits) != 10:
        return ["phone_wrong_length"]

    area, exchange = digits[:3], digits[3:6]
    issues = []

    if area[0] in "01":
        issues.append("phone_invalid_area_code")
    if area in _SERVICE_CODES or exchange in _SERVICE_CODES:
        issues.append("phone_service_code")
    if exchange.startswith(_FAKE_PHONE_PREFIXES):
        issues.append("phone_looks_fake")
    if len(set(digits)) == 1:
        issues.append("phone_repeated_digits")
    if digits in ("1234567890", "0123456789"):
        issues.append("phone_sequential")

    return issues


def name_issues(name: str | None) -> list[str]:
    if not name:
        return []

    cleaned = name.strip().lower()
    if cleaned in _PLACEHOLDER_NAMES:
        return ["name_is_placeholder"]
    if any(token in f" {cleaned} " for token in _NON_PERSON_TOKENS):
        return ["owner_is_an_entity"]
    if not any(c.isalpha() for c in cleaned):
        return ["name_has_no_letters"]
    return []


def address_issues(address: str | None) -> list[str]:
    if not address or not address.strip():
        return ["address_missing"]

    issues = []
    if _PO_BOX.search(address):
        issues.append("address_is_po_box")
    if not _HAS_STREET_NUMBER.match(address):
        issues.append("address_has_no_street_number")
    return issues


def property_issues(row: dict) -> list[str]:
    issues = []

    year = row.get("year_built")
    if year:
        current = datetime.now(UTC).year
        if int(year) > current:
            issues.append("year_built_in_the_future")
        elif int(year) < 1800:
            issues.append("year_built_implausible")

    beds = row.get("beds")
    sqft = row.get("sqft")
    if beds and sqft and int(beds) > 0 and int(sqft) / int(beds) < 150:
        issues.append("sqft_too_small_for_bed_count")

    value = row.get("estimated_value")
    if value is not None and int(value) <= 0:
        issues.append("value_is_zero")

    return issues


def validate_row(row: dict) -> dict:
    contact = row.get("contact") or {}

    issues = []
    issues += address_issues(row.get("address"))
    issues += property_issues(row)
    issues += phone_issues(contact.get("phone"))
    issues += phone_issues(contact.get("phone_2"))
    issues += name_issues(contact.get("name") or row.get("owner_name"))

    issues = sorted(set(issues))

    if "address_missing" in issues:
        severity = "reject"
    elif issues:
        severity = "suspect"
    else:
        severity = "ok"

    return {
        "issues": issues,
        "severity": severity,
        "confidence": _confidence(issues),
        "phone_usable": not phone_is_unusable(contact.get("phone")),
        "phone_2_usable": not phone_is_unusable(contact.get("phone_2")),
    }


UNUSABLE_PHONE_ISSUES = frozenset({
    "phone_wrong_length",
    "phone_invalid_area_code",
    "phone_service_code",
    "phone_looks_fake",
    "phone_repeated_digits",
    "phone_sequential",
})


def phone_is_unusable(phone: str | None) -> bool:
    if not phone:
        return False
    return bool(set(phone_issues(phone)) & UNUSABLE_PHONE_ISSUES)


def _confidence(issues: list[str]) -> float:
    if not issues:
        return 1.0
    return max(0.0, round(1.0 - 0.2 * len(issues), 2))


def find_duplicates(rows: list[dict]) -> dict[int, str]:
    seen_apn: dict[str, int] = {}
    seen_address: dict[str, int] = {}
    duplicates: dict[int, str] = {}

    for index, row in enumerate(rows):
        apn = (row.get("apn") or "").strip().lower()
        address = (row.get("address") or "").strip().lower()

        if apn:
            if apn in seen_apn:
                duplicates[index] = f"duplicate_apn_of_row_{seen_apn[apn]}"
                continue
            seen_apn[apn] = index

        if address:
            if address in seen_address:
                duplicates[index] = f"duplicate_address_of_row_{seen_address[address]}"
                continue
            seen_address[address] = index

    return duplicates
