from __future__ import annotations

import os
from uuid import uuid4

import psycopg
import pytest

from app.rag.repository import (
    AnswerGenerationCall,
    AnswerPersistenceError,
    PsycopgKnowledgeRepository,
    RetrievedChunk,
)

DATABASE_URL = os.getenv("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="TEST_DATABASE_URL is required for the repository integration test",
)


def source() -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_version_id=uuid4(),
        document_key="password-reset",
        title="Reset a password",
        canonical_path="/support/password-reset",
        source_url="https://support.example/password-reset",
        visibility="public",
        chunk_index=0,
        heading_path=("Reset links",),
        content="Reset links expire after 30 minutes.",
        metadata={},
        similarity=0.91,
    )


def test_repository_persists_exchange_citations_and_telemetry_atomically() -> None:
    assert DATABASE_URL is not None
    repository = PsycopgKnowledgeRepository(DATABASE_URL)
    tenant_id = f"answer-repository-{uuid4()}"
    citation = source()
    generation_call = AnswerGenerationCall(
        request_id=uuid4(),
        provider="openai",
        model="gpt-test",
        latency_ms=20.5,
        input_tokens=125,
        output_tokens=31,
    )

    try:
        stored = repository.save_answer_exchange(
            tenant_id=tenant_id,
            question="How long does a reset link last?",
            answer=f"Thirty minutes [source:{citation.chunk_id}].",
            abstained=False,
            citations=(citation,),
            generation_call=generation_call,
        )

        with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
            conversation = connection.execute(
                "select tenant_id from knowledge.conversations where id = %s",
                (stored.conversation_id,),
            ).fetchone()
            messages = connection.execute(
                """
                select role, sequence_number, content, citations, abstained
                from knowledge.messages
                where conversation_id = %s
                order by sequence_number
                """,
                (stored.conversation_id,),
            ).fetchall()
            model_call = connection.execute(
                """
                select operation, provider, model, outcome,
                       input_tokens, output_tokens, conversation_id, message_id
                from knowledge.model_calls
                where request_id = %s
                """,
                (generation_call.request_id,),
            ).fetchone()

        assert conversation == (tenant_id,)
        assert messages[0] == (
            "user",
            0,
            "How long does a reset link last?",
            [],
            None,
        )
        assert messages[1][0:3] == (
            "assistant",
            1,
            f"Thirty minutes [source:{citation.chunk_id}].",
        )
        assert messages[1][3][0]["chunk_id"] == str(citation.chunk_id)
        assert messages[1][3][0]["similarity"] == 0.91
        assert messages[1][4] is False
        assert model_call == (
            "grounded_answer",
            "openai",
            "gpt-test",
            "succeeded",
            125,
            31,
            stored.conversation_id,
            stored.assistant_message_id,
        )
    finally:
        _cleanup(tenant_id)


def test_repository_rolls_back_messages_when_model_call_is_invalid() -> None:
    assert DATABASE_URL is not None
    repository = PsycopgKnowledgeRepository(DATABASE_URL)
    tenant_id = f"answer-rollback-{uuid4()}"
    invalid_call = AnswerGenerationCall(
        request_id=uuid4(),
        provider="invalid-provider",  # type: ignore[arg-type]
        model="model",
        latency_ms=1,
        input_tokens=1,
        output_tokens=1,
    )

    try:
        with pytest.raises(AnswerPersistenceError):
            repository.save_answer_exchange(
                tenant_id=tenant_id,
                question="Question",
                answer="Answer",
                abstained=True,
                citations=(),
                generation_call=invalid_call,
            )

        with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
            counts = connection.execute(
                """
                select
                    (select count(*) from knowledge.conversations where tenant_id = %s),
                    (select count(*) from knowledge.messages where tenant_id = %s),
                    (select count(*) from knowledge.model_calls where tenant_id = %s)
                """,
                (tenant_id, tenant_id, tenant_id),
            ).fetchone()
        assert counts == (0, 0, 0)
    finally:
        _cleanup(tenant_id)


def _cleanup(tenant_id: str) -> None:
    assert DATABASE_URL is not None
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "delete from knowledge.model_calls where tenant_id = %s",
            (tenant_id,),
        )
        connection.execute(
            "delete from knowledge.conversations where tenant_id = %s",
            (tenant_id,),
        )
