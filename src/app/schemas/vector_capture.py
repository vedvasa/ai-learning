from __future__ import annotations

import math
import struct
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from app.schemas.retrieval_evaluation import (
    NonNegativeFloat, RankedChunkReference, Sha256,
    StrictRetrievalEvaluationModel, VectorEvaluationConfiguration,
)

Vector = Annotated[tuple[float, ...], Field(min_length=1536, max_length=1536)]


class CapturedVector(StrictRetrievalEvaluationModel):
    vector: Vector
    input_sha256: Sha256

    @field_validator("vector")
    @classmethod
    def validate_vector(cls, value):
        norm = math.fsum(component * component for component in value)
        if not math.isfinite(norm) or norm <= 0 or any(abs(component) > 3e38 for component in value):
            raise ValueError("vectors must be finite, nonzero, and fit pgvector float32")
        if not any(struct.unpack("!f", struct.pack("!f", component))[0] for component in value):
            raise ValueError("vectors must remain nonzero after conversion to float32")
        return value


class CapturedChunk(CapturedVector):
    reference: RankedChunkReference


class CapturedQuery(CapturedVector):
    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$", max_length=80)


class VectorCapture(StrictRetrievalEvaluationModel):
    schema_version: Literal["1.0"] = "1.0"
    evidence_kind: Literal["synthetic_test", "recorded_openai_embeddings"]
    source_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    dataset_sha256: Sha256
    corpus_sha256: Sha256
    configuration: VectorEvaluationConfiguration
    chunks: tuple[CapturedChunk, ...] = Field(min_length=1, max_length=10000)
    queries: tuple[CapturedQuery, ...] = Field(min_length=10, max_length=200)
    embedding_calls: int = Field(ge=0, strict=True)
    embedding_input_tokens: int | None = Field(default=None, ge=0, strict=True)
    embedding_latency_ms: NonNegativeFloat | None = None

    @model_validator(mode="after")
    def validate_capture(self) -> Self:
        queries = [query.case_id for query in self.queries]
        chunks = [
            (chunk.reference.document.tenant_id, chunk.reference.document.document_key,
             chunk.reference.chunk_index) for chunk in self.chunks
        ]
        if len(queries) != len(set(queries)) or len(chunks) != len(set(chunks)):
            raise ValueError("captured inputs must be unique")
        if self.evidence_kind == "recorded_openai_embeddings" and self.embedding_calls < 1:
            raise ValueError("recorded captures require actual embedding calls")
        return self
