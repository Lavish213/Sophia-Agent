from __future__ import annotations

import contextlib

from fastapi import APIRouter, Request, WebSocket
from fastapi.responses import PlainTextResponse
from loguru import logger

from backend.lib.config import get_settings
from backend.voice.context import preload_call_context, preload_outbound_context

router = APIRouter()


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
    form = await request.form()
    call_sid = str(form.get("CallSid", ""))

    logger.info("voice_outbound_connect lead_id={} call_sid={}", lead_id, call_sid)

    laml = build_connect_laml({"lead_id": lead_id})
    return PlainTextResponse(content=laml, media_type="text/xml")


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
