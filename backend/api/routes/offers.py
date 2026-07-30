from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.lib import db

router = APIRouter()

_VALID_STATUSES = {"draft", "sent", "countered", "accepted", "rejected", "expired"}


class OfferCreate(BaseModel):
    arv_used: int | None = None
    repair_estimate: int = 2500000
    amount: int | None = None
    notes: str | None = None
    created_by: str = "operator"


class OfferStatusUpdate(BaseModel):
    status: str
    notes: str | None = None


@router.get("/leads/{lead_id}/offers")
async def list_offers_route(lead_id: str):
    return db.get_offers_for_lead(lead_id)


@router.post("/leads/{lead_id}/offers")
async def create_offer_route(lead_id: str, offer: OfferCreate):
    lead = db.get_lead_with_property(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="lead_not_found")

    prop = lead.get("properties") or {}
    arv_used = offer.arv_used if offer.arv_used is not None else prop.get("estimated_arv")

    offer_id = db.create_offer(
        lead_id=lead_id,
        arv_used=arv_used,
        repair_estimate=offer.repair_estimate,
        amount=offer.amount,
        property_id=prop.get("id"),
        notes=offer.notes,
        created_by=offer.created_by,
    )
    return db.get_offer_by_id(offer_id)


@router.patch("/offers/{offer_id}")
async def update_offer_route(offer_id: str, update: OfferStatusUpdate):
    if update.status not in _VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"invalid_status_must_be_one_of:{sorted(_VALID_STATUSES)}")

    offer = db.get_offer_by_id(offer_id)
    if not offer:
        raise HTTPException(status_code=404, detail="offer_not_found")

    db.update_offer_status(offer_id, update.status, update.notes)
    return db.get_offer_by_id(offer_id)
