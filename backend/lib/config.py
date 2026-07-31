from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_url: str
    supabase_service_key: str

    anthropic_api_key: str
    deepgram_api_key: str

    signalwire_project_id: str = ""
    signalwire_token: str = ""
    signalwire_space: str = ""
    signalwire_phone: str = ""

    business_name: str = "San Joaquin House Buyers"
    agent_name: str = "Sophia Reyes"
    agent_phone: str = ""
    owner_phone: str = ""
    public_url: str = ""

    calling_hours_start: int = 9
    calling_hours_end: int = 21

    mao_multiplier: float = 0.70
    mao_repair_buffer_dollars: int = 25000

    log_level: str = "INFO"

    deepgram_stt_model: str = "nova-2"
    deepgram_tts_model: str = "aura-2-luna-en"
    llm_model: str = "claude-sonnet-4-6"

    bob_worker_interval_minutes: int = 5
    bob_batch_size: int = 20

    sendgrid_api_key: str = ""
    from_email: str = ""

    max_concurrent_outbound: int = 3
    dialer_interval_minutes: int = 10
    dialer_batch_size: int = 10
    outbound_reattempt_hours: int = 20

    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "sophia-agent:sjhb-monitor:v1.0"
    reddit_poll_interval_minutes: int = 30
    reddit_fetch_limit: int = 25

    intake_webhook_secret: str = ""
    intake_auto_call: bool = False

    smart_turn_enabled: bool = True
    vad_stop_secs: float = 0.6
    vad_confidence: float = 0.7
    user_speech_timeout_secs: float = 0.8

    machine_detection_timeout_seconds: int = 30
    voicemail_voice: str = ""
    max_voicemails_per_lead: int = 3

    batchdata_api_key: str = ""
    skiptrace_batch_size: int = 25

    environment: str = "development"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
