from datetime import timedelta
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    line_channel_secret: str
    line_channel_access_token: str

    # Primary LLM (any OpenAI-compatible endpoint)
    llm_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    llm_api_key: str
    llm_model: str = "gemini-flash-latest"

    # Fallback LLM, used when the primary fails; leave key empty to disable
    llm_fallback_base_url: str = "https://integrate.api.nvidia.com/v1"
    llm_fallback_api_key: str = ""
    llm_fallback_model: str = "qwen/qwen3.5-397b-a17b"

    db_path: str = "data/tldr.db"
    timezone: str = "Asia/Taipei"

    retention_days: int = 7
    default_window_hours: int = 12
    cooldown_seconds: int = 60
    max_messages: int = 2000
    max_input_chars: int = 60_000
    name_cache_hours: int = 24

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def retention(self) -> timedelta:
        return timedelta(days=self.retention_days)
