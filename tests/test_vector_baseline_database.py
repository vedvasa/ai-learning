from __future__ import annotations

import os
import json

import psycopg
import pytest

from app.services.retrieval_evaluation import evaluate_retrieval
from app.services.vector_evaluation import execute_local_vectors
from test_vector_baseline import vector_inputs
from ai_learning import vector_baseline as cli

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is required for disposable local integration tests",
)


def test_actual_query_reexecution_is_deterministic_isolated_and_provider_free(vector_inputs, monkeypatch):
    import openai
    from app.core.config import Settings
    def forbidden(*args, **kwargs):
        pytest.fail("Saved-vector execution needs neither providers nor application settings")
    monkeypatch.setattr(openai.OpenAI, "__init__", forbidden)
    monkeypatch.setattr(Settings, "__init__", forbidden)
    dataset, corpus, capture = vector_inputs
    runs = []
    with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as connection:
        before = connection.execute("select count(*) from knowledge.chunks").fetchone()
        for _ in range(2):
            run = execute_local_vectors(connection, capture, dataset, corpus, source_revision="a" * 40)
            report = evaluate_retrieval(dataset, corpus, run)
            assert report.gate_passed
            assert report.by_group["reviewed"].metrics.hit_rate_at_k == 1
            assert report.by_group["provisional"].metrics.hit_rate_at_k == 1
            assert report.metrics.search_latency_samples == 40
            assert report.metrics.embedding_input_tokens is None
            assert run.evidence_kind == "synthetic_test"
            assert run.search_execution == "local_pgvector"
            other_tenant = next(result for result in run.cases if result.case_id == "assisted-other-tenant-demo-limits")
            assert other_tenant.ranked_chunks == ()
            allowed_internal = next(result for result in run.cases if result.case_id == "assisted-authorized-internal-handoff")
            assert allowed_internal.ranked_chunks[0].document.document_key == "escalation-policy"
            runs.append([result.ranked_chunks for result in run.cases])
            connection.rollback()
            assert connection.execute("select to_regclass('pg_temp.chunks')").fetchone() == (None,)
            assert connection.execute("select count(*) from knowledge.chunks").fetchone() == before
        assert runs[0] == runs[1]


def test_local_command_produces_reports_and_comparable_rerun(tmp_path, monkeypatch, vector_inputs):
    monkeypatch.setattr(cli, "_source_revision", lambda: "a" * 40)
    monkeypatch.setattr(cli, "_local_connection", lambda port: psycopg.connect(os.environ["TEST_DATABASE_URL"]))
    capture = tmp_path / "synthetic-vectors.json"
    capture.write_text(vector_inputs[2].model_dump_json())
    first = tmp_path / "first"
    second = tmp_path / "second"
    parser = cli.build_parser()
    assert cli.run_cli(parser.parse_args(["--execute", str(capture), "--output-directory", str(first)])) == 0
    assert cli.run_cli(parser.parse_args([
        "--execute", str(capture), "--output-directory", str(second),
        "--baseline-results", str(first / "results.json"),
    ])) == 0
    report = json.loads((second / "report.json").read_text())
    assert report["evaluation_mode"] == "local_vector_execution"
    assert report["comparison"]["regressed_metrics"] == []
    assert report["capture_usage"]["input_tokens"] == 123
    assert "synthetic_test" in (second / "report.md").read_text()
