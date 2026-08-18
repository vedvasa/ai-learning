from __future__ import annotations

import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from app.api.dependencies import get_provider_registry
from app.api.provider_errors import PROVIDER_ERROR_RESPONSES
from app.core.config import Settings, get_settings
from app.core.errors import ApplicationError, ErrorResponse, request_id_for
from app.providers.base import (
    ProviderError,
    ProviderErrorKind,
    ProviderLookupError,
    ProviderRegistry,
)
from app.schemas.triage import TicketTriageRequest, TicketTriageResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["ticket triage"])


@router.post(
    "/triage",
    response_model=TicketTriageResponse,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
        status.HTTP_502_BAD_GATEWAY: {"model": ErrorResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
        status.HTTP_504_GATEWAY_TIMEOUT: {"model": ErrorResponse},
    },
    summary="Classify one support ticket into validated structured data",
)
async def triage_ticket(
    payload: TicketTriageRequest,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    registry: Annotated[ProviderRegistry, Depends(get_provider_registry)],
) -> TicketTriageResponse:
    request_id = request_id_for(request)

    try:
        provider = registry.get(payload.provider, payload.model)
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

    try:
        async with asyncio.timeout(settings.llm_timeout_seconds):
            result = await provider.triage(payload.ticket)
    except TimeoutError as error:
        logger.warning(
            "triage_failed request_id=%s ticket_id=%s provider=%s model=%s "
            "error_kind=total_timeout",
            request_id,
            payload.ticket.ticket_id,
            payload.provider,
            payload.model,
        )
        timeout_response = PROVIDER_ERROR_RESPONSES[ProviderErrorKind.TIMEOUT]
        raise ApplicationError(
            code=timeout_response.code,
            message=timeout_response.message,
            status_code=timeout_response.status_code,
        ) from error
    except ProviderError as error:
        logger.warning(
            "triage_failed request_id=%s ticket_id=%s provider=%s model=%s "
            "error_kind=%s provider_request_id=%s",
            request_id,
            payload.ticket.ticket_id,
            payload.provider,
            payload.model,
            error.kind.value,
            error.provider_request_id,
        )
        mapped_error = PROVIDER_ERROR_RESPONSES[error.kind]
        raise ApplicationError(
            code=mapped_error.code,
            message=mapped_error.message,
            status_code=mapped_error.status_code,
        ) from error

    logger.info(
        "triage_completed request_id=%s ticket_id=%s provider=%s model=%s "
        "category=%s priority=%s requires_human_review=%s "
        "confidence=%.3f latency_ms=%.2f input_tokens=%d output_tokens=%d "
        "finish_reason=%s provider_request_id=%s",
        request_id,
        payload.ticket.ticket_id,
        result.provider,
        result.model,
        result.triage.category,
        result.triage.priority,
        result.triage.requires_human_review,
        result.triage.confidence,
        result.latency_ms,
        result.input_tokens,
        result.output_tokens,
        result.finish_reason,
        result.provider_request_id,
    )

    return TicketTriageResponse(
        request_id=request_id,
        ticket_id=payload.ticket.ticket_id,
        triage=result.triage,
        provider=result.provider,
        model=result.model,
        latency_ms=result.latency_ms,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        finish_reason=result.finish_reason,
        provider_request_id=result.provider_request_id,
    )
