from __future__ import annotations

import asyncio
import logging
import math
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from typing import Protocol, Sequence

from app.providers.base import ProviderName
from app.schemas.rag_evaluation import (
    RagCaseKind,
    RagEvaluationCase,
    RagEvaluationConfiguration,
    RagEvaluationMetrics,
    RagEvaluationReport,
)
from app.services.answering import GroundedAnswerOutcome

logger = logging.getLogger(__name__)


class GroundedAnswerEvaluator(Protocol):
    async def answer(
        self,
        *,
        provider_name: ProviderName,
        model: str,
        question: str,
        top_k: int,
        request_id: str,
    ) -> GroundedAnswerOutcome: ...


@dataclass(frozen=True, slots=True)
class RagCaseEvaluation:
    case: RagEvaluationCase
    duration_ms: float
    result: GroundedAnswerOutcome | None = None
    error_kind: str | None = None


async def evaluate_rag_cases(
    cases: Sequence[RagEvaluationCase],
    *,
    service: GroundedAnswerEvaluator,
    provider_name: ProviderName,
    model: str,
    top_k: int,
    concurrency: int,
    source_name: str,
    dataset_sha256: str,
    available_cases: int,
    max_cases: int,
    forbidden_document_keys: Sequence[str],
    generated_at: datetime | None = None,
) -> RagEvaluationReport:
    if not cases:
        raise ValueError("at least one evaluation case is required")
    if not 1 <= top_k <= 10:
        raise ValueError("top_k must be between one and ten")
    if not 1 <= concurrency <= 4:
        raise ValueError("concurrency must be between one and four")
    if available_cases < len(cases):
        raise ValueError("available_cases cannot be smaller than evaluated cases")
    if max_cases < len(cases):
        raise ValueError("max_cases cannot be smaller than evaluated cases")

    semaphore = asyncio.Semaphore(concurrency)

    async def evaluate_one(
        case_number: int,
        case: RagEvaluationCase,
    ) -> RagCaseEvaluation:
        async with semaphore:
            return await _evaluate_one(
                case_number,
                case,
                service=service,
                provider_name=provider_name,
                model=model,
                top_k=top_k,
            )

    outcomes = await asyncio.gather(
        *(
            evaluate_one(case_number, case)
            for case_number, case in enumerate(cases, start=1)
        )
    )
    return RagEvaluationReport(
        generated_at=generated_at or datetime.now(UTC),
        source_name=source_name,
        dataset_sha256=dataset_sha256,
        available_cases=available_cases,
        provider=provider_name,
        model=model,
        configuration=RagEvaluationConfiguration(
            top_k=top_k,
            concurrency=concurrency,
            max_cases=max_cases,
        ),
        metrics=_calculate_metrics(
            outcomes,
            forbidden_document_keys=set(forbidden_document_keys),
        ),
    )


async def _evaluate_one(
    case_number: int,
    case: RagEvaluationCase,
    *,
    service: GroundedAnswerEvaluator,
    provider_name: ProviderName,
    model: str,
    top_k: int,
) -> RagCaseEvaluation:
    started_at = perf_counter()
    try:
        result = await service.answer(
            provider_name=provider_name,
            model=model,
            question=case.question,
            top_k=top_k,
            request_id=f"rag-eval-{case.case_id}-{case_number}",
        )
    except Exception as error:
        error_kind = _safe_error_kind(error)
        logger.error(
            "rag_evaluation_case_failed case_number=%d case_id=%s "
            "provider=%s model=%s error_kind=%s",
            case_number,
            case.case_id,
            provider_name,
            model,
            error_kind,
        )
        return RagCaseEvaluation(
            case=case,
            duration_ms=(perf_counter() - started_at) * 1_000,
            error_kind=error_kind,
        )
    return RagCaseEvaluation(
        case=case,
        result=result,
        duration_ms=(perf_counter() - started_at) * 1_000,
    )


def _safe_error_kind(error: Exception) -> str:
    kind = getattr(error, "kind", None)
    value = getattr(kind, "value", None)
    if isinstance(value, str) and value:
        return value[:80]
    return type(error).__name__[:80]


def _calculate_metrics(
    outcomes: Sequence[RagCaseEvaluation],
    *,
    forbidden_document_keys: set[str],
) -> RagEvaluationMetrics:
    total_cases = len(outcomes)
    completed = [outcome for outcome in outcomes if outcome.result is not None]
    failures = [outcome for outcome in outcomes if outcome.result is None]
    answerable = [
        outcome
        for outcome in outcomes
        if outcome.case.kind is RagCaseKind.ANSWERABLE
    ]
    ambiguous = [
        outcome
        for outcome in outcomes
        if outcome.case.kind is RagCaseKind.AMBIGUOUS
    ]
    unanswerable = [
        outcome
        for outcome in outcomes
        if outcome.case.kind is RagCaseKind.UNANSWERABLE
    ]

    retrieval_hits = sum(_has_expected_retrieval(outcome) for outcome in answerable)
    answered_answerable = sum(
        outcome.result is not None and not outcome.result.abstained
        for outcome in answerable
    )
    ambiguous_abstentions = sum(
        outcome.result is not None and outcome.result.abstained
        for outcome in ambiguous
    )
    unanswerable_abstentions = sum(
        outcome.result is not None and outcome.result.abstained
        for outcome in unanswerable
    )
    cited_answers = [
        outcome
        for outcome in completed
        if outcome.result is not None and not outcome.result.abstained
    ]
    valid_citations = sum(_citations_are_valid(outcome) for outcome in cited_answers)
    leakage_cases = sum(
        bool(_retrieved_document_keys(outcome) & forbidden_document_keys)
        for outcome in completed
    )
    embedding_tokens = [
        outcome.result.retrieval.embedding_input_tokens
        for outcome in completed
        if outcome.result is not None
    ]
    failure_counts = Counter(
        outcome.error_kind for outcome in failures if outcome.error_kind
    )
    durations = [outcome.duration_ms for outcome in completed]

    return RagEvaluationMetrics(
        total_cases=total_cases,
        completed_cases=len(completed),
        failed_cases=len(failures),
        completion_rate=len(completed) / total_cases,
        answerable_cases=len(answerable),
        ambiguous_cases=len(ambiguous),
        unanswerable_cases=len(unanswerable),
        answerable_retrieval_hit_rate_at_k=_rate(
            retrieval_hits,
            len(answerable),
        ),
        answerable_answer_rate=_rate(answered_answerable, len(answerable)),
        ambiguous_abstention_rate=_rate(
            ambiguous_abstentions,
            len(ambiguous),
        ),
        unanswerable_abstention_rate=_rate(
            unanswerable_abstentions,
            len(unanswerable),
        ),
        citation_validity_rate=_rate(valid_citations, len(cited_answers)),
        forbidden_retrieval_leakage_cases=leakage_cases,
        p50_duration_ms=_percentile(durations, 0.50),
        p95_duration_ms=_percentile(durations, 0.95),
        total_embedding_input_tokens=(
            None
            if any(value is None for value in embedding_tokens)
            else sum(value for value in embedding_tokens if value is not None)
        ),
        total_generation_input_tokens=sum(
            outcome.result.generation_input_tokens
            for outcome in completed
            if outcome.result is not None
        ),
        total_generation_output_tokens=sum(
            outcome.result.generation_output_tokens
            for outcome in completed
            if outcome.result is not None
        ),
        total_generation_attempts=sum(
            outcome.result.attempt_count
            for outcome in completed
            if outcome.result is not None
        ),
        failures_by_kind=dict(sorted(failure_counts.items())),
    )


def _has_expected_retrieval(outcome: RagCaseEvaluation) -> bool:
    if outcome.result is None:
        return False
    return bool(
        set(outcome.case.expected_document_keys)
        & _retrieved_document_keys(outcome)
    )


def _retrieved_document_keys(outcome: RagCaseEvaluation) -> set[str]:
    if outcome.result is None:
        return set()
    return {
        match.document_key for match in outcome.result.retrieval.matches
    }


def _citations_are_valid(outcome: RagCaseEvaluation) -> bool:
    if outcome.result is None or outcome.result.abstained:
        return False
    retrieved_ids = {
        match.chunk_id for match in outcome.result.retrieval.matches
    }
    source_ids = {source.chunk_id for source in outcome.result.sources}
    return bool(source_ids) and source_ids.issubset(retrieved_ids)


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _percentile(values: Sequence[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return ordered[lower_index]
    fraction = position - lower_index
    return (
        ordered[lower_index]
        + (ordered[upper_index] - ordered[lower_index]) * fraction
    )
