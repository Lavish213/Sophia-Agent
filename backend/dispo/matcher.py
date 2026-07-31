from __future__ import annotations

from loguru import logger


def buyer_matches_property(buyer: dict, prop: dict, asking_price_cents: int | None) -> tuple[bool, str]:
    if not buyer.get("active", True):
        return False, "inactive"
    if buyer.get("opted_out"):
        return False, "opted_out"

    if asking_price_cents is not None:
        min_price = buyer.get("min_price")
        max_price = buyer.get("max_price")
        if min_price is not None and asking_price_cents < min_price:
            return False, "below_min_price"
        if max_price is not None and asking_price_cents > max_price:
            return False, "above_max_price"

    cities = buyer.get("cities") or []
    prop_city = (prop.get("city") or "").strip().lower()
    if cities and prop_city and prop_city not in [c.strip().lower() for c in cities]:
        return False, "city_not_matched"

    min_beds = buyer.get("min_beds")
    beds = prop.get("beds")
    if min_beds is not None and beds is not None and beds < min_beds:
        return False, "below_min_beds"

    min_sqft = buyer.get("min_sqft")
    sqft = prop.get("sqft")
    if min_sqft is not None and sqft is not None and sqft < min_sqft:
        return False, "below_min_sqft"

    return True, "match"


def rank_buyers(buyers: list[dict]) -> list[dict]:
    return sorted(
        buyers,
        key=lambda b: (
            -(b.get("deals_closed") or 0),
            not b.get("proof_of_funds_on_file", False),
            (b.get("name") or "").lower(),
        ),
    )


def match_buyers_for_property(
    buyers: list[dict], prop: dict, asking_price_cents: int | None
) -> list[dict]:
    matched = []
    for buyer in buyers:
        ok, reason = buyer_matches_property(buyer, prop, asking_price_cents)
        if ok:
            matched.append(buyer)
        else:
            logger.debug("buyer_not_matched buyer_id={} reason={}", buyer.get("id"), reason)

    ranked = rank_buyers(matched)
    logger.info("matched_buyers count={} of={}", len(ranked), len(buyers))
    return ranked
