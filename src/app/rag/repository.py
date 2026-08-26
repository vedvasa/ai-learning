from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal, Sequence
from uuid import UUID, uuid4

import psycopg

from app.rag.chunking import DocumentChunk
from app.rag.documents import SourceDocument
from app.rag.embeddings import EmbeddingCall

IngestionStatus = Literal["succeeded", "skipped"]


@dataclass(frozen=True, slots=True)
class StoredDocument:
    document_id: UUID
    active_content_hash: str | None


class PsycopgKnowledgeRepository:
    """Short-lived Postgres operations for the explicit ingestion command."""

    def __init__(self, database_url: str) -> None:
        if not database_url.strip():
            raise ValueError("database_url must not be blank")
        self._database_url = database_url

    def create_job(self, document: SourceDocument) -> UUID:
        metadata = document.metadata
        job_id = uuid4()
        with psycopg.connect(self._database_url, autocommit=True) as connection:
            existing = connection.execute(
                """
                select id
                from knowledge.documents
                where tenant_id = %s and document_key = %s
                """,
                (metadata.tenant_id, metadata.document_key),
            ).fetchone()
            connection.execute(
                """
                insert into knowledge.ingestion_jobs (
                    id, document_id, tenant_id, status, source_path,
                    source_content_hash, started_at
                )
                values (%s, %s, %s, 'running', %s, %s, now())
                """,
                (
                    job_id,
                    existing[0] if existing else None,
                    metadata.tenant_id,
                    document.source_path,
                    document.content_hash,
                ),
            )
        return job_id

    def find_document(self, document: SourceDocument) -> StoredDocument | None:
        metadata = document.metadata
        with psycopg.connect(self._database_url, autocommit=True) as connection:
            row = connection.execute(
                """
                select document.id, active_version.content_hash
                from knowledge.documents as document
                left join knowledge.document_versions as active_version
                    on active_version.document_id = document.id
                    and active_version.is_active
                where document.tenant_id = %s and document.document_key = %s
                """,
                (metadata.tenant_id, metadata.document_key),
            ).fetchone()
        if row is None:
            return None
        return StoredDocument(document_id=row[0], active_content_hash=row[1])

    def find_cached_embeddings(
        self,
        *,
        tenant_id: str,
        content_hashes: Sequence[str],
        model: str,
        dimensions: int,
    ) -> dict[str, tuple[float, ...]]:
        if not content_hashes:
            return {}
        with psycopg.connect(self._database_url, autocommit=True) as connection:
            rows = connection.execute(
                """
                select distinct on (content_hash)
                    content_hash,
                    embedding::text
                from knowledge.chunks
                where tenant_id = %s
                    and content_hash = any(%s)
                    and embedding_model = %s
                    and embedding_dimension = %s
                order by content_hash, created_at desc
                """,
                (tenant_id, list(content_hashes), model, dimensions),
            ).fetchall()
        return {row[0]: self._parse_vector(row[1]) for row in rows}

    def mark_job_skipped(self, job_id: UUID, *, document_id: UUID | None) -> None:
        with psycopg.connect(self._database_url, autocommit=True) as connection:
            connection.execute(
                """
                update knowledge.ingestion_jobs
                set document_id = %s,
                    status = 'skipped',
                    finished_at = now()
                where id = %s
                """,
                (document_id, job_id),
            )

    def mark_job_failed(self, job_id: UUID, *, error_kind: str) -> None:
        safe_kind = error_kind[:120]
        with psycopg.connect(self._database_url, autocommit=True) as connection:
            connection.execute(
                """
                update knowledge.ingestion_jobs
                set status = 'failed',
                    error_kind = %s,
                    finished_at = now()
                where id = %s
                """,
                (safe_kind, job_id),
            )

    def record_embedding_calls(
        self,
        *,
        tenant_id: str,
        model: str,
        calls: Sequence[EmbeddingCall],
    ) -> None:
        if not calls:
            return
        with psycopg.connect(self._database_url) as connection:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    insert into knowledge.model_calls (
                        request_id, tenant_id, operation, provider, model,
                        outcome, latency_ms, input_tokens
                    )
                    values (%s, %s, 'document_embedding_batch', 'openai', %s,
                            'succeeded', %s, %s)
                    """,
                    [
                        (
                            call.request_id,
                            tenant_id,
                            model,
                            call.latency_ms,
                            call.input_tokens,
                        )
                        for call in calls
                    ],
                )

    def commit_document(
        self,
        *,
        job_id: UUID,
        document: SourceDocument,
        chunks: Sequence[DocumentChunk],
        embeddings: dict[str, tuple[float, ...]],
        embedding_model: str,
        embedding_dimensions: int,
    ) -> IngestionStatus:
        metadata = document.metadata
        with psycopg.connect(self._database_url) as connection:
            row = connection.execute(
                """
                insert into knowledge.documents (
                    tenant_id, document_key, title, canonical_path,
                    source_url, visibility
                )
                values (%s, %s, %s, %s, %s, %s)
                on conflict (tenant_id, document_key) do update
                set title = excluded.title,
                    canonical_path = excluded.canonical_path,
                    source_url = excluded.source_url,
                    visibility = excluded.visibility,
                    updated_at = now()
                returning id
                """,
                (
                    metadata.tenant_id,
                    metadata.document_key,
                    metadata.title,
                    metadata.canonical_path,
                    str(metadata.source_url) if metadata.source_url else None,
                    metadata.visibility,
                ),
            ).fetchone()
            if row is None:
                raise RuntimeError("document upsert returned no identifier")
            document_id = row[0]

            active = connection.execute(
                """
                select content_hash
                from knowledge.document_versions
                where document_id = %s and is_active
                for update
                """,
                (document_id,),
            ).fetchone()
            if active and active[0] == document.content_hash:
                connection.execute(
                    """
                    update knowledge.ingestion_jobs
                    set document_id = %s,
                        status = 'skipped',
                        finished_at = now()
                    where id = %s
                    """,
                    (document_id, job_id),
                )
                return "skipped"

            version_row = connection.execute(
                """
                insert into knowledge.document_versions (
                    document_id, tenant_id, version, content,
                    content_hash, is_active
                )
                values (%s, %s, %s, %s, %s, false)
                returning id
                """,
                (
                    document_id,
                    metadata.tenant_id,
                    metadata.version,
                    document.content,
                    document.content_hash,
                ),
            ).fetchone()
            if version_row is None:
                raise RuntimeError("document version insert returned no identifier")
            version_id = version_row[0]

            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    insert into knowledge.chunks (
                        document_version_id, tenant_id, chunk_index, heading_path,
                        content, token_count, content_hash, metadata,
                        embedding, embedding_model, embedding_dimension
                    )
                    values (
                        %s, %s, %s, %s, %s, %s, %s, %s::jsonb,
                        %s::extensions.vector, %s, %s
                    )
                    """,
                    [
                        (
                            version_id,
                            metadata.tenant_id,
                            chunk.chunk_index,
                            list(chunk.heading_path),
                            chunk.content,
                            chunk.token_count,
                            chunk.content_hash,
                            json.dumps(chunk.metadata, sort_keys=True),
                            self._serialize_vector(embeddings[chunk.content_hash]),
                            embedding_model,
                            embedding_dimensions,
                        )
                        for chunk in chunks
                    ],
                )
            connection.execute(
                """
                update knowledge.document_versions
                set is_active = false
                where document_id = %s and is_active
                """,
                (document_id,),
            )
            connection.execute(
                """
                update knowledge.document_versions
                set is_active = true
                where id = %s
                """,
                (version_id,),
            )
            connection.execute(
                """
                update knowledge.ingestion_jobs
                set document_id = %s,
                    status = 'succeeded',
                    chunks_written = %s,
                    finished_at = now()
                where id = %s
                """,
                (document_id, len(chunks), job_id),
            )
        return "succeeded"

    @staticmethod
    def _serialize_vector(vector: Sequence[float]) -> str:
        return "[" + ",".join(format(value, ".17g") for value in vector) + "]"

    @staticmethod
    def _parse_vector(value: str) -> tuple[float, ...]:
        serialized = value.removeprefix("[").removesuffix("]")
        return tuple(float(item) for item in serialized.split(","))
