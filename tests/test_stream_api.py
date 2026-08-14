from __future__ import annotations

import asyncio
import json
import logging
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.stream import stream_provider_events
from app.core.config import Settings
from app.main import create_app
from app.providers.base import (
    GenerationResult,
    ProviderError,
    ProviderErrorKind,
    ProviderRegistry,
    StreamCompleted,
    StreamTextDelta,
)
from app.schemas.generation import GenerationRequest


class FakeStreamingProvider:
    name = "openai"
    model = "gpt-test"

    def __init__(
        self,
        *,
        events=None,
        error: Exception | None = None,
        delay_seconds: float = 0,
    ) -> None:
        self.events = events or self.default_events()
        self.error = error
        self.delay_seconds = delay_seconds
        self.prompts: list[str] = []
        self.closed = False

    @classmethod
    def default_events(cls):
        return [
            StreamTextDelta(text="A streamed "),
            StreamTextDelta(text="fake response."),
            StreamCompleted(
                result=GenerationResult(
                    text="A streamed fake response.",
                    provider="openai",
                    model=cls.model,
                    latency_ms=14.25,
                    input_tokens=9,
                    output_tokens=6,
                    finish_reason="completed",
                    provider_request_id="provider-stream-request-123",
                )
            ),
        ]

    async def stream(self, prompt: str):
        self.prompts.append(prompt)
        try:
            if self.delay_seconds:
                await asyncio.sleep(self.delay_seconds)
            if self.error is not None:
                raise self.error
            for event in self.events:
                yield event
        finally:
            self.closed = True


class FakeRequest:
    def __init__(self, request_id: str) -> None:
        self.state = SimpleNamespace(request_id=request_id)


def make_settings(*, timeout_seconds: float = 1) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        openai_api_key="test-openai-key",
        anthropic_api_key="test-anthropic-key",
        openai_model="gpt-test",
        anthropic_model="claude-test",
        llm_timeout_seconds=timeout_seconds,
    )


def make_client(
    provider: FakeStreamingProvider | None,
    *,
    timeout_seconds: float = 1,
) -> TestClient:
    providers = [] if provider is None else [provider]
    app = create_app(
        make_settings(timeout_seconds=timeout_seconds),
        provider_registry=ProviderRegistry(providers),
    )
    return TestClient(app)


def stream_payload(**overrides: str) -> dict[str, str]:
    payload = {
        "provider": "openai",
        "model": "gpt-test",
        "prompt": "Explain why streaming improves perceived latency.",
    }
    payload.update(overrides)
    return payload


def parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.replace("\r\n", "\n").strip().split("\n\n"):
        lines = block.splitlines()
        event_name = next(
            line.removeprefix("event: ")
            for line in lines
            if line.startswith("event: ")
        )
        data = "\n".join(
            line.removeprefix("data: ")
            for line in lines
            if line.startswith("data: ")
        )
        events.append((event_name, json.loads(data)))
    return events


def test_stream_returns_incremental_sse_and_completion_metrics(caplog) -> None:
    provider = FakeStreamingProvider()
    secret_prompt = "A streaming prompt that must never enter logs."

    with caplog.at_level(logging.INFO, logger="app.api.stream"):
        with make_client(provider) as client:
            response = client.post(
                "/api/stream",
                json=stream_payload(prompt=secret_prompt),
                headers={"X-Request-ID": "browser-stream-request-123"},
            )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    assert response.headers["x-request-id"] == "browser-stream-request-123"
    events = parse_sse(response.text)
    assert [event_name for event_name, _ in events] == [
        "start",
        "delta",
        "delta",
        "complete",
    ]
    assert events[0][1] == {
        "request_id": "browser-stream-request-123",
        "provider": "openai",
        "model": "gpt-test",
    }
    assert events[1][1] == {"text": "A streamed "}
    assert events[2][1] == {"text": "fake response."}
    assert events[3][1] == {
        "request_id": "browser-stream-request-123",
        "provider": "openai",
        "model": "gpt-test",
        "latency_ms": 14.25,
        "input_tokens": 9,
        "output_tokens": 6,
        "finish_reason": "completed",
        "provider_request_id": "provider-stream-request-123",
    }
    assert provider.prompts == [secret_prompt]
    assert provider.closed is True
    assert "stream_completed" in caplog.text
    assert secret_prompt not in caplog.text
    assert "A streamed fake response." not in caplog.text


def test_stream_validation_failure_remains_regular_json() -> None:
    with make_client(FakeStreamingProvider()) as client:
        response = client.post(
            "/api/stream",
            json=stream_payload(prompt="   "),
            headers={"X-Request-ID": "stream-validation-request"},
        )

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["error"]["code"] == "invalid_request"
    assert response.json()["error"]["request_id"] == (
        "stream-validation-request"
    )


def test_stream_rejects_unconfigured_model_before_opening_sse() -> None:
    with make_client(FakeStreamingProvider()) as client:
        response = client.post(
            "/api/stream",
            json=stream_payload(model="unconfigured-model"),
        )

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["error"]["code"] == "unsupported_model"


def test_stream_maps_provider_failure_to_safe_sse_error() -> None:
    provider = FakeStreamingProvider(
        error=ProviderError(
            ProviderErrorKind.RATE_LIMIT,
            provider_request_id="provider-failure-123",
        )
    )

    with make_client(provider) as client:
        response = client.post(
            "/api/stream",
            json=stream_payload(),
            headers={"X-Request-ID": "stream-rate-limit-request"},
        )

    assert response.status_code == 200
    events = parse_sse(response.text)
    assert events == [
        (
            "start",
            {
                "request_id": "stream-rate-limit-request",
                "provider": "openai",
                "model": "gpt-test",
            },
        ),
        (
            "error",
            {
                "code": "provider_rate_limited",
                "message": (
                    "The selected provider is temporarily rate limited."
                ),
                "request_id": "stream-rate-limit-request",
            },
        ),
    ]
    assert "provider-failure-123" not in response.text
    assert provider.closed is True


def test_stream_applies_total_provider_deadline() -> None:
    provider = FakeStreamingProvider(delay_seconds=0.05)

    with make_client(provider, timeout_seconds=0.001) as client:
        response = client.post(
            "/api/stream",
            json=stream_payload(),
            headers={"X-Request-ID": "stream-timeout-request"},
        )

    events = parse_sse(response.text)
    assert [event_name for event_name, _ in events] == ["start", "error"]
    assert events[1][1]["code"] == "provider_timeout"
    assert events[1][1]["request_id"] == "stream-timeout-request"
    assert provider.closed is True


def test_stream_task_cancellation_closes_provider() -> None:
    started = asyncio.Event()
    provider_closed = False

    class WaitingProvider(FakeStreamingProvider):
        async def stream(self, prompt: str):
            nonlocal provider_closed
            self.prompts.append(prompt)
            try:
                started.set()
                await asyncio.Event().wait()
                yield StreamTextDelta(text="unreachable")
            finally:
                provider_closed = True

    async def cancel_stream() -> None:
        provider = WaitingProvider()
        request = FakeRequest("cancelled-request")
        generator = stream_provider_events(
            request=request,
            provider=provider,
            payload=GenerationRequest(**stream_payload()),
            timeout_seconds=1,
        )
        await anext(generator)
        pending_event = asyncio.create_task(anext(generator))
        await started.wait()
        pending_event.cancel()
        try:
            await pending_event
        except asyncio.CancelledError:
            pass
        await generator.aclose()

    asyncio.run(cancel_stream())

    assert provider_closed is True
