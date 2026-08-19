from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.providers.base import (
    ProviderError,
    ProviderErrorKind,
    ProviderRegistry,
    TriageResult,
)
from app.schemas.triage import SupportTicket, TicketTriage
from app.services.usage import (
    InMemoryUsageRecorder,
    UsageOutcome,
    UsageRecorder,
)


class FakeTriageProvider:
    name = "openai"
    model = "gpt-test"

    def __init__(
        self,
        *,
        error: Exception | None = None,
        errors_before_success: list[ProviderError] | None = None,
        delay_seconds: float = 0,
    ) -> None:
        self.error = error
        self.errors_before_success = list(errors_before_success or [])
        self.delay_seconds = delay_seconds
        self.tickets: list[SupportTicket] = []

    async def triage(self, ticket: SupportTicket) -> TriageResult:
        self.tickets.append(ticket)
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        if self.errors_before_success:
            raise self.errors_before_success.pop(0)
        if self.error is not None:
            raise self.error
        return TriageResult(
            triage=TicketTriage(
                category="billing",
                priority="medium",
                summary="The customer reports a duplicate charge.",
                sentiment="negative",
                requested_action="Verify and refund the duplicate if confirmed.",
                requires_human_review=True,
                confidence=0.97,
                rationale="A refund changes billing records and needs approval.",
            ),
            provider="openai",
            model=self.model,
            latency_ms=18.25,
            input_tokens=82,
            output_tokens=64,
            finish_reason="completed",
            provider_request_id="provider-triage-123",
        )


def make_settings(
    *,
    timeout_seconds: float = 1,
    max_attempts: int = 3,
) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        openai_api_key="test-openai-key",
        anthropic_api_key="test-anthropic-key",
        openai_model="gpt-test",
        anthropic_model="claude-test",
        llm_timeout_seconds=timeout_seconds,
        llm_max_attempts=max_attempts,
        llm_retry_base_delay_seconds=0,
    )


def make_client(
    provider: FakeTriageProvider | None,
    *,
    timeout_seconds: float = 1,
    max_attempts: int = 3,
    usage_recorder: UsageRecorder | None = None,
    raise_server_exceptions: bool = True,
) -> TestClient:
    providers = [] if provider is None else [provider]
    app = create_app(
        make_settings(
            timeout_seconds=timeout_seconds,
            max_attempts=max_attempts,
        ),
        provider_registry=ProviderRegistry(providers),
        usage_recorder=usage_recorder,
    )
    return TestClient(
        app,
        raise_server_exceptions=raise_server_exceptions,
    )


def triage_payload(**ticket_overrides: object) -> dict[str, object]:
    ticket: dict[str, object] = {
        "ticket_id": "TKT-200",
        "subject": "Duplicate charge contains private text",
        "body": "The invoice was charged twice; private customer detail.",
        "channel": "email",
    }
    ticket.update(ticket_overrides)
    return {
        "provider": "openai",
        "model": "gpt-test",
        "ticket": ticket,
    }


def test_triage_returns_validated_result_and_safe_telemetry(caplog) -> None:
    provider = FakeTriageProvider()
    recorder = InMemoryUsageRecorder(capacity=10)

    with caplog.at_level(logging.INFO, logger="app.api.triage"):
        with make_client(provider, usage_recorder=recorder) as client:
            response = client.post(
                "/api/triage",
                json=triage_payload(),
                headers={"X-Request-ID": "triage-request-123"},
            )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "triage-request-123"
    assert response.json() == {
        "request_id": "triage-request-123",
        "ticket_id": "TKT-200",
        "triage": {
            "category": "billing",
            "priority": "medium",
            "summary": "The customer reports a duplicate charge.",
            "sentiment": "negative",
            "requested_action": (
                "Verify and refund the duplicate if confirmed."
            ),
            "requires_human_review": True,
            "confidence": 0.97,
            "rationale": (
                "A refund changes billing records and needs approval."
            ),
        },
        "provider": "openai",
        "model": "gpt-test",
        "latency_ms": 18.25,
        "input_tokens": 82,
        "output_tokens": 64,
        "finish_reason": "completed",
        "provider_request_id": "provider-triage-123",
        "attempt_count": 1,
    }
    assert len(provider.tickets) == 1
    assert provider.tickets[0].ticket_id == "TKT-200"
    assert "triage_completed" in caplog.text
    assert "category=billing" in caplog.text
    assert "priority=medium" in caplog.text
    assert "Duplicate charge contains private text" not in caplog.text
    assert "private customer detail" not in caplog.text
    assert "The customer reports a duplicate charge" not in caplog.text

    records = asyncio.run(recorder.snapshot())
    assert len(records) == 1
    usage = records[0]
    assert usage.request_id == "triage-request-123"
    assert usage.operation.value == "triage"
    assert usage.provider == "openai"
    assert usage.model == "gpt-test"
    assert usage.outcome is UsageOutcome.SUCCESS
    assert usage.duration_ms >= 0
    assert usage.input_tokens == 82
    assert usage.output_tokens == 64
    assert usage.attempt_count == 1
    assert usage.error_kind is None
    assert "ticket_id" not in asdict(usage)
    assert "subject" not in asdict(usage)
    assert "body" not in asdict(usage)
    assert "private" not in repr(usage)


def test_triage_rejects_invalid_ticket_before_provider_call() -> None:
    provider = FakeTriageProvider()

    with make_client(provider) as client:
        response = client.post(
            "/api/triage",
            json=triage_payload(body="   "),
            headers={"X-Request-ID": "invalid-ticket-request"},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
    assert response.json()["error"]["request_id"] == "invalid-ticket-request"
    assert response.json()["error"]["details"][0]["field"] == "body.ticket.body"
    assert provider.tickets == []


def test_triage_rejects_model_outside_allowlist() -> None:
    provider = FakeTriageProvider()
    payload = triage_payload()
    payload["model"] = "unconfigured-expensive-model"

    with make_client(provider) as client:
        response = client.post("/api/triage", json=payload)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_model"
    assert provider.tickets == []


def test_triage_reports_provider_that_is_not_configured() -> None:
    with make_client(None) as client:
        response = client.post("/api/triage", json=triage_payload())

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "provider_not_configured"


def test_triage_maps_invalid_provider_output_to_safe_error() -> None:
    provider = FakeTriageProvider(
        error=ProviderError(
            ProviderErrorKind.INVALID_OUTPUT,
            provider_request_id="invalid-provider-output-123",
        )
    )
    recorder = InMemoryUsageRecorder(capacity=10)

    with make_client(provider, usage_recorder=recorder) as client:
        response = client.post(
            "/api/triage",
            json=triage_payload(),
            headers={"X-Request-ID": "invalid-output-request"},
        )

    assert response.status_code == 502
    assert response.json() == {
        "error": {
            "code": "provider_invalid_output",
            "message": (
                "The selected provider did not return a valid structured result."
            ),
            "request_id": "invalid-output-request",
        }
    }
    assert "invalid-provider-output-123" not in response.text
    assert len(provider.tickets) == 1
    records = asyncio.run(recorder.snapshot())
    assert len(records) == 1
    assert records[0].outcome is UsageOutcome.FAILURE
    assert records[0].error_kind is ProviderErrorKind.INVALID_OUTPUT
    assert records[0].input_tokens is None
    assert records[0].output_tokens is None
    assert records[0].attempt_count == 1


def test_triage_retries_rate_limits_then_returns_validated_result(
    caplog,
) -> None:
    provider = FakeTriageProvider(
        errors_before_success=[
            ProviderError(ProviderErrorKind.RATE_LIMIT),
            ProviderError(ProviderErrorKind.RATE_LIMIT),
        ]
    )
    recorder = InMemoryUsageRecorder(capacity=10)

    with caplog.at_level(logging.INFO, logger="app.api.triage"):
        with make_client(provider, usage_recorder=recorder) as client:
            response = client.post("/api/triage", json=triage_payload())

    assert response.status_code == 200
    assert response.json()["attempt_count"] == 3
    assert len(provider.tickets) == 3
    assert caplog.text.count("triage_retry_scheduled") == 2
    assert "attempt_count=3" in caplog.text
    assert "private customer detail" not in caplog.text
    records = asyncio.run(recorder.snapshot())
    assert len(records) == 1
    assert records[0].outcome is UsageOutcome.SUCCESS
    assert records[0].attempt_count == 3


def test_triage_stops_after_bounded_transient_attempts(caplog) -> None:
    provider = FakeTriageProvider(
        error=ProviderError(ProviderErrorKind.UNAVAILABLE)
    )
    recorder = InMemoryUsageRecorder(capacity=10)

    with caplog.at_level(logging.INFO, logger="app.api.triage"):
        with make_client(provider, usage_recorder=recorder) as client:
            response = client.post("/api/triage", json=triage_payload())

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "provider_unavailable"
    assert len(provider.tickets) == 3
    assert caplog.text.count("triage_retry_scheduled") == 2
    assert "attempt_count=3" in caplog.text
    records = asyncio.run(recorder.snapshot())
    assert len(records) == 1
    assert records[0].outcome is UsageOutcome.FAILURE
    assert records[0].error_kind is ProviderErrorKind.UNAVAILABLE
    assert records[0].attempt_count == 3


def test_triage_applies_total_request_timeout() -> None:
    provider = FakeTriageProvider(delay_seconds=0.05)
    recorder = InMemoryUsageRecorder(capacity=10)

    with make_client(
        provider,
        timeout_seconds=0.001,
        usage_recorder=recorder,
    ) as client:
        response = client.post("/api/triage", json=triage_payload())

    assert response.status_code == 504
    assert response.json()["error"]["code"] == "provider_timeout"
    records = asyncio.run(recorder.snapshot())
    assert len(records) == 1
    assert records[0].outcome is UsageOutcome.FAILURE
    assert records[0].error_kind is ProviderErrorKind.TIMEOUT
    assert records[0].attempt_count == 1


def test_usage_recorder_failure_does_not_break_triage_or_leak_error(caplog) -> None:
    class FailingUsageRecorder:
        async def record(self, _usage) -> None:
            raise RuntimeError("private recorder failure detail")

    with caplog.at_level(logging.ERROR, logger="app.services.usage"):
        with make_client(
            FakeTriageProvider(),
            usage_recorder=FailingUsageRecorder(),
        ) as client:
            response = client.post(
                "/api/triage",
                json=triage_payload(),
                headers={"X-Request-ID": "recorder-failure-request"},
            )

    assert response.status_code == 200
    assert "usage_record_failed" in caplog.text
    assert "request_id=recorder-failure-request" in caplog.text
    assert "private recorder failure detail" not in caplog.text


def test_unexpected_provider_failure_is_recorded_without_details() -> None:
    recorder = InMemoryUsageRecorder(capacity=10)

    with make_client(
        FakeTriageProvider(error=RuntimeError("private provider detail")),
        usage_recorder=recorder,
        raise_server_exceptions=False,
    ) as client:
        response = client.post(
            "/api/triage",
            json=triage_payload(),
            headers={"X-Request-ID": "unexpected-failure-request"},
        )

    assert response.status_code == 500
    assert "private provider detail" not in response.text
    records = asyncio.run(recorder.snapshot())
    assert len(records) == 1
    assert records[0].request_id == "unexpected-failure-request"
    assert records[0].outcome is UsageOutcome.FAILURE
    assert records[0].error_kind is ProviderErrorKind.FAILURE
    assert records[0].input_tokens is None
    assert records[0].output_tokens is None
