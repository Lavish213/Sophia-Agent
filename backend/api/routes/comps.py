from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.comps.service import recalculate_arv_for_property
from backend.lib import db

router = APIRouter()


class CompCreate(BaseModel):
    address: str | None = None
    sold_price: int
    sqft: int
    sold_date: str | None = None
    distance_miles: float | None = None
    source: str = "manual"


@router.get("/properties/{property_id}/comps")
async def list_comps_route(property_id: str):
    return db.get_comps_by_property(property_id)


@router.post("/properties/{property_id}/comps")
async def add_comp_route(property_id: str, comp: CompCreate):
    prop = db.get_property_by_id(property_id)
    if not prop:
        raise HTTPException(status_code=404, detail="property_not_found")

    data = comp.model_dump()
    data["subject_property_id"] = property_id
    db.insert_comp(data)

    return recalculate_arv_for_property(property_id)


@router.post("/properties/{property_id}/comps/recalculate")
async def recalculate_comps_route(property_id: str):
    try:
        return recalculate_arv_for_property(property_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="property_not_found")
