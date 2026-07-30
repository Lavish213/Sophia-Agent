from __future__ import annotations

import contextlib

from fastapi import APIRouter, Request, WebSocket
from fastapi.responses import PlainTextResponse
from loguru import logger

from backend.lib import db
from backend.lib.config import get_settings
from backend.voice.context import preload_call_context, preload_outbound_context

router = APIRouter()

_TERMINAL_NO_CONNECT_STATUSES = {"busy", "failed", "no-answer", "canceled"}


def build_stream_url() -> str:
    public_url = get_settings().public_url.rstrip("/")
    return public_url.replace("https://", "wss://").replace("http://", "ws://") + "/api/voice/stream"


def build_connect_laml(extra_params: dict[str, str]) -> str:
    stream_url = build_stream_url()
    params_xml = "".join(
        f'<Parameter name="{name}" value="{value}"/>'
        for name, value in extra_params.items()
        if value
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response><Connect><Stream url=\"" + stream_url + "\">"
        + params_xml +
        "</Stream></Connect></Response>"
    )


@router.post("/voice/inbound")
async def handle_inbound_call(request: Request):
    form = await request.form()
    from_number = str(form.get("From", ""))
    to_number = str(form.get("To", ""))
    call_sid = str(form.get("CallSid", ""))

    logger.info("voice_inbound from={} call_sid={}", from_number, call_sid)

    laml = build_connect_laml({"from_number": from_number, "to_number": to_number})
    return PlainTextResponse(content=laml, media_type="text/xml")


@router.post("/voice/outbound/{lead_id}")
async def handle_outbound_connect(lead_id: str, request: Request):
    from backend.voice import voicemail

    form = await request.form()
    call_sid = str(form.get("CallSid", ""))
    answered_by = str(form.get("AnsweredBy", ""))

    logger.info(
        "voice_outbound_connect lead_id={} call_sid={} answered_by={}", lead_id, call_sid, answered_by
    )

    if voicemail.is_unusable(answered_by):
        logger.info("voice_outbound_unusable lead_id={} answered_by={}", lead_id, answered_by)
        return PlainTextResponse(content=voicemail.build_hangup_laml(), media_type="text/xml")

    if voicemail.is_machine(answered_by):
        if not voicemail.should_leave_voicemail(answered_by):
            return PlainTextResponse(content=voicemail.build_hangup_laml(), media_type="text/xml")

        lead = db.get_lead_with_property(lead_id)

        if not voicemail.voicemail_allowed(lead):
            logger.info("voicemail_cap_reached lead_id={}", lead_id)
            return PlainTextResponse(content=voicemail.build_hangup_laml(), media_type="text/xml")

        attempt = ((lead or {}).get("voicemail_count") or 0) + 1
        script = voicemail.build_voicemail_script(lead, attempt)

        call = db.get_call_by_signalwire_sid(call_sid) if call_sid else None
        voicemail.record_voicemail_left(call["id"] if call else None, lead_id, script, lead)

        return PlainTextResponse(
            content=voicemail.build_voicemail_laml(script), media_type="text/xml"
        )

    laml = build_connect_laml({"lead_id": lead_id})
    return PlainTextResponse(content=laml, media_type="text/xml")


@router.post("/voice/status")
async def handle_status_callback(request: Request):
    form = await request.form()
    call_sid = str(form.get("CallSid", ""))
    call_status = str(form.get("CallStatus", ""))

    logger.info("voice_status_callback call_sid={} status={}", call_sid, call_status)

    if not call_sid:
        return PlainTextResponse(content="ok")

    if call_status == "completed":
        call = db.get_call_by_signalwire_sid(call_sid)
        is_voicemail = bool(call and call.get("voicemail_left") and call.get("lead_id"))
        if is_voicemail and db.mark_followup_sent_if_unset(call["id"]):
            from backend.alerts.followup import send_post_call_followup
            send_post_call_followup(call["lead_id"], call["id"], "voicemail")
        return PlainTextResponse(content="ok")

    if call_status not in _TERMINAL_NO_CONNECT_STATUSES:
        return PlainTextResponse(content="ok")

    updated = db.mark_call_terminal_if_unset(call_sid, call_status)
    if updated:
        call = db.get_call_by_signalwire_sid(call_sid)
        if call and call.get("lead_id") and db.mark_followup_sent_if_unset(call["id"]):
            from backend.alerts.followup import send_post_call_followup
            send_post_call_followup(call["lead_id"], call["id"], call_status)

    return PlainTextResponse(content="ok")


@router.websocket("/voice/stream")
async def handle_voice_stream(websocket: WebSocket):
    await websocket.accept()

    try:
        from pipecat.runner.utils import parse_telephony_websocket
        from pipecat.serializers.twilio import TwilioFrameSerializer
        from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams, FastAPIWebsocketTransport

        transport_type, call_data = await parse_telephony_websocket(websocket)
        if transport_type != "twilio":
            logger.error("voice_stream_unexpected_transport_type type={}", transport_type)
            await websocket.close()
            return

        serializer = TwilioFrameSerializer(
            stream_sid=call_data.stream_id,
            call_sid=call_data.call_id,
            params=TwilioFrameSerializer.InputParams(auto_hang_up=False),
        )
        transport = FastAPIWebsocketTransport(
            websocket=websocket,
            params=FastAPIWebsocketParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                add_wav_header=False,
                serializer=serializer,
            ),
        )

        lead_id_param = (call_data.body or {}).get("lead_id")
        if lead_id_param:
            call_context = preload_outbound_context(lead_id_param)
            call_context["direction"] = "outbound"
        else:
            call_context = preload_call_context(call_data.from_number or "")
            call_context["direction"] = "inbound"
        call_context["call_sid"] = call_data.call_id

        from backend.voice.agent import run_sophia_agent
        await run_sophia_agent(transport, call_context)

    except Exception as e:
        logger.exception("voice_stream_failed error={}", str(e))
    finally:
        with contextlib.suppress(Exception):
            await websocket.close()
