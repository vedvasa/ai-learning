# ADR 0004: Record triage usage behind a replaceable interface

- Status: Accepted
- Date: 2026-08-18

## Context

Ticket triage needs enough operational history to compare providers, understand
retries, and estimate later evaluation cost. Storing ticket subject, body, or
model-generated triage content would add privacy and retention concerns that are
not needed for those tasks. Week 2 also intentionally avoids introducing a
database before the persistence lessons in Week 3.

Application code should not depend directly on a process-memory collection. The
same route must be able to use a durable Postgres implementation later without
changing its provider or response contracts.

## Decision

Define an async `UsageRecorder` interface and inject one recorder into each
FastAPI application. The Week 2 implementation keeps a bounded deque of 1,000
records by default, with a configurable maximum between 1 and 10,000.

Record one aggregate event for every triage request that reaches the provider
boundary and then succeeds or fails. Each event contains only:

- application request ID;
- operation name;
- provider and allowlisted model;
- success or failure outcome;
- total duration across attempts and backoff;
- token counts returned by a successful provider response;
- total attempt count;
- a normalized provider error kind on failure; and
- a timezone-aware recording timestamp.

The schema has no field for ticket ID, subject, body, channel, prompt, triage
output, provider response ID, raw exception, or API key. Failed calls store token
counts as unknown rather than zero because the application cannot infer billing
from an error. After retries, successful token counts describe the final
successful response only; a failed attempt may not expose usage.

Treat the recorder as optional operational telemetry, not billing or audit data.
If recording fails, log only the safe application request ID and operation, then
preserve the original API result.

Do not expose the in-memory records through a public HTTP endpoint. Tests access
the concrete recorder through dependency injection.

## Consequences

- Triage success, expected provider failures, deadline failures, and unexpected
  provider failures share one provider-neutral metadata contract.
- Unit and API tests can inspect usage without paid model calls or a database.
- Capacity is bounded, and concurrent writes within one process are protected.
- Records disappear on restart or redeploy, differ between processes, and are
  unavailable for durable reporting, reconciliation, or billing.
- Validation failures and unsupported provider/model requests never reach the
  provider boundary and therefore create no usage record.
- Cancellation is propagated and is not retained in this first recorder slice.
- Week 3 can implement the same interface with Postgres and migrations while
  preserving the triage route contract.
