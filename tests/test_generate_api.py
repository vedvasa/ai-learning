from __future__ import annotations

import asyncio
import logging
import re

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.providers.base import (
    GenerationResult,
    ProviderError,
    ProviderErrorKind,
    ProviderRegistry,
)
from app.schemas.generation import MAX_PROMPT_CHARACTERS


class FakeProvider:
    name = "openai"
    model = "gpt-test"

    def __init__(
        self,
        *,
        error: Exception | None = None,
        delay_seconds: float = 0,
    ) -> None:
        self.error = error
        self.delay_seconds = delay_seconds
        self.prompts: list[str] = []

    async def generate(self, prompt: str) -> GenerationResult:
        self.prompts.append(prompt)
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        if self.error is not None:
            raise self.error
        return GenerationResult(
            text="A normalized fake response.",
            provider="openai",
            model=self.model,
            latency_ms=12.5,
            input_tokens=8,
            output_tokens=5,
            finish_reason="completed",
            provider_request_id="provider-request-123",
        )


def make_settings(*, timeout_seconds: float = 1) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        openai_api_key="test-openai-key",
        anthropic_api_key="test-anthropic-key",
        openai_model="gpt-test",
        anthropic_model="claude-test",
        llm_timeout_seconds=timeout_seconds,
        llm_retry_base_delay_seconds=0,
    )


def make_client(
    provider: FakeProvider | None,
    *,
    timeout_seconds: float = 1,
    raise_server_exceptions: bool = True,
) -> TestClient:
    providers = [] if provider is None else [provider]
    app = create_app(
        make_settings(timeout_seconds=timeout_seconds),
        provider_registry=ProviderRegistry(providers),
    )
    return TestClient(
        app,
        raise_server_exceptions=raise_server_exceptions,
    )


def generation_payload(**overrides: str) -> dict[str, str]:
    payload = {
        "provider": "openai",
        "model": "gpt-test",
        "prompt": "Explain one benefit of request IDs.",
    }
    payload.update(overrides)
    return payload


def test_generate_returns_provider_neutral_response_and_request_id(
    caplog,
) -> None:
    provider = FakeProvider()
    secret_prompt = "A prompt value that must never appear in logs."

    with caplog.at_level(logging.INFO, logger="app.api.generate"):
        with make_client(provider) as client:
            response = client.post(
                "/api/generate",
                json=generation_payload(prompt=secret_prompt),
                headers={"X-Request-ID": "browser-request-123"},
            )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "browser-request-123"
    assert response.json() == {
        "request_id": "browser-request-123",
        "text": "A normalized fake response.",
        "provider": "openai",
        "model": "gpt-test",
        "latency_ms": 12.5,
        "input_tokens": 8,
        "output_tokens": 5,
        "finish_reason": "completed",
        "provider_request_id": "provider-request-123",
        "attempt_count": 1,
    }
    assert provider.prompts == [secret_prompt]
    assert "generation_completed" in caplog.text
    assert "provider=openai" in caplog.text
    assert secret_prompt not in caplog.text
    assert "A normalized fake response." not in caplog.text


def test_generate_creates_request_id_when_header_is_not_safe() -> None:
    with make_client(FakeProvider()) as client:
        response = client.post(
            "/api/generate",
            json=generation_payload(),
            headers={"X-Request-ID": "spaces are not accepted"},
        )

    request_id = response.json()["request_id"]
    assert response.status_code == 200
    assert re.fullmatch(r"[0-9a-f]{32}", request_id)
    assert response.headers["X-Request-ID"] == request_id


def test_generate_rejects_blank_prompt_with_stable_error_shape() -> None:
    with make_client(FakeProvider()) as client:
        response = client.post(
            "/api/generate",
            json=generation_payload(prompt="   "),
            headers={"X-Request-ID": "validation-request"},
        )

    assert response.status_code == 422
    assert response.headers["X-Request-ID"] == "validation-request"
    body = response.json()
    assert body["error"]["code"] == "invalid_request"
    assert body["error"]["message"] == "The request did not pass validation."
    assert body["error"]["request_id"] == "validation-request"
    assert body["error"]["details"][0]["field"] == "body.prompt"


def test_generate_rejects_excessive_prompt_length() -> None:
    with make_client(FakeProvider()) as client:
        response = client.post(
            "/api/generate",
            json=generation_payload(
                prompt="x" * (MAX_PROMPT_CHARACTERS + 1)
            ),
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_generate_rejects_model_outside_configured_allowlist() -> None:
    with make_client(FakeProvider()) as client:
        response = client.post(
            "/api/generate",
            json=generation_payload(model="expensive-unconfigured-model"),
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_model"
    assert "expensive-unconfigured-model" in response.json()["error"]["message"]


def test_generate_reports_provider_that_is_not_configured() -> None:
    with make_client(None) as client:
        response = client.post(
            "/api/generate",
            json=generation_payload(),
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "provider_not_configured"


def test_generate_maps_provider_failure_without_leaking_sdk_details() -> None:
    provider = FakeProvider(
        error=ProviderError(
            ProviderErrorKind.RATE_LIMIT,
            provider_request_id="provider-failure-123",
        )
    )

    with make_client(provider) as client:
        response = client.post(
            "/api/generate",
            json=generation_payload(),
            headers={"X-Request-ID": "rate-limit-request"},
        )

    assert response.status_code == 429
    assert response.json() == {
        "error": {
            "code": "provider_rate_limited",
            "message": "The selected provider is temporarily rate limited.",
            "request_id": "rate-limit-request",
        }
    }
    assert "provider-failure-123" not in response.text
    assert len(provider.prompts) == 3


def test_generate_applies_total_request_timeout() -> None:
    provider = FakeProvider(delay_seconds=0.05)

    with make_client(provider, timeout_seconds=0.001) as client:
        response = client.post(
            "/api/generate",
            json=generation_payload(),
        )

    assert response.status_code == 504
    assert response.json()["error"]["code"] == "provider_timeout"


def test_unexpected_error_uses_safe_stable_response() -> None:
    provider = FakeProvider(error=RuntimeError("sensitive internal detail"))

    with make_client(
        provider,
        raise_server_exceptions=False,
    ) as client:
        response = client.post(
            "/api/generate",
            json=generation_payload(),
            headers={"X-Request-ID": "unexpected-error-request"},
        )

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "internal_error",
            "message": "The server could not complete the request.",
            "request_id": "unexpected-error-request",
        }
    }
    assert "sensitive internal detail" not in response.text
