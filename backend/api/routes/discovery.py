from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.lib import db
from backend.scout.convert import convert_reddit_match_to_lead

router = APIRouter()


class ConvertMatchRequest(BaseModel):
    address: str
    owner_phone: str
    owner_name: str | None = None
    owner_email: str | None = None
    city: str | None = None
    state: str = "CA"


@router.get("/discovery/reddit-matches")
async def list_reddit_matches_route(status: str | None = Query(default=None), limit: int = Query(default=50, le=200)):
    return db.list_reddit_matches(status=status, limit=limit)


@router.post("/discovery/reddit-matches/{match_id}/convert")
async def convert_reddit_match_route(match_id: str, body: ConvertMatchRequest):
    result = convert_reddit_match_to_lead(
        match_id,
        body.address,
        body.owner_phone,
        owner_name=body.owner_name,
        owner_email=body.owner_email,
        city=body.city,
        state=body.state,
    )
    if not result["success"]:
        raise HTTPException(status_code=422, detail=result["reason"])
    return result


@router.post("/discovery/reddit-matches/{match_id}/dismiss")
async def dismiss_reddit_match_route(match_id: str):
    match = db.get_reddit_match_by_id(match_id)
    if not match:
        raise HTTPException(status_code=404, detail="match_not_found")
    db.dismiss_reddit_match(match_id)
    return {"success": True}
