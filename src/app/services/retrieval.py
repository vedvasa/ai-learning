from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable, Protocol, Sequence

from app.rag.embeddings import EmbeddingCall, EmbeddingClient, EmbeddingError
from app.rag.repository import KnowledgeSearchError, RetrievedChunk

logger = logging.getLogger(__name__)


class RetrievalErrorKind(StrEnum):
    EMBEDDING = "embedding"
    INVALID_EMBEDDING = "invalid_embedding"
    DATABASE = "database"


class RetrievalError(RuntimeError):
    def __init__(self, kind: RetrievalErrorKind) -> None:
        super().__init__(kind.value)
        self.kind = kind


class RetrievalRepository(Protocol):
    def search_chunks(
        self,
        *,
        tenant_id: str,
        query_embedding: Sequence[float],
        embedding_model: str,
        embedding_dimensions: int,
        top_k: int,
        minimum_similarity: float,
        allowed_visibilities: Sequence[str],
    ) -> tuple[RetrievedChunk, ...]: ...

    def record_embedding_calls(
        self,
        *,
        tenant_id: str,
        model: str,
        calls: Sequence[EmbeddingCall],
        operation: str = "document_embedding_batch",
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class RetrievalOutcome:
    matches: tuple[RetrievedChunk, ...]
    embedding_model: str
    embedding_latency_ms: float
    embedding_input_tokens: int | None


class SemanticRetriever:
    def __init__(
        self,
        *,
        repository: RetrievalRepository,
        embedding_client: EmbeddingClient,
        tenant_id: str,
        minimum_similarity: float,
        allowed_visibilities: Sequence[str] = ("public",),
    ) -> None:
        if not tenant_id.strip():
            raise ValueError("tenant_id must not be blank")
        if not -1 <= minimum_similarity <= 1:
            raise ValueError("minimum_similarity must be between -1 and 1")
        if not allowed_visibilities:
            raise ValueError("allowed_visibilities must not be empty")
        self._repository = repository
        self._embedding_client = embedding_client
        self._tenant_id = tenant_id
        self._minimum_similarity = minimum_similarity
        self._allowed_visibilities = tuple(allowed_visibilities)

    def retrieve(self, question: str, *, top_k: int) -> RetrievalOutcome:
        try:
            embedding_result = self._embedding_client.embed_many([question])
        except EmbeddingError as error:
            raise RetrievalError(RetrievalErrorKind.EMBEDDING) from error

        if len(embedding_result.vectors) != 1:
            raise RetrievalError(RetrievalErrorKind.INVALID_EMBEDDING)

        try:
            matches = self._repository.search_chunks(
                tenant_id=self._tenant_id,
                query_embedding=embedding_result.vectors[0],
                embedding_model=self._embedding_client.model,
                embedding_dimensions=self._embedding_client.dimensions,
                top_k=top_k,
                minimum_similarity=self._minimum_similarity,
                allowed_visibilities=self._allowed_visibilities,
            )
        except KnowledgeSearchError as error:
            raise RetrievalError(RetrievalErrorKind.DATABASE) from error

        # Telemetry is deliberately best-effort: a completed search remains useful
        # even if its operational metadata cannot be written.
        try:
            self._repository.record_embedding_calls(
                tenant_id=self._tenant_id,
                model=self._embedding_client.model,
                calls=embedding_result.calls,
                operation="query_embedding",
            )
        except Exception as error:
            logger.warning(
                "retrieval_telemetry_failed error_kind=%s",
                type(error).__name__,
            )

        return RetrievalOutcome(
            matches=matches,
            embedding_model=self._embedding_client.model,
            embedding_latency_ms=round(
                sum(call.latency_ms for call in embedding_result.calls), 2
            ),
            embedding_input_tokens=_sum_optional_tokens(
                call.input_tokens for call in embedding_result.calls
            ),
        )


def _sum_optional_tokens(values: Iterable[int | None]) -> int | None:
    collected = tuple(values)
    if any(value is None for value in collected):
        return None
    return sum(value for value in collected if value is not None)
