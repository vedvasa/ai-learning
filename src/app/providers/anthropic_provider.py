from __future__ import annotations

from time import perf_counter
from typing import Any

from anthropic import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    AsyncAnthropic,
    AuthenticationError,
    BadRequestError,
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


class AnthropicProvider:
    name = "anthropic"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float,
        max_output_tokens: int,
        triage_max_output_tokens: int = 256,
        client: AsyncAnthropic | Any | None = None,
    ) -> None:
        self.model = model
        self._max_output_tokens = max_output_tokens
        self._triage_max_output_tokens = triage_max_output_tokens
        self._client = client or AsyncAnthropic(
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=2,
        )

    async def generate(self, prompt: str) -> GenerationResult:
        started_at = perf_counter()

        try:
            response = await self._client.messages.create(
                model=self.model,
                max_tokens=self._max_output_tokens,
                messages=[{"role": "user", "content": prompt}],
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
            kind = (
                ProviderErrorKind.UNAVAILABLE
                if error.status_code >= 500
                else ProviderErrorKind.FAILURE
            )
            raise self._provider_error(kind, error) from error
        except APIError as error:
            raise self._provider_error(ProviderErrorKind.FAILURE, error) from error

        output = "".join(
            block.text
            for block in response.content
            if getattr(block, "type", None) == "text"
        ).strip()

        return GenerationResult(
            text=output,
            provider=self.name,
            model=response.model,
            latency_ms=round((perf_counter() - started_at) * 1000, 2),
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            finish_reason=response.stop_reason or "unknown",
            provider_request_id=getattr(response, "_request_id", None),
        )

    async def stream(self, prompt: str) -> ProviderStream:
        started_at = perf_counter()

        try:
            async with self._client.messages.stream(
                model=self.model,
                max_tokens=self._max_output_tokens,
                messages=[{"role": "user", "content": prompt}],
            ) as provider_stream:
                async for text in provider_stream.text_stream:
                    if text:
                        yield StreamTextDelta(text=text)

                response = await provider_stream.get_final_message()
                output = "".join(
                    block.text
                    for block in response.content
                    if getattr(block, "type", None) == "text"
                ).strip()
                result = GenerationResult(
                    text=output,
                    provider=self.name,
                    model=response.model,
                    latency_ms=round(
                        (perf_counter() - started_at) * 1000,
                        2,
                    ),
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    finish_reason=response.stop_reason or "unknown",
                    provider_request_id=(
                        provider_stream.request_id
                        or getattr(response, "_request_id", None)
                    ),
                )
                yield StreamCompleted(result=result)
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
            kind = (
                ProviderErrorKind.UNAVAILABLE
                if error.status_code >= 500
                else ProviderErrorKind.FAILURE
            )
            raise self._provider_error(kind, error) from error
        except APIError as error:
            raise self._provider_error(ProviderErrorKind.FAILURE, error) from error

    async def triage(self, ticket: SupportTicket) -> TriageResult:
        started_at = perf_counter()

        try:
            response = await self._client.messages.parse(
                model=self.model,
                max_tokens=self._triage_max_output_tokens,
                system=TRIAGE_SYSTEM_INSTRUCTIONS,
                messages=[
                    {
                        "role": "user",
                        "content": serialize_ticket(ticket),
                    }
                ],
                output_format=TicketTriage,
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
            kind = (
                ProviderErrorKind.UNAVAILABLE
                if error.status_code >= 500
                else ProviderErrorKind.FAILURE
            )
            raise self._provider_error(kind, error) from error
        except APIError as error:
            raise self._provider_error(ProviderErrorKind.FAILURE, error) from error
        except ValidationError as error:
            raise ProviderError(ProviderErrorKind.INVALID_OUTPUT) from error

        triage = response.parsed_output
        if triage is None or response.stop_reason in {"max_tokens", "refusal"}:
            raise ProviderError(
                ProviderErrorKind.INVALID_OUTPUT,
                provider_request_id=getattr(response, "_request_id", None),
            )

        return TriageResult(
            triage=triage,
            provider=self.name,
            model=response.model,
            latency_ms=round((perf_counter() - started_at) * 1000, 2),
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            finish_reason=response.stop_reason or "unknown",
            provider_request_id=getattr(response, "_request_id", None),
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
