from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.lib import db

router = APIRouter()


class LeadUpdate(BaseModel):
    stage: str | None = None
    operator_notes: str | None = None
    callable: bool | None = None
    opted_out: bool | None = None
    priority_callback: bool | None = None


@router.get("/leads")
async def list_leads_route(stage: str | None = Query(default=None), limit: int = Query(default=50, le=200)):
    return db.list_leads(stage=stage, limit=limit)


@router.get("/leads/{lead_id}")
async def get_lead_route(lead_id: str):
    lead = db.get_lead_with_property(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="lead_not_found")
    lead["calls"] = db.get_calls_for_lead(lead_id)
    lead["offers"] = db.get_offers_for_lead(lead_id)
    return lead


@router.patch("/leads/{lead_id}")
async def update_lead_route(lead_id: str, update: LeadUpdate):
    lead = db.get_lead_by_id(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="lead_not_found")

    fields = update.model_dump(exclude_unset=True)
    if not fields:
        return lead

    if "stage" in fields:
        stage = fields.pop("stage")
        db.update_lead_stage(lead_id, stage)
    if fields:
        db.update_lead_fields(lead_id, fields)

    return db.get_lead_by_id(lead_id)
