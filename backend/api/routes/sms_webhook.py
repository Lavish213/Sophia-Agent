from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse
from loguru import logger

from backend.alerts.sms import handle_inbound_sms

router = APIRouter()

_EMPTY_RESPONSE = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'


def _stop_confirmation_response() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response><Message>You've been unsubscribed and won't receive further "
        "messages. Reply START to resubscribe.</Message></Response>"
    )


@router.post("/sms/inbound")
async def handle_sms_inbound(request: Request):
    form = await request.form()
    from_number = str(form.get("From", ""))
    body = str(form.get("Body", ""))

    logger.info("sms_inbound from={}", from_number)

    action = handle_inbound_sms(from_number, body)

    if action == "opted_out":
        return PlainTextResponse(content=_stop_confirmation_response(), media_type="text/xml")

    return PlainTextResponse(content=_EMPTY_RESPONSE, media_type="text/xml")
