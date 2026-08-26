from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence, cast

from pydantic import ValidationError

from ai_learning.database_safety import is_local_database
from app.core.config import Settings
from app.providers.base import ProviderLookupError, ProviderName, ProviderRegistry
from app.providers.registry import build_provider_registry
from app.rag.documents import DocumentFormatError, load_corpus
from app.rag.embeddings import OpenAIEmbeddingClient
from app.rag.repository import PsycopgKnowledgeRepository
from app.schemas.rag_evaluation import (
    RagAcceptanceDataset,
    RagCaseKind,
    RagEvaluationCase,
)
from app.services.answering import GroundedAnswerService
from app.services.rag_evaluation import evaluate_rag_cases
from app.services.retrieval import SemanticRetriever
from app.services.retry import RetryPolicy

DEFAULT_DATASET = Path("datasets/rag-evaluation/week3_acceptance.json")
DEFAULT_CORPUS = Path("datasets/knowledge-base")
DEFAULT_OUTPUT = Path("artifacts/rag-evaluation.json")
EXPECTED_CASE_COUNTS = {
    RagCaseKind.ANSWERABLE: 12,
    RagCaseKind.AMBIGUOUS: 4,
    RagCaseKind.UNANSWERABLE: 4,
}


class DatasetError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class LoadedRagDataset:
    dataset: RagAcceptanceDataset
    source_name: str
    sha256: str


def load_dataset(path: Path, *, corpus_directory: Path) -> LoadedRagDataset:
    try:
        raw_dataset = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise DatasetError(f"Could not read valid JSON from {path.name}.") from error
    try:
        dataset = RagAcceptanceDataset.model_validate(raw_dataset)
    except ValidationError as error:
        raise DatasetError(f"{path.name} does not satisfy the dataset schema.") from error

    case_counts = Counter(case.kind for case in dataset.cases)
    if case_counts != EXPECTED_CASE_COUNTS:
        raise DatasetError(
            "Week 3 acceptance data must contain exactly 12 answerable, "
            "4 ambiguous, and 4 unanswerable cases."
        )

    try:
        corpus = load_corpus(corpus_directory)
    except DocumentFormatError as error:
        raise DatasetError("The knowledge corpus is invalid.") from error
    corpus_by_key = {
        document.metadata.document_key: document for document in corpus
    }
    referenced_keys = {
        key
        for case in dataset.cases
        for key in case.expected_document_keys
    } | set(dataset.forbidden_document_keys)
    missing_keys = referenced_keys - corpus_by_key.keys()
    if missing_keys:
        raise DatasetError(
            "The dataset references document keys absent from the corpus."
        )
    if any(
        corpus_by_key[key].metadata.visibility == "public"
        for key in dataset.forbidden_document_keys
    ):
        raise DatasetError(
            "Forbidden evaluation documents must not have public visibility."
        )

    canonical_json = json.dumps(
        dataset.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return LoadedRagDataset(
        dataset=dataset,
        source_name=path.name,
        sha256=hashlib.sha256(canonical_json).hexdigest(),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate or run the local Week 3 citation-Q&A acceptance set."
        )
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--provider", choices=("openai", "anthropic"))
    parser.add_argument("--model")
    parser.add_argument(
        "--max-cases",
        type=_bounded_cases,
        default=3,
        help="Run a deterministic category-balanced subset (default: 3).",
    )
    parser.add_argument("--top-k", type=_bounded_top_k, default=5)
    parser.add_argument("--concurrency", type=_bounded_concurrency, default=1)
    parser.add_argument(
        "--allow-remote-database",
        action="store_true",
        help="Explicitly permit conversation writes to a non-local database.",
    )
    execution_mode = parser.add_mutually_exclusive_group()
    execution_mode.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate dataset and corpus references without clients or calls.",
    )
    execution_mode.add_argument(
        "--allow-paid-calls",
        action="store_true",
        help=(
            "Acknowledge paid embeddings/generation calls and local "
            "conversation writes."
        ),
    )
    return parser


async def run_cli(args: argparse.Namespace) -> int:
    try:
        loaded = load_dataset(args.dataset, corpus_directory=args.corpus)
    except DatasetError as error:
        print(f"Dataset error: {error}", file=sys.stderr)
        return 2

    if args.validate_only:
        print(
            "Validated 20 fictional RAG cases (12 answerable, 4 ambiguous, "
            f"4 unanswerable). Dataset SHA-256: {loaded.sha256}"
        )
        return 0
    if not args.allow_paid_calls:
        print(
            "Validated 20 fictional RAG cases; no provider calls or database "
            "writes were made. Choose --validate-only or --allow-paid-calls.",
            file=sys.stderr,
        )
        return 2
    if _output_overlaps_inputs(args.dataset, args.corpus, args.output):
        print(
            "Output must be outside the dataset and corpus paths.",
            file=sys.stderr,
        )
        return 2

    settings = Settings()
    if settings.database_url is None:
        print("DATABASE_URL is required for a live evaluation.", file=sys.stderr)
        return 2
    if settings.openai_api_key is None:
        print(
            "OPENAI_API_KEY is required for query embeddings.",
            file=sys.stderr,
        )
        return 2
    database_url = settings.database_url.get_secret_value()
    if not is_local_database(database_url) and not args.allow_remote_database:
        print(
            "--allow-remote-database is required for remote conversation writes.",
            file=sys.stderr,
        )
        return 2

    provider_name = cast(ProviderName, args.provider or settings.llm_provider)
    model = args.model or (
        settings.openai_model
        if provider_name == "openai"
        else settings.anthropic_model
    )
    registry = build_provider_registry(settings)
    try:
        registry.get(provider_name, model)
    except ProviderLookupError as error:
        print(f"Provider configuration error: {error.message}", file=sys.stderr)
        return 2

    service = _build_service(
        settings,
        registry=registry,
        database_url=database_url,
    )
    selected_cases = _select_cases(
        loaded.dataset.cases,
        maximum=args.max_cases,
    )
    logging.getLogger("app").setLevel(settings.log_level)
    report = await evaluate_rag_cases(
        selected_cases,
        service=service,
        provider_name=provider_name,
        model=model,
        top_k=args.top_k,
        concurrency=args.concurrency,
        source_name=loaded.source_name,
        dataset_sha256=loaded.sha256,
        available_cases=len(loaded.dataset.cases),
        max_cases=args.max_cases,
        forbidden_document_keys=loaded.dataset.forbidden_document_keys,
    )
    _write_report(args.output, report.model_dump_json(indent=2) + "\n")
    metrics = report.metrics
    print(
        f"Evaluated {metrics.total_cases} cases with {provider_name}/{model}: "
        f"{metrics.completed_cases} completed, {metrics.failed_cases} failed."
    )
    print(f"Aggregate report: {args.output}")
    return 1 if metrics.failed_cases else 0


def _build_service(
    settings: Settings,
    *,
    registry: ProviderRegistry,
    database_url: str,
) -> GroundedAnswerService:
    repository = PsycopgKnowledgeRepository(database_url)
    retriever = SemanticRetriever(
        repository=repository,
        embedding_client=OpenAIEmbeddingClient(
            api_key=settings.openai_api_key.get_secret_value(),
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
            batch_size=1,
            timeout_seconds=settings.llm_timeout_seconds,
        ),
        tenant_id=settings.rag_tenant_id,
        minimum_similarity=settings.rag_retrieval_min_similarity,
        allowed_visibilities=("public",),
    )
    return GroundedAnswerService(
        registry=registry,
        retriever=retriever,
        repository=repository,
        retry_policy=RetryPolicy.from_settings(settings),
        timeout_seconds=settings.llm_timeout_seconds,
        tenant_id=settings.rag_tenant_id,
    )


def _select_cases(
    cases: Sequence[RagEvaluationCase],
    *,
    maximum: int,
) -> list[RagEvaluationCase]:
    if maximum >= len(cases):
        return list(cases)
    buckets = {
        kind: [case for case in cases if case.kind is kind]
        for kind in RagCaseKind
    }
    selected: list[RagEvaluationCase] = []
    while len(selected) < maximum:
        made_progress = False
        for kind in RagCaseKind:
            bucket = buckets[kind]
            if bucket and len(selected) < maximum:
                selected.append(bucket.pop(0))
                made_progress = True
        if not made_progress:
            break
    return selected


def _write_report(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(content, encoding="utf-8")
    temporary_path.replace(path)


def _output_overlaps_inputs(
    dataset_path: Path,
    corpus_path: Path,
    output_path: Path,
) -> bool:
    output = output_path.resolve()
    dataset = dataset_path.resolve()
    corpus = corpus_path.resolve()
    return output == dataset or output == corpus or corpus in output.parents


def _bounded_cases(value: str) -> int:
    parsed = int(value)
    if not 1 <= parsed <= 20:
        raise argparse.ArgumentTypeError("must be between 1 and 20")
    return parsed


def _bounded_top_k(value: str) -> int:
    parsed = int(value)
    if not 1 <= parsed <= 10:
        raise argparse.ArgumentTypeError("must be between 1 and 10")
    return parsed


def _bounded_concurrency(value: str) -> int:
    parsed = int(value)
    if not 1 <= parsed <= 4:
        raise argparse.ArgumentTypeError("must be between 1 and 4")
    return parsed


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    exit_code = asyncio.run(run_cli(args))
    if exit_code:
        raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
