from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import uuid4

import pytest

from app.providers.base import (
    GroundedAnswerResult,
    ProviderErrorKind,
    ProviderRegistry,
)
from app.rag.repository import RetrievedChunk, StoredAnswerExchange
from app.schemas.answering import GroundedAnswerDraft
from app.services.answering import GroundedAnswerService, GroundingError
from app.services.retrieval import RetrievalOutcome
from app.services.retry import RetryPolicy


def match() -> RetrievedChunk:
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
        heading_path=("Reset links",),
        content="Reset links expire after 30 minutes.",
        metadata={},
        similarity=0.91,
    )


class FakeRetriever:
    def __init__(self, matches) -> None:
        self.matches = tuple(matches)
        self.calls = []

    def retrieve(self, question, *, top_k):
        self.calls.append((question, top_k))
        return RetrievalOutcome(
            matches=self.matches,
            embedding_model="embedding-test",
            embedding_latency_ms=5.5,
            embedding_input_tokens=8,
        )


class FakeProvider:
    name = "openai"
    model = "gpt-test"

    def __init__(
        self,
        draft: GroundedAnswerDraft | list[GroundedAnswerDraft],
    ) -> None:
        self.drafts = draft if isinstance(draft, list) else [draft]
        self.inputs = []

    async def answer_grounded(self, serialized_input):
        self.inputs.append(serialized_input)
        draft_index = min(len(self.inputs) - 1, len(self.drafts) - 1)
        return GroundedAnswerResult(
            draft=self.drafts[draft_index],
            provider="openai",
            model=self.model,
            latency_ms=15.5,
            input_tokens=100,
            output_tokens=30,
            finish_reason="completed",
            provider_request_id=f"provider-answer-{len(self.inputs)}",
        )


@dataclass
class FakeRepository:
    def __post_init__(self) -> None:
        self.saved = []
        self.conversation_id = uuid4()

    def save_answer_exchange(self, **kwargs):
        self.saved.append(kwargs)
        return StoredAnswerExchange(
            conversation_id=self.conversation_id,
            user_message_id=uuid4(),
            assistant_message_id=uuid4(),
        )


def service(
    provider,
    retriever,
    repository,
    *,
    max_attempts: int = 1,
) -> GroundedAnswerService:
    return GroundedAnswerService(
        registry=ProviderRegistry([provider]),
        retriever=retriever,
        repository=repository,
        retry_policy=RetryPolicy(max_attempts, 0, 0, 0),
        timeout_seconds=2,
        tenant_id="server-tenant",
    )


def run_answer(service):
    return asyncio.run(
        service.answer(
            provider_name="openai",
            model="gpt-test",
            question="How long does a reset link last?",
            top_k=5,
            request_id="answer-request-123",
        )
    )


def test_service_retrieves_validates_citations_and_persists_exchange() -> None:
    evidence = match()
    provider = FakeProvider(
        GroundedAnswerDraft(
            answer=f"It lasts 30 minutes [source:{evidence.chunk_id}].",
            abstained=False,
        )
    )
    retriever = FakeRetriever([evidence])
    repository = FakeRepository()

    outcome = run_answer(service(provider, retriever, repository))

    assert retriever.calls == [("How long does a reset link last?", 5)]
    assert str(evidence.chunk_id) in provider.inputs[0]
    assert outcome.sources == (evidence,)
    assert outcome.generation_performed is True
    assert outcome.attempt_count == 1
    saved = repository.saved[0]
    assert saved["tenant_id"] == "server-tenant"
    assert saved["citations"] == (evidence,)
    assert saved["generation_call"].provider == "openai"


def test_service_abstains_without_generation_when_retrieval_is_empty() -> None:
    provider = FakeProvider(
        GroundedAnswerDraft(answer="must not be used", abstained=False)
    )
    repository = FakeRepository()

    outcome = run_answer(service(provider, FakeRetriever([]), repository))

    assert provider.inputs == []
    assert outcome.abstained is True
    assert outcome.generation_performed is False
    assert outcome.attempt_count == 0
    assert repository.saved[0]["generation_call"] is None
    assert repository.saved[0]["citations"] == ()


def test_service_accepts_provider_abstention_without_citations() -> None:
    provider = FakeProvider(
        GroundedAnswerDraft(answer="There is not enough evidence.", abstained=True)
    )
    repository = FakeRepository()

    outcome = run_answer(service(provider, FakeRetriever([match()]), repository))

    assert outcome.abstained is True
    assert outcome.sources == ()
    assert repository.saved[0]["citations"] == ()


def test_service_rejects_unretrieved_citation_before_persistence() -> None:
    provider = FakeProvider(
        GroundedAnswerDraft(
            answer=f"An unsupported claim [source:{uuid4()}].",
            abstained=False,
        )
    )
    repository = FakeRepository()

    with pytest.raises(GroundingError) as caught:
        run_answer(
            service(
                provider,
                FakeRetriever([match()]),
                repository,
                max_attempts=3,
            )
        )

    assert caught.value.kind is ProviderErrorKind.INVALID_OUTPUT
    assert caught.value.attempt_count == 3
    assert len(provider.inputs) == 3
    assert repository.saved == []


def test_service_retries_invalid_citation_and_persists_only_valid_answer() -> None:
    evidence = match()
    provider = FakeProvider(
        [
            GroundedAnswerDraft(
                answer=f"Unsupported [source:{uuid4()}].",
                abstained=False,
            ),
            GroundedAnswerDraft(
                answer=f"It lasts 30 minutes [source:{evidence.chunk_id}].",
                abstained=False,
            ),
        ]
    )
    repository = FakeRepository()

    outcome = run_answer(
        service(
            provider,
            FakeRetriever([evidence]),
            repository,
            max_attempts=2,
        )
    )

    assert len(provider.inputs) == 2
    assert outcome.attempt_count == 2
    assert outcome.sources == (evidence,)
    assert outcome.generation_latency_ms == 31
    assert outcome.generation_input_tokens == 200
    assert outcome.generation_output_tokens == 60
    assert outcome.provider_request_id == "provider-answer-2"
    assert len(repository.saved) == 1
    generation_call = repository.saved[0]["generation_call"]
    assert generation_call.latency_ms == 31
    assert generation_call.input_tokens == 200
    assert generation_call.output_tokens == 60
