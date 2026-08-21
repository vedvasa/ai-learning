from __future__ import annotations

import asyncio
import logging
import math
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter

from app.providers.base import (
    Provider,
    ProviderError,
    ProviderErrorKind,
    TriageResult,
)
from app.schemas.evaluation import (
    EvaluationConfiguration,
    EvaluationMetrics,
    TriageEvaluationCase,
    TriageEvaluationReport,
)
from app.services.retry import (
    RetryDeadlineExceeded,
    RetryPolicy,
    call_with_retry,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EvaluationPricing:
    input_per_million_usd: float
    output_per_million_usd: float

    def __post_init__(self) -> None:
        if (
            not math.isfinite(self.input_per_million_usd)
            or self.input_per_million_usd < 0
        ):
            raise ValueError("input price must be finite and nonnegative")
        if (
            not math.isfinite(self.output_per_million_usd)
            or self.output_per_million_usd < 0
        ):
            raise ValueError("output price must be finite and nonnegative")


@dataclass(frozen=True, slots=True)
class CaseEvaluation:
    case: TriageEvaluationCase
    duration_ms: float
    attempt_count: int
    result: TriageResult | None = None
    error_kind: ProviderErrorKind | None = None


async def evaluate_triage_cases(
    cases: list[TriageEvaluationCase],
    *,
    provider: Provider,
    retry_policy: RetryPolicy,
    timeout_seconds: float,
    concurrency: int,
    source_name: str,
    dataset_sha256: str,
    available_cases: int,
    max_cases: int,
    pricing: EvaluationPricing | None = None,
    generated_at: datetime | None = None,
) -> TriageEvaluationReport:
    if not cases:
        raise ValueError("at least one evaluation case is required")
    if concurrency < 1:
        raise ValueError("concurrency must be at least one")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be greater than zero")
    if available_cases < len(cases):
        raise ValueError("available_cases cannot be smaller than evaluated cases")
    if max_cases < len(cases):
        raise ValueError("max_cases cannot be smaller than evaluated cases")

    semaphore = asyncio.Semaphore(concurrency)

    async def evaluate_one(
        case_number: int,
        case: TriageEvaluationCase,
    ) -> CaseEvaluation:
        async with semaphore:
            return await _evaluate_one(
                case_number,
                case,
                provider=provider,
                retry_policy=retry_policy,
                timeout_seconds=timeout_seconds,
            )

    outcomes = await asyncio.gather(
        *(
            evaluate_one(case_number, case)
            for case_number, case in enumerate(cases, start=1)
        )
    )

    return TriageEvaluationReport(
        generated_at=generated_at or datetime.now(UTC),
        source_name=source_name,
        dataset_sha256=dataset_sha256,
        available_cases=available_cases,
        provider=provider.name,
        model=provider.model,
        configuration=EvaluationConfiguration(
            timeout_seconds=timeout_seconds,
            max_attempts=retry_policy.max_attempts,
            concurrency=concurrency,
            max_cases=max_cases,
            input_price_per_million_usd=(
                pricing.input_per_million_usd if pricing else None
            ),
            output_price_per_million_usd=(
                pricing.output_per_million_usd if pricing else None
            ),
        ),
        metrics=_calculate_metrics(outcomes, pricing=pricing),
    )


async def _evaluate_one(
    case_number: int,
    case: TriageEvaluationCase,
    *,
    provider: Provider,
    retry_policy: RetryPolicy,
    timeout_seconds: float,
) -> CaseEvaluation:
    started_at = perf_counter()

    def log_retry(
        failed_attempt: int,
        error: ProviderError,
        delay_seconds: float,
    ) -> None:
        logger.warning(
            "evaluation_retry_scheduled case_number=%d ticket_id=%s "
            "provider=%s model=%s failed_attempt=%d next_attempt=%d "
            "delay_seconds=%.3f error_kind=%s",
            case_number,
            case.ticket.ticket_id,
            provider.name,
            provider.model,
            failed_attempt,
            failed_attempt + 1,
            delay_seconds,
            error.kind.value,
        )

    try:
        outcome = await call_with_retry(
            lambda: provider.triage(case.ticket),
            policy=retry_policy,
            timeout_seconds=timeout_seconds,
            on_retry=log_retry,
        )
    except RetryDeadlineExceeded as error:
        return _failed_case(
            case,
            started_at=started_at,
            attempt_count=error.attempt_count,
            error_kind=ProviderErrorKind.TIMEOUT,
        )
    except ProviderError as error:
        return _failed_case(
            case,
            started_at=started_at,
            attempt_count=error.attempt_count,
            error_kind=error.kind,
        )
    except Exception:
        logger.error(
            "evaluation_case_failed case_number=%d ticket_id=%s "
            "provider=%s model=%s error_kind=failure",
            case_number,
            case.ticket.ticket_id,
            provider.name,
            provider.model,
        )
        return _failed_case(
            case,
            started_at=started_at,
            attempt_count=1,
            error_kind=ProviderErrorKind.FAILURE,
        )

    return CaseEvaluation(
        case=case,
        result=outcome.value,
        duration_ms=(perf_counter() - started_at) * 1_000,
        attempt_count=outcome.attempt_count,
    )


def _failed_case(
    case: TriageEvaluationCase,
    *,
    started_at: float,
    attempt_count: int,
    error_kind: ProviderErrorKind,
) -> CaseEvaluation:
    return CaseEvaluation(
        case=case,
        duration_ms=(perf_counter() - started_at) * 1_000,
        attempt_count=attempt_count,
        error_kind=error_kind,
    )


def _calculate_metrics(
    outcomes: list[CaseEvaluation],
    *,
    pricing: EvaluationPricing | None,
) -> EvaluationMetrics:
    total_cases = len(outcomes)
    successful = [outcome for outcome in outcomes if outcome.result is not None]
    failures = [outcome for outcome in outcomes if outcome.result is None]

    category_correct = sum(
        outcome.result.triage.category is outcome.case.expected.category
        for outcome in successful
        if outcome.result is not None
    )
    priority_correct = sum(
        outcome.result.triage.priority is outcome.case.expected.priority
        for outcome in successful
        if outcome.result is not None
    )
    review_positive_cases = [
        outcome
        for outcome in outcomes
        if outcome.case.expected.requires_human_review
    ]
    review_true_positives = sum(
        outcome.result is not None
        and outcome.result.triage.requires_human_review
        for outcome in review_positive_cases
    )

    total_input_tokens = sum(
        outcome.result.input_tokens
        for outcome in successful
        if outcome.result is not None
    )
    total_output_tokens = sum(
        outcome.result.output_tokens
        for outcome in successful
        if outcome.result is not None
    )
    total_attempts = sum(outcome.attempt_count for outcome in outcomes)
    durations = [outcome.duration_ms for outcome in successful]
    failure_counts = Counter(
        outcome.error_kind.value
        for outcome in failures
        if outcome.error_kind is not None
    )

    run_cost = None
    cost_per_100 = None
    cost_is_lower_bound = None
    if pricing is not None:
        run_cost = (
            total_input_tokens * pricing.input_per_million_usd
            + total_output_tokens * pricing.output_per_million_usd
        ) / 1_000_000
        cost_per_100 = run_cost * 100 / total_cases
        cost_is_lower_bound = bool(failures) or total_attempts > total_cases

    return EvaluationMetrics(
        total_cases=total_cases,
        successful_cases=len(successful),
        failed_cases=len(failures),
        schema_valid_response_rate=len(successful) / total_cases,
        category_accuracy=category_correct / total_cases,
        priority_accuracy=priority_correct / total_cases,
        human_review_recall=(
            review_true_positives / len(review_positive_cases)
            if review_positive_cases
            else None
        ),
        p50_duration_ms=_percentile(durations, 0.50),
        p95_duration_ms=_percentile(durations, 0.95),
        mean_input_tokens=(
            total_input_tokens / len(successful) if successful else None
        ),
        mean_output_tokens=(
            total_output_tokens / len(successful) if successful else None
        ),
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        total_attempts=total_attempts,
        mean_attempt_count=total_attempts / total_cases,
        estimated_run_cost_usd=run_cost,
        estimated_cost_per_100_usd=cost_per_100,
        cost_estimate_is_lower_bound=cost_is_lower_bound,
        failures_by_kind=dict(sorted(failure_counts.items())),
    )


def _percentile(values: list[float], percentile: float) -> float | None:
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
