# ADR 0001: Ticket triage uses a strict provider-neutral contract

- Status: Accepted
- Date: 2026-08-17

## Context

Week 2 turns free-form support tickets into structured data. Provider-generated
JSON is untrusted input: valid JSON can still contain missing fields, invented
categories, coerced values, or internal reasoning that should not reach a user.
The same application contract must work with OpenAI and Anthropic without
exposing either SDK's response types to the API layer.

The course also needs reproducible evaluation data without using confidential
customer tickets or adding Jira authentication and permissions to this week's
scope.

## Decision

Define three separate contract layers with Pydantic models:

1. `SupportTicket` represents caller-controlled ticket input.
2. `TicketTriage` is the exact schema a provider must produce.
3. `TicketTriageRequest` and `TicketTriageResponse` form the HTTP
   boundary and keep provider telemetry outside the model-generated object.

All contracts reject unknown fields and enforce length or numeric bounds.
Boolean and confidence values use strict types so strings such as `"true"` and
`"0.9"` cannot silently pass validation. The public rationale is a concise,
evidence-based explanation, not hidden chain-of-thought.

Start with fictional, human-curated ticket fixtures. Keep expected evaluation
labels separate from ticket input so those labels cannot leak into the model
request. Jira or another live ticket system can later implement an input/tool
boundary without changing the triage contract.

## Consequences

- Both provider adapters satisfy the same schema before returning application
  data.
- Invalid model output will fail closed before an API response is constructed.
- Category and priority changes become deliberate schema-version decisions.
- Synthetic fixtures are safe to commit and deterministic to test.
- The contract PR did not expose a half-implemented endpoint or disabled UI;
  the working route and UI arrived with the provider implementation.
