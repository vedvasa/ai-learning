# ADR 0009: Ingest documents explicitly with content-addressed work

## Status

Accepted

## Context

The private Week 3 schema exists, but migrations should not contain changing
knowledge content and the web process must not create embeddings every time it
starts. Ingestion uses a paid external API, can fail partway through a corpus,
and must not replace a valid active document version with incomplete data.

## Decision

- Keep 21 fictional support documents under `datasets/knowledge-base/` with
  strict TOML front matter for document identity, tenant, visibility, version,
  source, and update time.
- Normalize Markdown and hash the normalized document before other work.
- Split at Markdown heading and paragraph boundaries with a 500-token maximum.
  Do not add overlap to this small, section-oriented corpus until retrieval
  evaluation demonstrates that it is useful.
- Count tokens with the tokenizer for `text-embedding-3-small` and request
  explicit 1,536-dimensional vectors from the embeddings endpoint.
- Batch missing embeddings, disable hidden SDK retries, and require a command
  flag acknowledging potential spend.
- Look up cached vectors by tenant, chunk content hash, model, and dimension.
- Record a job before work begins. Mark unchanged documents `skipped` without
  calling the provider.
- Insert a new version and all chunks in one Postgres transaction. Make the new
  version active only after every chunk is stored; a failed transaction leaves
  the earlier active version untouched.
- Store only safe model-call telemetry and failure kinds. Do not log source
  text, database URLs, API keys, or raw provider errors.
- Refuse remote database writes unless the operator provides a separate
  `--allow-remote-database` flag.
- Use fake embeddings in automated tests. Live provider calls are always a
  deliberate developer action outside CI.

## Consequences

- Local and hosted ingestion use the same command and database contract.
- Reprocessing unchanged content is cheap and produces an auditable skipped
  job rather than duplicate active chunks.
- A changed document must increment its declared version; conflicting version
  numbers fail closed.
- The initial chunking strategy is intentionally simple. Week 4 retrieval
  evaluation can justify overlap, different boundaries, or index changes.

## Out of scope

This decision does not add semantic retrieval, question answering, automatic
scheduled ingestion, a Cloud Run Job, or a production release.
