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


def test_vad_is_tuned_for_phone_pauses_not_default():
    from backend.lib.config import get_settings
    from backend.voice.agent import build_vad_analyzer

    analyzer = build_vad_analyzer()
    settings = get_settings()

    assert analyzer is not None
    assert settings.vad_stop_secs >= 0.5, (
        "pipecat defaults to 0.2s of silence, which cuts sellers off mid-sentence on a phone call"
    )


def test_smart_turn_is_used_when_enabled(monkeypatch):
    from backend.lib.config import get_settings
    from backend.voice.agent import build_user_turn_strategies

    monkeypatch.setenv("SMART_TURN_ENABLED", "true")
    get_settings.cache_clear()
    try:
        strategies = build_user_turn_strategies()
        assert type(strategies.stop).__name__ == "TurnAnalyzerUserTurnStopStrategy"
    finally:
        get_settings.cache_clear()


def test_falls_back_to_timeout_strategy_when_smart_turn_disabled(monkeypatch):
    from backend.lib.config import get_settings
    from backend.voice.agent import build_user_turn_strategies

    monkeypatch.setenv("SMART_TURN_ENABLED", "false")
    get_settings.cache_clear()
    try:
        strategies = build_user_turn_strategies()
        assert type(strategies.stop).__name__ == "SpeechTimeoutUserTurnStopStrategy"
    finally:
        get_settings.cache_clear()


def test_smart_turn_failure_does_not_break_the_call(monkeypatch):
    import backend.voice.agent as agent_module
    from backend.lib.config import get_settings

    monkeypatch.setenv("SMART_TURN_ENABLED", "true")
    get_settings.cache_clear()

    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def _boom(name, *args, **kwargs):
        if "smart_turn" in name:
            raise RuntimeError("model file missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", _boom)
    try:
        strategies = agent_module.build_user_turn_strategies()
        assert type(strategies.stop).__name__ == "SpeechTimeoutUserTurnStopStrategy"
    finally:
        get_settings.cache_clear()
