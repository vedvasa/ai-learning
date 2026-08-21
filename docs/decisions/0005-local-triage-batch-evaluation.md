# ADR 0005: Evaluate triage through a guarded local batch command

- Status: Accepted
- Date: 2026-08-18

## Context

Manual browser tests show that ticket triage works but do not measure whether it
consistently matches a labeled dataset. Week 2 needs a repeatable way to compare
providers and models across schema validity, classification quality, latency,
usage, and estimated cost.

An evaluation run can make many billable provider calls. Reports can also become
a second copy of ticket text or model output if their boundary is not deliberate.
CI must remain deterministic and must never depend on provider credentials.

## Decision

Commit 30 fictional, strictly validated ticket cases under
`datasets/ticket-triage`. Each case includes a `SupportTicket` and three expected
labels: category, priority, and whether human review is required. Sort cases by
ticket ID and hash their canonical validated representation so a report identifies
the exact dataset state it measured.

Add a `triage-batch` command with two explicit execution modes:

- `--validate-only` validates, de-duplicates, bounds, and hashes up to 100 local
  cases without constructing a provider client;
- `--allow-paid-calls` acknowledges that evaluation can create billable calls.

Actual runs use the same direct provider adapters and application-owned retry
policy as the API. Evaluate six cases with concurrency one by default. Allow an
explicit maximum of 100 cases and concurrency of 10.

Write one atomic, aggregate-only JSON report. Include dataset hash, provider,
model, run configuration, schema-valid response rate, category and priority
accuracy, human-review recall, p50/p95 successful-call duration, token totals and
means, attempts, normalized failure counts, and optional cost estimates. Do not
include ticket IDs, ticket text, generated summaries, rationales, provider
response IDs, raw errors, or credentials.

Count failed cases as incorrect in category and priority accuracy. Count them as
false negatives when human review was expected. Treat only provider results that
have already passed the strict Pydantic output contract as schema-valid.

Require both current input and output prices when cost estimation is requested;
do not hardcode model pricing. Mark cost as a lower bound if any case failed or
retried because failed attempts may not expose their token usage.

Use exit code 0 when every provider-bound case returned valid output, 1 when one
or more provider calls failed, and 2 for invalid input, configuration, or missing
paid-call acknowledgement.

## Consequences

- A local run can compare a provider or model using reproducible aggregate
  metrics without persisting ticket or generated text in the report.
- The default six-case limit and serial execution reduce accidental spend; a full
  30-case run remains an explicit choice.
- CI exercises loaders, metrics, retries, concurrency, privacy, and the CLI using
  fake providers, so tests make no external model calls.
- Prices are manual run inputs and must be checked against the provider's current
  pricing page before recording cost evidence.
- Successful token counts exclude usage hidden by failed attempts, so some cost
  estimates are lower bounds.
- Aggregate-only reports are safer but cannot diagnose an individual mismatch;
  detailed error analysis must be performed deliberately on fictional cases.
- This is application-level concurrent evaluation, not a provider asynchronous
  batch API; comparing those APIs remains a stretch goal.
