from __future__ import annotations

from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    field_validator,
)

from app.providers.base import ProviderName
from app.schemas.retrieval import (
    MAX_QUESTION_CHARACTERS,
    MAX_RETRIEVAL_RESULTS,
)

MAX_GROUNDED_ANSWER_CHARACTERS = 4_000


class AnswerQuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    provider: ProviderName
    model: str = Field(min_length=1, max_length=200)
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARACTERS)
    top_k: int = Field(default=5, ge=1, le=MAX_RETRIEVAL_RESULTS)

    @field_validator("question")
    @classmethod
    def question_must_contain_text(cls, question: str) -> str:
        if not question.strip():
            raise ValueError("Question must contain non-whitespace text.")
        return question.strip()


class GroundedAnswerDraft(BaseModel):
    """Provider-produced data; application grounding checks still follow."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    answer: str = Field(min_length=1, max_length=MAX_GROUNDED_ANSWER_CHARACTERS)
    abstained: StrictBool


class CitationSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: UUID
    document_id: UUID
    document_version_id: UUID
    document_key: str
    title: str
    canonical_path: str
    source_url: str | None
    heading_path: tuple[str, ...]
    similarity: float = Field(ge=-1, le=1)


class AnswerQuestionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    conversation_id: UUID
    answer: str
    abstained: StrictBool
    sources: tuple[CitationSource, ...]
    provider: ProviderName
    model: str
    generation_performed: StrictBool
    generation_latency_ms: float = Field(ge=0)
    generation_input_tokens: int = Field(ge=0)
    generation_output_tokens: int = Field(ge=0)
    finish_reason: str
    provider_request_id: str | None
    attempt_count: int = Field(ge=0)
    embedding_model: str
    embedding_latency_ms: float = Field(ge=0)
    embedding_input_tokens: int | None = Field(default=None, ge=0)
