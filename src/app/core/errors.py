from __future__ import annotations

import logging
import re
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class ValidationIssue(BaseModel):
    field: str
    message: str


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str
    details: list[ValidationIssue] | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


class ApplicationError(Exception):
    def __init__(self, *, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def request_id_for(request: Request) -> str:
    return getattr(request.state, "request_id", uuid4().hex)


def error_response(
    request: Request,
    *,
    code: str,
    message: str,
    status_code: int,
    details: list[ValidationIssue] | None = None,
) -> JSONResponse:
    request_id = request_id_for(request)
    payload = ErrorResponse(
        error=ErrorDetail(
            code=code,
            message=message,
            request_id=request_id,
            details=details,
        )
    )
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(exclude_none=True),
        headers={REQUEST_ID_HEADER: request_id},
    )


def register_error_handling(app: FastAPI) -> None:
    @app.middleware("http")
    async def attach_request_id(request: Request, call_next: Any) -> Any:
        supplied_request_id = request.headers.get(REQUEST_ID_HEADER, "")
        request.state.request_id = (
            supplied_request_id
            if _REQUEST_ID_PATTERN.fullmatch(supplied_request_id)
            else uuid4().hex
        )
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request.state.request_id
        return response

    @app.exception_handler(ApplicationError)
    async def handle_application_error(
        request: Request,
        error: ApplicationError,
    ) -> JSONResponse:
        return error_response(
            request,
            code=error.code,
            message=error.message,
            status_code=error.status_code,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        details = [
            ValidationIssue(
                field=".".join(str(part) for part in issue["loc"]),
                message=issue["msg"],
            )
            for issue in error.errors()
        ]
        return error_response(
            request,
            code="invalid_request",
            message="The request did not pass validation.",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            details=details,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(
        request: Request,
        _error: Exception,
    ) -> JSONResponse:
        request_id = request_id_for(request)
        logger.error("unhandled_error request_id=%s", request_id)
        return error_response(
            request,
            code="internal_error",
            message="The server could not complete the request.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
