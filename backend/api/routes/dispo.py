from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.dispo.blast import blast_deal, build_deal_summary
from backend.dispo.matcher import match_buyers_for_property
from backend.lib import db

router = APIRouter()


class BuyerCreate(BaseModel):
    name: str
    company: str | None = None
    phone: str | None = None
    email: str | None = None
    min_price: int | None = None
    max_price: int | None = None
    min_beds: int | None = None
    min_sqft: int | None = None
    cities: list[str] = []
    buys_cash: bool = True
    proof_of_funds_on_file: bool = False
    notes: str | None = None


class BlastRequest(BaseModel):
    asking_price_cents: int | None = None
    channel: str = "sms"


@router.get("/buyers")
async def list_buyers_route():
    return db.list_buyers()


@router.post("/buyers")
async def create_buyer_route(buyer: BuyerCreate):
    if not buyer.phone and not buyer.email:
        raise HTTPException(status_code=422, detail="phone_or_email_required")

    buyer_id = db.insert_buyer(buyer.model_dump())
    if not buyer_id:
        raise HTTPException(status_code=500, detail="buyer_create_failed")
    return {"success": True, "buyer_id": buyer_id}


@router.get("/properties/{property_id}/matching-buyers")
async def matching_buyers_route(property_id: str, asking_price_cents: int | None = None):
    prop = db.get_property_by_id(property_id)
    if not prop:
        raise HTTPException(status_code=404, detail="property_not_found")

    matched = match_buyers_for_property(db.list_active_buyers(), prop, asking_price_cents)
    return {
        "matched": matched,
        "count": len(matched),
        "preview": build_deal_summary(prop, asking_price_cents),
    }


@router.post("/properties/{property_id}/blast")
async def blast_deal_route(property_id: str, body: BlastRequest):
    result = blast_deal(property_id, body.asking_price_cents, body.channel)
    if not result["success"]:
        raise HTTPException(status_code=404, detail=result["reason"])
    return result


@router.get("/properties/{property_id}/blasts")
async def list_blasts_route(property_id: str):
    return db.get_blasts_for_property(property_id)
