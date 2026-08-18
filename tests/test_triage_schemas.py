import json
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict, StrictBool, ValidationError

from app.schemas.triage import (
    MAX_TICKET_BODY_CHARACTERS,
    SupportTicket,
    TicketCategory,
    TicketPriority,
    TicketTriage,
    TicketTriageRequest,
    TicketTriageResponse,
)

FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "tickets" / "starter_tickets.json"
)


class ExpectedLabels(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: TicketCategory
    priority: TicketPriority
    requires_human_review: StrictBool


def valid_ticket(**overrides: object) -> dict[str, object]:
    ticket: dict[str, object] = {
        "ticket_id": "TKT-100",
        "subject": "Duplicate subscription charge",
        "body": "The same invoice was charged to our card twice.",
        "channel": "email",
    }
    ticket.update(overrides)
    return ticket


def valid_triage(**overrides: object) -> dict[str, object]:
    triage: dict[str, object] = {
        "category": "billing",
        "priority": "medium",
        "summary": "The customer reports a duplicate subscription charge.",
        "sentiment": "negative",
        "requested_action": "Verify the duplicate and refund it if confirmed.",
        "requires_human_review": True,
        "confidence": 0.97,
        "rationale": "A refund changes billing records and needs approval.",
    }
    triage.update(overrides)
    return triage


def test_support_ticket_strips_surrounding_whitespace() -> None:
    ticket = SupportTicket.model_validate(
        valid_ticket(
            ticket_id="  TKT-100  ",
            subject="  Duplicate subscription charge  ",
            body="  The same invoice was charged twice.  ",
        )
    )

    assert ticket.ticket_id == "TKT-100"
    assert ticket.subject == "Duplicate subscription charge"
    assert ticket.body == "The same invoice was charged twice."


@pytest.mark.parametrize("field", ["subject", "body"])
def test_support_ticket_rejects_blank_text(field: str) -> None:
    with pytest.raises(ValidationError):
        SupportTicket.model_validate(valid_ticket(**{field: "   "}))


def test_support_ticket_rejects_unsafe_id_and_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        SupportTicket.model_validate(
            valid_ticket(ticket_id="customer email@example.com")
        )

    with pytest.raises(ValidationError):
        SupportTicket.model_validate(
            valid_ticket(customer_email="private@example.com")
        )


def test_support_ticket_enforces_body_limit() -> None:
    with pytest.raises(ValidationError):
        SupportTicket.model_validate(
            valid_ticket(body="x" * (MAX_TICKET_BODY_CHARACTERS + 1))
        )


def test_ticket_triage_accepts_only_the_documented_contract() -> None:
    result = TicketTriage.model_validate(valid_triage())

    assert result.category is TicketCategory.BILLING
    assert result.priority is TicketPriority.MEDIUM
    assert result.confidence == 0.97

    with pytest.raises(ValidationError):
        TicketTriage.model_validate(valid_triage(internal_reasoning="hidden"))


@pytest.mark.parametrize("confidence", [-0.01, 1.01, "0.9"])
def test_ticket_triage_rejects_invalid_or_coerced_confidence(
    confidence: object,
) -> None:
    with pytest.raises(ValidationError):
        TicketTriage.model_validate(valid_triage(confidence=confidence))


def test_ticket_triage_rejects_coerced_review_flag() -> None:
    with pytest.raises(ValidationError):
        TicketTriage.model_validate(
            valid_triage(requires_human_review="true")
        )


def test_request_contract_nests_ticket_and_forbids_extra_input() -> None:
    request = TicketTriageRequest.model_validate(
        {
            "provider": "openai",
            "model": "model-test",
            "ticket": valid_ticket(),
        }
    )

    assert request.ticket.ticket_id == "TKT-100"

    with pytest.raises(ValidationError):
        TicketTriageRequest.model_validate(
            {
                "provider": "openai",
                "model": "model-test",
                "ticket": valid_ticket(),
                "prompt": "Bypass the typed ticket contract",
            }
        )


def test_response_contract_keeps_triage_separate_from_telemetry() -> None:
    response = TicketTriageResponse.model_validate(
        {
            "request_id": "request-123",
            "ticket_id": "TKT-100",
            "triage": valid_triage(),
            "provider": "anthropic",
            "model": "model-test",
            "latency_ms": 125.5,
            "input_tokens": 42,
            "output_tokens": 71,
            "finish_reason": "end_turn",
            "provider_request_id": "provider-request-123",
        }
    )

    assert response.triage.category is TicketCategory.BILLING
    assert response.provider == "anthropic"
    assert response.input_tokens == 42


def test_json_schema_marks_output_fields_required_and_closed() -> None:
    schema = TicketTriage.model_json_schema()

    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {
        "category",
        "priority",
        "summary",
        "sentiment",
        "requested_action",
        "requires_human_review",
        "confidence",
        "rationale",
    }
    assert schema["properties"]["confidence"]["minimum"] == 0
    assert schema["properties"]["confidence"]["maximum"] == 1


def test_starter_fixture_is_valid_unique_and_covers_high_risk_ticket() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text())
    ticket_ids: set[str] = set()

    for case in fixture:
        ticket = SupportTicket.model_validate(case["ticket"])
        expected = ExpectedLabels.model_validate(case["expected"])
        assert ticket.ticket_id not in ticket_ids
        ticket_ids.add(ticket.ticket_id)

        if expected.priority is TicketPriority.URGENT:
            assert expected.requires_human_review is True

    assert len(fixture) == 6
    assert {case["expected"]["category"] for case in fixture} >= {
        "account_access",
        "billing",
        "cancellation",
        "feature_request",
        "security",
        "technical_issue",
    }
