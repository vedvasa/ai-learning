from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, AsyncGenerator, Literal, Protocol

if TYPE_CHECKING:
    from app.schemas.answering import GroundedAnswerDraft
    from app.schemas.triage import SupportTicket, TicketTriage

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
class TriageResult:
    triage: TicketTriage
    provider: ProviderName
    model: str
    latency_ms: float
    input_tokens: int
    output_tokens: int
    finish_reason: str
    provider_request_id: str | None


@dataclass(frozen=True, slots=True)
class GroundedAnswerResult:
    draft: GroundedAnswerDraft
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
    INVALID_OUTPUT = "invalid_output"
    FAILURE = "failure"


class ProviderError(Exception):
    def __init__(
        self,
        kind: ProviderErrorKind,
        *,
        provider_request_id: str | None = None,
        attempt_count: int = 1,
    ) -> None:
        super().__init__(kind.value)
        self.kind = kind
        self.provider_request_id = provider_request_id
        self.attempt_count = attempt_count


class Provider(Protocol):
    name: ProviderName
    model: str

    async def generate(self, prompt: str) -> GenerationResult: ...

    def stream(self, prompt: str) -> ProviderStream: ...

    async def triage(self, ticket: SupportTicket) -> TriageResult: ...

    async def answer_grounded(
        self, serialized_input: str
    ) -> GroundedAnswerResult: ...


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
