from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import psycopg
import pytest

from app.rag.chunking import DocumentChunk
from app.rag.documents import DocumentMetadata, SourceDocument, content_hash
from app.rag.embeddings import EmbeddingCall
from app.rag.repository import PsycopgKnowledgeRepository

DATABASE_URL = os.getenv("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="TEST_DATABASE_URL is required for the repository integration test",
)


def test_repository_commits_atomically_and_skips_same_active_content() -> None:
    assert DATABASE_URL is not None
    repository = PsycopgKnowledgeRepository(DATABASE_URL)
    tenant_id = f"repository-test-{uuid4()}"
    body = "# Integration test\n\nRepository content.\n"
    document = SourceDocument(
        metadata=DocumentMetadata(
            document_key="repository-contract",
            title="Repository contract",
            canonical_path=f"/tests/{tenant_id}/repository-contract",
            source_url=None,
            version=1,
            updated_at=datetime(2026, 8, 25, tzinfo=UTC),
            tenant_id=tenant_id,
            visibility="internal",
        ),
        content=body,
        content_hash=content_hash(body),
        source_path="repository-contract.md",
    )
    chunk = DocumentChunk(
        chunk_index=0,
        heading_path=("Integration test",),
        content=body.strip(),
        token_count=8,
        content_hash=content_hash(body.strip()),
        metadata={"source_path": "repository-contract.md"},
    )
    vector = tuple(0.0 for _ in range(1536))

    try:
        first_job = repository.create_job(document)
        first_status = repository.commit_document(
            job_id=first_job,
            document=document,
            chunks=[chunk],
            embeddings={chunk.content_hash: vector},
            embedding_model="text-embedding-3-small",
            embedding_dimensions=1536,
        )
        embedding_call = EmbeddingCall(
            request_id=uuid4(), latency_ms=12.5, input_tokens=8
        )
        repository.record_embedding_calls(
            tenant_id=tenant_id,
            model="text-embedding-3-small",
            calls=[embedding_call],
        )
        second_job = repository.create_job(document)
        second_status = repository.commit_document(
            job_id=second_job,
            document=document,
            chunks=[chunk],
            embeddings={chunk.content_hash: vector},
            embedding_model="text-embedding-3-small",
            embedding_dimensions=1536,
        )
        cached = repository.find_cached_embeddings(
            tenant_id=tenant_id,
            content_hashes=[chunk.content_hash],
            model="text-embedding-3-small",
            dimensions=1536,
        )

        with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
            counts = connection.execute(
                """
                select
                    (select count(*) from knowledge.documents where tenant_id = %s),
                    (select count(*) from knowledge.document_versions where tenant_id = %s),
                    (select count(*) from knowledge.chunks where tenant_id = %s),
                    (select count(*) from knowledge.model_calls where tenant_id = %s)
                """,
                (tenant_id, tenant_id, tenant_id, tenant_id),
            ).fetchone()
            statuses = dict(
                connection.execute(
                    """
                    select id, status
                    from knowledge.ingestion_jobs
                    where id = any(%s)
                    """,
                    ([first_job, second_job],),
                ).fetchall()
            )

        assert first_status == "succeeded"
        assert second_status == "skipped"
        assert counts == (1, 1, 1, 1)
        assert len(cached[chunk.content_hash]) == 1536
        assert statuses[first_job] == "succeeded"
        assert statuses[second_job] == "skipped"
    finally:
        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute(
                "delete from knowledge.model_calls where tenant_id = %s",
                (tenant_id,),
            )
            connection.execute(
                "delete from knowledge.ingestion_jobs where tenant_id = %s",
                (tenant_id,),
            )
            connection.execute(
                "delete from knowledge.documents where tenant_id = %s",
                (tenant_id,),
            )


def test_repository_keeps_previous_version_active_after_conflict() -> None:
    assert DATABASE_URL is not None
    repository = PsycopgKnowledgeRepository(DATABASE_URL)
    tenant_id = f"repository-rollback-test-{uuid4()}"
    original = _document(tenant_id, "# Policy\n\nOriginal content.\n")
    original_chunk = _chunk(original.content)
    changed = _document(tenant_id, "# Policy\n\nChanged without a new version.\n")
    changed_chunk = _chunk(changed.content)
    vector = tuple(0.0 for _ in range(1536))

    try:
        first_job = repository.create_job(original)
        repository.commit_document(
            job_id=first_job,
            document=original,
            chunks=[original_chunk],
            embeddings={original_chunk.content_hash: vector},
            embedding_model="text-embedding-3-small",
            embedding_dimensions=1536,
        )
        failed_job = repository.create_job(changed)
        with pytest.raises(psycopg.errors.UniqueViolation):
            repository.commit_document(
                job_id=failed_job,
                document=changed,
                chunks=[changed_chunk],
                embeddings={changed_chunk.content_hash: vector},
                embedding_model="text-embedding-3-small",
                embedding_dimensions=1536,
            )
        repository.mark_job_failed(failed_job, error_kind="UniqueViolation")

        with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
            active_hash = connection.execute(
                """
                select version.content_hash
                from knowledge.document_versions as version
                where version.tenant_id = %s and version.is_active
                """,
                (tenant_id,),
            ).fetchone()
            version_count = connection.execute(
                "select count(*) from knowledge.document_versions where tenant_id = %s",
                (tenant_id,),
            ).fetchone()
            failed_status = connection.execute(
                "select status from knowledge.ingestion_jobs where id = %s",
                (failed_job,),
            ).fetchone()

        assert active_hash == (original.content_hash,)
        assert version_count == (1,)
        assert failed_status == ("failed",)
    finally:
        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute(
                "delete from knowledge.ingestion_jobs where tenant_id = %s",
                (tenant_id,),
            )
            connection.execute(
                "delete from knowledge.documents where tenant_id = %s",
                (tenant_id,),
            )


def _document(tenant_id: str, body: str) -> SourceDocument:
    return SourceDocument(
        metadata=DocumentMetadata(
            document_key="rollback-contract",
            title="Rollback contract",
            canonical_path=f"/tests/{tenant_id}/rollback-contract",
            source_url=None,
            version=1,
            updated_at=datetime(2026, 8, 25, tzinfo=UTC),
            tenant_id=tenant_id,
            visibility="internal",
        ),
        content=body,
        content_hash=content_hash(body),
        source_path="rollback-contract.md",
    )


def _chunk(body: str) -> DocumentChunk:
    normalized = body.strip()
    return DocumentChunk(
        chunk_index=0,
        heading_path=("Policy",),
        content=normalized,
        token_count=8,
        content_hash=content_hash(normalized),
        metadata={"source_path": "rollback-contract.md"},
    )
