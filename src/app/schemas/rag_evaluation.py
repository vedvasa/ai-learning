from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from app.providers.base import ProviderName
from app.schemas.retrieval import MAX_QUESTION_CHARACTERS


class StrictEvaluationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class RagCaseKind(StrEnum):
    ANSWERABLE = "answerable"
    AMBIGUOUS = "ambiguous"
    UNANSWERABLE = "unanswerable"


class RagExpectedBehavior(StrEnum):
    ANSWER = "answer"
    ABSTAIN_OR_CLARIFY = "abstain_or_clarify"
    ABSTAIN = "abstain"


class RagEvaluationCase(StrictEvaluationModel):
    case_id: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[a-z0-9][a-z0-9-]*$",
    )
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARACTERS)
    kind: RagCaseKind
    expected_behavior: RagExpectedBehavior
    expected_document_keys: tuple[str, ...] = Field(default=(), max_length=8)

    @model_validator(mode="after")
    def validate_expectation(self) -> Self:
        if len(self.expected_document_keys) != len(
            set(self.expected_document_keys)
        ):
            raise ValueError("expected document keys must be unique")
        if self.kind is RagCaseKind.ANSWERABLE:
            if self.expected_behavior is not RagExpectedBehavior.ANSWER:
                raise ValueError("answerable cases must expect an answer")
            if not self.expected_document_keys:
                raise ValueError(
                    "answerable cases require an expected document key"
                )
        elif self.kind is RagCaseKind.AMBIGUOUS:
            if (
                self.expected_behavior
                is not RagExpectedBehavior.ABSTAIN_OR_CLARIFY
            ):
                raise ValueError(
                    "ambiguous cases must expect abstention or clarification"
                )
        else:
            if self.expected_behavior is not RagExpectedBehavior.ABSTAIN:
                raise ValueError("unanswerable cases must expect abstention")
            if self.expected_document_keys:
                raise ValueError(
                    "unanswerable cases cannot name expected documents"
                )
        return self


class RagAcceptanceDataset(StrictEvaluationModel):
    schema_version: Literal["1.0"] = "1.0"
    dataset_name: str = Field(min_length=1, max_length=120)
    forbidden_document_keys: tuple[str, ...] = Field(min_length=1, max_length=8)
    cases: tuple[RagEvaluationCase, ...] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_unique_ids_and_questions(self) -> Self:
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("case IDs must be unique")
        questions = [case.question.casefold() for case in self.cases]
        if len(questions) != len(set(questions)):
            raise ValueError("questions must be unique")
        if len(self.forbidden_document_keys) != len(
            set(self.forbidden_document_keys)
        ):
            raise ValueError("forbidden document keys must be unique")
        expected_keys = {
            key for case in self.cases for key in case.expected_document_keys
        }
        if expected_keys.intersection(self.forbidden_document_keys):
            raise ValueError(
                "expected and forbidden document keys cannot overlap"
            )
        return self


class RagEvaluationConfiguration(StrictEvaluationModel):
    top_k: int = Field(ge=1, le=10)
    concurrency: int = Field(ge=1, le=4)
    max_cases: int = Field(ge=1, le=100)


class RagEvaluationMetrics(StrictEvaluationModel):
    total_cases: int = Field(ge=1)
    completed_cases: int = Field(ge=0)
    failed_cases: int = Field(ge=0)
    completion_rate: float = Field(ge=0, le=1)
    answerable_cases: int = Field(ge=0)
    ambiguous_cases: int = Field(ge=0)
    unanswerable_cases: int = Field(ge=0)
    answerable_retrieval_hit_rate_at_k: float | None = Field(
        default=None,
        ge=0,
        le=1,
    )
    answerable_answer_rate: float | None = Field(default=None, ge=0, le=1)
    ambiguous_abstention_rate: float | None = Field(default=None, ge=0, le=1)
    unanswerable_abstention_rate: float | None = Field(
        default=None,
        ge=0,
        le=1,
    )
    citation_validity_rate: float | None = Field(default=None, ge=0, le=1)
    forbidden_retrieval_leakage_cases: int = Field(ge=0)
    p50_duration_ms: float | None = Field(default=None, ge=0)
    p95_duration_ms: float | None = Field(default=None, ge=0)
    total_embedding_input_tokens: int | None = Field(default=None, ge=0)
    total_generation_input_tokens: int = Field(ge=0)
    total_generation_output_tokens: int = Field(ge=0)
    total_generation_attempts: int = Field(ge=0)
    failures_by_kind: dict[str, int]


class RagEvaluationReport(StrictEvaluationModel):
    schema_version: Literal["1.0"] = "1.0"
    generated_at: datetime
    source_name: str = Field(min_length=1, max_length=255)
    dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    available_cases: int = Field(ge=1)
    provider: ProviderName
    model: str = Field(min_length=1, max_length=200)
    configuration: RagEvaluationConfiguration
    metrics: RagEvaluationMetrics
    aggregate_only: StrictBool = True
