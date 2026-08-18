from __future__ import annotations

import asyncio

import pytest

from app.providers.base import ProviderError, ProviderErrorKind
from app.services.retry import (
    RetryDeadlineExceeded,
    RetryPolicy,
    call_with_retry,
)


def policy(
    *,
    max_attempts: int = 3,
    base_delay_seconds: float = 0.5,
) -> RetryPolicy:
    return RetryPolicy(
        max_attempts=max_attempts,
        base_delay_seconds=base_delay_seconds,
        max_delay_seconds=2,
        jitter_ratio=0.25,
    )


def test_transient_errors_retry_with_exponential_delay_and_jitter() -> None:
    calls = 0
    delays: list[float] = []
    retries: list[tuple[int, ProviderErrorKind, float]] = []

    async def operation() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise ProviderError(ProviderErrorKind.RATE_LIMIT)
        return "validated result"

    async def fake_sleep(delay_seconds: float) -> None:
        delays.append(delay_seconds)

    outcome = asyncio.run(
        call_with_retry(
            operation,
            policy=policy(),
            timeout_seconds=5,
            sleep=fake_sleep,
            random_value=lambda: 1,
            on_retry=lambda attempt, error, delay: retries.append(
                (attempt, error.kind, delay)
            ),
        )
    )

    assert outcome.value == "validated result"
    assert outcome.attempt_count == 3
    assert calls == 3
    assert delays == [0.375, 0.75]
    assert retries == [
        (1, ProviderErrorKind.RATE_LIMIT, 0.375),
        (2, ProviderErrorKind.RATE_LIMIT, 0.75),
    ]


@pytest.mark.parametrize(
    "error_kind",
    [
        ProviderErrorKind.AUTHENTICATION,
        ProviderErrorKind.INVALID_REQUEST,
        ProviderErrorKind.INVALID_OUTPUT,
        ProviderErrorKind.FAILURE,
    ],
)
def test_non_retryable_provider_errors_fail_once(
    error_kind: ProviderErrorKind,
) -> None:
    calls = 0

    async def operation() -> None:
        nonlocal calls
        calls += 1
        raise ProviderError(error_kind)

    with pytest.raises(ProviderError) as caught:
        asyncio.run(
            call_with_retry(
                operation,
                policy=policy(),
                timeout_seconds=5,
            )
        )

    assert calls == 1
    assert caught.value.kind is error_kind
    assert caught.value.attempt_count == 1


def test_retryable_error_stops_at_max_attempts() -> None:
    calls = 0

    async def operation() -> None:
        nonlocal calls
        calls += 1
        raise ProviderError(ProviderErrorKind.UNAVAILABLE)

    with pytest.raises(ProviderError) as caught:
        asyncio.run(
            call_with_retry(
                operation,
                policy=policy(base_delay_seconds=0),
                timeout_seconds=5,
            )
        )

    assert calls == 3
    assert caught.value.kind is ProviderErrorKind.UNAVAILABLE
    assert caught.value.attempt_count == 3


def test_retry_is_not_scheduled_beyond_total_deadline() -> None:
    calls = 0

    async def operation() -> None:
        nonlocal calls
        calls += 1
        raise ProviderError(ProviderErrorKind.RATE_LIMIT)

    with pytest.raises(RetryDeadlineExceeded) as caught:
        asyncio.run(
            call_with_retry(
                operation,
                policy=policy(base_delay_seconds=1),
                timeout_seconds=0.001,
                random_value=lambda: 0,
            )
        )

    assert calls == 1
    assert caught.value.attempt_count == 1


def test_total_deadline_cancels_an_in_flight_attempt() -> None:
    async def operation() -> None:
        await asyncio.sleep(0.05)

    with pytest.raises(RetryDeadlineExceeded) as caught:
        asyncio.run(
            call_with_retry(
                operation,
                policy=policy(),
                timeout_seconds=0.001,
            )
        )

    assert caught.value.attempt_count == 1


def test_cancellation_is_never_retried() -> None:
    calls = 0

    async def operation() -> None:
        nonlocal calls
        calls += 1
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            call_with_retry(
                operation,
                policy=policy(),
                timeout_seconds=5,
            )
        )

    assert calls == 1
