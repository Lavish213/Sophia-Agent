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
    llm_model: str = "claude-sonnet-4-5"

    bob_worker_interval_minutes: int = 5
    bob_batch_size: int = 20

    environment: str = "development"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
