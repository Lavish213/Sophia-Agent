from __future__ import annotations

from loguru import logger

from backend.lib import db
from backend.scout.intake import normalize_phone
from backend.scout.scorer import calculate_distress_score
from backend.scout.validate import find_duplicates, validate_row


def ingest_property_row(row: dict) -> dict:
    validation = validate_row(row)
    contact = row.pop("contact", None) or {}

    if validation["severity"] == "reject":
        logger.warning(
            "ingest_row_rejected apn={} issues={}", row.get("apn"), validation["issues"]
        )
        return {
            "property_id": None,
            "lead_id": None,
            "distress_score": 0,
            "deal_viable": False,
            "rejected": True,
            "issues": validation["issues"],
        }

    row["data_issues"] = validation["issues"]
    row["data_confidence"] = validation["confidence"]
    row["distress_score"] = calculate_distress_score(row)
    property_id = db.upsert_property(row)

    if not property_id:
        return {
            "property_id": None,
            "lead_id": None,
            "distress_score": row["distress_score"],
            "deal_viable": row.get("deal_viable", False),
        }

    phone = normalize_phone(contact.get("phone")) or contact.get("phone")
    phone_2 = normalize_phone(contact.get("phone_2")) or contact.get("phone_2")

    if not validation["phone_usable"]:
        phone = None
    if not validation["phone_2_usable"]:
        phone_2 = None
    email = (contact.get("email") or "").strip().lower() or None

    if phone or email:
        db.insert_contact({
            "property_id": property_id,
            "name": contact.get("name"),
            "phone": phone,
            "phone_2": phone_2,
            "email": email,
        })

    lead = db.get_or_create_lead(property_id)

    lead_updates = {}
    if phone and not lead.get("owner_phone"):
        lead_updates["owner_phone"] = phone
    if phone_2 and not lead.get("owner_phone_2"):
        lead_updates["owner_phone_2"] = phone_2
    if email and not lead.get("owner_email"):
        lead_updates["owner_email"] = email
    if lead_updates:
        db.update_lead_fields(lead["id"], lead_updates)

    return {
        "property_id": property_id,
        "lead_id": lead["id"],
        "distress_score": row["distress_score"],
        "deal_viable": row.get("deal_viable", False),
    }


def ingest_csv_rows(rows: list[dict]) -> dict:
    processed = 0
    leads_created = 0
    errors = 0
    rejected = 0
    suspect = 0
    duplicates = find_duplicates(rows)

    for index, row in enumerate(rows):
        if index in duplicates:
            rejected += 1
            logger.info("ingest_row_duplicate apn={} reason={}", row.get("apn"), duplicates[index])
            continue

        try:
            result = ingest_property_row(row)
            if result.get("rejected"):
                rejected += 1
                continue
            processed += 1
            if result.get("issues"):
                suspect += 1
            if result["lead_id"]:
                leads_created += 1
        except Exception as e:
            errors += 1
            logger.exception("ingest_property_row_failed apn={} error={}", row.get("apn"), str(e))

    logger.info(
        "ingest_csv_rows processed={} leads={} suspect={} rejected={} errors={}",
        processed, leads_created, suspect, rejected, errors,
    )
    return {
        "processed": processed,
        "leads_created": leads_created,
        "suspect": suspect,
        "rejected": rejected,
        "errors": errors,
    }
