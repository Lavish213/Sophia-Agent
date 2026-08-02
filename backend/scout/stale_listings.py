from __future__ import annotations

from loguru import logger

from backend.lib import db
from backend.lib.config import get_settings
from backend.scout.intake import intake_lead

ACTIVE_STATUSES = {"active", "listed", "for_sale", "pending"}
OWNER_CONTACTABLE_STATUSES = {"expired", "withdrawn", "cancelled", "off_market"}


def is_stale(prop: dict, min_days: int) -> bool:
    dom = prop.get("days_on_market")
    if dom is None:
        return False
    return int(dom) >= min_days


def contact_target(prop: dict) -> str:
    status = (prop.get("listing_status") or "unknown").strip().lower()

    if status in OWNER_CONTACTABLE_STATUSES:
        return "owner"
    if status in ACTIVE_STATUSES:
        return "listing_agent"
    return "review"


def build_stale_note(prop: dict) -> str:
    dom = prop.get("days_on_market")
    status = (prop.get("listing_status") or "unknown").strip().lower()
    source = prop.get("listing_source") or "listing data"

    parts = [f"Listing has sat {dom} days on market ({source}, status: {status})."]

    if prop.get("price_drop_count"):
        parts.append(f"Price cut {prop['price_drop_count']} time(s).")

    target = contact_target(prop)
    if target == "listing_agent":
        parts.append(
            "Still actively listed — contact the listing agent, not the owner. "
            "Approaching a seller under an exclusive agreement risks tortious interference."
        )
    elif target == "owner":
        parts.append("Listing is no longer active, so the owner can be approached directly.")
    else:
        parts.append("Listing status unknown — confirm before any outreach.")

    return " ".join(parts)


def process_stale_listing(prop: dict) -> dict:
    target = contact_target(prop)
    note = build_stale_note(prop)

    if target == "review":
        db.update_property_fields(prop["id"], {"stale_listing_flagged_at": db.now_iso()})
        logger.info("stale_listing_needs_review property_id={}", prop["id"])
        return {"success": False, "reason": "status_unknown", "target": target}

    if target == "listing_agent":
        phone = prop.get("listing_agent_phone")
        if not phone:
            db.update_property_fields(prop["id"], {"stale_listing_flagged_at": db.now_iso()})
            return {"success": False, "reason": "no_agent_phone", "target": target}

        result = intake_lead(
            "stale_listing",
            address=prop.get("address"),
            owner_name=prop.get("listing_agent_name"),
            owner_phone=phone,
            city=prop.get("city"),
            distress_type="stale_listing",
            notes=note,
        )
    else:
        phone = prop.get("owner_phone") or prop.get("contact_phone")
        result = intake_lead(
            "stale_listing",
            address=prop.get("address"),
            owner_name=prop.get("owner_name"),
            owner_phone=phone,
            city=prop.get("city"),
            distress_type="expired_listing",
            notes=note,
        )

    db.update_property_fields(prop["id"], {"stale_listing_flagged_at": db.now_iso()})
    result["target"] = target
    return result


def run_stale_listing_pass(limit: int | None = None) -> dict:
    settings = get_settings()
    min_days = settings.stale_listing_min_days
    batch = limit if limit is not None else settings.stale_listing_batch_size

    results = {"checked": 0, "flagged": 0, "to_agent": 0, "to_owner": 0, "skipped": 0}

    properties = db.get_unflagged_stale_listings(min_days=min_days, limit=batch)
    for prop in properties:
        results["checked"] += 1

        if not is_stale(prop, min_days):
            continue

        try:
            outcome = process_stale_listing(prop)
            if outcome.get("success"):
                results["flagged"] += 1
                if outcome["target"] == "listing_agent":
                    results["to_agent"] += 1
                else:
                    results["to_owner"] += 1
            else:
                results["skipped"] += 1
        except Exception as e:
            results["skipped"] += 1
            logger.error("stale_listing_failed property_id={} error={}", prop.get("id"), str(e))

    logger.info("stale_listing_pass_complete results={}", results)
    return results
