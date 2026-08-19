from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from threading import Lock
from typing import Protocol

from app.providers.base import ProviderErrorKind, ProviderName

logger = logging.getLogger(__name__)


class UsageOperation(StrEnum):
    TRIAGE = "triage"


class UsageOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"


@dataclass(frozen=True, slots=True)
class UsageRecord:
    request_id: str
    operation: UsageOperation
    provider: ProviderName
    model: str
    outcome: UsageOutcome
    duration_ms: float
    input_tokens: int | None
    output_tokens: int | None
    attempt_count: int
    error_kind: ProviderErrorKind | None = None
    recorded_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.request_id or len(self.request_id) > 128:
            raise ValueError("request_id must contain 1 to 128 characters")
        if not self.model or len(self.model) > 256:
            raise ValueError("model must contain 1 to 256 characters")
        if self.provider not in ("openai", "anthropic"):
            raise ValueError("provider must be openai or anthropic")
        if self.duration_ms < 0:
            raise ValueError("duration_ms cannot be negative")
        if self.input_tokens is not None and self.input_tokens < 0:
            raise ValueError("token counts cannot be negative")
        if self.output_tokens is not None and self.output_tokens < 0:
            raise ValueError("token counts cannot be negative")
        if self.attempt_count < 1:
            raise ValueError("attempt_count must be at least one")
        if self.outcome is UsageOutcome.SUCCESS and self.error_kind is not None:
            raise ValueError("successful records cannot contain an error kind")
        if self.outcome is UsageOutcome.SUCCESS and (
            self.input_tokens is None or self.output_tokens is None
        ):
            raise ValueError("successful records require token counts")
        if self.outcome is UsageOutcome.FAILURE and self.error_kind is None:
            raise ValueError("failed records require an error kind")
        if self.recorded_at.utcoffset() is None:
            raise ValueError("recorded_at must include a timezone")


class UsageRecorder(Protocol):
    async def record(self, usage: UsageRecord) -> None: ...


class InMemoryUsageRecorder:
    """A bounded, process-local recorder for development and learning."""

    def __init__(self, *, capacity: int) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least one")
        self._records: deque[UsageRecord] = deque(maxlen=capacity)
        self._lock = Lock()

    async def record(self, usage: UsageRecord) -> None:
        with self._lock:
            self._records.append(usage)

    async def snapshot(self) -> tuple[UsageRecord, ...]:
        with self._lock:
            return tuple(self._records)


async def record_usage_safely(
    recorder: UsageRecorder,
    usage: UsageRecord,
) -> None:
    """Keep optional operational telemetry from breaking the user request."""

    try:
        await recorder.record(usage)
    except Exception:
        logger.error(
            "usage_record_failed request_id=%s operation=%s",
            usage.request_id,
            usage.operation.value,
        )
