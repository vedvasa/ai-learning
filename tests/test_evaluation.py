from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from app.providers.base import (
    ProviderError,
    ProviderErrorKind,
    TriageResult,
)
from app.schemas.evaluation import TriageEvaluationCase
from app.schemas.triage import TicketTriage
from app.services.evaluation import (
    EvaluationPricing,
    _percentile,
    evaluate_triage_cases,
)
from app.services.retry import RetryPolicy


def make_case(
    ticket_id: str,
    *,
    category: str = "billing",
    priority: str = "medium",
    requires_human_review: bool = True,
) -> TriageEvaluationCase:
    return TriageEvaluationCase.model_validate(
        {
            "ticket": {
                "ticket_id": ticket_id,
                "subject": f"Synthetic subject for {ticket_id}",
                "body": "Synthetic ticket body that must not enter the report.",
                "channel": "email",
            },
            "expected": {
                "category": category,
                "priority": priority,
                "requires_human_review": requires_human_review,
            },
        }
    )


class FakeEvaluationProvider:
    name = "openai"
    model = "gpt-test"

    def __init__(
        self,
        *,
        fail_ticket: str | None = None,
        retry_ticket: str | None = None,
        wrong_priority_ticket: str | None = None,
        wrong_review_ticket: str | None = None,
        delay_seconds: float = 0,
    ) -> None:
        self.fail_ticket = fail_ticket
        self.retry_ticket = retry_ticket
        self.wrong_priority_ticket = wrong_priority_ticket
        self.wrong_review_ticket = wrong_review_ticket
        self.delay_seconds = delay_seconds
        self.attempts: dict[str, int] = {}
        self.active_calls = 0
        self.max_active_calls = 0

    async def triage(self, ticket) -> TriageResult:
        ticket_id = ticket.ticket_id
        self.attempts[ticket_id] = self.attempts.get(ticket_id, 0) + 1
        self.active_calls += 1
        self.max_active_calls = max(self.max_active_calls, self.active_calls)
        try:
            if self.delay_seconds:
                await asyncio.sleep(self.delay_seconds)
            if ticket_id == self.fail_ticket:
                raise ProviderError(ProviderErrorKind.INVALID_OUTPUT)
            if ticket_id == self.retry_ticket and self.attempts[ticket_id] == 1:
                raise ProviderError(ProviderErrorKind.RATE_LIMIT)

            case = CASES_BY_ID[ticket_id]
            return TriageResult(
                triage=TicketTriage(
                    category=case.expected.category,
                    priority=(
                        "low"
                        if ticket_id == self.wrong_priority_ticket
                        else case.expected.priority
                    ),
                    summary="Synthetic validated summary.",
                    sentiment="neutral",
                    requested_action="Use the fictional support workflow.",
                    requires_human_review=(
                        False
                        if ticket_id == self.wrong_review_ticket
                        else case.expected.requires_human_review
                    ),
                    confidence=0.9,
                    rationale="The synthetic ticket matches the policy label.",
                ),
                provider="openai",
                model=self.model,
                latency_ms=10,
                input_tokens=10,
                output_tokens=5,
                finish_reason="completed",
                provider_request_id=None,
            )
        finally:
            self.active_calls -= 1


CASES = [
    make_case("EVAL-1"),
    make_case(
        "EVAL-2",
        category="security",
        priority="urgent",
    ),
    make_case(
        "EVAL-3",
        category="feature_request",
        priority="low",
        requires_human_review=False,
    ),
    make_case(
        "EVAL-4",
        category="technical_issue",
        priority="high",
        requires_human_review=False,
    ),
]
CASES_BY_ID = {case.ticket.ticket_id: case for case in CASES}


def run_evaluation(
    cases: list[TriageEvaluationCase],
    provider: FakeEvaluationProvider,
    *,
    concurrency: int = 1,
    pricing: EvaluationPricing | None = None,
):
    return asyncio.run(
        evaluate_triage_cases(
            cases,
            provider=provider,
            retry_policy=RetryPolicy(
                max_attempts=2,
                base_delay_seconds=0,
                max_delay_seconds=0,
                jitter_ratio=0,
            ),
            timeout_seconds=1,
            concurrency=concurrency,
            source_name="synthetic.json",
            dataset_sha256="a" * 64,
            available_cases=30,
            max_cases=len(cases),
            pricing=pricing,
            generated_at=datetime(2026, 8, 18, tzinfo=UTC),
        )
    )


def test_evaluation_reports_quality_usage_and_cost_without_ticket_text() -> None:
    report = run_evaluation(
        CASES[:3],
        FakeEvaluationProvider(),
        pricing=EvaluationPricing(
            input_per_million_usd=1,
            output_per_million_usd=2,
        ),
    )

    assert report.available_cases == 30
    assert report.metrics.total_cases == 3
    assert report.metrics.successful_cases == 3
    assert report.metrics.failed_cases == 0
    assert report.metrics.schema_valid_response_rate == 1
    assert report.metrics.category_accuracy == 1
    assert report.metrics.priority_accuracy == 1
    assert report.metrics.human_review_recall == 1
    assert report.metrics.total_input_tokens == 30
    assert report.metrics.total_output_tokens == 15
    assert report.metrics.mean_input_tokens == 10
    assert report.metrics.mean_output_tokens == 5
    assert report.metrics.total_attempts == 3
    assert report.metrics.estimated_run_cost_usd == 0.00006
    assert report.metrics.estimated_cost_per_100_usd == 0.002
    assert report.metrics.cost_estimate_is_lower_bound is False
    serialized = report.model_dump_json()
    assert "ticket_id" not in serialized
    assert "Synthetic subject" not in serialized
    assert "Synthetic ticket body" not in serialized
    assert "Synthetic validated summary" not in serialized


def test_evaluation_counts_failures_as_incorrect_and_keeps_unknown_usage_out() -> None:
    provider = FakeEvaluationProvider(
        fail_ticket="EVAL-2",
        wrong_priority_ticket="EVAL-1",
        wrong_review_ticket="EVAL-1",
    )

    report = run_evaluation(
        CASES[:2],
        provider,
        pricing=EvaluationPricing(
            input_per_million_usd=1,
            output_per_million_usd=2,
        ),
    )

    assert report.metrics.successful_cases == 1
    assert report.metrics.failed_cases == 1
    assert report.metrics.schema_valid_response_rate == 0.5
    assert report.metrics.category_accuracy == 0.5
    assert report.metrics.priority_accuracy == 0
    assert report.metrics.human_review_recall == 0
    assert report.metrics.total_input_tokens == 10
    assert report.metrics.total_output_tokens == 5
    assert report.metrics.failures_by_kind == {"invalid_output": 1}
    assert report.metrics.cost_estimate_is_lower_bound is True


def test_evaluation_aggregates_retries_and_marks_cost_as_lower_bound() -> None:
    provider = FakeEvaluationProvider(retry_ticket="EVAL-1")

    report = run_evaluation(
        CASES[:1],
        provider,
        pricing=EvaluationPricing(
            input_per_million_usd=1,
            output_per_million_usd=2,
        ),
    )

    assert provider.attempts == {"EVAL-1": 2}
    assert report.metrics.successful_cases == 1
    assert report.metrics.total_attempts == 2
    assert report.metrics.mean_attempt_count == 2
    assert report.metrics.cost_estimate_is_lower_bound is True


def test_evaluation_bounds_concurrent_provider_calls() -> None:
    provider = FakeEvaluationProvider(delay_seconds=0.01)

    report = run_evaluation(CASES, provider, concurrency=2)

    assert report.metrics.successful_cases == 4
    assert provider.max_active_calls == 2


def test_percentile_uses_linear_interpolation_and_handles_empty_input() -> None:
    assert _percentile([], 0.95) is None
    assert _percentile([10], 0.95) == 10
    assert _percentile([10, 20, 30, 40], 0.5) == 25
    assert _percentile([10, 20, 30, 40], 0.95) == 38.5


@pytest.mark.parametrize("invalid_price", [-1, float("nan"), float("inf")])
def test_evaluation_pricing_rejects_unsafe_values(invalid_price: float) -> None:
    with pytest.raises(ValueError):
        EvaluationPricing(
            input_per_million_usd=invalid_price,
            output_per_million_usd=1,
        )
