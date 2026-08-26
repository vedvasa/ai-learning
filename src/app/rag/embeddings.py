from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any, Protocol, Sequence
from uuid import UUID, uuid4

from openai import OpenAI, OpenAIError


class EmbeddingError(RuntimeError):
    def __init__(self, kind: str, *, request_id: UUID | None = None) -> None:
        super().__init__(kind)
        self.kind = kind
        self.request_id = request_id


@dataclass(frozen=True, slots=True)
class EmbeddingCall:
    request_id: UUID
    latency_ms: float
    input_tokens: int | None


@dataclass(frozen=True, slots=True)
class EmbeddingResult:
    vectors: tuple[tuple[float, ...], ...]
    calls: tuple[EmbeddingCall, ...]


class EmbeddingClient(Protocol):
    model: str
    dimensions: int

    def embed_many(self, texts: Sequence[str]) -> EmbeddingResult: ...


class OpenAIEmbeddingClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str = "text-embedding-3-small",
        dimensions: int = 1536,
        batch_size: int = 64,
        timeout_seconds: float = 30,
        client: Any | None = None,
    ) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        self.model = model
        self.dimensions = dimensions
        self._batch_size = batch_size
        self._client = client or OpenAI(
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=0,
        )

    def embed_many(self, texts: Sequence[str]) -> EmbeddingResult:
        if not texts:
            return EmbeddingResult(vectors=(), calls=())
        if any(not text.strip() for text in texts):
            raise ValueError("embedding inputs must not be blank")

        vectors: list[tuple[float, ...]] = []
        calls: list[EmbeddingCall] = []
        for offset in range(0, len(texts), self._batch_size):
            batch = list(texts[offset : offset + self._batch_size])
            request_id = uuid4()
            started_at = perf_counter()
            try:
                response = self._client.embeddings.create(
                    model=self.model,
                    input=batch,
                    dimensions=self.dimensions,
                    encoding_format="float",
                )
            except OpenAIError as error:
                raise EmbeddingError(
                    type(error).__name__, request_id=request_id
                ) from error

            latency_ms = round((perf_counter() - started_at) * 1000, 2)
            ordered = sorted(response.data, key=lambda item: item.index)
            if [item.index for item in ordered] != list(range(len(batch))):
                raise EmbeddingError("invalid_embedding_indexes", request_id=request_id)

            batch_vectors = [tuple(item.embedding) for item in ordered]
            if any(len(vector) != self.dimensions for vector in batch_vectors):
                raise EmbeddingError("invalid_embedding_dimensions", request_id=request_id)

            vectors.extend(batch_vectors)
            usage = getattr(response, "usage", None)
            calls.append(
                EmbeddingCall(
                    request_id=request_id,
                    latency_ms=latency_ms,
                    input_tokens=(
                        getattr(usage, "total_tokens", None) if usage else None
                    ),
                )
            )

        return EmbeddingResult(vectors=tuple(vectors), calls=tuple(calls))
