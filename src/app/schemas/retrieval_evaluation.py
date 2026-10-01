from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.golden_retrieval import StableDocumentReference

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
NonNegativeFloat = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Rate = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
EvidenceKind = Literal["synthetic_test", "recorded_exact_vector"]


class StrictRetrievalEvaluationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class VectorEvaluationConfiguration(StrictRetrievalEvaluationModel):
    method: Literal["exact_cosine"] = "exact_cosine"
    embedding_model: Literal["text-embedding-3-small"] = "text-embedding-3-small"
    embedding_dimensions: Literal[1536] = 1536
    chunker: Literal["markdown_heading_paragraph"] = "markdown_heading_paragraph"
    chunk_max_tokens: int = Field(default=500, ge=32, le=8_000, strict=True)
    chunk_overlap_tokens: Literal[0] = 0
    top_k: int = Field(default=5, ge=1, le=10, strict=True)
    minimum_similarity: float = Field(default=0, ge=-1, le=1)
    context_policy: Literal["case_tenant_and_visibilities"] = (
        "case_tenant_and_visibilities"
    )


class RankedChunkReference(StrictRetrievalEvaluationModel):
    document: StableDocumentReference
    chunk_index: int = Field(ge=0, strict=True)


class RecordedRetrievalCase(StrictRetrievalEvaluationModel):
    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$", max_length=80)
    ranked_chunks: tuple[RankedChunkReference, ...] = Field(default=(), max_length=10)
    search_latency_ms: NonNegativeFloat | None = None
    embedding_latency_ms: NonNegativeFloat | None = None
    embedding_input_tokens: int | None = Field(default=None, ge=0, strict=True)
    error_kind: Literal["embedding", "invalid_embedding", "database"] | None = None

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        if self.error_kind is not None and self.ranked_chunks:
            raise ValueError("failed cases cannot contain ranked results")
        identities = [
            (chunk.document.tenant_id, chunk.document.document_key, chunk.chunk_index)
            for chunk in self.ranked_chunks
        ]
        if len(identities) != len(set(identities)):
            raise ValueError("ranked chunks must be unique")
        return self


class EmbeddingCaptureUsage(StrictRetrievalEvaluationModel):
    calls: int = Field(ge=0, strict=True)
    input_tokens: int | None = Field(default=None, ge=0, strict=True)
    latency_ms: NonNegativeFloat | None = None


class RecordedRetrievalRun(StrictRetrievalEvaluationModel):
    schema_version: Literal["1.0"] = "1.0"
    evidence_kind: EvidenceKind
    source_revision: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")
    search_execution: Literal["unspecified", "local_pgvector"] = "unspecified"
    vector_capture_sha256: Sha256 | None = None
    capture_usage: EmbeddingCaptureUsage | None = None
    dataset_sha256: Sha256
    corpus_sha256: Sha256
    configuration: VectorEvaluationConfiguration
    cases: tuple[RecordedRetrievalCase, ...] = Field(min_length=10, max_length=200)

    @model_validator(mode="after")
    def validate_run(self) -> Self:
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("result case IDs must be unique")
        if any(len(case.ranked_chunks) > self.configuration.top_k for case in self.cases):
            raise ValueError("results exceed the configured top k")
        if self.evidence_kind == "recorded_exact_vector" and self.source_revision is None:
            raise ValueError("recorded vector runs require a source revision")
        if self.search_execution == "local_pgvector" and self.vector_capture_sha256 is None:
            raise ValueError("local executions must identify their captured vectors")
        return self


class RetrievalMetrics(StrictRetrievalEvaluationModel):
    total_cases: int
    completed_cases: int
    failed_cases: int
    relevance_cases: int
    no_relevance_cases: int
    hit_rate_at_k: Rate | None
    recall_at_k: Rate | None
    mean_reciprocal_rank_at_k: Rate | None
    empty_result_cases: int
    no_relevance_cases_with_results: int
    unauthorized_result_cases: int
    search_latency_samples: int
    p50_search_latency_ms: NonNegativeFloat | None
    p95_search_latency_ms: NonNegativeFloat | None
    embedding_latency_samples: int
    p50_embedding_latency_ms: NonNegativeFloat | None
    p95_embedding_latency_ms: NonNegativeFloat | None
    embedding_input_tokens: int | None


class RetrievalComparison(StrictRetrievalEvaluationModel):
    baseline_results_sha256: Sha256
    maximum_metric_drop: Rate
    metric_deltas: dict[str, float | None]
    regressed_metrics: tuple[str, ...]
    provisional_metric_deltas: dict[str, float | None] = Field(default_factory=dict)


class RetrievalGroupReport(StrictRetrievalEvaluationModel):
    metrics: RetrievalMetrics
    by_category: dict[str, RetrievalMetrics]


class RetrievalEvaluationReport(StrictRetrievalEvaluationModel):
    schema_version: Literal["1.1"] = "1.1"
    evaluation_mode: Literal["ranked_result_replay", "local_vector_execution"] = "ranked_result_replay"
    evidence_kind: EvidenceKind
    source_revision: str | None
    search_execution: Literal["unspecified", "local_pgvector"]
    vector_capture_sha256: Sha256 | None
    capture_usage: EmbeddingCaptureUsage | None
    dataset_version: str
    dataset_sha256: Sha256
    corpus_sha256: Sha256
    results_sha256: Sha256
    configuration: VectorEvaluationConfiguration
    metrics: RetrievalMetrics
    by_category: dict[str, RetrievalMetrics]
    by_group: dict[Literal["reviewed", "provisional"], RetrievalGroupReport]
    comparison: RetrievalComparison | None = None
    gate_passed: bool
    replay_provider_calls: Literal[0] = 0
    replay_cost_usd: Literal[0] = 0
