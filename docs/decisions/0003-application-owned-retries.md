# ADR 0003: Own bounded retries at the application boundary

- Status: Accepted
- Date: 2026-08-17

## Context

The OpenAI and Anthropic Python SDKs enable two automatic retries by default.
Leaving those retries enabled while adding route-level retries would multiply
attempts, obscure cost and latency, and make the service's existing total
deadline difficult to reason about.

Not every failure is transient. Retrying authentication failures, invalid
requests, schema-invalid model output, or arbitrary unknown failures increases
load and cost without changing the result. Replaying an SSE request after any
partial output can also duplicate or splice browser-visible text.

## Decision

Configure both application provider clients with `max_retries=0`. Use one
application-owned async retry helper for non-streaming generation and ticket
triage with these properties:

- at most three total attempts by default, configurable from one to five;
- retry only rate limits, provider timeouts, connection/unavailability errors,
  HTTP `408`, HTTP `409`, and HTTP `5xx` responses;
- use capped exponential backoff with bounded random jitter;
- keep provider calls and backoff sleeps inside one total request deadline;
- propagate cancellation immediately;
- expose `attempt_count` on successful non-streaming responses;
- log the failed attempt, next attempt, delay, error class, and safe IDs without
  logging prompts, ticket text, or raw provider errors.

Do not replay streaming requests. Their existing total deadline and cancellation
behavior remain, but a transient stream failure returns one safe SSE error.

## Consequences

- Retry count, delay, and final outcome are observable and deterministic to test.
- CI can simulate `429`, transient exhaustion, deadline exhaustion, non-retryable
  failures, and cancellation without provider credentials or paid calls.
- A request never silently expands into SDK retries multiplied by application
  retries.
- A retry can create another billable provider request, so the bounded attempt
  count and returned telemetry are also cost controls.
- The current policy does not yet honor provider `Retry-After` headers because
  the provider-neutral error contract does not carry them.
- Some transient failures may still end without a retry when the remaining total
  deadline is too short for the next scheduled delay.
