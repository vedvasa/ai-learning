from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import AsyncGenerator, Literal, Protocol

ProviderName = Literal["openai", "anthropic"]


@dataclass(frozen=True, slots=True)
class GenerationResult:
    text: str
    provider: ProviderName
    model: str
    latency_ms: float
    input_tokens: int
    output_tokens: int
    finish_reason: str
    provider_request_id: str | None


@dataclass(frozen=True, slots=True)
class StreamTextDelta:
    text: str


@dataclass(frozen=True, slots=True)
class StreamCompleted:
    result: GenerationResult


ProviderStreamEvent = StreamTextDelta | StreamCompleted
ProviderStream = AsyncGenerator[ProviderStreamEvent, None]


class ProviderErrorKind(StrEnum):
    AUTHENTICATION = "authentication"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    INVALID_REQUEST = "invalid_request"
    UNAVAILABLE = "unavailable"
    FAILURE = "failure"


class ProviderError(Exception):
    def __init__(
        self,
        kind: ProviderErrorKind,
        *,
        provider_request_id: str | None = None,
    ) -> None:
        super().__init__(kind.value)
        self.kind = kind
        self.provider_request_id = provider_request_id


class Provider(Protocol):
    name: ProviderName
    model: str

    async def generate(self, prompt: str) -> GenerationResult: ...

    def stream(self, prompt: str) -> ProviderStream: ...


class ProviderLookupError(Exception):
    def __init__(self, *, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ProviderRegistry:
    def __init__(self, providers: list[Provider] | tuple[Provider, ...]) -> None:
        self._providers = {provider.name: provider for provider in providers}

    def get(self, provider_name: ProviderName, model: str) -> Provider:
        provider = self._providers.get(provider_name)
        if provider is None:
            raise ProviderLookupError(
                code="provider_not_configured",
                message=(
                    f"{provider_name.title()} is not configured on this server."
                ),
            )

        if model != provider.model:
            raise ProviderLookupError(
                code="unsupported_model",
                message=(
                    f"Model {model!r} is not enabled for "
                    f"{provider_name.title()}."
                ),
            )

        return provider
