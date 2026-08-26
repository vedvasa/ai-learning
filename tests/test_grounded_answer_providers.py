from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.providers.anthropic_provider import AnthropicProvider
from app.providers.base import ProviderError, ProviderErrorKind
from app.providers.openai_provider import OpenAIProvider
from app.rag.grounding import GROUNDED_ANSWER_INSTRUCTIONS
from app.schemas.answering import GroundedAnswerDraft


def draft() -> GroundedAnswerDraft:
    return GroundedAnswerDraft(
        answer=f"Reset links expire in 30 minutes [source:{uuid4()}].",
        abstained=False,
    )


def test_openai_adapter_requests_and_normalizes_grounded_structured_output() -> None:
    answer = draft()
    response = SimpleNamespace(
        output_parsed=answer,
        model="gpt-test",
        usage=SimpleNamespace(input_tokens=120, output_tokens=42),
        status="completed",
        _request_id="openai-answer-123",
    )
    parse = AsyncMock(return_value=response)
    provider = OpenAIProvider(
        api_key="test-key",
        model="gpt-test",
        timeout_seconds=2,
        max_output_tokens=64,
        answer_max_output_tokens=512,
        client=SimpleNamespace(responses=SimpleNamespace(parse=parse)),
    )

    result = asyncio.run(provider.answer_grounded('{"evidence":[]}'))

    parse.assert_awaited_once_with(
        model="gpt-test",
        instructions=GROUNDED_ANSWER_INSTRUCTIONS,
        input='{"evidence":[]}',
        text_format=GroundedAnswerDraft,
        max_output_tokens=512,
        reasoning={"effort": "none"},
        store=False,
    )
    assert result.draft == answer
    assert result.provider == "openai"
    assert result.input_tokens == 120
    assert result.output_tokens == 42
    assert result.provider_request_id == "openai-answer-123"


def test_anthropic_adapter_requests_and_normalizes_grounded_output() -> None:
    answer = draft()
    response = SimpleNamespace(
        parsed_output=answer,
        model="claude-test",
        usage=SimpleNamespace(input_tokens=118, output_tokens=39),
        stop_reason="end_turn",
        _request_id="anthropic-answer-123",
    )
    parse = AsyncMock(return_value=response)
    provider = AnthropicProvider(
        api_key="test-key",
        model="claude-test",
        timeout_seconds=2,
        max_output_tokens=64,
        answer_max_output_tokens=512,
        client=SimpleNamespace(messages=SimpleNamespace(parse=parse)),
    )

    result = asyncio.run(provider.answer_grounded('{"evidence":[]}'))

    parse.assert_awaited_once_with(
        model="claude-test",
        max_tokens=512,
        system=GROUNDED_ANSWER_INSTRUCTIONS,
        messages=[{"role": "user", "content": '{"evidence":[]}'}],
        output_format=GroundedAnswerDraft,
    )
    assert result.draft == answer
    assert result.provider == "anthropic"
    assert result.input_tokens == 118
    assert result.output_tokens == 39
    assert result.provider_request_id == "anthropic-answer-123"


@pytest.mark.parametrize(
    ("provider_name", "terminal_state"),
    [("openai", "incomplete"), ("anthropic", "max_tokens")],
)
def test_grounded_adapters_reject_missing_or_truncated_output(
    provider_name, terminal_state
) -> None:
    if provider_name == "openai":
        response = SimpleNamespace(
            output_parsed=None,
            status=terminal_state,
            _request_id="invalid-openai-answer",
        )
        provider = OpenAIProvider(
            api_key="test-key",
            model="gpt-test",
            timeout_seconds=2,
            max_output_tokens=64,
            client=SimpleNamespace(
                responses=SimpleNamespace(parse=AsyncMock(return_value=response))
            ),
        )
    else:
        response = SimpleNamespace(
            parsed_output=None,
            stop_reason=terminal_state,
            _request_id="invalid-anthropic-answer",
        )
        provider = AnthropicProvider(
            api_key="test-key",
            model="claude-test",
            timeout_seconds=2,
            max_output_tokens=64,
            client=SimpleNamespace(
                messages=SimpleNamespace(parse=AsyncMock(return_value=response))
            ),
        )

    with pytest.raises(ProviderError) as caught:
        asyncio.run(provider.answer_grounded("{}"))

    assert caught.value.kind is ProviderErrorKind.INVALID_OUTPUT
    assert caught.value.provider_request_id == f"invalid-{provider_name}-answer"
