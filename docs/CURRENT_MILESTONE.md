# Current milestone: Week 4 RAG Quality Lab

Last updated: 2026-09-27

Status: Objective 4.1a human checkpoint merged in
[PR #32](https://github.com/vedvasa/ai-learning/pull/32) at merge commit
`84ec22b`. The first objective 4.1b increment adds the provider-free retrieval
scorer on `codex/week4-retrieval-evaluator`, starting from `492d7e9`.
Dataset expansion and the measured vector baseline remain incomplete.

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

## Completed objective: 4.1a golden dataset foundation and human checkpoint

The provider-free foundation was merged in
[PR #31](https://github.com/vedvasa/ai-learning/pull/31):

- a separate strict Week 4 retrieval schema defines fictional tenant/user
  context, version-and-content-hash-pinned document references, key answer
  facts, abstention, six categories, difficulty, adversarial notes, and closed
  non-personal provenance;
- validation rejects duplicate cases, missing category coverage, missing or
  stale corpus references, cross-tenant references, and expected documents
  outside the user's visibility scope;
- the canonical dataset hash is computed only from strict validated data;
- `datasets/rag-evaluation/week4_human_labels.json` contains exactly ten
  sequential, project-owner-authored human labels;
- `rag-golden-dataset` validates the dataset and prints a content-free corpus
  reference manifest, while `--require-complete` verifies that all ten labels
  form a valid human-authored dataset; and
- isolated fixtures are marked `contract_test` / `synthetic_test`, cannot be
  accepted as golden data, and exercise the completed form deterministically.

ADR 0015 records the provenance, privacy, staleness, and hashing decisions. The
exact review workflow is in `docs/DATABASE_DEVELOPMENT.md`.

### Completed human checkpoint

The project owner authored and reviewed the first ten labels from the fictional
corpus. The checkpoint contains two direct-fact, two multi-document, one
ambiguous, two unanswerable, two adversarial, and one privacy-boundary case, so
all six required categories are represented. Every label uses non-personal
`human` / `project_owner` provenance.

Validate the preserved checkpoint with:

```bash
uv sync --locked --no-editable --reinstall-package ai-learning
uv run --no-sync rag-golden-dataset --require-complete
```

The canonical completed dataset SHA-256 is
`092042662d3d2b5e641d70a26f8f241a02344471dd05b60df14462a22b7b3418`.
Later work must preserve these ten labels unchanged. Do not begin
model-assisted labeling or create the remaining 30 cases until objective 4.1b
agrees on labeling provenance and review. Paid vector baselines and remote
database writes still require separate explicit approval.

### Provider-free verification on 2026-09-23

- `uv sync --locked --no-editable` succeeded.
- `uv run --no-sync pytest` passed: 224 passed and 6 local database tests
  skipped because no disposable Supabase stack was running.
- The triage dataset retained canonical SHA-256
  `334f962322f5845b23c18c19e4ae5e7b83682f723818512d40d8d7a104a52c63`.
- The unchanged Week 3 RAG dataset retained its recorded canonical SHA-256
  `7cd6be7d6af670adf4b9accab489d9cb1bcb154561cce61339c2a4dfb3e3d775`.
- The completed Week 4 dataset validated as 10/10 complete with canonical
  dataset SHA-256
  `092042662d3d2b5e641d70a26f8f241a02344471dd05b60df14462a22b7b3418`.
- `docker build --tag ai-learning:local .` and
  `sh scripts/smoke-container.sh ai-learning:local` passed, including all three
  offline dataset validators inside the production image.
- `git diff --check` passed. No application runtime, dependency, database, or
  deployment behavior changed in this checkpoint.

## Current objective: 4.1b retrieval evaluator foundation

The first increment provides:

- `rag-retrieval-evaluation --validate-only` to check the unchanged human
  checkpoint and corpus without settings, provider clients, or database access;
- `--minimum-cases 40` as a separate completion gate (currently fails as
  expected because the preserved dataset contains ten cases);
- strict saved-ranking inputs pinned to the dataset and corpus hashes, with
  explicit synthetic versus recorded evidence and retrieval configuration;
- document hit@k, macro document recall@k, MRR@k over the original ranked
  chunks, category breakdowns, failures, leakage, source timings, and tokens;
- deterministic aggregate JSON/Markdown reports under ignored `artifacts/`;
- compatible-run comparisons and a test proving that removing relevant
  evidence fails the scorer's regression gate; and
- CI and production-container validation for the new offline command.

ADR 0016 defines scoring, scope enforcement, replay provenance, and limitations.
The synthetic ranking fixture tests the evaluator; it is not a measured vector
baseline. Replay does not execute SQL, embeddings, or the chunker and cannot
substitute for the later real search-regression gate. No human labels, corpus,
runtime retrieval, database schema, or deployment behavior changed.

### Provider-free verification on 2026-09-27

- Locked non-editable installation passed; no dependency or lockfile changes.
- Full local suite: 258 passed, 6 local database tests skipped because the
  disposable Supabase stack was not running.
- All three existing offline dataset validators passed with their recorded
  hashes unchanged, including the ten-label human checkpoint.
- The new validator and synthetic replay/comparison commands passed; reports
  were generated only in ignored `artifacts/`.
- The local production image built and its smoke test passed, including the
  new evaluator's provider-free validation command.
- `git diff --check` passed. No paid calls or hosted mutations were performed.

### Next implementation and review decisions

1. Agree on the remaining thirty labels' authorship and review workflow. A
   proposed workflow is three model-assisted batches of ten, with project-owner
   review before any draft is accepted as golden data. Drafting is not yet
   authorized or performed in this increment. Preserve the original file;
   an expanded worksheet must contain the exact first ten labels.
2. Choose the final category/difficulty balance. A possible 40-case mix is
   12 direct-fact, 8 multi-document, and 5 each of ambiguous, unanswerable,
   adversarial, and privacy-boundary cases; this is a proposal, not a new
   schema requirement. Include harder cases beyond the current easy/medium set.
3. Add an explicit capture and re-execution path for real vector evidence,
   including query and corpus vectors, actual chunk identities, configuration,
   and source timings. Use the disposable local database for search tests and
   make telemetry writes explicit. Paid calls and hosted writes require
   separate approval.
4. Complete at least 40 reviewed cases, capture the exact vector baseline,
   choose thresholds using the evidence, and document limitations before 4.2.

The current command can replay saved rankings only. The remaining work must not
be reported as complete just because its synthetic scoring fixture passes.

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

## Next and later objectives

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

## Suggested opening prompt for continuing objective 4.1b

The reusable opening and closing templates live in
[`CODEX_SESSION_PROMPTS.md`](CODEX_SESSION_PROMPTS.md). For objective 4.1b, use
this ready-to-copy version:

```text
Continue objective 4.1b of the ai-learning project after the provider-free
retrieval scorer foundation. The ten human labels are frozen; the 40-case
dataset and measured vector baseline are still pending.

Read AGENTS.md, docs/CURRENT_MILESTONE.md, the Week 4 section of
PRODUCTION_AI_SELF_LEARNING_GUIDE.md, LEARNING_PROGRESS_TRACKER.md, relevant
ADRs, and recent Git history.

Before making changes:
1. Run rag-golden-dataset --require-complete and record the canonical hash.
2. Verify that the first ten slots retain human-authored provenance, but do not
   create, rewrite, or silently repair any of those labels.
3. Inspect the scorer, ADR 0016, and retrieval code; distinguish replayed
   synthetic metrics from actual measured vector quality.
4. Agree on labeling/review and propose the next small increment for dataset
   completion, vector capture, local re-execution, and the measured baseline.
5. Ask before model-assisted labeling, paid calls, database writes, remote
   actions, destructive actions, or cloud changes.

Never read any secret value. If secret setup becomes necessary, give me exact
commands that use hidden input so I enter the value without exposing it to you,
shell history, logs, or Git. Never commit secrets to GitHub.
```
