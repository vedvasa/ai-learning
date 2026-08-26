from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_QUESTION_CHARACTERS = 2_000
MAX_RETRIEVAL_RESULTS = 10


class RetrievalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARACTERS)
    top_k: int = Field(default=5, ge=1, le=MAX_RETRIEVAL_RESULTS)

    @field_validator("question")
    @classmethod
    def question_must_contain_text(cls, question: str) -> str:
        if not question.strip():
            raise ValueError("Question must contain non-whitespace text.")
        return question.strip()


class RetrievalMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: UUID
    document_id: UUID
    document_version_id: UUID
    document_key: str
    title: str
    canonical_path: str
    source_url: str | None
    visibility: str
    chunk_index: int = Field(ge=0)
    heading_path: tuple[str, ...]
    content: str
    metadata: dict[str, Any]
    similarity: float = Field(ge=-1, le=1)


class RetrievalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    embedding_model: str
    embedding_latency_ms: float = Field(ge=0)
    embedding_input_tokens: int | None = Field(default=None, ge=0)
    matches: tuple[RetrievalMatch, ...]
