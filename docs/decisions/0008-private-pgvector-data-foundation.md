# ADR 0008: Build RAG storage in a private, migrated Postgres schema

## Status

Accepted on 2026-08-24.

## Context

Week 3 turns KnowledgeDesk into a citation-grounded RAG application. The system
needs durable source versions, chunks, embeddings, ingestion state,
conversations, and privacy-aware model telemetry. Building those tables by hand
in the hosted dashboard would make the database difficult to recreate, review,
test, and promote safely.

The browser does not need direct database access. The FastAPI backend will use
a server-side Postgres connection, and the hosted project's Data API is
disabled. Approximate-nearest-neighbor indexes also add tuning choices that the
small Week 3 corpus cannot yet justify.

## Decision

- Store application data under a dedicated `knowledge` schema rather than an
  API-exposed schema.
- Revoke schema access from `PUBLIC`, `anon`, and `authenticated`; browser
  requests must cross the FastAPI boundary.
- Define every schema change as a committed Supabase migration and test it
  locally with pgTAP before applying it to a hosted project.
- Model documents, immutable versions, chunks, ingestion jobs, conversations,
  messages, and model calls separately.
- Carry `tenant_id` through document versions, chunks, and conversations, with
  composite foreign keys that reject cross-tenant relationships.
- Use content hashes and uniqueness constraints to support idempotent
  ingestion and exactly one active version per document.
- Store embeddings in an explicit `vector(1536)` column. A populated embedding
  must identify `text-embedding-3-small` and dimension `1536`; changing that
  contract requires a migration.
- Begin with exact vector search. Week 4 will measure retrieval before choosing
  HNSW or IVFFlat parameters.
- Keep prompts, retrieved context, and model output out of `model_calls`.

## Consequences

- A clean local database can be rebuilt from Git without using hosted state as
  undocumented configuration.
- The initial schema supports ingestion and retrieval without committing to a
  premature approximate index.
- Direct browser database access is unavailable by design. Authenticated
  end-user access and RLS policies remain a later multi-tenancy lesson.
- The 1,536-dimension column cannot accept a differently sized embedding. A
  future model or dimension change needs a new column or migration and an
  explicit re-embedding plan.
- The backend database credential remains sensitive and must be stored in local
  `.env` and Google Secret Manager, never in Git or frontend code.

## Deferred work

This decision does not link or modify the hosted Supabase project, ingest a
corpus, call an embeddings API, add a retrieval function, or connect FastAPI to
Postgres. Those are separate reviewable increments.
