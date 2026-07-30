from __future__ import annotations

from fastapi import APIRouter
from loguru import logger

from backend.lib import db
from backend.lib.config import get_settings

router = APIRouter()


@router.get("/health")
async def health():
    settings = get_settings()
    checks = {}

    try:
        db.health_check()
        checks["supabase"] = "ok"
    except Exception as e:
        logger.warning("health_check_supabase_failed error={}", str(e))
        checks["supabase"] = "error"

    checks["anthropic"] = "configured" if settings.anthropic_api_key else "not_configured"
    checks["deepgram"] = "configured" if settings.deepgram_api_key else "not_configured"
    signalwire_ready = settings.signalwire_project_id and settings.signalwire_token
    checks["signalwire"] = "configured" if signalwire_ready else "not_configured"

    overall = "ok" if checks["supabase"] == "ok" else "degraded"
    return {"status": overall, "checks": checks}
