from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

import pytest

from app.rag.embeddings import EmbeddingCall, EmbeddingError, EmbeddingResult
from app.rag.repository import KnowledgeSearchError, RetrievedChunk
from app.services.retrieval import (
    RetrievalError,
    RetrievalErrorKind,
    SemanticRetriever,
)


def retrieved_chunk() -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_version_id=uuid4(),
        document_key="password-reset",
        title="Reset a password",
        canonical_path="/support/password-reset",
        source_url="https://support.example/password-reset",
        visibility="public",
        chunk_index=0,
        heading_path=("Reset link",),
        content="Reset links expire after 30 minutes.",
        metadata={"source_path": "password-reset.md"},
        similarity=0.91,
    )


class FakeEmbeddingClient:
    model = "embedding-test"
    dimensions = 2

    def __init__(
        self,
        *,
        result: EmbeddingResult | None = None,
        error: EmbeddingError | None = None,
    ) -> None:
        self.result = result or EmbeddingResult(
            vectors=((0.1, 0.2),),
            calls=(EmbeddingCall(uuid4(), 12.5, 7),),
        )
        self.error = error
        self.inputs: list[list[str]] = []

    def embed_many(self, texts):
        self.inputs.append(list(texts))
        if self.error is not None:
            raise self.error
        return self.result


@dataclass
class FakeRepository:
    search_error: KnowledgeSearchError | None = None
    telemetry_error: Exception | None = None

    def __post_init__(self) -> None:
        self.searches: list[dict] = []
        self.telemetry: list[dict] = []

    def search_chunks(self, **kwargs):
        self.searches.append(kwargs)
        if self.search_error is not None:
            raise self.search_error
        return (retrieved_chunk(),)

    def record_embedding_calls(self, **kwargs):
        self.telemetry.append(kwargs)
        if self.telemetry_error is not None:
            raise self.telemetry_error


def make_retriever(
    repository: FakeRepository,
    embedding_client: FakeEmbeddingClient | None = None,
) -> SemanticRetriever:
    return SemanticRetriever(
        repository=repository,
        embedding_client=embedding_client or FakeEmbeddingClient(),
        tenant_id="tenant-from-server",
        minimum_similarity=0.25,
        allowed_visibilities=("public",),
    )


def test_retriever_embeds_once_and_applies_server_owned_filters() -> None:
    repository = FakeRepository()
    embedding_client = FakeEmbeddingClient()

    outcome = make_retriever(repository, embedding_client).retrieve(
        "How long does a reset link last?", top_k=4
    )

    assert embedding_client.inputs == [["How long does a reset link last?"]]
    assert len(outcome.matches) == 1
    assert outcome.embedding_model == "embedding-test"
    assert outcome.embedding_latency_ms == 12.5
    assert outcome.embedding_input_tokens == 7
    assert repository.searches == [
        {
            "tenant_id": "tenant-from-server",
            "query_embedding": (0.1, 0.2),
            "embedding_model": "embedding-test",
            "embedding_dimensions": 2,
            "top_k": 4,
            "minimum_similarity": 0.25,
            "allowed_visibilities": ("public",),
        }
    ]
    assert repository.telemetry[0]["operation"] == "query_embedding"


def test_retriever_maps_embedding_and_database_failures() -> None:
    embedding_failure = make_retriever(
        FakeRepository(),
        FakeEmbeddingClient(error=EmbeddingError("provider detail")),
    )
    with pytest.raises(RetrievalError) as embedding_error:
        embedding_failure.retrieve("question", top_k=5)
    assert embedding_error.value.kind is RetrievalErrorKind.EMBEDDING

    database_failure = make_retriever(
        FakeRepository(search_error=KnowledgeSearchError("database detail"))
    )
    with pytest.raises(RetrievalError) as database_error:
        database_failure.retrieve("question", top_k=5)
    assert database_error.value.kind is RetrievalErrorKind.DATABASE


def test_retriever_rejects_invalid_embedding_cardinality() -> None:
    client = FakeEmbeddingClient(
        result=EmbeddingResult(vectors=(), calls=())
    )

    with pytest.raises(RetrievalError) as caught:
        make_retriever(FakeRepository(), client).retrieve("question", top_k=5)

    assert caught.value.kind is RetrievalErrorKind.INVALID_EMBEDDING


def test_retrieval_telemetry_failure_does_not_discard_search(caplog) -> None:
    repository = FakeRepository(
        telemetry_error=RuntimeError("private database detail")
    )

    outcome = make_retriever(repository).retrieve("secret question", top_k=5)

    assert len(outcome.matches) == 1
    assert "retrieval_telemetry_failed" in caplog.text
    assert "error_kind=RuntimeError" in caplog.text
    assert "private database detail" not in caplog.text
    assert "secret question" not in caplog.text


def test_missing_embedding_token_usage_remains_unknown() -> None:
    client = FakeEmbeddingClient(
        result=EmbeddingResult(
            vectors=((0.1, 0.2),),
            calls=(EmbeddingCall(uuid4(), 1.0, None),),
        )
    )

    outcome = make_retriever(FakeRepository(), client).retrieve(
        "question", top_k=5
    )

    assert outcome.embedding_input_tokens is None
