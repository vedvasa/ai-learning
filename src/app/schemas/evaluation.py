from datetime import datetime
from typing import Literal

from pydantic import Field, StrictBool

from app.providers.base import ProviderName
from app.schemas.triage import (
    StrictContract,
    SupportTicket,
    TicketCategory,
    TicketPriority,
)


class ExpectedTriageLabels(StrictContract):
    category: TicketCategory
    priority: TicketPriority
    requires_human_review: StrictBool


class TriageEvaluationCase(StrictContract):
    ticket: SupportTicket
    expected: ExpectedTriageLabels


class EvaluationConfiguration(StrictContract):
    timeout_seconds: float = Field(gt=0)
    max_attempts: int = Field(ge=1)
    concurrency: int = Field(ge=1)
    max_cases: int = Field(ge=1)
    input_price_per_million_usd: float | None = Field(default=None, ge=0)
    output_price_per_million_usd: float | None = Field(default=None, ge=0)


class EvaluationMetrics(StrictContract):
    total_cases: int = Field(ge=1)
    successful_cases: int = Field(ge=0)
    failed_cases: int = Field(ge=0)
    schema_valid_response_rate: float = Field(ge=0, le=1)
    category_accuracy: float = Field(ge=0, le=1)
    priority_accuracy: float = Field(ge=0, le=1)
    human_review_recall: float | None = Field(default=None, ge=0, le=1)
    p50_duration_ms: float | None = Field(default=None, ge=0)
    p95_duration_ms: float | None = Field(default=None, ge=0)
    mean_input_tokens: float | None = Field(default=None, ge=0)
    mean_output_tokens: float | None = Field(default=None, ge=0)
    total_input_tokens: int = Field(ge=0)
    total_output_tokens: int = Field(ge=0)
    total_attempts: int = Field(ge=1)
    mean_attempt_count: float = Field(ge=1)
    estimated_run_cost_usd: float | None = Field(default=None, ge=0)
    estimated_cost_per_100_usd: float | None = Field(default=None, ge=0)
    cost_estimate_is_lower_bound: bool | None = None
    failures_by_kind: dict[str, int]


class TriageEvaluationReport(StrictContract):
    schema_version: Literal["1.0"] = "1.0"
    generated_at: datetime
    source_name: str = Field(min_length=1, max_length=255)
    dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    available_cases: int = Field(ge=1)
    provider: ProviderName
    model: str = Field(min_length=1, max_length=200)
    configuration: EvaluationConfiguration
    metrics: EvaluationMetrics
