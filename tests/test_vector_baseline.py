from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from ai_learning import vector_baseline as cli
from ai_learning.golden_retrieval import DEFAULT_CORPUS
from ai_learning.retrieval_working_set import DEFAULT_REVIEWED_WORKSHEET, load_evaluation_dataset
from app.rag.documents import load_corpus
from app.rag.embeddings import EmbeddingCall, EmbeddingResult
from app.schemas.retrieval_evaluation import VectorEvaluationConfiguration
from app.schemas.vector_capture import VectorCapture
from app.services.retrieval_evaluation import RetrievalEvaluationError
from app.services.vector_evaluation import capture_plan, capture_vectors, prepare_vector_inputs, validate_capture


@pytest.fixture(scope="module")
def vector_inputs():
    dataset = load_evaluation_dataset(worksheet=DEFAULT_REVIEWED_WORKSHEET, include_provisional=True)
    corpus = load_corpus(DEFAULT_CORPUS)
    config = VectorEvaluationConfiguration()
    chunks = prepare_vector_inputs(dataset, corpus, config)
    document_indices = {document.metadata.document_key: i for i, document in enumerate(corpus)}
    def vector(key):
        index = document_indices[key]
        return tuple(1.0 if i == index else 0.0 for i in range(1536))
    vectors = [vector(ref.document.document_key) for ref, _ in chunks]
    vectors += [
        vector(case.expected_relevant_documents[0].document_key if case.expected_relevant_documents
               else corpus[0].metadata.document_key) for case in dataset.cases
    ]
    client = SimpleNamespace(
        model=config.embedding_model, dimensions=1536,
        embed_many=lambda texts: EmbeddingResult(
            vectors=tuple(vectors), calls=(EmbeddingCall(uuid4(), 10, 123),),
        ),
    )
    capture = capture_vectors(dataset, corpus, config, client=client, source_revision="a" * 40)
    # These are deliberately hand-assigned vectors, never real quality evidence.
    capture = capture.model_copy(update={"evidence_kind": "synthetic_test"})
    return dataset, corpus, capture


def test_plan_matches_capture_and_preserves_actual_usage(vector_inputs):
    dataset, corpus, capture = vector_inputs
    chunks = validate_capture(capture, dataset, corpus)
    plan = capture_plan(dataset, chunks, capture.configuration)
    assert (plan["documents"], plan["chunks"], plan["queries"]) == (21, 63, 40)
    assert plan["maximum_api_requests"] == 2
    assert 0 < plan["estimated_input_tokens"] <= 4000
    assert capture.embedding_input_tokens == 123
    assert capture.embedding_latency_ms == 10
    assert capture.embedding_calls == 1


@pytest.mark.parametrize("mutation", [
    lambda p: p.update(dataset_sha256="0" * 64),
    lambda p: p.update(corpus_sha256="0" * 64),
    lambda p: p["chunks"][0].update(input_sha256="0" * 64),
    lambda p: p["chunks"][0]["reference"].update(chunk_index=999),
    lambda p: p["chunks"].pop(),
    lambda p: p["queries"][0].update(input_sha256="0" * 64),
    lambda p: p["queries"].pop(),
])
def test_changed_input_or_chunker_mapping_rejected(vector_inputs, mutation):
    dataset, corpus, capture = vector_inputs
    payload = capture.model_dump(mode="json")
    mutation(payload)
    with pytest.raises(RetrievalEvaluationError):
        validate_capture(VectorCapture.model_validate(payload), dataset, corpus)


@pytest.mark.parametrize("vector", [
    [0.0] * 1536, [1.0] * 10, [float("nan")] * 1536,
    [float("inf")] * 1536, [1e100] * 1536, [1e-50] * 1536,
])
def test_invalid_vectors_rejected_before_database_access(vector_inputs, vector):
    payload = vector_inputs[2].model_dump(mode="json")
    payload["queries"][0]["vector"] = vector
    with pytest.raises(ValidationError):
        VectorCapture.model_validate(payload)


def test_duplicate_queries_and_content_fields_rejected(vector_inputs):
    payload = vector_inputs[2].model_dump(mode="json")
    payload["queries"][0]["raw_text"] = "Never store raw prompts in capture artifacts"
    with pytest.raises(ValidationError):
        VectorCapture.model_validate(payload)
    del payload["queries"][0]["raw_text"]
    payload["queries"].append(payload["queries"][0])
    with pytest.raises(ValidationError):
        VectorCapture.model_validate(payload)


def test_plan_and_spend_guards_do_not_prompt_or_create_clients(tmp_path, monkeypatch):
    import openai
    import psycopg
    from app.core.config import Settings
    def forbidden(*args, **kwargs):
        pytest.fail("No credentials, providers, settings, or database before approved capture")
    monkeypatch.setattr(cli, "_prompt_api_key", forbidden)
    monkeypatch.setattr(openai.OpenAI, "__init__", forbidden)
    monkeypatch.setattr(Settings, "__init__", forbidden)
    monkeypatch.setattr(psycopg, "connect", forbidden)
    parser = cli.build_parser()
    assert cli.run_cli(parser.parse_args(["--plan"])) == 0
    output = tmp_path / "capture.json"
    assert cli.run_cli(parser.parse_args(["--capture-to", str(output)])) == 2
    assert cli.run_cli(parser.parse_args([
        "--capture-to", str(output), "--confirm-spend", "--maximum-input-tokens", "1",
    ])) == 2
    output.write_text("Existing capture must survive")
    assert cli.run_cli(parser.parse_args(["--capture-to", str(output), "--confirm-spend"])) == 2
    assert output.read_text() == "Existing capture must survive"


def test_execute_rejects_malformed_capture_without_echo_or_db(tmp_path, monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail("Malformed captures must fail before database access")
    monkeypatch.setattr(cli, "_local_connection", forbidden)
    path = tmp_path / "bad.json"
    path.write_text('{"sensitive": "DO-NOT-ECHO"}')
    assert cli.run_cli(cli.build_parser().parse_args(["--execute", str(path)])) == 2
    output = capsys.readouterr()
    assert "DO-NOT-ECHO" not in output.out + output.err


def test_capture_writes_only_validated_artifact_without_database(tmp_path, monkeypatch, vector_inputs):
    def forbidden(*args, **kwargs):
        pytest.fail("Capture must not connect to the database")
    monkeypatch.setattr(cli, "_local_connection", forbidden)
    monkeypatch.setattr(cli, "_source_revision", lambda: "a" * 40)
    monkeypatch.setattr(cli, "_prompt_api_key", lambda: "synthetic-unit-test-placeholder")
    clients = []
    monkeypatch.setattr(cli, "OpenAIEmbeddingClient", lambda **kwargs: clients.append(kwargs) or object())
    monkeypatch.setattr(cli, "capture_vectors", lambda *args, **kwargs: vector_inputs[2])
    output = tmp_path / "capture.json"
    assert cli.run_cli(cli.build_parser().parse_args([
        "--capture-to", str(output), "--confirm-spend", "--maximum-input-tokens", "4000",
    ])) == 0
    assert clients[0]["batch_size"] == 64
    assert "synthetic-unit-test-placeholder" not in output.read_text()
    assert VectorCapture.model_validate_json(output.read_text()) == vector_inputs[2]


def test_client_initialization_error_cannot_echo_credentials(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_source_revision", lambda: "a" * 40)
    monkeypatch.setattr(cli, "_prompt_api_key", lambda: "synthetic-unit-test-placeholder")
    def fail(**kwargs):
        raise RuntimeError("DO-NOT-ECHO")
    monkeypatch.setattr(cli, "OpenAIEmbeddingClient", fail)
    assert cli.run_cli(cli.build_parser().parse_args([
        "--capture-to", str(tmp_path / "capture.json"), "--confirm-spend",
    ])) == 2
    output = capsys.readouterr()
    assert "DO-NOT-ECHO" not in output.out + output.err


def test_local_execution_failure_rolls_back_without_echo(tmp_path, monkeypatch, capsys, vector_inputs):
    class Connection:
        rolled_back = False
        closed = False
        def rollback(self):
            self.rolled_back = True
        def close(self):
            self.closed = True
    connection = Connection()
    def fail(*args, **kwargs):
        import psycopg
        raise psycopg.OperationalError("DO-NOT-ECHO")
    monkeypatch.setattr(cli, "_source_revision", lambda: "a" * 40)
    monkeypatch.setattr(cli, "_local_connection", lambda port: connection)
    monkeypatch.setattr(cli, "execute_local_vectors", fail)
    path = tmp_path / "capture.json"
    path.write_text(vector_inputs[2].model_dump_json())
    assert cli.run_cli(cli.build_parser().parse_args(["--execute", str(path)])) == 2
    assert connection.rolled_back and connection.closed
    assert "DO-NOT-ECHO" not in capsys.readouterr().err
