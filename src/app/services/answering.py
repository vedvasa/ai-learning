from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Protocol, Sequence
from uuid import UUID, uuid4

from app.providers.base import (
    GroundedAnswerResult,
    ProviderError,
    ProviderErrorKind,
    ProviderName,
    ProviderRegistry,
)
from app.rag.grounding import (
    ABSTENTION_ANSWER,
    CitationValidationError,
    serialize_grounded_input,
    validated_citation_ids,
)
from app.rag.repository import (
    AnswerGenerationCall,
    RetrievedChunk,
    StoredAnswerExchange,
)
from app.services.retrieval import RetrievalOutcome, SemanticRetriever
from app.services.retry import (
    RETRYABLE_PROVIDER_ERRORS,
    RetryOutcome,
    RetryPolicy,
    call_with_retry,
)

logger = logging.getLogger(__name__)


GROUNDED_RETRYABLE_ERRORS = RETRYABLE_PROVIDER_ERRORS | {
    ProviderErrorKind.INVALID_OUTPUT
}


class GroundingError(ProviderError):
    """Provider output passed schema validation but failed grounding checks."""

    def __init__(
        self,
        _detail: str = "provider citations failed validation",
        *,
        provider_request_id: str | None = None,
    ) -> None:
        super().__init__(
            ProviderErrorKind.INVALID_OUTPUT,
            provider_request_id=provider_request_id,
        )


class AnswerRepository(Protocol):
    def save_answer_exchange(
        self,
        *,
        tenant_id: str,
        question: str,
        answer: str,
        abstained: bool,
        citations: Sequence[RetrievedChunk],
        generation_call: AnswerGenerationCall | None,
    ) -> StoredAnswerExchange: ...


@dataclass(frozen=True, slots=True)
class GroundedAnswerOutcome:
    conversation_id: UUID
    answer: str
    abstained: bool
    sources: tuple[RetrievedChunk, ...]
    provider: ProviderName
    model: str
    generation_performed: bool
    generation_latency_ms: float
    generation_input_tokens: int
    generation_output_tokens: int
    finish_reason: str
    provider_request_id: str | None
    attempt_count: int
    retrieval: RetrievalOutcome


@dataclass(frozen=True, slots=True)
class ValidatedGroundedAnswer:
    result: GroundedAnswerResult
    sources: tuple[RetrievedChunk, ...]


class GroundedAnswerService:
    def __init__(
        self,
        *,
        registry: ProviderRegistry,
        retriever: SemanticRetriever,
        repository: AnswerRepository,
        retry_policy: RetryPolicy,
        timeout_seconds: float,
        tenant_id: str,
    ) -> None:
        self._registry = registry
        self._retriever = retriever
        self._repository = repository
        self._retry_policy = retry_policy
        self._timeout_seconds = timeout_seconds
        self._tenant_id = tenant_id

    async def answer(
        self,
        *,
        provider_name: ProviderName,
        model: str,
        question: str,
        top_k: int,
        request_id: str,
    ) -> GroundedAnswerOutcome:
        provider = self._registry.get(provider_name, model)
        retrieval = await asyncio.to_thread(
            self._retriever.retrieve,
            question,
            top_k=top_k,
        )

        if not retrieval.matches:
            stored = await asyncio.to_thread(
                self._repository.save_answer_exchange,
                tenant_id=self._tenant_id,
                question=question,
                answer=ABSTENTION_ANSWER,
                abstained=True,
                citations=(),
                generation_call=None,
            )
            return GroundedAnswerOutcome(
                conversation_id=stored.conversation_id,
                answer=ABSTENTION_ANSWER,
                abstained=True,
                sources=(),
                provider=provider_name,
                model=model,
                generation_performed=False,
                generation_latency_ms=0,
                generation_input_tokens=0,
                generation_output_tokens=0,
                finish_reason="not_called_no_evidence",
                provider_request_id=None,
                attempt_count=0,
                retrieval=retrieval,
            )

        serialized_input = serialize_grounded_input(question, retrieval.matches)

        def log_retry(
            failed_attempt: int,
            error: ProviderError,
            delay_seconds: float,
        ) -> None:
            logger.warning(
                "grounded_answer_retry_scheduled request_id=%s provider=%s "
                "model=%s failed_attempt=%d next_attempt=%d "
                "delay_seconds=%.3f error_kind=%s provider_request_id=%s",
                request_id,
                provider_name,
                model,
                failed_attempt,
                failed_attempt + 1,
                delay_seconds,
                error.kind.value,
                error.provider_request_id,
            )

        observed_results: list[GroundedAnswerResult] = []

        async def generate_validated_answer() -> ValidatedGroundedAnswer:
            result = await provider.answer_grounded(serialized_input)
            observed_results.append(result)
            return ValidatedGroundedAnswer(
                result=result,
                sources=_validated_sources(result, retrieval.matches),
            )

        retry_outcome = await call_with_retry(
            generate_validated_answer,
            policy=self._retry_policy,
            timeout_seconds=self._timeout_seconds,
            on_retry=log_retry,
            retryable_errors=GROUNDED_RETRYABLE_ERRORS,
        )
        result = retry_outcome.value.result
        sources = retry_outcome.value.sources
        generation_latency_ms = sum(
            attempt.latency_ms for attempt in observed_results
        )
        generation_input_tokens = sum(
            attempt.input_tokens for attempt in observed_results
        )
        generation_output_tokens = sum(
            attempt.output_tokens for attempt in observed_results
        )
        generation_call = AnswerGenerationCall(
            request_id=uuid4(),
            provider=result.provider,
            model=result.model,
            latency_ms=generation_latency_ms,
            input_tokens=generation_input_tokens,
            output_tokens=generation_output_tokens,
        )
        stored = await asyncio.to_thread(
            self._repository.save_answer_exchange,
            tenant_id=self._tenant_id,
            question=question,
            answer=result.draft.answer,
            abstained=result.draft.abstained,
            citations=sources,
            generation_call=generation_call,
        )
        return _outcome_from_generation(
            stored=stored,
            result=result,
            retry_outcome=retry_outcome,
            sources=sources,
            retrieval=retrieval,
            generation_latency_ms=generation_latency_ms,
            generation_input_tokens=generation_input_tokens,
            generation_output_tokens=generation_output_tokens,
        )


def _validated_sources(
    result: GroundedAnswerResult,
    matches: Sequence[RetrievedChunk],
) -> tuple[RetrievedChunk, ...]:
    try:
        citation_ids = validated_citation_ids(
            result.draft.answer,
            abstained=result.draft.abstained,
            matches=matches,
        )
    except CitationValidationError as error:
        raise GroundingError(
            provider_request_id=result.provider_request_id
        ) from error
    match_by_id = {match.chunk_id: match for match in matches}
    return tuple(match_by_id[citation_id] for citation_id in citation_ids)


def _outcome_from_generation(
    *,
    stored: StoredAnswerExchange,
    result: GroundedAnswerResult,
    retry_outcome: RetryOutcome[ValidatedGroundedAnswer],
    sources: tuple[RetrievedChunk, ...],
    retrieval: RetrievalOutcome,
    generation_latency_ms: float,
    generation_input_tokens: int,
    generation_output_tokens: int,
) -> GroundedAnswerOutcome:
    return GroundedAnswerOutcome(
        conversation_id=stored.conversation_id,
        answer=result.draft.answer,
        abstained=result.draft.abstained,
        sources=sources,
        provider=result.provider,
        model=result.model,
        generation_performed=True,
        generation_latency_ms=generation_latency_ms,
        generation_input_tokens=generation_input_tokens,
        generation_output_tokens=generation_output_tokens,
        finish_reason=result.finish_reason,
        provider_request_id=result.provider_request_id,
        attempt_count=retry_outcome.attempt_count,
        retrieval=retrieval,
    )
