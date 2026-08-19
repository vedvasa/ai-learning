from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PositiveFloat = Annotated[float, Field(gt=0)]
PositiveInt = Annotated[int, Field(gt=0)]
RetryAttempts = Annotated[int, Field(ge=1, le=5)]
RetryDelay = Annotated[float, Field(ge=0, le=60)]
RetryJitter = Annotated[float, Field(ge=0, le=1)]
UsageRecorderCapacity = Annotated[int, Field(ge=1, le=10_000)]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "KnowledgeDesk"
    app_env: str = "development"
    app_version: str = "0.1.0"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    llm_provider: Literal["openai", "anthropic"] = "openai"
    llm_timeout_seconds: PositiveFloat = 30
    llm_max_attempts: RetryAttempts = 3
    llm_retry_base_delay_seconds: RetryDelay = 0.25
    llm_retry_max_delay_seconds: RetryDelay = 2
    llm_retry_jitter_ratio: RetryJitter = 0.25
    llm_max_output_tokens: PositiveInt = 64
    triage_max_output_tokens: PositiveInt = 256
    max_model_cost_usd_per_request: PositiveFloat = 0.05
    usage_recorder_capacity: UsageRecorderCapacity = 1_000

    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-5.6-luna"
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-haiku-4-5-20251001"

    def readiness_checks(self) -> dict[str, bool]:
        return {
            "openai_api_key": self._secret_is_set(self.openai_api_key),
            "anthropic_api_key": self._secret_is_set(self.anthropic_api_key),
        }

    @staticmethod
    def _secret_is_set(secret: SecretStr | None) -> bool:
        return bool(secret and secret.get_secret_value().strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
