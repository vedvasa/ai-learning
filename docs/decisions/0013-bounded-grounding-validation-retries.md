# ADR 0013: Retry grounding validation failures within the existing budget

## Status

Accepted.

## Context

The 20-case Week 3 acceptance run completed 19 cases and safely rejected one
ambiguous case because its structurally valid model output failed citation
grounding. The rejection occurred before persistence, proving the fail-closed
boundary, but it also turned a recoverable model variation into a user-visible
failure. A smaller run of the same fictional question had produced a valid
abstention.

Structured output guarantees a shape, not application-specific citation
correctness. Missing, malformed, or unretrieved source markers must still be
validated in application code. Retrying without a shared deadline or attempt
limit would create unpredictable cost and latency.

## Decision

- Make `GroundingError` a safe `ProviderErrorKind.INVALID_OUTPUT` so the API
  continues to return the existing `provider_invalid_output` response if all
  attempts fail.
- Run citation validation inside the provider attempt. A result is successful
  only when its structured draft and citations both pass application checks.
- Let grounded answering opt into retrying `INVALID_OUTPUT` in addition to the
  shared transient error set. Keep invalid output non-retryable by default for
  prompt generation, ticket triage, and other callers.
- Reuse the existing `LLM_MAX_ATTEMPTS`, exponential backoff, jitter, and single
  `LLM_TIMEOUT_SECONDS` deadline. Do not add a separate hidden retry loop.
- Persist nothing from a rejected attempt. After a successful retry, atomically
  store only the accepted answer and its verified citations.
- Sum known provider latency and input/output tokens from every attempt that
  returned a structured result. Return and persist those totals with the
  successful exchange. Keep the final accepted result's finish reason and
  provider request ID.
- Keep question, answer, and evidence text out of retry logs. Log only safe
  operational fields, including request ID, provider, model, attempt number,
  delay, error kind, and provider request ID.

## Consequences

- A stochastic citation-format failure can recover without weakening grounding
  checks or creating a partial conversation.
- A successful request can make more than one paid generation call. Its known
  token totals reflect citation-invalid attempts rather than hiding their cost.
- Provider failures that expose no usage can still make successful request
  telemetry a lower bound.
- Repeating the same grounded input may reproduce the same invalid output; the
  bounded attempt count and total deadline prevent an unbounded loop.
- When every attempt fails validation, no conversation or model-call row is
  stored and the client receives the existing safe HTTP 502 invalid-output
  response.

## Out of scope

This decision does not change the prompt, add model-specific correction
messages, retry authentication or invalid requests, create failure telemetry
rows, rerun the paid acceptance set automatically, deploy the application, or
change the hosted database.

## References

- [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [OpenAI evaluation best practices](https://developers.openai.com/api/docs/guides/evaluation-best-practices)
