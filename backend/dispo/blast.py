from __future__ import annotations

from loguru import logger

from backend.dispo.matcher import match_buyers_for_property
from backend.lib import db
from backend.lib.config import get_settings


def _format_cents(cents: int | None) -> str:
    if cents is None:
        return "TBD"
    return f"${cents / 100:,.0f}"


def build_deal_summary(prop: dict, asking_price_cents: int | None) -> str:
    settings = get_settings()
    parts = [f"{settings.business_name} has a new one:"]

    address = prop.get("address") or "San Joaquin County"
    city = prop.get("city")
    parts.append(f"{address}{f', {city}' if city else ''}.")

    specs = []
    if prop.get("beds"):
        specs.append(f"{prop['beds']}bd")
    if prop.get("baths"):
        specs.append(f"{prop['baths']}ba")
    if prop.get("sqft"):
        specs.append(f"{prop['sqft']} sqft")
    if specs:
        parts.append(" / ".join(specs) + ".")

    parts.append(f"Asking {_format_cents(asking_price_cents)}.")

    arv = prop.get("estimated_arv")
    if arv:
        parts.append(f"ARV around {_format_cents(arv)}.")

    parts.append("Reply if you want the address details and photos.")
    return " ".join(parts)


def blast_deal(property_id: str, asking_price_cents: int | None = None, channel: str = "sms") -> dict:
    prop = db.get_property_by_id(property_id)
    if not prop:
        return {"success": False, "reason": "property_not_found", "sent": 0}

    buyers = db.list_active_buyers()
    matched = match_buyers_for_property(buyers, prop, asking_price_cents)

    if not matched:
        logger.info("blast_deal_no_matching_buyers property_id={}", property_id)
        return {"success": True, "reason": "no_matching_buyers", "sent": 0, "skipped": 0}

    body = build_deal_summary(prop, asking_price_cents)
    sent = 0
    skipped = 0

    for buyer in matched:
        if db.deal_already_blasted(property_id, buyer["id"], channel):
            skipped += 1
            continue

        result = _send_to_buyer(buyer, body, channel)
        if result.get("success"):
            db.insert_deal_blast(property_id, buyer["id"], channel, "sent")
            sent += 1
        else:
            db.insert_deal_blast(property_id, buyer["id"], channel, "failed")
            logger.warning("blast_failed buyer_id={} reason={}", buyer["id"], result.get("reason"))

    logger.info("blast_deal_complete property_id={} sent={} skipped={}", property_id, sent, skipped)
    return {"success": True, "reason": "sent", "sent": sent, "skipped": skipped, "matched": len(matched)}


def _send_to_buyer(buyer: dict, body: str, channel: str) -> dict:
    settings = get_settings()

    if channel == "email":
        if buyer.get("email_opted_out") or not buyer.get("email"):
            return {"success": False, "reason": "no_email_or_opted_out"}
        from backend.alerts.email import send_raw_email

        return send_raw_email(buyer["email"], "New off-market deal", body)

    if buyer.get("opted_out") or not buyer.get("phone"):
        return {"success": False, "reason": "no_phone_or_opted_out"}

    from signalwire.rest import Client as SignalwireClient

    try:
        client = SignalwireClient(
            settings.signalwire_project_id,
            settings.signalwire_token,
            signalwire_space_url=settings.signalwire_space,
        )
        message = client.messages.create(
            to=buyer["phone"],
            from_=settings.signalwire_phone,
            body=body + " Reply STOP to opt out.",
        )
        return {"success": True, "message_sid": message.sid}
    except Exception as e:
        logger.error("blast_sms_failed buyer_id={} error={}", buyer.get("id"), str(e))
        return {"success": False, "reason": str(e)}
