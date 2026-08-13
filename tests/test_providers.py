import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import anthropic
import httpx
import httpx2
import openai
import pytest

from app.providers.anthropic_provider import AnthropicProvider
from app.providers.base import ProviderError, ProviderErrorKind
from app.providers.openai_provider import OpenAIProvider


def test_openai_adapter_normalizes_responses_api_result() -> None:
    response = SimpleNamespace(
        output_text="  A concise OpenAI response.  ",
        model="gpt-test",
        usage=SimpleNamespace(input_tokens=11, output_tokens=7),
        incomplete_details=None,
        status="completed",
        _request_id="openai-request-123",
    )
    create = AsyncMock(return_value=response)
    client = SimpleNamespace(responses=SimpleNamespace(create=create))
    provider = OpenAIProvider(
        api_key="test-key",
        model="gpt-test",
        timeout_seconds=2,
        max_output_tokens=64,
        client=client,
    )

    result = asyncio.run(provider.generate("A test prompt"))

    create.assert_awaited_once_with(
        model="gpt-test",
        input="A test prompt",
        max_output_tokens=64,
        reasoning={"effort": "none"},
        store=False,
    )
    assert result.text == "A concise OpenAI response."
    assert result.provider == "openai"
    assert result.model == "gpt-test"
    assert result.input_tokens == 11
    assert result.output_tokens == 7
    assert result.finish_reason == "completed"
    assert result.provider_request_id == "openai-request-123"
    assert result.latency_ms >= 0


def test_openai_adapter_uses_incomplete_reason_as_finish_reason() -> None:
    response = SimpleNamespace(
        output_text="Partial response",
        model="gpt-test",
        usage=SimpleNamespace(input_tokens=4, output_tokens=64),
        incomplete_details=SimpleNamespace(reason="max_output_tokens"),
        status="incomplete",
        _request_id=None,
    )
    client = SimpleNamespace(
        responses=SimpleNamespace(create=AsyncMock(return_value=response))
    )
    provider = OpenAIProvider(
        api_key="test-key",
        model="gpt-test",
        timeout_seconds=2,
        max_output_tokens=64,
        client=client,
    )

    result = asyncio.run(provider.generate("A test prompt"))

    assert result.finish_reason == "max_output_tokens"


def test_anthropic_adapter_normalizes_messages_api_result() -> None:
    response = SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text="Anthropic "),
            SimpleNamespace(type="tool_use", name="ignored"),
            SimpleNamespace(type="text", text="response."),
        ],
        model="claude-test",
        usage=SimpleNamespace(input_tokens=9, output_tokens=6),
        stop_reason="end_turn",
        _request_id="anthropic-request-123",
    )
    create = AsyncMock(return_value=response)
    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    provider = AnthropicProvider(
        api_key="test-key",
        model="claude-test",
        timeout_seconds=2,
        max_output_tokens=64,
        client=client,
    )

    result = asyncio.run(provider.generate("A test prompt"))

    create.assert_awaited_once_with(
        model="claude-test",
        max_tokens=64,
        messages=[{"role": "user", "content": "A test prompt"}],
    )
    assert result.text == "Anthropic response."
    assert result.provider == "anthropic"
    assert result.model == "claude-test"
    assert result.input_tokens == 9
    assert result.output_tokens == 6
    assert result.finish_reason == "end_turn"
    assert result.provider_request_id == "anthropic-request-123"
    assert result.latency_ms >= 0


def test_openai_adapter_maps_typed_rate_limit_error() -> None:
    response = httpx2.Response(
        429,
        request=httpx2.Request("POST", "https://api.openai.com/v1/responses"),
        headers={"x-request-id": "openai-rate-limit-123"},
    )
    sdk_error = openai.RateLimitError(
        "raw provider detail",
        response=response,
        body=None,
    )
    client = SimpleNamespace(
        responses=SimpleNamespace(create=AsyncMock(side_effect=sdk_error))
    )
    provider = OpenAIProvider(
        api_key="test-key",
        model="gpt-test",
        timeout_seconds=2,
        max_output_tokens=64,
        client=client,
    )

    with pytest.raises(ProviderError) as caught:
        asyncio.run(provider.generate("A test prompt"))

    assert caught.value.kind is ProviderErrorKind.RATE_LIMIT
    assert caught.value.provider_request_id == "openai-rate-limit-123"
    assert "raw provider detail" not in str(caught.value)


def test_anthropic_adapter_maps_typed_rate_limit_error() -> None:
    response = httpx.Response(
        429,
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
        headers={"request-id": "anthropic-rate-limit-123"},
    )
    sdk_error = anthropic.RateLimitError(
        "raw provider detail",
        response=response,
        body=None,
    )
    client = SimpleNamespace(
        messages=SimpleNamespace(create=AsyncMock(side_effect=sdk_error))
    )
    provider = AnthropicProvider(
        api_key="test-key",
        model="claude-test",
        timeout_seconds=2,
        max_output_tokens=64,
        client=client,
    )

    with pytest.raises(ProviderError) as caught:
        asyncio.run(provider.generate("A test prompt"))

    assert caught.value.kind is ProviderErrorKind.RATE_LIMIT
    assert caught.value.provider_request_id == "anthropic-rate-limit-123"
    assert "raw provider detail" not in str(caught.value)
