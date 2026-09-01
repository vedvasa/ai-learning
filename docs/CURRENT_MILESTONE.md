# Current milestone: Week 4 RAG Quality Lab

Last updated: 2026-09-01

Status: Objective 4.1a foundation implemented; waiting for the project owner to
author the first ten golden labels.

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

## Current objective: 4.1a golden dataset foundation and human checkpoint

The provider-free foundation is implemented on
`codex/objective-4-1a-golden-foundation` (PR not yet opened):

- a separate strict Week 4 retrieval schema defines fictional tenant/user
  context, version-and-content-hash-pinned document references, key answer
  facts, abstention, six categories, difficulty, adversarial notes, and closed
  non-personal provenance;
- validation rejects duplicate cases, missing category coverage, missing or
  stale corpus references, cross-tenant references, and expected documents
  outside the user's visibility scope;
- the canonical dataset hash is computed only from strict validated data;
- `datasets/rag-evaluation/week4_human_labels.json` contains exactly ten
  sequential slots whose labels are all intentionally `null`;
- `rag-golden-dataset` validates the scaffold and prints a content-free corpus
  reference manifest, while `--require-complete` fails until all ten labels form
  a valid human-authored dataset; and
- isolated fixtures are marked `contract_test` / `synthetic_test`, cannot be
  accepted as golden data, and exercise the completed form deterministically.

ADR 0015 records the provenance, privacy, staleness, and hashing decisions. The
exact human-only labeling workflow is in `docs/DATABASE_DEVELOPMENT.md`.

### Required human checkpoint

The project owner must now author all ten blank labels directly from the
fictional corpus, without model assistance. Start with:

```bash
uv sync --locked --no-editable --reinstall-package ai-learning
uv run --no-sync rag-golden-dataset
uv run --no-sync rag-golden-dataset --print-corpus-manifest
```

After editing the worksheet, run:

```bash
uv run --no-sync rag-golden-dataset --require-complete
```

Stop after that command reports ten valid labels and a canonical dataset hash.
Do not begin model-assisted labeling, create the remaining 30 cases, capture a
paid vector baseline, or implement retrieval experiments in this increment.

### Provider-free verification on 2026-09-01

- `uv sync --locked --no-editable --reinstall-package ai-learning` succeeded.
- `uv run --no-sync pytest` passed: 224 passed and 6 local database tests
  skipped because no disposable Supabase stack was running.
- The triage dataset retained canonical SHA-256
  `334f962322f5845b23c18c19e4ae5e7b83682f723818512d40d8d7a104a52c63`.
- The unchanged Week 3 RAG dataset retained its recorded canonical SHA-256
  `7cd6be7d6af670adf4b9accab489d9cb1bcb154561cce61339c2a4dfb3e3d775`.
- The blank Week 4 worksheet validated as 0/10 complete with worksheet SHA-256
  `b8c51ea99a6c0f2d87836d0f5c3b4b7c08484bdee456eda9f579a7842dd0eb04`.
- Shell syntax checks passed. Container build/smoke was not run because the
  local Docker daemon was unavailable.

## Broader objective: 4.1 golden retrieval dataset and baseline

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

1. **4.1b Dataset completion and vector baseline:** after the human checkpoint,
   preserve the first ten labels, agree on how the remaining 30 will be labeled,
   add retrieval-only metrics/reports and deterministic CI, then capture the
   exact vector baseline only with separate approval for paid calls or database
   writes.
2. **4.2 Keyword retrieval:** add Postgres full-text search and measure it
   independently against the same dataset.
3. **4.3 Hybrid retrieval:** implement reciprocal rank fusion, then accept or
   reject it using a chosen metric and failure-case review.
4. **4.4 Metadata and reranking experiments:** change one variable at a time;
   keep only evidence-backed improvements.
5. **4.5 Index experiment:** add HNSW in a migration with the matching cosine
   operator class, inspect query plans, and document small-corpus limitations.
6. **4.6 Quality gate and release:** produce JSON/Markdown reports, fail CI on a
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

## Suggested opening prompt after the human checkpoint

The reusable opening and closing templates live in
[`CODEX_SESSION_PROMPTS.md`](CODEX_SESSION_PROMPTS.md). For objective 4.1b, use
this ready-to-copy version:

```text
We are starting objective 4.1b of the ai-learning project after I authored the
first ten Week 4 golden retrieval labels.

Read AGENTS.md, docs/CURRENT_MILESTONE.md, the Week 4 section of
PRODUCTION_AI_SELF_LEARNING_GUIDE.md, LEARNING_PROGRESS_TRACKER.md, relevant
ADRs, and recent Git history.

Before making changes:
1. Run rag-golden-dataset --require-complete and record the canonical hash.
2. Verify that the first ten slots retain human-authored provenance, but do not
   create, rewrite, or silently repair any of those labels.
3. Inspect retrieval and evaluation code and explain the Week 3 baseline.
4. Propose a PR-sized sequence for reaching 40 cases, retrieval-only metrics,
   deterministic CI, JSON/Markdown reports, and the exact vector baseline.
5. Ask before model-assisted labeling, paid calls, database writes, remote
   actions, destructive actions, or cloud changes.

Never read any secret value. If secret setup becomes necessary, give me exact
commands that use hidden input so I enter the value without exposing it to you,
shell history, logs, or Git. Never commit secrets to GitHub.
```
