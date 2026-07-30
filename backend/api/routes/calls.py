from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.lib import db
from backend.voice.outbound import place_outbound_call

router = APIRouter()


@router.get("/calls")
async def list_calls_route(limit: int = Query(default=50, le=200)):
    return db.list_calls(limit=limit)


@router.get("/calls/{call_id}")
async def get_call_route(call_id: str):
    call = db.get_call_by_id(call_id)
    if not call:
        raise HTTPException(status_code=404, detail="call_not_found")
    call["transcript_chunks"] = db.get_transcript_chunks(call_id)
    return call


@router.post("/leads/{lead_id}/call")
async def trigger_outbound_call_route(lead_id: str):
    result = place_outbound_call(lead_id)
    if not result["success"]:
        raise HTTPException(status_code=422, detail=result["reason"])
    return result
