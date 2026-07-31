from __future__ import annotations

from datetime import UTC, datetime

from loguru import logger

from backend.lib import db
from backend.lib.config import get_settings
from backend.voice.tools import build_sophia_tool_schemas

_PROMPT_PATH = __file__.rsplit("/", 1)[0] + "/prompts/sophia_runtime.md"


def load_system_prompt() -> str:
    with open(_PROMPT_PATH, encoding="utf-8") as f:
        return f.read()


def extract_transcript_chunks_from_messages(messages: list[dict]) -> list[dict]:
    chunks = []
    order = 0
    for message in messages:
        role = message.get("role")
        if role not in ("user", "assistant"):
            continue

        content = message.get("content")
        if isinstance(content, list):
            text = " ".join(
                block.get("text", "") for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            )
        else:
            text = str(content or "")

        text = text.strip()
        if not text:
            continue

        chunks.append({
            "speaker": "sophia" if role == "assistant" else "seller",
            "text": text,
            "sequence_order": order,
        })
        order += 1

    return chunks


def build_vad_analyzer():
    from pipecat.audio.vad.silero import SileroVADAnalyzer
    from pipecat.audio.vad.vad_analyzer import VADParams

    settings = get_settings()
    return SileroVADAnalyzer(
        params=VADParams(
            confidence=settings.vad_confidence,
            stop_secs=settings.vad_stop_secs,
        )
    )


def build_user_turn_strategies():
    from pipecat.processors.aggregators.llm_response_universal import UserTurnStrategies
    from pipecat.turns.user_stop import SpeechTimeoutUserTurnStopStrategy

    settings = get_settings()

    if settings.smart_turn_enabled:
        try:
            from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
            from pipecat.turns.user_stop.turn_analyzer_user_turn_stop_strategy import (
                TurnAnalyzerUserTurnStopStrategy,
            )

            stop = TurnAnalyzerUserTurnStopStrategy(turn_analyzer=LocalSmartTurnAnalyzerV3())
            logger.info("smart_turn_enabled")
            return UserTurnStrategies(stop=stop)
        except Exception as e:
            logger.warning("smart_turn_unavailable_falling_back error={}", str(e))

    return UserTurnStrategies(
        stop=SpeechTimeoutUserTurnStopStrategy(
            user_speech_timeout=settings.user_speech_timeout_secs
        )
    )


def resolve_final_disposition(intel: dict | None, tool_disposition: str | None, has_transcript: bool) -> str | None:
    extracted = (intel or {}).get("disposition")
    if extracted:
        return extracted
    if tool_disposition:
        return tool_disposition
    if has_transcript:
        return "WARM"
    return None


def build_pipeline_worker(transport, call_context: dict, on_end_call):
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.pipeline.worker import PipelineParams, PipelineWorker
    from pipecat.processors.aggregators.llm_context import LLMContext
    from pipecat.processors.aggregators.llm_response_universal import (
        LLMContextAggregatorPair,
        LLMUserAggregatorParams,
    )
    from pipecat.services.anthropic.llm import AnthropicLLMService
    from pipecat.services.deepgram.stt import DeepgramSTTService
    from pipecat.services.deepgram.tts import DeepgramTTSService

    settings = get_settings()

    stt = DeepgramSTTService(api_key=settings.deepgram_api_key)
    tts = DeepgramTTSService(
        api_key=settings.deepgram_api_key,
        settings=DeepgramTTSService.Settings(voice=settings.deepgram_tts_model),
    )
    llm = AnthropicLLMService(
        api_key=settings.anthropic_api_key,
        settings=AnthropicLLMService.Settings(
            model=settings.llm_model,
            system_instruction=load_system_prompt(),
        ),
    )

    tools = build_sophia_tool_schemas(lead_id=call_context.get("lead_id"), on_end_call=on_end_call)
    context = LLMContext(tools=tools)
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=build_vad_analyzer(),
            user_turn_strategies=build_user_turn_strategies(),
        ),
    )

    pipeline = Pipeline([
        transport.input(),
        stt,
        user_aggregator,
        llm,
        tts,
        transport.output(),
        assistant_aggregator,
    ])

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            audio_in_sample_rate=8000,
            audio_out_sample_rate=8000,
        ),
    )

    return worker, context, llm


async def run_sophia_agent(transport, call_context: dict) -> None:
    from pipecat.frames.frames import LLMRunFrame
    from pipecat.workers.runner import WorkerRunner

    call_id_holder: dict = {"call_id": None}
    end_disposition_holder: dict = {"disposition": None}
    started_at_holder: dict = {"started_at": None}

    def _on_end_call(disposition: str) -> None:
        end_disposition_holder["disposition"] = disposition

    worker, context, llm = build_pipeline_worker(transport, call_context, _on_end_call)

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        lead_id = call_context.get("lead_id")
        call_sid = call_context.get("call_sid")
        started_at_holder["started_at"] = datetime.now(UTC)

        existing_call = db.get_call_by_signalwire_sid(call_sid) if call_sid else None
        if existing_call:
            call_id = existing_call["id"]
        else:
            call_id = db.insert_call({
                "lead_id": lead_id,
                "direction": call_context.get("direction", "inbound"),
                "signalwire_call_id": call_sid,
            })
        call_id_holder["call_id"] = call_id
        if lead_id:
            db.insert_call_event(call_id, lead_id, "call_started")

        greeting_instruction = (
            f"The caller's first name is {call_context.get('owner_first_name', 'there')}. "
            f"{call_context.get('caller_awareness_str', '')} "
            f"{call_context.get('property_context_str', '')} "
            f"{call_context.get('call_brief_str', '')} "
            "Start the call by greeting them naturally and, if you have a property on file, "
            "referencing it briefly. If you don't recognize them, greet them and ask how you can help."
        )
        context.add_message({"role": "developer", "content": greeting_instruction})
        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        await worker.cancel()

    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)
    await runner.run()

    call_id = call_id_holder["call_id"]
    lead_id = call_context.get("lead_id")
    tool_disposition = end_disposition_holder["disposition"]
    started_at = started_at_holder["started_at"]
    duration_seconds = int((datetime.now(UTC) - started_at).total_seconds()) if started_at else None

    if call_id:
        chunks = extract_transcript_chunks_from_messages(context.messages)
        db.insert_transcript_chunks(call_id, lead_id, chunks)

        from backend.voice.post_call_intel import run_post_call_intel
        intel = run_post_call_intel(call_id, lead_id)

        final_disposition = resolve_final_disposition(intel, tool_disposition, bool(chunks))

        db.update_call_fields(call_id, {
            "call_disposition": final_disposition,
            "duration_seconds": duration_seconds,
            "ended_at": datetime.now(UTC).isoformat(),
        })
        if lead_id:
            db.update_lead_call_outcome(lead_id, final_disposition or "completed")
            db.insert_call_event(call_id, lead_id, "call_ended", {"disposition": final_disposition})

        if lead_id and final_disposition:
            from backend.alerts.followup import send_post_call_followup
            send_post_call_followup(lead_id, call_id, final_disposition)

        logger.info("call_finished call_id={} lead_id={} disposition={}", call_id, lead_id, final_disposition)
    else:
        logger.info("call_finished_no_call_row lead_id={}", lead_id)
