from __future__ import annotations

import logging
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.providers.base import ProviderError, ProviderErrorKind, ProviderLookupError
from app.rag.repository import (
    AnswerPersistenceError,
    RetrievedChunk,
)
from app.services.answering import GroundedAnswerOutcome, GroundingError
from app.services.retrieval import RetrievalError, RetrievalErrorKind, RetrievalOutcome


class FakeAnswerService:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.calls = []
        self.source = RetrievedChunk(
            chunk_id=uuid4(),
            document_id=uuid4(),
            document_version_id=uuid4(),
            document_key="password-reset",
            title="Reset a password",
            canonical_path="/support/password-reset",
            source_url="https://support.example/password-reset",
            visibility="public",
            chunk_index=0,
            heading_path=("Reset links",),
            content="Reset links expire after 30 minutes.",
            metadata={},
            similarity=0.91,
        )
        self.conversation_id = uuid4()

    async def answer(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return GroundedAnswerOutcome(
            conversation_id=self.conversation_id,
            answer=(
                "Reset links expire after 30 minutes "
                f"[source:{self.source.chunk_id}]."
            ),
            abstained=False,
            sources=(self.source,),
            provider="openai",
            model="gpt-test",
            generation_performed=True,
            generation_latency_ms=20.5,
            generation_input_tokens=125,
            generation_output_tokens=31,
            finish_reason="completed",
            provider_request_id="provider-answer-123",
            attempt_count=1,
            retrieval=RetrievalOutcome(
                matches=(self.source,),
                embedding_model="embedding-test",
                embedding_latency_ms=4.5,
                embedding_input_tokens=9,
            ),
        )


def settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        openai_api_key="test-openai-key",
        anthropic_api_key="test-anthropic-key",
        openai_model="gpt-test",
        anthropic_model="claude-test",
    )


def client(service) -> TestClient:
    return TestClient(
        create_app(settings(), grounded_answer_service=service)
    )


def payload(**overrides):
    value = {
        "provider": "openai",
        "model": "gpt-test",
        "question": "How long does a password reset link last?",
        "top_k": 5,
    }
    value.update(overrides)
    return value


def test_answer_returns_grounded_contract_without_logging_content(caplog) -> None:
    service = FakeAnswerService()
    question = "How long does my private reset link last?"

    with caplog.at_level(logging.INFO, logger="app.api.answering"):
        with client(service) as test_client:
            response = test_client.post(
                "/api/answer",
                json=payload(question=question),
                headers={"X-Request-ID": "grounded-request-123"},
            )

    assert response.status_code == 200
    body = response.json()
    assert body["request_id"] == "grounded-request-123"
    assert body["conversation_id"] == str(service.conversation_id)
    assert body["abstained"] is False
    assert body["generation_performed"] is True
    assert body["sources"][0]["chunk_id"] == str(service.source.chunk_id)
    assert body["sources"][0]["similarity"] == 0.91
    assert body["embedding_model"] == "embedding-test"
    assert service.calls[0]["question"] == question
    assert "grounded_answer_completed" in caplog.text
    assert question not in caplog.text
    assert body["answer"] not in caplog.text
    assert service.source.content not in caplog.text


@pytest.mark.parametrize(
    "invalid_payload",
    [
        payload(question="   "),
        payload(top_k=0),
        payload(top_k=11),
        payload(tenant_id="caller-selected"),
    ],
)
def test_answer_rejects_invalid_or_caller_owned_scope(invalid_payload) -> None:
    with client(FakeAnswerService()) as test_client:
        response = test_client.post("/api/answer", json=invalid_payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_answer_is_unavailable_without_database_backed_service() -> None:
    with client(None) as test_client:
        response = test_client.post("/api/answer", json=payload())

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "grounded_answer_not_configured"


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (
            ProviderLookupError(code="unsupported_model", message="unsupported"),
            400,
            "unsupported_model",
        ),
        (
            ProviderError(ProviderErrorKind.RATE_LIMIT),
            429,
            "provider_rate_limited",
        ),
        (
            RetrievalError(RetrievalErrorKind.DATABASE),
            503,
            "retrieval_database_unavailable",
        ),
        (
            GroundingError("private grounding detail"),
            502,
            "provider_invalid_output",
        ),
        (
            AnswerPersistenceError("private database detail"),
            503,
            "answer_persistence_unavailable",
        ),
    ],
)
def test_answer_maps_failures_to_safe_responses(error, status_code, code) -> None:
    with client(FakeAnswerService(error=error)) as test_client:
        response = test_client.post(
            "/api/answer",
            json=payload(question="Sensitive question"),
            headers={"X-Request-ID": "safe-answer-error"},
        )

    assert response.status_code == status_code
    assert response.json()["error"]["code"] == code
    assert response.json()["error"]["request_id"] == "safe-answer-error"
    assert "Sensitive question" not in response.text
    assert "private" not in response.text
