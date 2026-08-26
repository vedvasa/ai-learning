from __future__ import annotations

import asyncio
import json
from collections import Counter
from pathlib import Path
from uuid import uuid4

from ai_learning import rag_evaluation
from ai_learning.rag_evaluation import load_dataset
from app.core.config import Settings
from app.rag.repository import RetrievedChunk
from app.schemas.rag_evaluation import RagCaseKind
from app.services.answering import GroundedAnswerOutcome
from app.services.retrieval import RetrievalOutcome

REPOSITORY_ROOT = Path(__file__).parents[1]
DATASET_PATH = (
    REPOSITORY_ROOT / "datasets" / "rag-evaluation" / "week3_acceptance.json"
)
CORPUS_PATH = REPOSITORY_ROOT / "datasets" / "knowledge-base"


def _match(document_key: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_version_id=uuid4(),
        document_key=document_key,
        title="Fictional support document",
        canonical_path=f"/support/{document_key}",
        source_url=f"https://support.example/{document_key}",
        visibility="public",
        chunk_index=0,
        heading_path=("Example",),
        content="Synthetic evidence used only by an isolated test.",
        metadata={},
        similarity=0.9,
    )


class FakeRegistry:
    def get(self, provider_name, model):
        assert provider_name == "openai"
        assert model == "gpt-test"
        return object()


class FakeAnswerService:
    async def answer(
        self,
        *,
        provider_name,
        model,
        question,
        top_k,
        request_id,
    ) -> GroundedAnswerOutcome:
        assert provider_name == "openai"
        assert model == "gpt-test"
        assert top_k == 5
        assert request_id.startswith("rag-eval-")
        answerable = question.startswith("How long is a password reset")
        evidence = _match("account-password-reset" if answerable else "service-status")
        abstained = not answerable
        return GroundedAnswerOutcome(
            conversation_id=uuid4(),
            answer=(
                f"Thirty minutes [source:{evidence.chunk_id}]."
                if answerable
                else "There is not enough evidence."
            ),
            abstained=abstained,
            sources=(evidence,) if answerable else (),
            provider="openai",
            model="gpt-test",
            generation_performed=True,
            generation_latency_ms=12,
            generation_input_tokens=20,
            generation_output_tokens=5,
            finish_reason="completed",
            provider_request_id=None,
            attempt_count=1,
            retrieval=RetrievalOutcome(
                matches=(evidence,),
                embedding_model="embedding-test",
                embedding_latency_ms=4,
                embedding_input_tokens=6,
            ),
        )


def test_committed_dataset_has_required_week3_composition() -> None:
    first = load_dataset(DATASET_PATH, corpus_directory=CORPUS_PATH)
    second = load_dataset(DATASET_PATH, corpus_directory=CORPUS_PATH)

    assert len(first.dataset.cases) == 20
    assert first.sha256 == second.sha256
    assert len(first.sha256) == 64
    assert Counter(case.kind for case in first.dataset.cases) == {
        RagCaseKind.ANSWERABLE: 12,
        RagCaseKind.AMBIGUOUS: 4,
        RagCaseKind.UNANSWERABLE: 4,
    }
    assert first.dataset.forbidden_document_keys == ("escalation-policy",)
    assert all(
        case.expected_document_keys
        for case in first.dataset.cases
        if case.kind is RagCaseKind.ANSWERABLE
    )


def test_validate_only_does_not_construct_settings(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        rag_evaluation,
        "Settings",
        lambda: (_ for _ in ()).throw(AssertionError("must not load settings")),
    )
    args = rag_evaluation.build_parser().parse_args(
        [
            "--dataset",
            str(DATASET_PATH),
            "--corpus",
            str(CORPUS_PATH),
            "--validate-only",
        ]
    )

    exit_code = asyncio.run(rag_evaluation.run_cli(args))

    assert exit_code == 0
    assert "Validated 20 fictional RAG cases" in capsys.readouterr().out


def test_live_evaluation_requires_explicit_paid_call_acknowledgement(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(
        rag_evaluation,
        "Settings",
        lambda: (_ for _ in ()).throw(AssertionError("must not load settings")),
    )
    args = rag_evaluation.build_parser().parse_args(
        [
            "--dataset",
            str(DATASET_PATH),
            "--corpus",
            str(CORPUS_PATH),
        ]
    )

    exit_code = asyncio.run(rag_evaluation.run_cli(args))

    assert exit_code == 2
    assert "no provider calls or database writes" in capsys.readouterr().err


def test_remote_database_requires_separate_permission(monkeypatch, capsys) -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="postgresql://user:private@db.example.com/database",
        openai_api_key="test-key",
    )
    monkeypatch.setattr(rag_evaluation, "Settings", lambda: settings)
    args = rag_evaluation.build_parser().parse_args(
        [
            "--dataset",
            str(DATASET_PATH),
            "--corpus",
            str(CORPUS_PATH),
            "--allow-paid-calls",
        ]
    )

    exit_code = asyncio.run(rag_evaluation.run_cli(args))

    assert exit_code == 2
    error = capsys.readouterr().err
    assert "--allow-remote-database is required" in error
    assert "private" not in error
    assert "db.example.com" not in error


def test_fake_live_run_writes_aggregate_only_report(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    output_path = tmp_path / "artifacts" / "rag.json"
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="postgresql://postgres:postgres@127.0.0.1:54322/postgres",
        openai_api_key="test-key",
        openai_model="gpt-test",
    )
    monkeypatch.setattr(rag_evaluation, "Settings", lambda: settings)
    monkeypatch.setattr(
        rag_evaluation,
        "build_provider_registry",
        lambda _settings: FakeRegistry(),
    )
    monkeypatch.setattr(
        rag_evaluation,
        "_build_service",
        lambda _settings, **_kwargs: FakeAnswerService(),
    )
    args = rag_evaluation.build_parser().parse_args(
        [
            "--dataset",
            str(DATASET_PATH),
            "--corpus",
            str(CORPUS_PATH),
            "--output",
            str(output_path),
            "--provider",
            "openai",
            "--model",
            "gpt-test",
            "--max-cases",
            "3",
            "--allow-paid-calls",
        ]
    )

    exit_code = asyncio.run(rag_evaluation.run_cli(args))

    assert exit_code == 0
    report = json.loads(output_path.read_text(encoding="utf-8"))
    metrics = report["metrics"]
    assert report["aggregate_only"] is True
    assert report["available_cases"] == 20
    assert metrics["total_cases"] == 3
    assert metrics["answerable_cases"] == 1
    assert metrics["ambiguous_cases"] == 1
    assert metrics["unanswerable_cases"] == 1
    assert metrics["answerable_retrieval_hit_rate_at_k"] == 1
    assert metrics["unanswerable_abstention_rate"] == 1
    assert metrics["citation_validity_rate"] == 1
    assert metrics["forbidden_retrieval_leakage_cases"] == 0
    serialized = output_path.read_text(encoding="utf-8")
    assert "question" not in serialized
    assert "case_id" not in serialized
    assert "account-password-reset" not in serialized
    assert "Evaluated 3 cases" in capsys.readouterr().out
