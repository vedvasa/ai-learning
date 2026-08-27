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
EmbeddingBatchSize = Annotated[int, Field(ge=1, le=2_048)]
ChunkMaxTokens = Annotated[int, Field(ge=32, le=8_000)]
RetrievalSimilarity = Annotated[float, Field(ge=-1, le=1)]


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
    rag_answer_max_output_tokens: PositiveInt = 512
    max_model_cost_usd_per_request: PositiveFloat = 0.05
    usage_recorder_capacity: UsageRecorderCapacity = 1_000

    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-5.6-luna"
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-haiku-4-5-20251001"

    database_url: SecretStr | None = None
    rag_database_required: bool = False
    embedding_model: Literal["text-embedding-3-small"] = "text-embedding-3-small"
    embedding_dimensions: Literal[1536] = 1536
    embedding_batch_size: EmbeddingBatchSize = 64
    rag_chunk_max_tokens: ChunkMaxTokens = 500
    rag_tenant_id: str = Field(
        default="knowledgedesk-demo",
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
    )
    rag_retrieval_min_similarity: RetrievalSimilarity = 0

    def readiness_checks(self) -> dict[str, bool]:
        checks = {
            "openai_api_key": self._secret_is_set(self.openai_api_key),
            "anthropic_api_key": self._secret_is_set(self.anthropic_api_key),
        }
        if self.rag_database_required:
            checks["database_url"] = self._secret_is_set(self.database_url)
        return checks

    @staticmethod
    def _secret_is_set(secret: SecretStr | None) -> bool:
        return bool(secret and secret.get_secret_value().strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
