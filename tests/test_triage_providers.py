import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.providers.anthropic_provider import AnthropicProvider
from app.providers.base import ProviderError, ProviderErrorKind
from app.providers.openai_provider import OpenAIProvider
from app.schemas.triage import SupportTicket, TicketTriage
from app.services.triage import TRIAGE_SYSTEM_INSTRUCTIONS, serialize_ticket


def sample_ticket() -> SupportTicket:
    return SupportTicket(
        ticket_id="TKT-100",
        subject="Duplicate subscription charge",
        body="The same invoice was charged to our card twice.",
        channel="email",
    )


def sample_triage() -> TicketTriage:
    return TicketTriage(
        category="billing",
        priority="medium",
        summary="The customer reports a duplicate subscription charge.",
        sentiment="negative",
        requested_action="Verify and refund the duplicate if confirmed.",
        requires_human_review=True,
        confidence=0.97,
        rationale="A refund changes billing records and needs approval.",
    )


def test_openai_adapter_normalizes_structured_triage_result() -> None:
    response = SimpleNamespace(
        output_parsed=sample_triage(),
        model="gpt-test",
        usage=SimpleNamespace(input_tokens=81, output_tokens=63),
        status="completed",
        _request_id="openai-triage-123",
    )
    parse = AsyncMock(return_value=response)
    client = SimpleNamespace(responses=SimpleNamespace(parse=parse))
    provider = OpenAIProvider(
        api_key="test-key",
        model="gpt-test",
        timeout_seconds=2,
        max_output_tokens=64,
        triage_max_output_tokens=256,
        client=client,
    )
    ticket = sample_ticket()

    result = asyncio.run(provider.triage(ticket))

    parse.assert_awaited_once_with(
        model="gpt-test",
        instructions=TRIAGE_SYSTEM_INSTRUCTIONS,
        input=serialize_ticket(ticket),
        text_format=TicketTriage,
        max_output_tokens=256,
        reasoning={"effort": "none"},
        store=False,
    )
    assert result.triage == sample_triage()
    assert result.provider == "openai"
    assert result.model == "gpt-test"
    assert result.input_tokens == 81
    assert result.output_tokens == 63
    assert result.finish_reason == "completed"
    assert result.provider_request_id == "openai-triage-123"
    assert result.latency_ms >= 0


def test_anthropic_adapter_normalizes_structured_triage_result() -> None:
    response = SimpleNamespace(
        parsed_output=sample_triage(),
        model="claude-test",
        usage=SimpleNamespace(input_tokens=79, output_tokens=66),
        stop_reason="end_turn",
        _request_id="anthropic-triage-123",
    )
    parse = AsyncMock(return_value=response)
    client = SimpleNamespace(messages=SimpleNamespace(parse=parse))
    provider = AnthropicProvider(
        api_key="test-key",
        model="claude-test",
        timeout_seconds=2,
        max_output_tokens=64,
        triage_max_output_tokens=256,
        client=client,
    )
    ticket = sample_ticket()

    result = asyncio.run(provider.triage(ticket))

    parse.assert_awaited_once_with(
        model="claude-test",
        max_tokens=256,
        system=TRIAGE_SYSTEM_INSTRUCTIONS,
        messages=[
            {
                "role": "user",
                "content": serialize_ticket(ticket),
            }
        ],
        output_format=TicketTriage,
    )
    assert result.triage == sample_triage()
    assert result.provider == "anthropic"
    assert result.model == "claude-test"
    assert result.input_tokens == 79
    assert result.output_tokens == 66
    assert result.finish_reason == "end_turn"
    assert result.provider_request_id == "anthropic-triage-123"
    assert result.latency_ms >= 0


@pytest.mark.parametrize(
    ("provider_name", "terminal_state"),
    [("openai", "incomplete"), ("anthropic", "max_tokens")],
)
def test_adapters_reject_missing_or_truncated_structured_output(
    provider_name: str,
    terminal_state: str,
) -> None:
    if provider_name == "openai":
        response = SimpleNamespace(
            output_parsed=None,
            status=terminal_state,
            _request_id="invalid-openai-output",
        )
        client = SimpleNamespace(
            responses=SimpleNamespace(parse=AsyncMock(return_value=response))
        )
        provider = OpenAIProvider(
            api_key="test-key",
            model="gpt-test",
            timeout_seconds=2,
            max_output_tokens=64,
            client=client,
        )
    else:
        response = SimpleNamespace(
            parsed_output=None,
            stop_reason=terminal_state,
            _request_id="invalid-anthropic-output",
        )
        client = SimpleNamespace(
            messages=SimpleNamespace(parse=AsyncMock(return_value=response))
        )
        provider = AnthropicProvider(
            api_key="test-key",
            model="claude-test",
            timeout_seconds=2,
            max_output_tokens=64,
            client=client,
        )

    with pytest.raises(ProviderError) as caught:
        asyncio.run(provider.triage(sample_ticket()))

    assert caught.value.kind is ProviderErrorKind.INVALID_OUTPUT
    assert caught.value.provider_request_id == f"invalid-{provider_name}-output"


def test_ticket_serialization_is_deterministic_and_contains_no_instructions() -> None:
    serialized = serialize_ticket(sample_ticket())

    assert serialized == (
        '{"body":"The same invoice was charged to our card twice.",'
        '"channel":"email","subject":"Duplicate subscription charge",'
        '"ticket_id":"TKT-100"}'
    )
    assert "untrusted data" not in serialized
    assert "Duplicate subscription charge" not in TRIAGE_SYSTEM_INSTRUCTIONS
