from __future__ import annotations

import tempfile

from fastapi import APIRouter, HTTPException, Query, UploadFile

from backend.lib import db
from backend.scout.ingest import ingest_csv_rows
from backend.scout.parser import parse_csv

router = APIRouter()


@router.post("/properties/upload")
async def upload_properties_csv(file: UploadFile):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="file_must_be_csv")

    contents = await file.read()
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".csv", delete=True) as tmp:
        tmp.write(contents)
        tmp.flush()
        rows = parse_csv(tmp.name)

    if not rows:
        return {"processed": 0, "leads_created": 0, "errors": 0, "message": "no_valid_rows_found"}

    return ingest_csv_rows(rows)


@router.get("/properties")
async def list_properties(min_score: int = Query(default=0, ge=0, le=100)):
    return db.get_properties_by_score(min_score)


@router.get("/properties/{property_id}")
async def get_property(property_id: str):
    prop = db.get_property_by_id(property_id)
    if not prop:
        raise HTTPException(status_code=404, detail="property_not_found")
    return prop
