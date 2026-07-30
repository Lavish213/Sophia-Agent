from __future__ import annotations

from backend.lib import db

_INTENT_TO_SCORE = {"hot": 75, "warm": 55, "cold": 35, "none": 20}


def convert_reddit_match_to_lead(
    match_id: str,
    address: str,
    owner_phone: str,
    owner_name: str | None = None,
    owner_email: str | None = None,
    city: str | None = None,
    state: str = "CA",
) -> dict:
    match = db.get_reddit_match_by_id(match_id)
    if not match:
        return {"success": False, "reason": "match_not_found"}

    if match.get("lead_id"):
        return {"success": False, "reason": "already_converted"}

    distress_score = _INTENT_TO_SCORE.get(match.get("intent_label", "none"), 20)

    property_id = db.upsert_property({
        "address": address,
        "city": city,
        "state": state,
        "county": "San Joaquin",
        "distress_type": "unknown",
        "distress_score": distress_score,
        "deal_viable": True,
        "source": "reddit",
    })

    if not property_id:
        return {"success": False, "reason": "property_create_failed"}

    if owner_phone or owner_email:
        db.insert_contact({
            "property_id": property_id,
            "name": owner_name,
            "phone": owner_phone,
            "email": owner_email,
            "source": "reddit",
        })

    lead = db.get_or_create_lead(property_id)

    lead_updates: dict = {"operator_notes": f"Found via Reddit: {match['url']}"}
    if owner_phone:
        lead_updates["owner_phone"] = owner_phone
    if owner_email:
        lead_updates["owner_email"] = owner_email
    db.update_lead_fields(lead["id"], lead_updates)

    db.link_reddit_match_to_lead(match_id, lead["id"])

    return {"success": True, "lead_id": lead["id"], "property_id": property_id}
