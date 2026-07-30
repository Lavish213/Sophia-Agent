import pytest

from backend.voice.agent import load_system_prompt
from backend.voice.tools import build_sophia_tool_schemas

_FAKE_KEY = "test-key-not-real"


def test_system_prompt_loads_and_is_substantive():
    prompt = load_system_prompt()
    assert "Sophia Reyes" in prompt
    assert len(prompt) > 500


def test_prompt_covers_the_objections_that_end_calls():
    prompt = load_system_prompt().lower()
    for phrase in ("where did you get my number", "take me off your list", "not interested"):
        assert phrase in prompt, f"prompt has no guidance for: {phrase}"


def test_prompt_forbids_fabricating_numbers():
    prompt = load_system_prompt().lower()
    assert "never invent a number" in prompt
    assert "never make things up" in prompt


def test_prompt_requires_admitting_it_is_ai():
    prompt = load_system_prompt().lower()
    assert "never deny being ai" in prompt


def test_prompt_has_no_unspeakable_formatting():
    prompt = load_system_prompt()
    body = "\n".join(
        line for line in prompt.splitlines()
        if not line.startswith("#") and not line.strip().startswith("**")
    )
    assert "•" not in body
    assert "→" not in body


def test_deepgram_services_construct():
    from pipecat.services.deepgram.stt import DeepgramSTTService
    from pipecat.services.deepgram.tts import DeepgramTTSService

    stt = DeepgramSTTService(api_key=_FAKE_KEY)
    tts = DeepgramTTSService(
        api_key=_FAKE_KEY,
        settings=DeepgramTTSService.Settings(voice="aura-2-luna-en"),
    )
    assert stt is not None
    assert tts is not None


def test_anthropic_service_constructs_with_the_real_prompt():
    from pipecat.services.anthropic.llm import AnthropicLLMService

    llm = AnthropicLLMService(
        api_key=_FAKE_KEY,
        settings=AnthropicLLMService.Settings(
            model="claude-sonnet-4-6",
            system_instruction=load_system_prompt(),
        ),
    )
    assert llm is not None


def test_tool_schemas_are_accepted_by_a_real_llm_context():
    from pipecat.processors.aggregators.llm_context import LLMContext

    tools = build_sophia_tool_schemas(lead_id="lead-1", on_end_call=lambda disposition: None)
    context = LLMContext(tools=tools)
    assert context is not None


def test_full_pipeline_assembles():
    from pipecat.audio.vad.silero import SileroVADAnalyzer
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

    stt = DeepgramSTTService(api_key=_FAKE_KEY)
    tts = DeepgramTTSService(
        api_key=_FAKE_KEY, settings=DeepgramTTSService.Settings(voice="aura-2-luna-en")
    )
    llm = AnthropicLLMService(
        api_key=_FAKE_KEY,
        settings=AnthropicLLMService.Settings(
            model="claude-sonnet-4-6", system_instruction=load_system_prompt()
        ),
    )

    tools = build_sophia_tool_schemas(lead_id="lead-1", on_end_call=lambda disposition: None)
    context = LLMContext(tools=tools)
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context, user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer())
    )

    pipeline = Pipeline([stt, user_aggregator, llm, tts, assistant_aggregator])
    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            enable_metrics=True, audio_in_sample_rate=8000, audio_out_sample_rate=8000
        ),
    )

    assert worker is not None


def test_telephony_sample_rate_is_8k_not_studio_quality():
    from pipecat.pipeline.worker import PipelineParams

    params = PipelineParams(audio_in_sample_rate=8000, audio_out_sample_rate=8000)
    assert params.audio_in_sample_rate == 8000
    assert params.audio_out_sample_rate == 8000


def test_serializer_imports_for_signalwire_protocol():
    from pipecat.serializers.twilio import TwilioFrameSerializer

    assert TwilioFrameSerializer is not None


@pytest.mark.parametrize("required", ["parse_telephony_websocket"])
def test_runner_helper_still_exists(required):
    from pipecat.runner import utils

    assert hasattr(utils, required), f"pipecat.runner.utils lost {required}"
