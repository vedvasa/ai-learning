from __future__ import annotations

import asyncio
from uuid import uuid4

from app.rag.repository import RetrievedChunk
from app.schemas.rag_evaluation import RagEvaluationCase
from app.services.answering import GroundedAnswerOutcome
from app.services.rag_evaluation import evaluate_rag_cases
from app.services.retrieval import RetrievalOutcome


def _match(document_key: str, *, visibility: str = "public") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_version_id=uuid4(),
        document_key=document_key,
        title="Document",
        canonical_path="/support/document",
        source_url=None,
        visibility=visibility,
        chunk_index=0,
        heading_path=(),
        content="Synthetic test evidence.",
        metadata={},
        similarity=0.8,
    )


class FixedService:
    def __init__(self, result: GroundedAnswerOutcome) -> None:
        self.result = result

    async def answer(self, **_kwargs) -> GroundedAnswerOutcome:
        return self.result


def test_metrics_count_forbidden_retrieval_and_invalid_source() -> None:
    expected = _match("account-profile")
    forbidden = _match("escalation-policy", visibility="internal")
    unretrieved = _match("other-document")
    result = GroundedAnswerOutcome(
        conversation_id=uuid4(),
        answer=f"Answer [source:{unretrieved.chunk_id}].",
        abstained=False,
        sources=(unretrieved,),
        provider="openai",
        model="gpt-test",
        generation_performed=True,
        generation_latency_ms=1,
        generation_input_tokens=2,
        generation_output_tokens=1,
        finish_reason="completed",
        provider_request_id=None,
        attempt_count=1,
        retrieval=RetrievalOutcome(
            matches=(expected, forbidden),
            embedding_model="embedding-test",
            embedding_latency_ms=1,
            embedding_input_tokens=None,
        ),
    )
    case = RagEvaluationCase(
        case_id="answerable-example",
        question="How do I change my profile?",
        kind="answerable",
        expected_behavior="answer",
        expected_document_keys=("account-profile",),
    )

    report = asyncio.run(
        evaluate_rag_cases(
            [case],
            service=FixedService(result),
            provider_name="openai",
            model="gpt-test",
            top_k=5,
            concurrency=1,
            source_name="test.json",
            dataset_sha256="a" * 64,
            available_cases=1,
            max_cases=1,
            forbidden_document_keys=("escalation-policy",),
        )
    )

    assert report.metrics.answerable_retrieval_hit_rate_at_k == 1
    assert report.metrics.citation_validity_rate == 0
    assert report.metrics.forbidden_retrieval_leakage_cases == 1
    assert report.metrics.total_embedding_input_tokens is None
