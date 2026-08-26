from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from app.api.dependencies import get_grounded_answer_service
from app.api.provider_errors import PROVIDER_ERROR_RESPONSES
from app.core.errors import ApplicationError, ErrorResponse, request_id_for
from app.providers.base import ProviderError, ProviderErrorKind, ProviderLookupError
from app.rag.repository import AnswerPersistenceError
from app.schemas.answering import (
    AnswerQuestionRequest,
    AnswerQuestionResponse,
    CitationSource,
)
from app.services.answering import GroundedAnswerService, GroundingError
from app.services.retrieval import RetrievalError, RetrievalErrorKind
from app.services.retry import RetryDeadlineExceeded

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["grounded question answering"])


@router.post(
    "/answer",
    response_model=AnswerQuestionResponse,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
        status.HTTP_502_BAD_GATEWAY: {"model": ErrorResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
        status.HTTP_504_GATEWAY_TIMEOUT: {"model": ErrorResponse},
    },
    summary="Answer one support question using retrieved public evidence",
)
async def answer_question(
    payload: AnswerQuestionRequest,
    request: Request,
    service: Annotated[
        GroundedAnswerService, Depends(get_grounded_answer_service)
    ],
) -> AnswerQuestionResponse:
    request_id = request_id_for(request)
    try:
        outcome = await service.answer(
            provider_name=payload.provider,
            model=payload.model,
            question=payload.question,
            top_k=payload.top_k,
            request_id=request_id,
        )
    except ProviderLookupError as error:
        status_code = (
            status.HTTP_503_SERVICE_UNAVAILABLE
            if error.code == "provider_not_configured"
            else status.HTTP_400_BAD_REQUEST
        )
        raise ApplicationError(
            code=error.code,
            message=error.message,
            status_code=status_code,
        ) from error
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
    except RetryDeadlineExceeded as error:
        mapped = PROVIDER_ERROR_RESPONSES[ProviderErrorKind.TIMEOUT]
        raise ApplicationError(
            code=mapped.code,
            message=mapped.message,
            status_code=mapped.status_code,
        ) from error
    except ProviderError as error:
        mapped = PROVIDER_ERROR_RESPONSES[error.kind]
        raise ApplicationError(
            code=mapped.code,
            message=mapped.message,
            status_code=mapped.status_code,
        ) from error
    except GroundingError as error:
        mapped = PROVIDER_ERROR_RESPONSES[ProviderErrorKind.INVALID_OUTPUT]
        raise ApplicationError(
            code=mapped.code,
            message=mapped.message,
            status_code=mapped.status_code,
        ) from error
    except AnswerPersistenceError as error:
        raise ApplicationError(
            code="answer_persistence_unavailable",
            message="The answer could not be saved safely.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from error

    logger.info(
        "grounded_answer_completed request_id=%s conversation_id=%s "
        "provider=%s model=%s abstained=%s source_count=%d "
        "generation_performed=%s attempt_count=%d",
        request_id,
        outcome.conversation_id,
        outcome.provider,
        outcome.model,
        outcome.abstained,
        len(outcome.sources),
        outcome.generation_performed,
        outcome.attempt_count,
    )
    return AnswerQuestionResponse(
        request_id=request_id,
        conversation_id=outcome.conversation_id,
        answer=outcome.answer,
        abstained=outcome.abstained,
        sources=tuple(
            CitationSource(
                chunk_id=source.chunk_id,
                document_id=source.document_id,
                document_version_id=source.document_version_id,
                document_key=source.document_key,
                title=source.title,
                canonical_path=source.canonical_path,
                source_url=source.source_url,
                heading_path=source.heading_path,
                similarity=source.similarity,
            )
            for source in outcome.sources
        ),
        provider=outcome.provider,
        model=outcome.model,
        generation_performed=outcome.generation_performed,
        generation_latency_ms=outcome.generation_latency_ms,
        generation_input_tokens=outcome.generation_input_tokens,
        generation_output_tokens=outcome.generation_output_tokens,
        finish_reason=outcome.finish_reason,
        provider_request_id=outcome.provider_request_id,
        attempt_count=outcome.attempt_count,
        embedding_model=outcome.retrieval.embedding_model,
        embedding_latency_ms=outcome.retrieval.embedding_latency_ms,
        embedding_input_tokens=outcome.retrieval.embedding_input_tokens,
    )
