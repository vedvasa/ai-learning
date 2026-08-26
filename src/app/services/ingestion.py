from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence
from uuid import UUID

from app.rag.chunking import DocumentChunk, MarkdownChunker
from app.rag.documents import SourceDocument
from app.rag.embeddings import EmbeddingCall, EmbeddingClient
from app.rag.repository import IngestionStatus, StoredDocument


class IngestionRepository(Protocol):
    def create_job(self, document: SourceDocument) -> UUID: ...

    def find_document(self, document: SourceDocument) -> StoredDocument | None: ...

    def find_cached_embeddings(
        self,
        *,
        tenant_id: str,
        content_hashes: Sequence[str],
        model: str,
        dimensions: int,
    ) -> dict[str, tuple[float, ...]]: ...

    def mark_job_skipped(self, job_id: UUID, *, document_id: UUID | None) -> None: ...

    def mark_job_failed(self, job_id: UUID, *, error_kind: str) -> None: ...

    def record_embedding_calls(
        self,
        *,
        tenant_id: str,
        model: str,
        calls: Sequence[EmbeddingCall],
        operation: str = "document_embedding_batch",
    ) -> None: ...

    def commit_document(
        self,
        *,
        job_id: UUID,
        document: SourceDocument,
        chunks: Sequence[DocumentChunk],
        embeddings: dict[str, tuple[float, ...]],
        embedding_model: str,
        embedding_dimensions: int,
    ) -> IngestionStatus: ...


class DocumentIngestionError(RuntimeError):
    def __init__(self, document_key: str, kind: str) -> None:
        super().__init__(f"ingestion failed for {document_key}: {kind}")
        self.document_key = document_key
        self.kind = kind


@dataclass(frozen=True, slots=True)
class IngestionOutcome:
    document_key: str
    status: IngestionStatus
    chunks_written: int
    embeddings_created: int
    embeddings_reused: int


class DocumentIngestor:
    def __init__(
        self,
        *,
        repository: IngestionRepository,
        embedding_client: EmbeddingClient,
        chunker: MarkdownChunker,
    ) -> None:
        self._repository = repository
        self._embedding_client = embedding_client
        self._chunker = chunker

    def ingest(self, document: SourceDocument) -> IngestionOutcome:
        job_id: UUID | None = None
        try:
            job_id = self._repository.create_job(document)
            stored = self._repository.find_document(document)
            if stored and stored.active_content_hash == document.content_hash:
                self._repository.mark_job_skipped(
                    job_id, document_id=stored.document_id
                )
                return IngestionOutcome(
                    document_key=document.metadata.document_key,
                    status="skipped",
                    chunks_written=0,
                    embeddings_created=0,
                    embeddings_reused=0,
                )

            chunks = self._chunker.chunk(document)
            unique_chunks = {chunk.content_hash: chunk for chunk in chunks}
            cached = self._repository.find_cached_embeddings(
                tenant_id=document.metadata.tenant_id,
                content_hashes=list(unique_chunks),
                model=self._embedding_client.model,
                dimensions=self._embedding_client.dimensions,
            )
            missing_hashes = [
                content_hash
                for content_hash in unique_chunks
                if content_hash not in cached
            ]
            result = self._embedding_client.embed_many(
                [unique_chunks[content_hash].content for content_hash in missing_hashes]
            )
            generated = dict(zip(missing_hashes, result.vectors, strict=True))
            embeddings = cached | generated
            self._repository.record_embedding_calls(
                tenant_id=document.metadata.tenant_id,
                model=self._embedding_client.model,
                calls=result.calls,
            )
            status = self._repository.commit_document(
                job_id=job_id,
                document=document,
                chunks=chunks,
                embeddings=embeddings,
                embedding_model=self._embedding_client.model,
                embedding_dimensions=self._embedding_client.dimensions,
            )
            return IngestionOutcome(
                document_key=document.metadata.document_key,
                status=status,
                chunks_written=len(chunks) if status == "succeeded" else 0,
                embeddings_created=len(missing_hashes) if status == "succeeded" else 0,
                embeddings_reused=(
                    len(chunks) - len(missing_hashes)
                    if status == "succeeded"
                    else 0
                ),
            )
        except Exception as error:
            kind = getattr(error, "kind", type(error).__name__)
            if job_id is not None:
                try:
                    self._repository.mark_job_failed(job_id, error_kind=str(kind))
                except Exception:
                    pass
            raise DocumentIngestionError(
                document.metadata.document_key, str(kind)
            ) from error
