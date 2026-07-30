from __future__ import annotations

import backend.lib.db as db
from backend.comps.calculator import calculate_arv


def recalculate_arv_for_property(property_id: str) -> dict:
    prop = db.get_property_by_id(property_id)
    if not prop:
        raise ValueError(f"property_not_found:{property_id}")

    comps = db.get_comps_by_property(property_id)
    result = calculate_arv(comps, prop.get("sqft"))

    if result["arv"] is not None:
        db.update_property_arv(
            property_id,
            arv=result["arv"],
            mao=result["mao"],
            confidence=result["confidence"],
            extra={"comp_count": result["comp_count"], "price_per_sqft": result["price_per_sqft"]},
        )

    return result
