from __future__ import annotations

import logging
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.rag.repository import RetrievedChunk
from app.services.retrieval import (
    RetrievalError,
    RetrievalErrorKind,
    RetrievalOutcome,
)


class FakeRetriever:
    def __init__(self, *, error: RetrievalError | None = None) -> None:
        self.error = error
        self.calls: list[tuple[str, int]] = []
        self.match = RetrievedChunk(
            chunk_id=uuid4(),
            document_id=uuid4(),
            document_version_id=uuid4(),
            document_key="password-reset",
            title="Reset a password",
            canonical_path="/support/password-reset",
            source_url="https://support.example/password-reset",
            visibility="public",
            chunk_index=1,
            heading_path=("Reset link behavior",),
            content="Reset links expire after 30 minutes.",
            metadata={"source_path": "password-reset.md"},
            similarity=0.912345,
        )

    def retrieve(self, question: str, *, top_k: int) -> RetrievalOutcome:
        self.calls.append((question, top_k))
        if self.error is not None:
            raise self.error
        return RetrievalOutcome(
            matches=(self.match,),
            embedding_model="embedding-test",
            embedding_latency_ms=12.5,
            embedding_input_tokens=8,
        )


def make_settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        openai_api_key="test-openai-key",
        anthropic_api_key="test-anthropic-key",
    )


def make_client(
    retriever: FakeRetriever | None,
    *,
    raise_server_exceptions: bool = True,
) -> TestClient:
    return TestClient(
        create_app(make_settings(), semantic_retriever=retriever),
        raise_server_exceptions=raise_server_exceptions,
    )


def test_retrieve_returns_ranked_source_contract_without_logging_content(
    caplog,
) -> None:
    retriever = FakeRetriever()
    question = "How long does my private reset link last?"

    with caplog.at_level(logging.INFO, logger="app.api.retrieval"):
        with make_client(retriever) as client:
            response = client.post(
                "/api/retrieve",
                json={"question": question, "top_k": 3},
                headers={"X-Request-ID": "retrieval-request-123"},
            )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "retrieval-request-123"
    body = response.json()
    assert body["request_id"] == "retrieval-request-123"
    assert body["embedding_model"] == "embedding-test"
    assert body["embedding_latency_ms"] == 12.5
    assert body["embedding_input_tokens"] == 8
    assert body["matches"] == [
        {
            "chunk_id": str(retriever.match.chunk_id),
            "document_id": str(retriever.match.document_id),
            "document_version_id": str(retriever.match.document_version_id),
            "document_key": "password-reset",
            "title": "Reset a password",
            "canonical_path": "/support/password-reset",
            "source_url": "https://support.example/password-reset",
            "visibility": "public",
            "chunk_index": 1,
            "heading_path": ["Reset link behavior"],
            "content": "Reset links expire after 30 minutes.",
            "metadata": {"source_path": "password-reset.md"},
            "similarity": 0.912345,
        }
    ]
    assert retriever.calls == [(question, 3)]
    assert "retrieval_completed" in caplog.text
    assert question not in caplog.text
    assert retriever.match.content not in caplog.text


@pytest.mark.parametrize(
    "payload",
    [
        {"question": "   "},
        {"question": "question", "top_k": 0},
        {"question": "question", "top_k": 11},
        {"question": "question", "tenant_id": "attacker-selected"},
    ],
)
def test_retrieve_rejects_invalid_or_caller_owned_filters(payload) -> None:
    with make_client(FakeRetriever()) as client:
        response = client.post("/api/retrieve", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_retrieve_is_unavailable_without_server_configuration() -> None:
    with make_client(None) as client:
        response = client.post(
            "/api/retrieve", json={"question": "Where is my invoice?"}
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "retrieval_not_configured"


@pytest.mark.parametrize(
    ("kind", "status_code", "code"),
    [
        (RetrievalErrorKind.EMBEDDING, 502, "retrieval_embedding_failed"),
        (RetrievalErrorKind.INVALID_EMBEDDING, 502, "retrieval_embedding_failed"),
        (RetrievalErrorKind.DATABASE, 503, "retrieval_database_unavailable"),
    ],
)
def test_retrieve_maps_failures_to_safe_responses(kind, status_code, code) -> None:
    retriever = FakeRetriever(error=RetrievalError(kind))

    with make_client(retriever) as client:
        response = client.post(
            "/api/retrieve",
            json={"question": "Sensitive question"},
            headers={"X-Request-ID": "safe-retrieval-error"},
        )

    assert response.status_code == status_code
    assert response.json()["error"]["code"] == code
    assert response.json()["error"]["request_id"] == "safe-retrieval-error"
    assert "Sensitive question" not in response.text
