from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal, Sequence
from uuid import UUID, uuid4

import psycopg

from app.providers.base import ProviderName
from app.rag.chunking import DocumentChunk
from app.rag.documents import SourceDocument
from app.rag.embeddings import EmbeddingCall

IngestionStatus = Literal["succeeded", "skipped"]


@dataclass(frozen=True, slots=True)
class StoredDocument:
    document_id: UUID
    active_content_hash: str | None


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    chunk_id: UUID
    document_id: UUID
    document_version_id: UUID
    document_key: str
    title: str
    canonical_path: str
    source_url: str | None
    visibility: str
    chunk_index: int
    heading_path: tuple[str, ...]
    content: str
    metadata: dict[str, Any]
    similarity: float


@dataclass(frozen=True, slots=True)
class AnswerGenerationCall:
    request_id: UUID
    provider: ProviderName
    model: str
    latency_ms: float
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True, slots=True)
class StoredAnswerExchange:
    conversation_id: UUID
    user_message_id: UUID
    assistant_message_id: UUID


class KnowledgeSearchError(RuntimeError):
    """Safe repository error that does not expose connection details."""


class AnswerPersistenceError(RuntimeError):
    """Safe repository error for an atomic question/answer write."""


class PsycopgKnowledgeRepository:
    """Short-lived Postgres operations for ingestion and exact retrieval."""

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
        operation: str = "document_embedding_batch",
    ) -> None:
        if not calls:
            return
        if not operation.strip():
            raise ValueError("operation must not be blank")
        with psycopg.connect(self._database_url) as connection:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    insert into knowledge.model_calls (
                        request_id, tenant_id, operation, provider, model,
                        outcome, latency_ms, input_tokens
                    )
                    values (%s, %s, %s, 'openai', %s,
                            'succeeded', %s, %s)
                    """,
                    [
                        (
                            call.request_id,
                            tenant_id,
                            operation,
                            model,
                            call.latency_ms,
                            call.input_tokens,
                        )
                        for call in calls
                    ],
                )

    def search_chunks(
        self,
        *,
        tenant_id: str,
        query_embedding: Sequence[float],
        embedding_model: str,
        embedding_dimensions: int,
        top_k: int,
        minimum_similarity: float,
        allowed_visibilities: Sequence[str],
    ) -> tuple[RetrievedChunk, ...]:
        if len(query_embedding) != embedding_dimensions:
            raise ValueError("query embedding dimension does not match contract")
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        if not allowed_visibilities:
            raise ValueError("allowed_visibilities must not be empty")

        serialized_embedding = self._serialize_vector(query_embedding)
        try:
            with psycopg.connect(self._database_url, autocommit=True) as connection:
                rows = connection.execute(
                    """
                    with query_vector as (
                        select %s::extensions.vector as embedding
                    ),
                    candidates as (
                        select
                            chunk.id as chunk_id,
                            document.id as document_id,
                            version.id as document_version_id,
                            document.document_key,
                            document.title,
                            document.canonical_path,
                            document.source_url,
                            document.visibility,
                            chunk.chunk_index,
                            chunk.heading_path,
                            chunk.content,
                            chunk.metadata,
                            (
                                1 - (
                                    chunk.embedding
                                    operator(extensions.<=>)
                                    query_vector.embedding
                                )
                            )::double precision as similarity
                        from knowledge.chunks as chunk
                        join knowledge.document_versions as version
                            on version.id = chunk.document_version_id
                            and version.tenant_id = chunk.tenant_id
                        join knowledge.documents as document
                            on document.id = version.document_id
                            and document.tenant_id = version.tenant_id
                        cross join query_vector
                        where chunk.tenant_id = %s
                            and version.is_active
                            and document.visibility = any(%s)
                            and chunk.embedding is not null
                            and chunk.embedding_model = %s
                            and chunk.embedding_dimension = %s
                    )
                    select *
                    from candidates
                    where similarity >= %s
                    order by similarity desc, chunk_id
                    limit %s
                    """,
                    (
                        serialized_embedding,
                        tenant_id,
                        list(allowed_visibilities),
                        embedding_model,
                        embedding_dimensions,
                        minimum_similarity,
                        top_k,
                    ),
                ).fetchall()
        except psycopg.Error as error:
            raise KnowledgeSearchError("knowledge search failed") from error

        return tuple(
            RetrievedChunk(
                chunk_id=row[0],
                document_id=row[1],
                document_version_id=row[2],
                document_key=row[3],
                title=row[4],
                canonical_path=row[5],
                source_url=row[6],
                visibility=row[7],
                chunk_index=row[8],
                heading_path=tuple(row[9]),
                content=row[10],
                metadata=row[11],
                similarity=round(row[12], 6),
            )
            for row in rows
        )

    def save_answer_exchange(
        self,
        *,
        tenant_id: str,
        question: str,
        answer: str,
        abstained: bool,
        citations: Sequence[RetrievedChunk],
        generation_call: AnswerGenerationCall | None,
    ) -> StoredAnswerExchange:
        conversation_id = uuid4()
        user_message_id = uuid4()
        assistant_message_id = uuid4()
        citation_payload = [
            {
                "chunk_id": str(citation.chunk_id),
                "document_id": str(citation.document_id),
                "document_version_id": str(citation.document_version_id),
                "document_key": citation.document_key,
                "canonical_path": citation.canonical_path,
                "source_url": citation.source_url,
                "similarity": citation.similarity,
            }
            for citation in citations
        ]
        try:
            with psycopg.connect(self._database_url) as connection:
                connection.execute(
                    """
                    insert into knowledge.conversations (id, tenant_id)
                    values (%s, %s)
                    """,
                    (conversation_id, tenant_id),
                )
                connection.execute(
                    """
                    insert into knowledge.messages (
                        id, conversation_id, tenant_id, sequence_number,
                        role, content
                    )
                    values (%s, %s, %s, 0, 'user', %s)
                    """,
                    (user_message_id, conversation_id, tenant_id, question),
                )
                connection.execute(
                    """
                    insert into knowledge.messages (
                        id, conversation_id, tenant_id, sequence_number,
                        role, content, citations, abstained
                    )
                    values (%s, %s, %s, 1, 'assistant', %s, %s::jsonb, %s)
                    """,
                    (
                        assistant_message_id,
                        conversation_id,
                        tenant_id,
                        answer,
                        json.dumps(citation_payload, sort_keys=True),
                        abstained,
                    ),
                )
                if generation_call is not None:
                    connection.execute(
                        """
                        insert into knowledge.model_calls (
                            request_id, tenant_id, conversation_id, message_id,
                            operation, provider, model, outcome, latency_ms,
                            input_tokens, output_tokens
                        )
                        values (
                            %s, %s, %s, %s, 'grounded_answer', %s, %s,
                            'succeeded', %s, %s, %s
                        )
                        """,
                        (
                            generation_call.request_id,
                            tenant_id,
                            conversation_id,
                            assistant_message_id,
                            generation_call.provider,
                            generation_call.model,
                            generation_call.latency_ms,
                            generation_call.input_tokens,
                            generation_call.output_tokens,
                        ),
                    )
        except psycopg.Error as error:
            raise AnswerPersistenceError("answer exchange write failed") from error

        return StoredAnswerExchange(
            conversation_id=conversation_id,
            user_message_id=user_message_id,
            assistant_message_id=assistant_message_id,
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
