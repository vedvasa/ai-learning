from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_learning import retrieval_evaluation as cli
from ai_learning.golden_retrieval import DEFAULT_CORPUS, DEFAULT_WORKSHEET, load_worksheet
from app.rag.documents import load_corpus
from app.schemas.retrieval_evaluation import RecordedRetrievalRun
from app.services.retrieval_evaluation import (
    RetrievalEvaluationError,
    compare_retrieval_reports,
    corpus_sha256,
    evaluate_retrieval,
    render_retrieval_markdown,
)

FIXTURE = Path(__file__).parent / "fixtures/retrieval_evaluation/synthetic_week4_rankings.json"


@pytest.fixture
def inputs():
    loaded = load_worksheet(DEFAULT_WORKSHEET, corpus_directory=DEFAULT_CORPUS, require_complete=True)
    corpus = load_corpus(DEFAULT_CORPUS)
    run = RecordedRetrievalRun.model_validate_json(FIXTURE.read_text())
    return loaded.dataset, corpus, run


def _updated_run(run, update):
    payload = run.model_dump(mode="json")
    update(payload)
    return RecordedRetrievalRun.model_validate(payload)


def test_hand_calculated_document_metrics_and_category_denominators(inputs):
    report = evaluate_retrieval(*inputs)
    metrics = report.metrics
    assert metrics.total_cases == metrics.completed_cases == 10
    assert metrics.relevance_cases == 4
    assert metrics.no_relevance_cases == 6
    assert metrics.hit_rate_at_k == 0.75
    assert metrics.recall_at_k == 0.625
    assert metrics.mean_reciprocal_rank_at_k == 0.5
    assert metrics.empty_result_cases == 6
    assert metrics.no_relevance_cases_with_results == 1
    assert metrics.unauthorized_result_cases == 0
    assert report.by_category["multi_document"].recall_at_k == 0.75
    assert report.by_category["direct_fact"].hit_rate_at_k == 0.5
    assert report.by_category["ambiguous"].hit_rate_at_k is None
    assert report.by_category["unanswerable"].recall_at_k is None
    assert metrics.search_latency_samples == 10
    assert metrics.p50_search_latency_ms == 5.5
    assert metrics.p95_search_latency_ms == pytest.approx(9.55)
    assert metrics.p50_embedding_latency_ms == 11
    assert metrics.embedding_input_tokens == 100
    assert report.gate_passed


def test_failed_answerable_case_remains_in_denominator(inputs):
    dataset, corpus, run = inputs
    def fail(payload):
        payload["cases"][0].update(ranked_chunks=[], error_kind="database", embedding_input_tokens=None)
    report = evaluate_retrieval(dataset, corpus, _updated_run(run, fail))
    assert report.metrics.relevance_cases == 4
    assert report.metrics.hit_rate_at_k == 0.5
    assert report.metrics.failed_cases == 1
    assert report.metrics.search_latency_samples == 9
    assert report.metrics.embedding_input_tokens is None
    assert not report.gate_passed


def test_missing_timings_are_unknown_not_zero(inputs):
    dataset, corpus, run = inputs
    def remove(payload):
        for case in payload["cases"]:
            case.update(search_latency_ms=None, embedding_latency_ms=None, embedding_input_tokens=None)
    metrics = evaluate_retrieval(dataset, corpus, _updated_run(run, remove)).metrics
    assert metrics.search_latency_samples == 0
    assert metrics.embedding_latency_samples == 0
    assert metrics.p50_search_latency_ms is None
    assert metrics.p95_embedding_latency_ms is None
    assert metrics.embedding_input_tokens is None


@pytest.mark.parametrize("boundary", ["visibility", "tenant"])
def test_out_of_scope_results_fail_gate_using_corpus_metadata(inputs, boundary):
    dataset, corpus, run = inputs
    document = next(d for d in corpus if d.metadata.document_key == "escalation-policy")
    if boundary == "tenant":
        document = replace(document, metadata=document.metadata.model_copy(update={
            "tenant_id": "fictional-other-tenant", "visibility": "public",
        }))
        corpus = [*corpus, document]
    def leak(payload):
        payload["corpus_sha256"] = corpus_sha256(corpus)
        payload["cases"][0]["ranked_chunks"] = [{
            "document": {
                "tenant_id": document.metadata.tenant_id,
                "document_key": document.metadata.document_key,
                "document_version": document.metadata.version,
                "content_sha256": document.content_hash,
            }, "chunk_index": 0,
        }]
    report = evaluate_retrieval(dataset, corpus, _updated_run(run, leak))
    assert report.metrics.unauthorized_result_cases == 1
    assert report.metrics.hit_rate_at_k == 0.5
    assert not report.gate_passed


@pytest.mark.parametrize("field", ["dataset_sha256", "corpus_sha256"])
def test_hash_mismatch_is_rejected(inputs, field):
    dataset, corpus, run = inputs
    run = _updated_run(run, lambda payload: payload.update({field: "0" * 64}))
    with pytest.raises(RetrievalEvaluationError, match="hashes"):
        evaluate_retrieval(dataset, corpus, run)


def test_corpus_hash_is_order_independent_and_pins_visibility(inputs):
    _, corpus, _ = inputs
    assert corpus_sha256(corpus) == corpus_sha256(list(reversed(corpus)))
    changed = replace(corpus[0], metadata=corpus[0].metadata.model_copy(update={"visibility": "internal"}))
    assert corpus_sha256(corpus) != corpus_sha256([changed, *corpus[1:]])


@pytest.mark.parametrize("field,value", [
    ("document_version", 999), ("content_sha256", "0" * 64), ("document_key", "unknown-document"),
])
def test_stale_or_unknown_result_references_are_rejected(inputs, field, value):
    dataset, corpus, run = inputs
    def change(payload):
        payload["cases"][0]["ranked_chunks"][0]["document"][field] = value
    with pytest.raises(RetrievalEvaluationError, match="missing or stale"):
        evaluate_retrieval(dataset, corpus, _updated_run(run, change))


def test_result_case_coverage_is_exact_and_order_independent(inputs):
    dataset, corpus, run = inputs
    shuffled = _updated_run(run, lambda payload: payload["cases"].reverse())
    assert evaluate_retrieval(dataset, corpus, shuffled).metrics == evaluate_retrieval(*inputs).metrics
    unknown = _updated_run(run, lambda payload: payload["cases"][0].update(case_id="unknown-case"))
    with pytest.raises(RetrievalEvaluationError, match="every dataset case"):
        evaluate_retrieval(dataset, corpus, unknown)


@pytest.mark.parametrize("mutation", [
    lambda p: p["cases"].append(p["cases"][0]),
    lambda p: p["cases"][0]["ranked_chunks"].append(p["cases"][0]["ranked_chunks"][0]),
    lambda p: p["cases"][0].update(error_kind="database"),
    lambda p: p["cases"][0].update(search_latency_ms=float("nan")),
    lambda p: p["cases"][0].update(embedding_latency_ms=float("inf")),
    lambda p: p["cases"][0].update(search_latency_ms=-1),
    lambda p: p["cases"][0].update(raw_error="sensitive-content"),
    lambda p: p["configuration"].update(top_k=1),
    lambda p: p.update(evidence_kind="recorded_exact_vector"),
])
def test_result_contract_rejects_invalid_or_content_bearing_data(inputs, mutation):
    with pytest.raises(ValidationError):
        _updated_run(inputs[2], mutation)


def test_regression_comparison_detects_deliberately_removed_evidence(inputs):
    dataset, corpus, run = inputs
    baseline = evaluate_retrieval(*inputs)
    degraded = _updated_run(run, lambda p: p["cases"][0].update(ranked_chunks=[]))
    report = compare_retrieval_reports(evaluate_retrieval(dataset, corpus, degraded), baseline)
    assert not report.gate_passed
    assert report.comparison.regressed_metrics == (
        "hit_rate_at_k", "recall_at_k", "mean_reciprocal_rank_at_k",
    )
    assert report.comparison.metric_deltas["hit_rate_at_k"] == -0.25
    assert compare_retrieval_reports(baseline, baseline).gate_passed
    assert compare_retrieval_reports(
        evaluate_retrieval(dataset, corpus, degraded), baseline, maximum_metric_drop=0.25,
    ).gate_passed


@pytest.mark.parametrize("field,value", [
    ("dataset_sha256", "0" * 64), ("corpus_sha256", "0" * 64),
    ("evidence_kind", "recorded_exact_vector"), ("gate_passed", False),
])
def test_comparison_rejects_incompatible_or_failing_baseline(inputs, field, value):
    report = evaluate_retrieval(*inputs)
    with pytest.raises(RetrievalEvaluationError):
        compare_retrieval_reports(report, report.model_copy(update={field: value}))


def test_comparison_rejects_different_configuration_and_invalid_threshold(inputs):
    report = evaluate_retrieval(*inputs)
    changed = report.model_copy(update={"configuration": report.configuration.model_copy(update={"top_k": 4})})
    with pytest.raises(RetrievalEvaluationError, match="not comparable"):
        compare_retrieval_reports(report, changed)
    for value in (-1, 2, float("nan")):
        with pytest.raises(RetrievalEvaluationError):
            compare_retrieval_reports(report, report, maximum_metric_drop=value)


def test_reports_are_aggregate_only_and_disclose_replay_limits(inputs):
    dataset, _, _ = inputs
    report = evaluate_retrieval(*inputs)
    markdown = render_retrieval_markdown(report)
    rendered = report.model_dump_json() + markdown
    for case in dataset.cases:
        assert case.case_id not in rendered
        assert case.question not in rendered
        assert case.context.principal_id not in rendered
        for ref in case.expected_relevant_documents:
            assert ref.document_key not in rendered
    assert "synthetic_test" in markdown
    assert "does not rerun vector search" in markdown
    assert "not an answer-abstention score" in markdown


def test_cli_runs_without_settings_providers_or_database(tmp_path, monkeypatch, capsys):
    import psycopg
    import openai
    from app.core.config import Settings
    def forbidden(*args, **kwargs):
        pytest.fail("Offline evaluation must not construct external clients or settings")
    monkeypatch.setattr(Settings, "__init__", forbidden)
    monkeypatch.setattr(openai.OpenAI, "__init__", forbidden)
    monkeypatch.setattr(psycopg, "connect", forbidden)
    args = cli.build_parser().parse_args([
        "--results", str(FIXTURE), "--baseline-results", str(FIXTURE),
        "--output-directory", str(tmp_path),
    ])
    assert cli.run_cli(args) == 0
    first = (tmp_path / "report.json").read_bytes()
    assert cli.run_cli(args) == 0
    assert first == (tmp_path / "report.json").read_bytes()
    assert (tmp_path / "report.md").exists()
    assert "synthetic_test" in capsys.readouterr().out
    assert cli.run_cli(cli.build_parser().parse_args(["--validate-only"])) == 0


def test_cli_minimum_40_cases_is_a_distinct_gate(capsys):
    assert cli.run_cli(cli.build_parser().parse_args(["--validate-only", "--minimum-cases", "40"])) == 2
    assert "minimum case count" in capsys.readouterr().err


def test_changed_first_human_label_is_rejected_without_repair(inputs):
    dataset, _, _ = inputs
    changed_case = dataset.cases[0].model_copy(update={"question": "Changed test question"})
    changed_dataset = dataset.model_copy(update={"cases": (changed_case, *dataset.cases[1:])})
    with pytest.raises(RetrievalEvaluationError, match="first ten labels"):
        cli.validate_checkpoint(changed_dataset, corpus_directory=DEFAULT_CORPUS)


def test_cli_rejects_malformed_results_without_echoing_contents(tmp_path, capsys):
    path = tmp_path / "bad.json"
    path.write_text('{"secret": "DO-NOT-ECHO"}')
    assert cli.run_cli(cli.build_parser().parse_args(["--results", str(path)])) == 2
    output = capsys.readouterr()
    assert "DO-NOT-ECHO" not in output.err + output.out


def test_cli_regression_writes_reports_and_exits_nonzero(inputs, tmp_path):
    run = _updated_run(inputs[2], lambda p: p["cases"][0].update(ranked_chunks=[]))
    path = tmp_path / "degraded.json"
    path.write_text(run.model_dump_json())
    assert cli.run_cli(cli.build_parser().parse_args([
        "--results", str(path), "--baseline-results", str(FIXTURE),
        "--output-directory", str(tmp_path / "reports"),
    ])) == 1
    report = json.loads((tmp_path / "reports/report.json").read_text())
    assert not report["gate_passed"]


def test_cli_cannot_overwrite_input_results(tmp_path):
    path = tmp_path / "report.json"
    path.write_bytes(FIXTURE.read_bytes())
    original = path.read_bytes()
    assert cli.run_cli(cli.build_parser().parse_args([
        "--results", str(path), "--output-directory", str(tmp_path),
    ])) == 2
    assert path.read_bytes() == original
