# ADR 0002: Use provider-native structured output behind one application contract

- Status: Accepted
- Date: 2026-08-17

## Context

OpenAI and Anthropic expose different SDK request and response types, but the
application needs one exact `TicketTriage` result. Asking a model for ordinary
JSON and parsing it manually would still allow schema drift, coercion, missing
fields, and provider-specific behavior to leak across the application boundary.

## Decision

Use each direct SDK's Pydantic structured-output helper:

- OpenAI: `responses.parse(..., text_format=TicketTriage)` and
  `output_parsed`.
- Anthropic: `messages.parse(..., output_format=TicketTriage)` and
  `parsed_output`.

Both adapters return the same application-owned `TriageResult`. They reject
missing parsed output, validation errors, refusals, and token-truncated results
as `invalid_output`. FastAPI translates that internal failure into one safe,
stable HTTP error without exposing raw provider details.

Ticket data is serialized as JSON and sent as untrusted user input. Stable
classification instructions remain in the system/instructions channel. The
triage path has its own bounded output-token setting, independent of the Week 1
prose-generation budget.

## Consequences

- The HTTP route and UI are independent of provider SDK response objects.
- Invalid model data cannot silently become application data.
- Unit and API tests can inject fake SDK clients and providers, so CI makes no
  paid model calls.
- Schema changes require coordinated Pydantic, provider, fixture, API, and UI
  updates.
- A valid schema does not prove classification quality; fixture-based evaluation
  remains a separate Week 2 task.
