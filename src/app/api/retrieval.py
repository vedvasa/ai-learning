from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.concurrency import run_in_threadpool

from app.api.dependencies import get_semantic_retriever
from app.core.errors import ApplicationError, ErrorResponse, request_id_for
from app.schemas.retrieval import (
    RetrievalMatch,
    RetrievalRequest,
    RetrievalResponse,
)
from app.services.retrieval import (
    RetrievalError,
    RetrievalErrorKind,
    SemanticRetriever,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["semantic retrieval"])


@router.post(
    "/retrieve",
    response_model=RetrievalResponse,
    responses={
        status.HTTP_502_BAD_GATEWAY: {"model": ErrorResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
    },
    summary="Retrieve public support evidence with exact cosine search",
)
async def retrieve_evidence(
    payload: RetrievalRequest,
    request: Request,
    retriever: Annotated[SemanticRetriever, Depends(get_semantic_retriever)],
) -> RetrievalResponse:
    request_id = request_id_for(request)
    try:
        outcome = await run_in_threadpool(
            retriever.retrieve,
            payload.question,
            top_k=payload.top_k,
        )
    except RetrievalError as error:
        if error.kind is RetrievalErrorKind.DATABASE:
            raise ApplicationError(
                code="retrieval_database_unavailable",
                message="The knowledge store is temporarily unavailable.",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            ) from error
        raise ApplicationError(
            code="retrieval_embedding_failed",
            message="The question could not be prepared for retrieval.",
            status_code=status.HTTP_502_BAD_GATEWAY,
        ) from error

    logger.info(
        "retrieval_completed request_id=%s embedding_model=%s "
        "match_count=%d top_k=%d",
        request_id,
        outcome.embedding_model,
        len(outcome.matches),
        payload.top_k,
    )
    return RetrievalResponse(
        request_id=request_id,
        embedding_model=outcome.embedding_model,
        embedding_latency_ms=outcome.embedding_latency_ms,
        embedding_input_tokens=outcome.embedding_input_tokens,
        matches=tuple(
            RetrievalMatch(
                chunk_id=match.chunk_id,
                document_id=match.document_id,
                document_version_id=match.document_version_id,
                document_key=match.document_key,
                title=match.title,
                canonical_path=match.canonical_path,
                source_url=match.source_url,
                visibility=match.visibility,
                chunk_index=match.chunk_index,
                heading_path=match.heading_path,
                content=match.content,
                metadata=match.metadata,
                similarity=match.similarity,
            )
            for match in outcome.matches
        ),
    )
