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

from app.providers.base import (
    GenerationResult,
    ProviderError,
    ProviderErrorKind,
)


class AnthropicProvider:
    name = "anthropic"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float,
        max_output_tokens: int,
        client: AsyncAnthropic | Any | None = None,
    ) -> None:
        self.model = model
        self._max_output_tokens = max_output_tokens
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

    @staticmethod
    def _provider_error(
        kind: ProviderErrorKind,
        error: APIError,
    ) -> ProviderError:
        return ProviderError(
            kind,
            provider_request_id=getattr(error, "request_id", None),
        )
