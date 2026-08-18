from enum import StrEnum
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
)

from app.providers.base import ProviderName

MAX_TICKET_ID_CHARACTERS = 100
MAX_TICKET_SUBJECT_CHARACTERS = 200
MAX_TICKET_BODY_CHARACTERS = 8_000
MAX_TRIAGE_SUMMARY_CHARACTERS = 500
MAX_REQUESTED_ACTION_CHARACTERS = 500
MAX_RATIONALE_CHARACTERS = 500


class StrictContract(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class TicketChannel(StrEnum):
    EMAIL = "email"
    CHAT = "chat"
    WEB = "web"
    PHONE = "phone"
    API = "api"


class TicketCategory(StrEnum):
    ACCOUNT_ACCESS = "account_access"
    BILLING = "billing"
    CANCELLATION = "cancellation"
    FEATURE_REQUEST = "feature_request"
    SECURITY = "security"
    TECHNICAL_ISSUE = "technical_issue"
    OTHER = "other"


class TicketPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class TicketSentiment(StrEnum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class SupportTicket(StrictContract):
    ticket_id: str = Field(
        min_length=1,
        max_length=MAX_TICKET_ID_CHARACTERS,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
        description="Caller-supplied identifier safe to use in logs.",
    )
    subject: str = Field(
        min_length=1,
        max_length=MAX_TICKET_SUBJECT_CHARACTERS,
    )
    body: str = Field(
        min_length=1,
        max_length=MAX_TICKET_BODY_CHARACTERS,
    )
    channel: TicketChannel


class TicketTriage(StrictContract):
    category: TicketCategory
    priority: TicketPriority
    summary: str = Field(
        min_length=1,
        max_length=MAX_TRIAGE_SUMMARY_CHARACTERS,
    )
    sentiment: TicketSentiment
    requested_action: str = Field(
        min_length=1,
        max_length=MAX_REQUESTED_ACTION_CHARACTERS,
    )
    requires_human_review: StrictBool
    confidence: Annotated[StrictFloat, Field(ge=0, le=1)]
    rationale: str = Field(
        min_length=1,
        max_length=MAX_RATIONALE_CHARACTERS,
        description=(
            "Concise evidence-based explanation safe to show an end user; "
            "never hidden chain-of-thought."
        ),
    )


class TicketTriageRequest(StrictContract):
    provider: ProviderName
    model: str = Field(min_length=1, max_length=200)
    ticket: SupportTicket


class TicketTriageResponse(StrictContract):
    request_id: str
    ticket_id: str
    triage: TicketTriage
    provider: ProviderName
    model: str
    latency_ms: float = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    finish_reason: str
    provider_request_id: str | None
