# Current milestone: Week 4 RAG Quality Lab

Last updated: 2026-08-30

Status: Ready to start in a fresh Codex task.

Starting release: `v0.3.0` at commit `1dba96aed7cc7aec3a0d50609b9d42b71d591b31`

Live baseline: [KnowledgeDesk on Cloud Run](https://ai-learning-3y5vyfqynq-uw.a.run.app/)

## Week 4 goal

Turn the Week 3 citation-grounded RAG application into an evaluated retrieval
system. Compare vector, keyword, and hybrid retrieval under a fixed labeled
dataset; add an index only after measuring the exact baseline; and make quality
regressions visible and reproducible.

The detailed requirements remain in the
[Week 4 guide](../PRODUCTION_AI_SELF_LEARNING_GUIDE.md#week-4--rag-quality-lab-measure-before-adding-complexity).

## Baseline inherited from Week 3

- 21 fictional Markdown support documents are versioned and ingested into a
  private Supabase `knowledge` schema with pgvector.
- Ingestion is explicit, content-addressed, idempotent, and model/dimension
  aware.
- Retrieval is an exact cosine scan over active, public, server-tenant-scoped
  chunks using `text-embedding-3-small` vectors with 1,536 dimensions.
- Grounded answers validate every citation before returning and persist the
  successful exchange atomically.
- The existing 20-question set contains 12 answerable, 4 ambiguous, and 4
  unanswerable cases.
- The recorded vector-only baseline completed 20/20 cases with 100% answerable
  retrieval hits at 5, 100% citation validity, 75% ambiguous abstention, 100%
  unanswerable abstention, and zero forbidden-document leakage.
- The Week 3 Cloud Run revision is live, but the public learning service still
  has no authentication or rate limit.

See `docs/evidence/week-3/README.md` and ADRs 0008 through 0014 for evidence and
the reasoning behind the current design.

## Current objective: 4.1 golden retrieval dataset and baseline

Create a versioned retrieval-focused golden dataset with at least 40 examples
and a reproducible, provider-free vector-only evaluation baseline.

This objective should include:

- a strict dataset schema containing the question, tenant/user context,
  expected relevant document IDs, key answer facts, abstention expectation,
  category, difficulty, and adversarial notes;
- the first 10 labels authored by the user before any model-assisted labeling;
- validation for document references, category coverage, privacy, and canonical
  dataset hashing;
- retrieval-only metrics including hit rate at k, recall at k, mean reciprocal
  rank, latency, and results by category;
- machine-readable aggregate JSON and a human-readable Markdown summary;
- a checked-in vector-only baseline and regression comparison;
- fake or recorded embeddings/results for deterministic CI where appropriate;
  and
- no keyword, hybrid, reranking, or HNSW implementation yet.

Codex may scaffold the schema and provide a labeling worksheet, but must not
author the first 10 human-reference labels on the user's behalf.

## Planned later objectives

1. **4.2 Keyword retrieval:** add Postgres full-text search and measure it
   independently against the same dataset.
2. **4.3 Hybrid retrieval:** implement reciprocal rank fusion, then accept or
   reject it using a chosen metric and failure-case review.
3. **4.4 Metadata and reranking experiments:** change one variable at a time;
   keep only evidence-backed improvements.
4. **4.5 Index experiment:** add HNSW in a migration with the matching cosine
   operator class, inspect query plans, and document small-corpus limitations.
5. **4.6 Quality gate and release:** produce JSON/Markdown reports, fail CI on a
   deliberate regression, expose app and dataset versions, deploy only after
   explicit approval, and record Week 4 evidence.

## Open decisions

- Exact golden-dataset category balance beyond the required first 10 human
  labels.
- Whether deterministic CI should use committed query vectors, recorded ranked
  results, or an injected fake retriever at each evaluation layer.
- Initial regression thresholds after the 40-case vector baseline is measured.
- Whether the optional failure-case dashboard belongs in the core Week 4 scope
  or remains a stretch goal.
- Whether reranking produces enough measured value to justify another model or
  dependency.

Resolve these through a focused plan and evidence; do not preselect tools merely
because they are popular.

## Safety and approval boundary

- Use fictional questions and documents only.
- Never read secret values; follow the secret-handling rules in `AGENTS.md`.
- Start with provider-free validation and the disposable local Supabase stack.
- Paid embeddings, model-assisted labeling, remote database writes, cloud
  deployment, and traffic changes require separate explicit user approval.
- A Week 4 code PR never authorizes a Cloud Run deployment.

## Objective 4.1 definition of done

- The dataset schema and at least 40 valid cases are committed.
- The first 10 human labels are identifiable as user-authored provenance without
  storing personal information.
- One command reproduces the provider-free vector-only evaluation.
- Hit rate, recall, reciprocal rank, latency, and category metrics are reported.
- Tests reject malformed, leaking, or stale document references.
- The baseline and limitations are documented.
- Relevant tests and CI pass.
- The handoff identifies the exact starting point for objective 4.2.

## Suggested opening prompt for the next Codex task

The reusable opening and closing templates live in
[`CODEX_SESSION_PROMPTS.md`](CODEX_SESSION_PROMPTS.md). For objective 4.1, use
this ready-to-copy version:

```text
We are starting objective 4.1 of the ai-learning project.

Read AGENTS.md, docs/CURRENT_MILESTONE.md, the Week 4 section of
PRODUCTION_AI_SELF_LEARNING_GUIDE.md, LEARNING_PROGRESS_TRACKER.md, relevant
ADRs, and recent Git history.

Before making changes:
1. Inspect the current dataset, retrieval implementation, and evaluation code.
2. Explain the Week 3 baseline that objective 4.1 depends on.
3. Identify discrepancies between the milestone and current code.
4. Propose a PR-sized implementation sequence.
5. Separate provider-free work from paid, remote, destructive, or cloud actions.

Never read any secret value. If secret setup becomes necessary, give me exact
commands that use hidden input so I enter the value without exposing it to you,
shell history, logs, or Git. Never commit secrets to GitHub.
```
