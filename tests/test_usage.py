from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from app.providers.base import ProviderErrorKind
from app.services.usage import (
    InMemoryUsageRecorder,
    UsageOperation,
    UsageOutcome,
    UsageRecord,
)


def make_usage_record(
    request_id: str,
    *,
    outcome: UsageOutcome = UsageOutcome.SUCCESS,
) -> UsageRecord:
    return UsageRecord(
        request_id=request_id,
        operation=UsageOperation.TRIAGE,
        provider="openai",
        model="gpt-test",
        outcome=outcome,
        duration_ms=12.5,
        input_tokens=8,
        output_tokens=5,
        attempt_count=1,
        error_kind=(
            None
            if outcome is UsageOutcome.SUCCESS
            else ProviderErrorKind.UNAVAILABLE
        ),
    )


def test_in_memory_recorder_is_bounded() -> None:
    recorder = InMemoryUsageRecorder(capacity=2)

    async def exercise() -> tuple[UsageRecord, ...]:
        await recorder.record(make_usage_record("request-1"))
        await recorder.record(make_usage_record("request-2"))
        await recorder.record(make_usage_record("request-3"))
        return await recorder.snapshot()

    records = asyncio.run(exercise())

    assert [record.request_id for record in records] == [
        "request-2",
        "request-3",
    ]


def test_in_memory_recorder_accepts_concurrent_writes() -> None:
    recorder = InMemoryUsageRecorder(capacity=100)

    async def exercise() -> tuple[UsageRecord, ...]:
        await asyncio.gather(
            *(
                recorder.record(make_usage_record(f"request-{index}"))
                for index in range(100)
            )
        )
        return await recorder.snapshot()

    records = asyncio.run(exercise())

    assert len(records) == 100
    assert {record.request_id for record in records} == {
        f"request-{index}" for index in range(100)
    }


@pytest.mark.parametrize(
    "invalid_record",
    [
        lambda record: replace(record, duration_ms=-1),
        lambda record: replace(record, input_tokens=-1),
        lambda record: replace(record, output_tokens=-1),
        lambda record: replace(record, input_tokens=None),
        lambda record: replace(record, attempt_count=0),
        lambda record: replace(
            record,
            outcome=UsageOutcome.SUCCESS,
            error_kind=ProviderErrorKind.FAILURE,
        ),
        lambda record: replace(
            record,
            outcome=UsageOutcome.FAILURE,
            error_kind=None,
        ),
    ],
)
def test_usage_record_rejects_inconsistent_metadata(invalid_record) -> None:
    with pytest.raises(ValueError):
        invalid_record(make_usage_record("request-1"))


def test_in_memory_recorder_rejects_nonpositive_capacity() -> None:
    with pytest.raises(ValueError):
        InMemoryUsageRecorder(capacity=0)
