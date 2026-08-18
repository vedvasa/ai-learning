from __future__ import annotations

from time import perf_counter
from typing import Any

from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    BadRequestError,
    ContentFilterFinishReasonError,
    LengthFinishReasonError,
    RateLimitError,
)
from pydantic import ValidationError

from app.providers.base import (
    GenerationResult,
    TriageResult,
    ProviderStream,
    ProviderError,
    ProviderErrorKind,
    StreamCompleted,
    StreamTextDelta,
)
from app.schemas.triage import SupportTicket, TicketTriage
from app.services.triage import TRIAGE_SYSTEM_INSTRUCTIONS, serialize_ticket


class OpenAIProvider:
    name = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float,
        max_output_tokens: int,
        triage_max_output_tokens: int = 256,
        client: AsyncOpenAI | Any | None = None,
    ) -> None:
        self.model = model
        self._max_output_tokens = max_output_tokens
        self._triage_max_output_tokens = triage_max_output_tokens
        self._client = client or AsyncOpenAI(
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=0,
        )

    async def generate(self, prompt: str) -> GenerationResult:
        started_at = perf_counter()

        try:
            response = await self._client.responses.create(
                model=self.model,
                input=prompt,
                max_output_tokens=self._max_output_tokens,
                reasoning={"effort": "none"},
                store=False,
            )
        except AuthenticationError as error:
            raise self._provider_error(
                ProviderErrorKind.AUTHENTICATION, error
            ) from error
        except RateLimitError as error:
            raise self._provider_error(
                ProviderErrorKind.RATE_LIMIT, error
            ) from error
        except APITimeoutError as error:
            raise self._provider_error(ProviderErrorKind.TIMEOUT, error) from error
        except BadRequestError as error:
            raise self._provider_error(
                ProviderErrorKind.INVALID_REQUEST, error
            ) from error
        except APIConnectionError as error:
            raise self._provider_error(
                ProviderErrorKind.UNAVAILABLE, error
            ) from error
        except APIStatusError as error:
            kind = self._status_error_kind(error)
            raise self._provider_error(kind, error) from error
        except APIError as error:
            raise self._provider_error(ProviderErrorKind.FAILURE, error) from error

        usage = response.usage
        incomplete_details = getattr(response, "incomplete_details", None)
        finish_reason = (
            getattr(incomplete_details, "reason", None)
            or getattr(response, "status", None)
            or "unknown"
        )

        return GenerationResult(
            text=response.output_text.strip(),
            provider=self.name,
            model=response.model,
            latency_ms=round((perf_counter() - started_at) * 1000, 2),
            input_tokens=usage.input_tokens if usage else 0,
            output_tokens=usage.output_tokens if usage else 0,
            finish_reason=finish_reason,
            provider_request_id=getattr(response, "_request_id", None),
        )

    async def stream(self, prompt: str) -> ProviderStream:
        started_at = perf_counter()

        try:
            provider_stream = await self._client.responses.create(
                model=self.model,
                input=prompt,
                max_output_tokens=self._max_output_tokens,
                reasoning={"effort": "none"},
                store=False,
                stream=True,
            )

            async with provider_stream:
                provider_request_id = provider_stream.response.headers.get(
                    "x-request-id"
                )
                terminal_event_seen = False

                async for event in provider_stream:
                    if event.type == "response.output_text.delta":
                        if event.delta:
                            yield StreamTextDelta(text=event.delta)
                        continue

                    if event.type in {
                        "response.completed",
                        "response.incomplete",
                    }:
                        terminal_event_seen = True
                        response = event.response
                        result = self._result_from_response(
                            response,
                            started_at=started_at,
                            provider_request_id=(
                                provider_request_id
                                or getattr(response, "_request_id", None)
                            ),
                        )
                        yield StreamCompleted(result=result)
                        continue

                    if event.type in {"error", "response.failed"}:
                        raise ProviderError(
                            ProviderErrorKind.FAILURE,
                            provider_request_id=provider_request_id,
                        )

                if not terminal_event_seen:
                    raise ProviderError(
                        ProviderErrorKind.FAILURE,
                        provider_request_id=provider_request_id,
                    )
        except AuthenticationError as error:
            raise self._provider_error(
                ProviderErrorKind.AUTHENTICATION, error
            ) from error
        except RateLimitError as error:
            raise self._provider_error(
                ProviderErrorKind.RATE_LIMIT, error
            ) from error
        except APITimeoutError as error:
            raise self._provider_error(ProviderErrorKind.TIMEOUT, error) from error
        except BadRequestError as error:
            raise self._provider_error(
                ProviderErrorKind.INVALID_REQUEST, error
            ) from error
        except APIConnectionError as error:
            raise self._provider_error(
                ProviderErrorKind.UNAVAILABLE, error
            ) from error
        except APIStatusError as error:
            kind = self._status_error_kind(error)
            raise self._provider_error(kind, error) from error
        except APIError as error:
            raise self._provider_error(ProviderErrorKind.FAILURE, error) from error

    async def triage(self, ticket: SupportTicket) -> TriageResult:
        started_at = perf_counter()

        try:
            response = await self._client.responses.parse(
                model=self.model,
                instructions=TRIAGE_SYSTEM_INSTRUCTIONS,
                input=serialize_ticket(ticket),
                text_format=TicketTriage,
                max_output_tokens=self._triage_max_output_tokens,
                reasoning={"effort": "none"},
                store=False,
            )
        except AuthenticationError as error:
            raise self._provider_error(
                ProviderErrorKind.AUTHENTICATION, error
            ) from error
        except RateLimitError as error:
            raise self._provider_error(
                ProviderErrorKind.RATE_LIMIT, error
            ) from error
        except APITimeoutError as error:
            raise self._provider_error(ProviderErrorKind.TIMEOUT, error) from error
        except BadRequestError as error:
            raise self._provider_error(
                ProviderErrorKind.INVALID_REQUEST, error
            ) from error
        except APIConnectionError as error:
            raise self._provider_error(
                ProviderErrorKind.UNAVAILABLE, error
            ) from error
        except APIStatusError as error:
            kind = self._status_error_kind(error)
            raise self._provider_error(kind, error) from error
        except APIError as error:
            raise self._provider_error(ProviderErrorKind.FAILURE, error) from error
        except (
            ContentFilterFinishReasonError,
            LengthFinishReasonError,
            ValidationError,
        ) as error:
            raise ProviderError(ProviderErrorKind.INVALID_OUTPUT) from error

        triage = response.output_parsed
        if triage is None or response.status != "completed":
            raise ProviderError(
                ProviderErrorKind.INVALID_OUTPUT,
                provider_request_id=getattr(response, "_request_id", None),
            )

        usage = response.usage
        return TriageResult(
            triage=triage,
            provider=self.name,
            model=response.model,
            latency_ms=round((perf_counter() - started_at) * 1000, 2),
            input_tokens=usage.input_tokens if usage else 0,
            output_tokens=usage.output_tokens if usage else 0,
            finish_reason=response.status,
            provider_request_id=getattr(response, "_request_id", None),
        )

    def _result_from_response(
        self,
        response: Any,
        *,
        started_at: float,
        provider_request_id: str | None,
    ) -> GenerationResult:
        usage = response.usage
        incomplete_details = getattr(response, "incomplete_details", None)
        finish_reason = (
            getattr(incomplete_details, "reason", None)
            or getattr(response, "status", None)
            or "unknown"
        )
        return GenerationResult(
            text=response.output_text.strip(),
            provider=self.name,
            model=response.model,
            latency_ms=round((perf_counter() - started_at) * 1000, 2),
            input_tokens=usage.input_tokens if usage else 0,
            output_tokens=usage.output_tokens if usage else 0,
            finish_reason=finish_reason,
            provider_request_id=provider_request_id,
        )

    @staticmethod
    def _provider_error(
        kind: ProviderErrorKind,
        error: APIError,
    ) -> ProviderError:
        return ProviderError(
            kind,
            provider_request_id=getattr(error, "request_id", None),
        )

    @staticmethod
    def _status_error_kind(error: APIStatusError) -> ProviderErrorKind:
        if error.status_code == 408:
            return ProviderErrorKind.TIMEOUT
        if error.status_code == 409 or error.status_code >= 500:
            return ProviderErrorKind.UNAVAILABLE
        return ProviderErrorKind.FAILURE
