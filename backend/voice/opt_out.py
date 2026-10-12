import asyncio
import re

from loguru import logger
from pipecat.frames.frames import EndWorkerFrame, TranscriptionFrame, TTSSpeakFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from backend.lib import db

_STOP = re.compile(
    r"\b(stop calling|stop contacting|take me off|do not call|don't call|remove me|"
    r"lose my number|never call again|leave me alone|no me llames|deja de llamar)\b",
    re.IGNORECASE,
)


def stop_requested(text: str) -> bool:
    return bool(_STOP.search(text)) or text.strip().lower().strip(".!?") == "stop"


async def persist_stop(call_context: dict) -> str:
    call_context["stop_requested"] = True
    phone = call_context.get("caller_phone") or (call_context.get("lead") or {}).get("owner_phone")
    try:
        persisted = bool(phone) and await asyncio.to_thread(
            db.suppress_voice_contact,
            call_context.get("lead_id"),
            phone,
        )
    except Exception:
        persisted = False
        logger.exception("voice_opt_out_persistence_failed call_sid={}", call_context.get("call_sid"))
    if persisted:
        return "Understood. Your number has been removed from our contact list. Goodbye."
    logger.critical("voice_opt_out_requires_recovery call_sid={}", call_context.get("call_sid"))
    return (
        "Understood. I'm ending this call. I couldn't confirm your number was removed from the contact list. Goodbye."
    )


class VoiceOptOutGuard(FrameProcessor):
    def __init__(self, call_context: dict, on_end_call):
        super().__init__()
        self.call_context = call_context
        self.on_end_call = on_end_call
        self.worker = None

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if direction == FrameDirection.DOWNSTREAM and isinstance(frame, TranscriptionFrame):
            if self.call_context.get("stop_requested"):
                return
            if stop_requested(frame.text):
                response = await persist_stop(self.call_context)
                self.on_end_call("OPTED_OUT")
                if self.worker:
                    await self.worker.queue_frames([TTSSpeakFrame(response), EndWorkerFrame()])
                return
        await self.push_frame(frame, direction)
