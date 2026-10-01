from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Sequence

from app.rag.documents import SourceDocument
from app.schemas.golden_retrieval import GoldenRetrievalDataset, RetrievalCategory
from app.schemas.retrieval_working_set import RetrievalWorkingSet
from app.schemas.retrieval_evaluation import (
    RecordedRetrievalCase,
    RecordedRetrievalRun,
    RetrievalComparison,
    RetrievalEvaluationReport,
    RetrievalMetrics,
    RetrievalGroupReport,
)

RELEVANCE_METRICS = (
    "hit_rate_at_k",
    "recall_at_k",
    "mean_reciprocal_rank_at_k",
)


class RetrievalEvaluationError(ValueError):
    """Content-free evaluation error suitable for operator output."""


def _canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        .encode("utf-8")
    ).hexdigest()


def corpus_sha256(corpus: Sequence[SourceDocument]) -> str:
    # Include visibility, even though it is outside the document body hash.
    return _canonical_hash([
        {
            "tenant_id": document.metadata.tenant_id,
            "document_key": document.metadata.document_key,
            "document_version": document.metadata.version,
            "content_sha256": document.content_hash,
            "visibility": document.metadata.visibility,
        }
        for document in sorted(
            corpus,
            key=lambda document: (
                document.metadata.tenant_id, document.metadata.document_key
            ),
        )
    ])


@dataclass(frozen=True)
class _ScoredCase:
    group: str
    category: str
    result: RecordedRetrievalCase
    relevant: bool
    hit: float
    recall: float
    reciprocal_rank: float
    unauthorized: bool


def evaluate_retrieval(
    dataset: GoldenRetrievalDataset | RetrievalWorkingSet,
    corpus: Sequence[SourceDocument],
    run: RecordedRetrievalRun,
) -> RetrievalEvaluationReport:
    dataset_hash = _canonical_hash(dataset.model_dump(mode="json"))
    corpus_hash = corpus_sha256(corpus)
    if run.dataset_sha256 != dataset_hash or run.corpus_sha256 != corpus_hash:
        raise RetrievalEvaluationError("Results do not match the dataset and corpus hashes.")
    results = {result.case_id: result for result in run.cases}
    if set(results) != {case.case_id for case in dataset.cases}:
        raise RetrievalEvaluationError("Results must cover every dataset case exactly once.")
    documents = {
        (document.metadata.tenant_id, document.metadata.document_key): document
        for document in corpus
    }
    reviewed_ids = {
        case.case_id for case in (
            dataset.reviewed.cases if isinstance(dataset, RetrievalWorkingSet) else dataset.cases
        )
    }
    scored = []
    for case in dataset.cases:
        result = results[case.case_id]
        expected = {
            (reference.tenant_id, reference.document_key)
            for reference in case.expected_relevant_documents
        }
        found = set()
        first_rank = None
        unauthorized = False
        for rank, chunk in enumerate(result.ranked_chunks, start=1):
            reference = chunk.document
            identity = (reference.tenant_id, reference.document_key)
            document = documents.get(identity)
            if document is None or (
                reference.document_version != document.metadata.version
                or reference.content_sha256 != document.content_hash
            ):
                raise RetrievalEvaluationError("A retrieved document reference is missing or stale.")
            allowed = (
                reference.tenant_id == case.context.tenant_id
                and document.metadata.visibility in case.context.allowed_visibilities
            )
            unauthorized |= not allowed
            if allowed and identity in expected:
                found.add(identity)
                if first_rank is None:
                    first_rank = rank
        scored.append(_ScoredCase(
            group="reviewed" if case.case_id in reviewed_ids else "provisional",
            category=case.category.value,
            result=result,
            relevant=bool(expected),
            hit=float(bool(found)),
            recall=len(found) / len(expected) if expected else 0,
            reciprocal_rank=1 / first_rank if first_rank is not None else 0,
            unauthorized=unauthorized,
        ))

    mixed = any(case.group == "provisional" for case in scored)
    metrics = _aggregate(scored, suppress_relevance=mixed)
    return RetrievalEvaluationReport(
        evidence_kind=run.evidence_kind,
        source_revision=run.source_revision,
        search_execution=run.search_execution,
        vector_capture_sha256=run.vector_capture_sha256,
        capture_usage=run.capture_usage,
        dataset_version=dataset.dataset_version,
        dataset_sha256=dataset_hash,
        corpus_sha256=corpus_hash,
        results_sha256=_canonical_hash(run.model_dump(mode="json")),
        configuration=run.configuration,
        metrics=metrics,
        by_category={
            category.value: _aggregate([
                case for case in scored if case.category == category.value
            ], suppress_relevance=mixed)
            for category in RetrievalCategory
        },
        by_group={
            group: RetrievalGroupReport(
                metrics=_aggregate([case for case in scored if case.group == group]),
                by_category={
                    category.value: _aggregate([
                        case for case in scored
                        if case.group == group and case.category == category.value
                    ]) for category in RetrievalCategory
                },
            ) for group in ("reviewed", "provisional")
        },
        gate_passed=not (metrics.failed_cases or metrics.unauthorized_result_cases),
    )


def _aggregate(cases: Sequence[_ScoredCase], *, suppress_relevance: bool = False) -> RetrievalMetrics:
    completed = [case for case in cases if case.result.error_kind is None]
    relevant = [case for case in cases if case.relevant]
    denominator = len(relevant) if not suppress_relevance else 0
    search_latencies = [
        case.result.search_latency_ms for case in completed
        if case.result.search_latency_ms is not None
    ]
    embedding_latencies = [
        case.result.embedding_latency_ms for case in completed
        if case.result.embedding_latency_ms is not None
    ]
    tokens = [case.result.embedding_input_tokens for case in cases]
    return RetrievalMetrics(
        total_cases=len(cases),
        completed_cases=len(completed),
        failed_cases=len(cases) - len(completed),
        relevance_cases=len(relevant),
        no_relevance_cases=len(cases) - len(relevant),
        hit_rate_at_k=sum(case.hit for case in relevant) / denominator if denominator else None,
        recall_at_k=sum(case.recall for case in relevant) / denominator if denominator else None,
        mean_reciprocal_rank_at_k=(
            sum(case.reciprocal_rank for case in relevant) / denominator
            if denominator else None
        ),
        empty_result_cases=sum(not case.result.ranked_chunks for case in completed),
        no_relevance_cases_with_results=sum(
            not case.relevant and bool(case.result.ranked_chunks) for case in completed
        ),
        unauthorized_result_cases=sum(case.unauthorized for case in cases),
        search_latency_samples=len(search_latencies),
        p50_search_latency_ms=_percentile(search_latencies, 0.50),
        p95_search_latency_ms=_percentile(search_latencies, 0.95),
        embedding_latency_samples=len(embedding_latencies),
        p50_embedding_latency_ms=_percentile(embedding_latencies, 0.50),
        p95_embedding_latency_ms=_percentile(embedding_latencies, 0.95),
        embedding_input_tokens=(
            sum(value for value in tokens if value is not None)
            if tokens and all(value is not None for value in tokens) else None
        ),
    )


def _percentile(values: Sequence[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower, upper = math.floor(position), math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def compare_retrieval_reports(
    current: RetrievalEvaluationReport,
    baseline: RetrievalEvaluationReport,
    *,
    maximum_metric_drop: float = 0,
) -> RetrievalEvaluationReport:
    if not math.isfinite(maximum_metric_drop) or not 0 <= maximum_metric_drop <= 1:
        raise RetrievalEvaluationError("Maximum metric drop must be between zero and one.")
    for field in ("dataset_sha256", "corpus_sha256", "configuration", "evidence_kind",
                  "search_execution", "vector_capture_sha256"):
        if getattr(current, field) != getattr(baseline, field):
            raise RetrievalEvaluationError("Baseline and current run are not comparable.")
    if not baseline.gate_passed:
        raise RetrievalEvaluationError("A failing run cannot serve as the baseline.")
    deltas = {}
    for name in RELEVANCE_METRICS:
        value = getattr(current.by_group["reviewed"].metrics, name)
        previous = getattr(baseline.by_group["reviewed"].metrics, name)
        deltas[name] = value - previous if value is not None and previous is not None else None
    regressed = tuple(
        name for name, delta in deltas.items()
        if delta is not None and delta < -maximum_metric_drop - 1e-12
    )
    return current.model_copy(update={
        "comparison": RetrievalComparison(
            baseline_results_sha256=baseline.results_sha256,
            maximum_metric_drop=maximum_metric_drop,
            metric_deltas=deltas,
            regressed_metrics=regressed,
            provisional_metric_deltas={
                name: (
                    getattr(current.by_group["provisional"].metrics, name)
                    - getattr(baseline.by_group["provisional"].metrics, name)
                    if getattr(current.by_group["provisional"].metrics, name) is not None
                    and getattr(baseline.by_group["provisional"].metrics, name) is not None
                    else None
                ) for name in RELEVANCE_METRICS
            },
        ),
        "gate_passed": current.gate_passed and not regressed,
    })


def render_retrieval_markdown(report: RetrievalEvaluationReport) -> str:
    def rate(value: float | None) -> str:
        return "n/a" if value is None else f"{value:.3f}"

    rows = [
        "# Retrieval evaluation",
        "",
        f"Evidence: **{report.evidence_kind}**; mode: {report.evaluation_mode}.",
        "Synthetic evidence tests evaluation logic, not semantic quality. Ranked-result replay does not rerun vector search.",
        f"Vector capture SHA-256: `{report.vector_capture_sha256 or 'none'}`",
        "",
        f"Dataset SHA-256: `{report.dataset_sha256}`",
        f"Corpus SHA-256: `{report.corpus_sha256}`",
        f"Results SHA-256: `{report.results_sha256}`",
        "",
        f"Top k: {report.configuration.top_k} chunks; gate: **{'PASS' if report.gate_passed else 'FAIL'}**.",
        "",
        "Reviewed relevance scores drive acceptance; provisional scores are diagnostic.",
        "Mixed-group relevance scores are deliberately omitted. Failures and leakage fail either group.",
        "",
        "| Group / category | Cases | Relevance cases | Hit@k | Recall@k | MRR@k | Failures | Leakage |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    group_rows = [
        (f"{group} / {name}", metrics)
        for group, result in report.by_group.items()
        for name, metrics in [("all", result.metrics), *result.by_category.items()]
    ]
    for name, metrics in group_rows:
        rows.append(
            f"| {name} | {metrics.total_cases} | {metrics.relevance_cases} | "
            f"{rate(metrics.hit_rate_at_k)} | {rate(metrics.recall_at_k)} | "
            f"{rate(metrics.mean_reciprocal_rank_at_k)} | {metrics.failed_cases} | "
            f"{metrics.unauthorized_result_cases} |"
        )
    metrics = report.metrics
    rows.extend([
        "",
        "Relevance averages include failed answerable cases as zero; cases with no "
        "relevant-document labels are excluded. Repeated chunks do not increase document recall.",
        "",
        f"Cases with no relevance labels that returned results: {metrics.no_relevance_cases_with_results} "
        f"of {metrics.no_relevance_cases}. This is not an answer-abstention score.",
        "",
        f"Source search latency p50 / p95 (ms): {rate(metrics.p50_search_latency_ms)} / "
        f"{rate(metrics.p95_search_latency_ms)} ({metrics.search_latency_samples} successful samples).",
        f"Source embedding latency p50 / p95 (ms): {rate(metrics.p50_embedding_latency_ms)} / "
        f"{rate(metrics.p95_embedding_latency_ms)} ({metrics.embedding_latency_samples} successful samples).",
        "Latencies describe the supplied source run, not replay wall time; synthetic timings are not production evidence.",
        f"Source embedding input tokens: {metrics.embedding_input_tokens if metrics.embedding_input_tokens is not None else 'unknown'}.",
        "Evaluation provider calls: 0. Evaluation API cost: $0. Source capture cost: not estimated.",
    ])
    if report.comparison is not None:
        rows.extend([
            "",
            f"Baseline results SHA-256: `{report.comparison.baseline_results_sha256}`",
            f"Allowed absolute metric drop: {report.comparison.maximum_metric_drop:.3f}.",
            "Regressed metrics: " + (", ".join(report.comparison.regressed_metrics) or "none") + ".",
            "Provisional metric deltas (diagnostic only): " + ", ".join(
                f"{name}={rate(value)}" for name, value in report.comparison.provisional_metric_deltas.items()
            ) + ".",
        ])
    if report.capture_usage is not None:
        usage = report.capture_usage
        rows.extend([
            "",
            f"Saved embedding capture: {usage.calls} calls; input tokens: "
            f"{usage.input_tokens if usage.input_tokens is not None else 'unknown'}; "
            f"latency (ms): {rate(usage.latency_ms)}.",
            "Capture usage includes corpus and queries together; it is not incurred by local execution "
            "and cannot be apportioned to individual queries from batched timings.",
        ])
    return "\n".join(rows) + "\n"
