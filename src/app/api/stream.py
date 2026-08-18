from __future__ import annotations

import asyncio
import logging
from contextlib import aclosing
from typing import Annotated, AsyncIterator

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.dependencies import get_provider_registry
from app.api.provider_errors import PROVIDER_ERROR_RESPONSES
from app.core.config import Settings, get_settings
from app.core.errors import ApplicationError, ErrorResponse, request_id_for
from app.providers.base import (
    Provider,
    ProviderError,
    ProviderErrorKind,
    ProviderLookupError,
    ProviderRegistry,
    StreamCompleted,
    StreamTextDelta,
)
from app.schemas.generation import (
    GenerationRequest,
    StreamCompletion,
    StreamDelta,
    StreamFailure,
    StreamStart,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["generation"])


def encode_sse(event: str, payload: BaseModel) -> str:
    return f"event: {event}\ndata: {payload.model_dump_json()}\n\n"


async def stream_provider_events(
    *,
    request: Request,
    provider: Provider,
    payload: GenerationRequest,
    timeout_seconds: float,
) -> AsyncIterator[str]:
    request_id = request_id_for(request)
    logger.info(
        "stream_started request_id=%s provider=%s model=%s",
        request_id,
        payload.provider,
        payload.model,
    )
    yield encode_sse(
        "start",
        StreamStart(
            request_id=request_id,
            provider=payload.provider,
            model=payload.model,
        ),
    )

    provider_stream = provider.stream(payload.prompt)
    deadline = asyncio.get_running_loop().time() + timeout_seconds

    try:
        async with aclosing(provider_stream):
            while True:
                try:
                    async with asyncio.timeout_at(deadline):
                        provider_event = await anext(provider_stream)
                except StopAsyncIteration:
                    raise ProviderError(ProviderErrorKind.FAILURE) from None

                if isinstance(provider_event, StreamTextDelta):
                    yield encode_sse(
                        "delta",
                        StreamDelta(text=provider_event.text),
                    )
                    continue

                if isinstance(provider_event, StreamCompleted):
                    result = provider_event.result
                    logger.info(
                        "stream_completed request_id=%s provider=%s model=%s "
                        "latency_ms=%.2f input_tokens=%d output_tokens=%d "
                        "finish_reason=%s provider_request_id=%s",
                        request_id,
                        result.provider,
                        result.model,
                        result.latency_ms,
                        result.input_tokens,
                        result.output_tokens,
                        result.finish_reason,
                        result.provider_request_id,
                    )
                    yield encode_sse(
                        "complete",
                        StreamCompletion(
                            request_id=request_id,
                            provider=result.provider,
                            model=result.model,
                            latency_ms=result.latency_ms,
                            input_tokens=result.input_tokens,
                            output_tokens=result.output_tokens,
                            finish_reason=result.finish_reason,
                            provider_request_id=result.provider_request_id,
                        ),
                    )
                    return
    except asyncio.CancelledError:
        logger.info(
            "stream_cancelled request_id=%s provider=%s model=%s",
            request_id,
            payload.provider,
            payload.model,
        )
        raise
    except TimeoutError:
        timeout_error = PROVIDER_ERROR_RESPONSES[ProviderErrorKind.TIMEOUT]
        logger.warning(
            "stream_failed request_id=%s provider=%s model=%s "
            "error_kind=total_timeout",
            request_id,
            payload.provider,
            payload.model,
        )
        yield encode_sse(
            "error",
            StreamFailure(
                code=timeout_error.code,
                message=timeout_error.message,
                request_id=request_id,
            ),
        )
    except ProviderError as error:
        mapped_error = PROVIDER_ERROR_RESPONSES[error.kind]
        logger.warning(
            "stream_failed request_id=%s provider=%s model=%s "
            "error_kind=%s provider_request_id=%s",
            request_id,
            payload.provider,
            payload.model,
            error.kind.value,
            error.provider_request_id,
        )
        yield encode_sse(
            "error",
            StreamFailure(
                code=mapped_error.code,
                message=mapped_error.message,
                request_id=request_id,
            ),
        )
    except Exception:
        logger.error(
            "stream_failed request_id=%s provider=%s model=%s "
            "error_kind=internal",
            request_id,
            payload.provider,
            payload.model,
        )
        yield encode_sse(
            "error",
            StreamFailure(
                code="internal_error",
                message="The server could not complete the request.",
                request_id=request_id,
            ),
        )


@router.post(
    "/stream",
    response_class=StreamingResponse,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
        status.HTTP_200_OK: {
            "content": {"text/event-stream": {}},
            "description": (
                "A server-sent event stream containing start, delta, "
                "complete, or safe error events."
            ),
        },
    },
    summary="Stream one model response using server-sent events",
)
async def stream(
    payload: GenerationRequest,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    registry: Annotated[ProviderRegistry, Depends(get_provider_registry)],
) -> StreamingResponse:
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

    return StreamingResponse(
        stream_provider_events(
            request=request,
            provider=provider,
            payload=payload,
            timeout_seconds=settings.llm_timeout_seconds,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
