from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

from ai_learning.database_safety import is_local_database as _is_local_database
from app.core.config import Settings
from app.rag.chunking import MarkdownChunker
from app.rag.documents import DocumentFormatError, load_corpus
from app.rag.embeddings import OpenAIEmbeddingClient
from app.rag.repository import PsycopgKnowledgeRepository
from app.services.ingestion import DocumentIngestionError, DocumentIngestor

DEFAULT_CORPUS = Path("datasets/knowledge-base")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ingest the fictional KnowledgeDesk corpus into Postgres."
    )
    parser.add_argument(
        "--directory",
        type=Path,
        default=DEFAULT_CORPUS,
        help=f"Markdown corpus directory (default: {DEFAULT_CORPUS})",
    )
    parser.add_argument(
        "--max-documents",
        type=_positive_int,
        help="Process only the first N sorted documents.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and chunk documents without database or provider calls.",
    )
    parser.add_argument(
        "--confirm-spend",
        action="store_true",
        help="Acknowledge that missing embeddings can create paid API usage.",
    )
    parser.add_argument(
        "--allow-remote-database",
        action="store_true",
        help="Explicitly permit writes when DATABASE_URL is not local.",
    )
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings()
    try:
        documents = load_corpus(args.directory, limit=args.max_documents)
    except DocumentFormatError as error:
        print(json.dumps({"status": "failed", "error": str(error)}))
        return 2

    chunker = MarkdownChunker(
        max_tokens=settings.rag_chunk_max_tokens,
        model=settings.embedding_model,
    )
    if args.dry_run:
        summaries = [
            {
                "document_key": document.metadata.document_key,
                "content_hash": document.content_hash,
                "chunks": len(chunker.chunk(document)),
            }
            for document in documents
        ]
        print(
            json.dumps(
                {
                    "status": "dry_run",
                    "documents": len(summaries),
                    "chunks": sum(item["chunks"] for item in summaries),
                    "results": summaries,
                },
                indent=2,
            )
        )
        return 0

    if not args.confirm_spend:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "error": "--confirm-spend is required for live ingestion",
                }
            )
        )
        return 2
    if settings.database_url is None:
        print(json.dumps({"status": "blocked", "error": "DATABASE_URL is required"}))
        return 2
    if settings.openai_api_key is None:
        print(json.dumps({"status": "blocked", "error": "OPENAI_API_KEY is required"}))
        return 2

    database_url = settings.database_url.get_secret_value()
    if not _is_local_database(database_url) and not args.allow_remote_database:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "error": "--allow-remote-database is required for remote writes",
                }
            )
        )
        return 2

    ingestor = DocumentIngestor(
        repository=PsycopgKnowledgeRepository(database_url),
        embedding_client=OpenAIEmbeddingClient(
            api_key=settings.openai_api_key.get_secret_value(),
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
            batch_size=settings.embedding_batch_size,
            timeout_seconds=settings.llm_timeout_seconds,
        ),
        chunker=chunker,
    )
    failures = 0
    for document in documents:
        try:
            outcome = ingestor.ingest(document)
            print(json.dumps(asdict(outcome), sort_keys=True))
        except DocumentIngestionError as error:
            failures += 1
            print(
                json.dumps(
                    {
                        "document_key": error.document_key,
                        "status": "failed",
                        "error_kind": error.kind,
                    },
                    sort_keys=True,
                )
            )
    return 1 if failures else 0


def main() -> None:
    raise SystemExit(run())


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


if __name__ == "__main__":
    main()
