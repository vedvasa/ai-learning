from __future__ import annotations

import hashlib
import json
import os
from uuid import uuid4

import psycopg
import pytest

from app.rag.repository import PsycopgKnowledgeRepository

DATABASE_URL = os.getenv("TEST_DATABASE_URL")
DIMENSIONS = 1536

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="TEST_DATABASE_URL is required for the repository integration test",
)


def test_exact_search_orders_matches_and_enforces_metadata_boundaries() -> None:
    assert DATABASE_URL is not None
    repository = PsycopgKnowledgeRepository(DATABASE_URL)
    tenant_id = f"retrieval-test-{uuid4()}"
    other_tenant_id = f"retrieval-other-{uuid4()}"
    query = _vector(1.0, 0.0)

    try:
        with psycopg.connect(DATABASE_URL) as connection:
            _insert_chunk(
                connection,
                tenant_id=tenant_id,
                document_key="exact-public",
                visibility="public",
                is_active=True,
                vector=query,
            )
            _insert_chunk(
                connection,
                tenant_id=tenant_id,
                document_key="near-public",
                visibility="public",
                is_active=True,
                vector=_vector(1.0, 1.0),
            )
            _insert_chunk(
                connection,
                tenant_id=tenant_id,
                document_key="orthogonal-public",
                visibility="public",
                is_active=True,
                vector=_vector(0.0, 1.0),
            )
            _insert_chunk(
                connection,
                tenant_id=tenant_id,
                document_key="exact-internal",
                visibility="internal",
                is_active=True,
                vector=query,
            )
            _insert_chunk(
                connection,
                tenant_id=tenant_id,
                document_key="inactive-public",
                visibility="public",
                is_active=False,
                vector=query,
            )
            _insert_chunk(
                connection,
                tenant_id=other_tenant_id,
                document_key="other-tenant-public",
                visibility="public",
                is_active=True,
                vector=query,
            )

        matches = repository.search_chunks(
            tenant_id=tenant_id,
            query_embedding=query,
            embedding_model="text-embedding-3-small",
            embedding_dimensions=DIMENSIONS,
            top_k=5,
            minimum_similarity=0.5,
            allowed_visibilities=("public",),
        )

        assert [match.document_key for match in matches] == [
            "exact-public",
            "near-public",
        ]
        assert matches[0].similarity == 1.0
        assert matches[1].similarity == pytest.approx(0.707107)
        assert all(match.visibility == "public" for match in matches)
        assert all(match.content.startswith("Evidence for") for match in matches)
    finally:
        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute(
                "delete from knowledge.documents where tenant_id = any(%s)",
                ([tenant_id, other_tenant_id],),
            )


def test_search_rejects_query_vector_outside_embedding_contract() -> None:
    assert DATABASE_URL is not None
    repository = PsycopgKnowledgeRepository(DATABASE_URL)

    with pytest.raises(ValueError, match="dimension"):
        repository.search_chunks(
            tenant_id="tenant",
            query_embedding=(1.0, 0.0),
            embedding_model="text-embedding-3-small",
            embedding_dimensions=DIMENSIONS,
            top_k=5,
            minimum_similarity=0,
            allowed_visibilities=("public",),
        )


def _insert_chunk(
    connection,
    *,
    tenant_id: str,
    document_key: str,
    visibility: str,
    is_active: bool,
    vector: tuple[float, ...],
) -> None:
    document_id = uuid4()
    version_id = uuid4()
    content = f"Evidence for {document_key}."
    connection.execute(
        """
        insert into knowledge.documents (
            id, tenant_id, document_key, title, canonical_path, visibility
        )
        values (%s, %s, %s, %s, %s, %s)
        """,
        (
            document_id,
            tenant_id,
            document_key,
            document_key.replace("-", " ").title(),
            f"/tests/{document_key}",
            visibility,
        ),
    )
    connection.execute(
        """
        insert into knowledge.document_versions (
            id, document_id, tenant_id, version, content,
            content_hash, is_active
        )
        values (%s, %s, %s, 1, %s, %s, %s)
        """,
        (
            version_id,
            document_id,
            tenant_id,
            content,
            _hash(content),
            is_active,
        ),
    )
    connection.execute(
        """
        insert into knowledge.chunks (
            document_version_id, tenant_id, chunk_index, heading_path,
            content, token_count, content_hash, metadata,
            embedding, embedding_model, embedding_dimension
        )
        values (
            %s, %s, 0, %s, %s, 4, %s, %s::jsonb,
            %s::extensions.vector, 'text-embedding-3-small', 1536
        )
        """,
        (
            version_id,
            tenant_id,
            ["Evidence"],
            content,
            _hash(f"chunk-{content}"),
            json.dumps({"fixture": document_key}),
            _serialize_vector(vector),
        ),
    )


def _vector(first: float, second: float) -> tuple[float, ...]:
    return (first, second, *(0.0 for _ in range(DIMENSIONS - 2)))


def _serialize_vector(vector: tuple[float, ...]) -> str:
    return "[" + ",".join(str(value) for value in vector) + "]"


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
