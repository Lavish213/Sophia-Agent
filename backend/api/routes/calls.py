from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.lib import db

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
