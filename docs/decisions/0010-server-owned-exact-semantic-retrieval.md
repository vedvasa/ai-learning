# ADR 0010: Keep initial semantic retrieval exact and server-scoped

## Status

Accepted.

## Context

The Week 3 corpus now has active, embedded chunks in local and hosted Postgres.
The next boundary must turn a question into ranked evidence without allowing an
unauthenticated caller to select another tenant, expose non-public documents,
or silently query vectors produced by a different embedding contract.

The corpus has only 63 chunks. Adding an approximate-nearest-neighbor index now
would introduce tuning choices without a representative scale or retrieval
evaluation.

## Decision

- Add `POST /api/retrieve` as a retrieval-only endpoint. It returns ranked
  evidence and source metadata; it does not generate an answer yet.
- Accept only a validated question and a result count bounded from 1 through
  10. The request cannot supply a tenant or visibility filter.
- Select `RAG_TENANT_ID` on the backend and permit only `public` documents until
  authentication provides a trustworthy authorization context.
- Embed each question once with the same `text-embedding-3-small`, 1,536-
  dimension contract used by ingestion.
- Search only active document versions whose stored model and dimension match
  the query. Apply tenant and visibility filters inside the SQL query, before
  ranking or limiting results.
- Use exact cosine distance through pgvector's `<=>` operator and expose
  `1 - cosine distance` as the similarity score. Do not add HNSW or IVFFlat in
  this increment.
- Keep `RAG_RETRIEVAL_MIN_SIMILARITY=0` as a transparent provisional floor.
  Week 4's labeled retrieval evaluation must calibrate it before it is treated
  as a quality threshold.
- Execute the synchronous embedding SDK and psycopg work outside FastAPI's
  event loop. Record query-embedding telemetry without storing the question or
  retrieved content; telemetry failure must not discard an otherwise completed
  search.
- Use fake embeddings in ordinary tests and deterministic vectors in the local
  Postgres integration test. CI never makes a paid provider call.

## Consequences

- Cross-tenant, internal-document, inactive-version, model-mismatch, and
  below-threshold records are excluded by the repository query.
- A public API caller cannot override the server's data scope.
- Results contain stable chunk and document-version identifiers that the next
  increment can use for verifiable citations.
- Exact search is intentionally sufficient for the small corpus and gives Week
  4 a baseline against which an approximate index can be measured.
- Sending a live retrieval request creates a paid OpenAI embedding call and a
  best-effort `query_embedding` telemetry row.

## Out of scope

This decision does not add answer generation, conversation persistence,
authentication, hybrid search, reranking, an approximate index, a user
interface, a production deployment, or any hosted database change.
