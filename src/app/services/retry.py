from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from random import random
from typing import TYPE_CHECKING, AbstractSet, Generic, TypeVar

from app.providers.base import ProviderError, ProviderErrorKind

if TYPE_CHECKING:
    from app.core.config import Settings

ResultT = TypeVar("ResultT")
Sleep = Callable[[float], Awaitable[None]]
RandomValue = Callable[[], float]
OnRetry = Callable[[int, ProviderError, float], None]

RETRYABLE_PROVIDER_ERRORS = frozenset(
    {
        ProviderErrorKind.RATE_LIMIT,
        ProviderErrorKind.TIMEOUT,
        ProviderErrorKind.UNAVAILABLE,
    }
)


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int
    base_delay_seconds: float
    max_delay_seconds: float
    jitter_ratio: float

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least one")
        if self.base_delay_seconds < 0 or self.max_delay_seconds < 0:
            raise ValueError("retry delays cannot be negative")
        if not 0 <= self.jitter_ratio <= 1:
            raise ValueError("jitter_ratio must be between zero and one")

    @classmethod
    def from_settings(cls, settings: Settings) -> RetryPolicy:
        return cls(
            max_attempts=settings.llm_max_attempts,
            base_delay_seconds=settings.llm_retry_base_delay_seconds,
            max_delay_seconds=settings.llm_retry_max_delay_seconds,
            jitter_ratio=settings.llm_retry_jitter_ratio,
        )

    def delay_after(self, failed_attempt: int, random_sample: float) -> float:
        bounded_sample = min(max(random_sample, 0), 1)
        exponential_delay = min(
            self.max_delay_seconds,
            self.base_delay_seconds * (2 ** (failed_attempt - 1)),
        )
        return exponential_delay * (1 - self.jitter_ratio * bounded_sample)


@dataclass(frozen=True, slots=True)
class RetryOutcome(Generic[ResultT]):
    value: ResultT
    attempt_count: int


class RetryDeadlineExceeded(TimeoutError):
    def __init__(self, *, attempt_count: int) -> None:
        super().__init__("provider retry deadline exceeded")
        self.attempt_count = attempt_count


async def call_with_retry(
    operation: Callable[[], Awaitable[ResultT]],
    *,
    policy: RetryPolicy,
    timeout_seconds: float,
    on_retry: OnRetry | None = None,
    retryable_errors: AbstractSet[ProviderErrorKind] = RETRYABLE_PROVIDER_ERRORS,
    sleep: Sleep = asyncio.sleep,
    random_value: RandomValue = random,
) -> RetryOutcome[ResultT]:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds

    for attempt in range(1, policy.max_attempts + 1):
        try:
            async with asyncio.timeout_at(deadline):
                value = await operation()
        except ProviderError as error:
            error.attempt_count = attempt
            if (
                error.kind not in retryable_errors
                or attempt >= policy.max_attempts
            ):
                raise

            delay_seconds = policy.delay_after(attempt, random_value())
            remaining_seconds = deadline - loop.time()
            if remaining_seconds <= delay_seconds:
                raise RetryDeadlineExceeded(
                    attempt_count=attempt,
                ) from error

            if on_retry is not None:
                on_retry(attempt, error, delay_seconds)

            try:
                async with asyncio.timeout_at(deadline):
                    await sleep(delay_seconds)
            except TimeoutError as sleep_error:
                raise RetryDeadlineExceeded(
                    attempt_count=attempt,
                ) from sleep_error
        except TimeoutError as error:
            raise RetryDeadlineExceeded(
                attempt_count=attempt,
            ) from error
        else:
            return RetryOutcome(value=value, attempt_count=attempt)

    raise AssertionError("retry loop exited without a result or error")
