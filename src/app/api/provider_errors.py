from dataclasses import dataclass

from fastapi import status

from app.providers.base import ProviderErrorKind


@dataclass(frozen=True, slots=True)
class ProviderErrorResponse:
    code: str
    message: str
    status_code: int


PROVIDER_ERROR_RESPONSES = {
    ProviderErrorKind.AUTHENTICATION: ProviderErrorResponse(
        code="provider_authentication_failed",
        message="The selected provider rejected the server credentials.",
        status_code=status.HTTP_502_BAD_GATEWAY,
    ),
    ProviderErrorKind.RATE_LIMIT: ProviderErrorResponse(
        code="provider_rate_limited",
        message="The selected provider is temporarily rate limited.",
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
    ),
    ProviderErrorKind.TIMEOUT: ProviderErrorResponse(
        code="provider_timeout",
        message="The selected provider did not respond before the deadline.",
        status_code=status.HTTP_504_GATEWAY_TIMEOUT,
    ),
    ProviderErrorKind.INVALID_REQUEST: ProviderErrorResponse(
        code="provider_rejected_request",
        message="The selected provider rejected this request.",
        status_code=status.HTTP_502_BAD_GATEWAY,
    ),
    ProviderErrorKind.UNAVAILABLE: ProviderErrorResponse(
        code="provider_unavailable",
        message="The selected provider is temporarily unavailable.",
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    ),
    ProviderErrorKind.FAILURE: ProviderErrorResponse(
        code="provider_error",
        message="The selected provider request failed.",
        status_code=status.HTTP_502_BAD_GATEWAY,
    ),
}
