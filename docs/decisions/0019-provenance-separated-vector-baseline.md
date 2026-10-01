# ADR 0019: Separate evaluation groups and replay captured vectors locally

## Status

Accepted for the objective 4.1b implementation on 2026-09-30. Actual paid
capture and the measured baseline require separate operator approval.

## Context

The working set contains 16 reviewed and 24 provisional cases. The original
scorer accepts golden worksheets and saved rankings only; it cannot exercise
search or reveal defects in the SQL/chunker path. The deployed retriever also
records telemetry, which is unnecessary for an isolated learning experiment.

## Decision

- Add an explicit working-set contract, separate from golden data. Compose it
  from the reviewed worksheet plus draft IDs not already accepted. A reviewed
  copy must match the draft's content; only provenance may differ. Preserve
  the first ten exactly and hash the complete composition including review
  status. Keep the original ten-case command and synthetic fixture compatible.
- Report metrics and category breakdowns for `reviewed` and `provisional`
  separately. Combined operational counts remain available, but combined
  relevance averages are null whenever provisional cases are present.
  Reviewed relevance regression controls acceptance; provisional deltas are
  diagnostic. Failures and unauthorized results fail either group.
- Add `rag-vector-baseline --plan`, `--capture-to`, and `--execute`. Planning
  uses the real chunker and tokenizer without providers, settings, or a
  database. The container caches the public tokenizer asset during its build
  and tests planning with network access disabled.
- Capture corpus chunks and questions with the existing application-owned
  embedding client in batches of 64, with retries disabled. Require an
  explicit spend flag, a preflight input-token budget, a clean source commit,
  and hidden interactive API-key entry. Never load `.env` or display/store
  credentials. Refuse to overwrite a capture. A failed capture may consume
  part of the approved budget; there is no automatic retry.
- Store strict vectors and input hashes, document/chunk identities, query
  IDs, configuration, source revision, and aggregate capture usage. Do not
  store text or raw errors. Validate finite nonzero float32-compatible vectors,
  dimension/count/identity coverage, source pins, and reconstructed chunk
  hashes before database work. Synthetic vectors remain explicitly synthetic.
- Execute on the fixed loopback Supabase development endpoint. Create three
  temporary tables from the migrated `knowledge` tables, populate only those
  tables, and call the same search-query implementation as the application.
  The only namespace choices are `knowledge` for the application and `pg_temp`
  for evaluation. Always roll back and close the evaluation connection; no
  persistent ingestion, conversation, or telemetry writes are made.
- Use deterministic temporary UUIDs for stable tie ordering, while retaining
  the runtime query's cosine distance, active-version/model checks, tenant,
  visibility, threshold, and original chunk top-k semantics. Record actual
  local search timing, never substitute replay time for production latency.
- Bind ranked results and comparisons to the captured-vector hash as well as
  the dataset, corpus, configuration, evidence kind, and execution method.
  Preserve capture-wide usage separately: batched embedding timing/tokens
  cannot be honestly split into per-query values. Local re-execution makes
  zero provider calls. Report schema 1.1 adds these fields and group metrics.

## Consequences and limits

One paid capture enables repeatable provider-free executions of the real SQL
over frozen vectors and current chunk reconstruction. CI uses hand-assigned
synthetic vectors to exercise execution, isolation, and deterministic ranking;
their scores do not measure embedding quality. A saved-ranking replay remains
distinct from a new local search execution.

Temporary-table latency is a local diagnostic, not hosted-service latency or
scale evidence. Temporary UUIDs can resolve exact ties differently from a
previous production ingestion. A changed chunker that changes chunk identity
fails capture validation; evaluating its new semantic quality needs new
embeddings, not a claim that stale vectors represent the new chunks.

The reference set has only seven answerable relevance cases. The provisional
set is useful for finding failures but is not independent ground truth. The
second tenant is empty, and retrieval alone does not establish correct answer
abstention or instruction resistance. No keyword/hybrid retrieval, index,
reranker, UI feature, cloud operation, or deployment is added here.
