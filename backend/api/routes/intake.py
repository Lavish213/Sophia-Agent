from __future__ import annotations

import hmac

from fastapi import APIRouter, Header, HTTPException
from loguru import logger
from pydantic import BaseModel

from backend.lib.config import get_settings
from backend.scout.intake import intake_lead

router = APIRouter()


class WebFormLead(BaseModel):
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    city: str | None = None
    state: str = "CA"
    timeline: str | None = None
    condition: str | None = None
    asking_price: str | None = None
    message: str | None = None


def _authorize(provided: str | None) -> None:
    secret = get_settings().intake_webhook_secret
    if not secret:
        logger.error("intake_secret_not_configured")
        raise HTTPException(status_code=503, detail="intake_not_configured")
    if not provided or not hmac.compare_digest(provided, secret):
        logger.warning("intake_unauthorized")
        raise HTTPException(status_code=401, detail="unauthorized")


def build_intake_notes(body: WebFormLead) -> str:
    parts = ["Submitted the website form."]
    if body.timeline:
        parts.append(f"Timeline: {body.timeline}.")
    if body.condition:
        parts.append(f"Condition: {body.condition}.")
    if body.asking_price:
        parts.append(f"Asking: {body.asking_price}.")
    if body.message:
        parts.append(f"Message: {body.message}")
    return " ".join(parts)


@router.post("/intake/web-form")
async def web_form_intake(body: WebFormLead, x_intake_secret: str | None = Header(default=None)):
    _authorize(x_intake_secret)

    if not body.phone and not body.email:
        raise HTTPException(status_code=422, detail="phone_or_email_required")

    result = intake_lead(
        "web_form",
        address=body.address,
        owner_name=body.name,
        owner_phone=body.phone,
        owner_email=body.email,
        city=body.city,
        state=body.state,
        notes=build_intake_notes(body),
    )

    if not result["success"]:
        raise HTTPException(status_code=422, detail=result["reason"])

    logger.info("web_form_intake lead_id={} created={}", result["lead_id"], result["created"])

    if get_settings().intake_auto_call and result["lead_id"]:
        from backend.voice.outbound import place_outbound_call

        try:
            call_result = place_outbound_call(result["lead_id"])
            result["call_triggered"] = call_result.get("success", False)
        except Exception as e:
            logger.exception("web_form_auto_call_failed lead_id={} error={}", result["lead_id"], str(e))
            result["call_triggered"] = False

    return result
