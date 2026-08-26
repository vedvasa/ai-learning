from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.rag.chunking import DocumentChunk
from app.rag.documents import DocumentMetadata, SourceDocument, content_hash
from app.rag.embeddings import EmbeddingCall, EmbeddingResult
from app.services.ingestion import DocumentIngestionError, DocumentIngestor


def make_document(content: str) -> SourceDocument:
    return SourceDocument(
        metadata=DocumentMetadata(
            document_key="sync-help",
            title="Sync help",
            canonical_path="/support/sync",
            source_url="https://support.knowledgedesk.example/sync",
            version=1,
            updated_at=datetime(2026, 8, 25, tzinfo=UTC),
            tenant_id="tenant-a",
            visibility="public",
        ),
        content=content,
        content_hash=content_hash(content),
        source_path="sync.md",
    )


class FixedChunker:
    def chunk(self, _document):
        return [
            DocumentChunk(0, ("One",), "one", 1, "a" * 64, {}),
            DocumentChunk(1, ("Two",), "two", 1, "b" * 64, {}),
        ]


class FakeEmbeddingClient:
    model = "text-embedding-3-small"
    dimensions = 2

    def __init__(self) -> None:
        self.inputs = []

    def embed_many(self, texts):
        self.inputs.append(list(texts))
        return EmbeddingResult(
            vectors=tuple((0.1, 0.2) for _ in texts),
            calls=(EmbeddingCall(uuid4(), 1.2, len(texts)),) if texts else (),
        )


@dataclass
class FakeRepository:
    stored: object | None = None
    fail_commit: bool = False

    def __post_init__(self):
        self.job_id = uuid4()
        self.failed = None
        self.skipped = None
        self.committed = None
        self.calls = []

    def create_job(self, _document):
        return self.job_id

    def find_document(self, _document):
        return self.stored

    def find_cached_embeddings(self, **_kwargs):
        return {"a" * 64: (0.9, 0.8)}

    def mark_job_skipped(self, job_id, *, document_id):
        self.skipped = (job_id, document_id)

    def mark_job_failed(self, job_id, *, error_kind):
        self.failed = (job_id, error_kind)

    def record_embedding_calls(self, **kwargs):
        self.calls.append(kwargs)

    def commit_document(self, **kwargs):
        if self.fail_commit:
            raise RuntimeError("database detail must remain internal")
        self.committed = kwargs
        return "succeeded"


def test_ingestion_reuses_cached_embeddings_and_commits_all_chunks() -> None:
    repository = FakeRepository()
    embedding_client = FakeEmbeddingClient()
    ingestor = DocumentIngestor(
        repository=repository,
        embedding_client=embedding_client,
        chunker=FixedChunker(),
    )

    outcome = ingestor.ingest(make_document("# Help\n\nBody.\n"))

    assert outcome.status == "succeeded"
    assert outcome.chunks_written == 2
    assert outcome.embeddings_created == 1
    assert outcome.embeddings_reused == 1
    assert embedding_client.inputs == [["two"]]
    assert set(repository.committed["embeddings"]) == {"a" * 64, "b" * 64}
    assert repository.failed is None


def test_ingestion_skips_unchanged_document_without_embedding_call() -> None:
    document = make_document("# Help\n\nBody.\n")
    document_id = uuid4()
    repository = FakeRepository(
        stored=SimpleNamespace(
            document_id=document_id,
            active_content_hash=document.content_hash,
        )
    )
    embedding_client = FakeEmbeddingClient()
    ingestor = DocumentIngestor(
        repository=repository,
        embedding_client=embedding_client,
        chunker=FixedChunker(),
    )

    outcome = ingestor.ingest(document)

    assert outcome.status == "skipped"
    assert embedding_client.inputs == []
    assert repository.skipped == (repository.job_id, document_id)


def test_ingestion_records_safe_failure_kind() -> None:
    repository = FakeRepository(fail_commit=True)
    ingestor = DocumentIngestor(
        repository=repository,
        embedding_client=FakeEmbeddingClient(),
        chunker=FixedChunker(),
    )

    with pytest.raises(DocumentIngestionError) as caught:
        ingestor.ingest(make_document("# Help\n\nBody.\n"))

    assert caught.value.kind == "RuntimeError"
    assert "database detail" not in str(caught.value)
    assert repository.failed == (repository.job_id, "RuntimeError")
