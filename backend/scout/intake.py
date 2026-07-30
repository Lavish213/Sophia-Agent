from __future__ import annotations

import re

from loguru import logger

from backend.lib import db

SOURCE_DEFAULT_SCORES = {
    "web_form": 80,
    "inbound_call": 70,
    "inbound_sms": 65,
    "referral": 60,
    "reddit": 45,
    "skiptrace": 50,
    "csv_import": 40,
}

_NON_DIGITS = re.compile(r"\D")


def normalize_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = _NON_DIGITS.sub("", phone)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        return None
    return f"+1{digits}"


def phone_variants(phone: str | None) -> list[str]:
    normalized = normalize_phone(phone)
    if not normalized:
        return []
    bare = normalized[2:]
    return [
        normalized,
        bare,
        f"1{bare}",
        f"+1 {bare[:3]} {bare[3:6]} {bare[6:]}",
        f"({bare[:3]}) {bare[3:6]}-{bare[6:]}",
        f"{bare[:3]}-{bare[3:6]}-{bare[6:]}",
    ]


def find_existing_lead(phone: str | None, email: str | None = None) -> dict | None:
    for variant in phone_variants(phone):
        lead = db.get_lead_by_owner_phone(variant)
        if lead:
            return lead
    if email:
        return db.get_lead_by_owner_email(email.strip().lower())
    return None


def _synthetic_apn(source: str, phone: str | None, email: str | None) -> str | None:
    normalized = normalize_phone(phone)
    if normalized:
        return f"{source}:{normalized}"
    if email:
        return f"{source}:{email.strip().lower()}"
    return None


def _placeholder_address(source: str, phone: str | None, email: str | None) -> str:
    handle = normalize_phone(phone) or (email or "").strip().lower() or "unknown contact"
    return f"Address needed - {source} from {handle}"


def _append_note(existing: str | None, addition: str) -> str:
    if not existing:
        return addition
    if addition in existing:
        return existing
    return f"{existing}\n{addition}"


def intake_lead(
    source: str,
    address: str | None = None,
    owner_name: str | None = None,
    owner_phone: str | None = None,
    owner_email: str | None = None,
    city: str | None = None,
    state: str = "CA",
    distress_score: int | None = None,
    distress_type: str = "unknown",
    notes: str | None = None,
    property_fields: dict | None = None,
) -> dict:
    normalized_phone = normalize_phone(owner_phone)
    clean_email = (owner_email or "").strip().lower() or None

    if not normalized_phone and not clean_email and not address:
        logger.warning("intake_lead_insufficient_identity source={}", source)
        return {"success": False, "reason": "no_identity", "lead_id": None, "property_id": None, "created": False}

    existing = find_existing_lead(normalized_phone, clean_email)
    if existing:
        updates: dict = {}
        if normalized_phone and not existing.get("owner_phone"):
            updates["owner_phone"] = normalized_phone
        if clean_email and not existing.get("owner_email"):
            updates["owner_email"] = clean_email
        if notes:
            updates["operator_notes"] = _append_note(existing.get("operator_notes"), notes)
        if updates:
            db.update_lead_fields(existing["id"], updates)
        logger.info("intake_lead_matched_existing source={} lead_id={}", source, existing["id"])
        return {
            "success": True,
            "reason": "existing_lead",
            "lead_id": existing["id"],
            "property_id": existing.get("property_id"),
            "created": False,
        }

    score = distress_score if distress_score is not None else SOURCE_DEFAULT_SCORES.get(source, 40)

    property_payload: dict = {
        "address": address or _placeholder_address(source, normalized_phone, clean_email),
        "city": city,
        "state": state,
        "county": "San Joaquin",
        "owner_name": owner_name,
        "distress_type": distress_type,
        "distress_score": score,
        "deal_viable": True,
        "source": source,
    }
    if not address:
        property_payload["apn"] = _synthetic_apn(source, normalized_phone, clean_email)
    if property_fields:
        property_payload.update(property_fields)

    property_id = db.upsert_property(property_payload)
    if not property_id:
        logger.error("intake_lead_property_failed source={}", source)
        return {
            "success": False,
            "reason": "property_create_failed",
            "lead_id": None,
            "property_id": None,
            "created": False,
        }

    if normalized_phone or clean_email:
        db.insert_contact({
            "property_id": property_id,
            "name": owner_name,
            "phone": normalized_phone,
            "email": clean_email,
            "source": source,
        })

    lead = db.get_or_create_lead(property_id)

    lead_updates: dict = {}
    if normalized_phone:
        lead_updates["owner_phone"] = normalized_phone
    if clean_email:
        lead_updates["owner_email"] = clean_email
    if notes:
        lead_updates["operator_notes"] = _append_note(lead.get("operator_notes"), notes)
    if lead_updates:
        db.update_lead_fields(lead["id"], lead_updates)

    logger.info("intake_lead_created source={} lead_id={} score={}", source, lead["id"], score)
    return {
        "success": True,
        "reason": "created",
        "lead_id": lead["id"],
        "property_id": property_id,
        "created": True,
    }
