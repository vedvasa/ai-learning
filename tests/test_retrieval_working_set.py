from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_learning import retrieval_evaluation as cli
from ai_learning.golden_retrieval import DEFAULT_CORPUS, GoldenDatasetError, canonical_sha256
from ai_learning.retrieval_working_set import DEFAULT_REVIEWED_WORKSHEET, load_evaluation_dataset
from app.rag.documents import load_corpus
from app.schemas.retrieval_evaluation import (
    RankedChunkReference, RecordedRetrievalCase, RecordedRetrievalRun, VectorEvaluationConfiguration,
)
from app.schemas.retrieval_working_set import RetrievalWorkingSet
from app.services.retrieval_evaluation import (
    RetrievalEvaluationError, compare_retrieval_reports, corpus_sha256, evaluate_retrieval,
)


@pytest.fixture
def working_inputs():
    dataset = load_evaluation_dataset(worksheet=DEFAULT_REVIEWED_WORKSHEET, include_provisional=True)
    corpus = load_corpus(DEFAULT_CORPUS)
    run = RecordedRetrievalRun(
        evidence_kind="synthetic_test", dataset_sha256=canonical_sha256(dataset),
        corpus_sha256=corpus_sha256(corpus), configuration=VectorEvaluationConfiguration(),
        cases=tuple(RecordedRetrievalCase(
            case_id=case.case_id,
            ranked_chunks=tuple(RankedChunkReference(document=ref, chunk_index=0)
                                for ref in case.expected_relevant_documents),
        ) for case in dataset.cases),
    )
    return dataset, corpus, run


def change_result(run, case_id, **update):
    payload = run.model_dump(mode="json")
    next(case for case in payload["cases"] if case["case_id"] == case_id).update(update)
    return RecordedRetrievalRun.model_validate(payload)


def test_composition_excludes_accepted_draft_duplicates_and_preserves_provenance(working_inputs):
    dataset, _, _ = working_inputs
    assert len(dataset.cases) == len({case.case_id for case in dataset.cases}) == 40
    assert len(dataset.reviewed.cases) == 16
    assert len(dataset.provisional) == 24
    assert all(case.label_provenance.human_reviewed for case in dataset.reviewed.cases)
    assert not any(case.label_provenance.human_reviewed for case in dataset.provisional)
    assert len({case.case_id for case in dataset.reviewed.cases} & {
        case.case_id for case in dataset.provisional
    }) == 0


def test_reviewed_copy_cannot_silently_diverge_from_draft(tmp_path):
    payload = json.loads(DEFAULT_REVIEWED_WORKSHEET.read_text())
    payload["slots"][-1]["label"]["question"] += " Changed."
    path = tmp_path / "changed.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(GoldenDatasetError, match="pinned draft"):
        load_evaluation_dataset(worksheet=path, include_provisional=True)


def test_duplicate_groups_rejected(working_inputs):
    dataset, _, _ = working_inputs
    payload = dataset.model_dump(mode="json")
    payload["provisional"][0]["case_id"] = dataset.reviewed.cases[0].case_id
    with pytest.raises(ValidationError, match="unique"):
        RetrievalWorkingSet.model_validate(payload)


def test_group_denominators_and_no_blended_relevance_score(working_inputs):
    dataset, corpus, run = working_inputs
    # One reviewed multi-document case returns only one of two required sources.
    case = next(case for case in dataset.reviewed.cases if len(case.expected_relevant_documents) == 2)
    result = next(result for result in run.cases if result.case_id == case.case_id)
    run = change_result(run, case.case_id, ranked_chunks=[result.ranked_chunks[0].model_dump(mode="json")])
    report = evaluate_retrieval(dataset, corpus, run)
    assert report.metrics.total_cases == 40
    assert report.metrics.relevance_cases == 24
    assert report.metrics.hit_rate_at_k is None
    assert all(category.hit_rate_at_k is None for category in report.by_category.values())
    reviewed = report.by_group["reviewed"].metrics
    provisional = report.by_group["provisional"].metrics
    assert (reviewed.total_cases, reviewed.relevance_cases, reviewed.no_relevance_cases) == (16, 7, 9)
    assert reviewed.hit_rate_at_k == 1
    assert reviewed.recall_at_k == pytest.approx(6.5 / 7)
    assert (provisional.total_cases, provisional.relevance_cases, provisional.no_relevance_cases) == (24, 17, 7)
    assert provisional.recall_at_k == 1


@pytest.mark.parametrize("group,should_pass", [("reviewed", False), ("provisional", True)])
def test_only_reviewed_relevance_regression_blocks_acceptance(working_inputs, group, should_pass):
    dataset, corpus, run = working_inputs
    cases = dataset.reviewed.cases if group == "reviewed" else dataset.provisional
    case = next(case for case in cases if not case.should_abstain)
    baseline = evaluate_retrieval(dataset, corpus, run)
    current = evaluate_retrieval(dataset, corpus, change_result(run, case.case_id, ranked_chunks=[]))
    report = compare_retrieval_reports(current, baseline)
    assert report.gate_passed is should_pass
    if group == "provisional":
        assert report.comparison.provisional_metric_deltas["hit_rate_at_k"] == pytest.approx(-1 / 17)
        assert report.comparison.metric_deltas["hit_rate_at_k"] == 0


@pytest.mark.parametrize("group", ["reviewed", "provisional"])
@pytest.mark.parametrize("problem", ["leakage", "failure"])
def test_execution_failures_and_scope_violations_fail_both_groups(working_inputs, group, problem):
    dataset, corpus, run = working_inputs
    cases = dataset.reviewed.cases if group == "reviewed" else dataset.provisional
    case = next(case for case in cases if list(case.context.allowed_visibilities) == ["public"])
    update = {"ranked_chunks": [], "error_kind": "database"}
    if problem == "leakage":
        internal = next(ref for item in dataset.reviewed.cases for ref in item.expected_relevant_documents
                        if ref.document_key == "escalation-policy")
        update = {"ranked_chunks": [{"document": internal.model_dump(mode="json"), "chunk_index": 0}]}
    report = evaluate_retrieval(dataset, corpus, change_result(run, case.case_id, **update))
    assert not report.gate_passed
    metrics = report.by_group[group].metrics
    assert metrics.failed_cases + metrics.unauthorized_result_cases == 1


def test_review_status_change_invalidates_hash_and_comparison(working_inputs):
    dataset, corpus, run = working_inputs
    payload = dataset.model_dump(mode="json")
    case = payload["provisional"].pop(0)
    case["label_provenance"] = {
        "origin": "model_assisted", "annotator_role": "project_owner",
        "labeled_on": "2026-09-30", "human_reviewed": True,
    }
    payload["reviewed"]["cases"].append(case)
    changed = RetrievalWorkingSet.model_validate(payload)
    assert canonical_sha256(changed) != canonical_sha256(dataset)
    with pytest.raises(RetrievalEvaluationError, match="hashes"):
        evaluate_retrieval(changed, corpus, run)
    new_run = run.model_copy(update={"dataset_sha256": canonical_sha256(changed)})
    with pytest.raises(RetrievalEvaluationError, match="not comparable"):
        compare_retrieval_reports(evaluate_retrieval(changed, corpus, new_run), evaluate_retrieval(*working_inputs))


def test_working_cli_is_provider_free_and_reports_groups(tmp_path, monkeypatch, working_inputs):
    import openai
    import psycopg
    from app.core.config import Settings
    def forbidden(*args, **kwargs):
        pytest.fail("Working-set replay must not construct external clients/settings")
    for target in (Settings, openai.OpenAI):
        monkeypatch.setattr(target, "__init__", forbidden)
    monkeypatch.setattr(psycopg, "connect", forbidden)
    parser = cli.build_parser()
    assert cli.run_cli(parser.parse_args(["--include-provisional", "--validate-only", "--minimum-cases", "40"])) == 0
    results = tmp_path / "rankings.json"
    results.write_text(working_inputs[2].model_dump_json())
    assert cli.run_cli(parser.parse_args([
        "--include-provisional", "--results", str(results), "--baseline-results", str(results),
        "--output-directory", str(tmp_path / "reports"),
    ])) == 0
    report = json.loads((tmp_path / "reports/report.json").read_text())
    assert report["metrics"]["hit_rate_at_k"] is None
    assert report["by_group"]["reviewed"]["metrics"]["relevance_cases"] == 7
    assert "provisional / all" in (tmp_path / "reports/report.md").read_text()
