# Current milestone: Week 4 RAG Quality Lab

Last updated: 2026-09-30

Status: Objective 4.1a human checkpoint merged in
[PR #32](https://github.com/vedvasa/ai-learning/pull/32) at merge commit
`84ec22b`. The provider-free retrieval scorer merged in
[PR #34](https://github.com/vedvasa/ai-learning/pull/34) at `ee7e3d1`.
[PR #35](https://github.com/vedvasa/ai-learning/pull/35) now includes thirty
model-assisted source cases and the owner's review of six selected judgments.
The working set is **16 reviewed cases plus 24 provisional cases**; the original
ten remain unchanged. The follow-up on `codex/week4-vector-baseline` implements
separate group scoring, explicit vector capture, and provider-free local SQL
re-execution. Real paid capture and the measured baseline remain pending.
PR #35 is still open; the follow-up is stacked on its branch. No batch review
or deployment is required before the experiment.

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
Later work must preserve these ten labels unchanged. Model-assisted drafting
and the focused review policy are now authorized; see the current objective
and ADR 0018. Paid vector baselines and remote database writes still require
separate explicit approval.

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

## Completed increment: 4.1b retrieval evaluator foundation

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

## Current objective: 4.1b separate evaluation groups and vector baseline

The project owner approved a lighter review workflow on 2026-09-29: Codex
checks all thirty model-assisted cases against the sources, the owner reviews
six instructive judgments, and the rest remain provisional. ADR 0018 updates
the earlier blanket human-review requirement. The guide now permits a 40-case
working set with separately reported human-reviewed and provisional results.

### Completed source check and focused review

- Codex read all 21 corpus documents and checked all thirty proposed cases;
  no factual corrections were identified. The [source-check record](../datasets/rag-evaluation/week4_drafts/source-check.md)
  documents the findings and limitations. This check is not human validation.
- The owner reviewed source slots **15, 19, 26, 27, 30, and 40**, responding
  “These six judgments look right” to the [short review](../datasets/rag-evaluation/week4_drafts/quick-review.md).
  No further batch-review round is required before preparing experiments.
- `datasets/rag-evaluation/week4_reviewed_labels.json` contains the exact
  original ten followed by those six unchanged labels, with model-assisted
  origin, project-owner review, and date 2026-09-29. Canonical dataset SHA-256:
  `48aebb88f953b10db215146e77b50f2f5e4a44f69692bfd837dc5cb05341baff`.
- The original ten-label file and all three draft JSON files remain unchanged.
  Drafts retain their original unreviewed provenance as snapshots; use case IDs
  to match the six accepted copies to their source slots.
- The working mix remains 12 direct-fact, 8 multi-document, and 5 each of
  ambiguous, unanswerable, adversarial, and privacy-boundary cases. Expected
  references cover all 21 documents. These are coverage counts, not quality
  measurements.

| Evaluation group | Cases | With relevance labels | Abstention cases |
|---|---:|---:|---:|
| Human-reviewed reference | 16 | 7 | 9 |
| Provisional model-assisted | 24 | 17 | 7 |
| Working total | 40 | 24 | 16 |

Compose the working set from the reviewed worksheet plus the draft cases whose
IDs are absent from that worksheet. Do not count the six accepted cases twice,
blend provisional scores into golden quality, or rewrite the frozen checkpoint.
Review status and exact inputs must be pinned in comparisons. Provisional
relevance scores guide diagnosis; human-reference scores drive acceptance.
Execution failures and unauthorized results fail checks in either group.

Validate the package without providers or a database:

```bash
uv run --no-sync rag-retrieval-drafts --check-review-sheets
uv run --no-sync rag-retrieval-evaluation \
  --worksheet datasets/rag-evaluation/week4_reviewed_labels.json --validate-only
```

### Completed implementation: separate groups and vector execution

- `rag-retrieval-evaluation --include-provisional --minimum-cases 40` composes
  the reviewed worksheet and remaining draft IDs, checks accepted copies, and
  pins all label content/provenance. Working-set SHA-256:
  `c0c2ee0f8416a079336560271f9ea0376d74aa32f6ed67c0023e3f3c78806c4a`.
- Reports include separate group/category metrics. Mixed relevance averages
  are omitted; reviewed relevance regressions gate acceptance, provisional
  deltas are diagnostic, and errors/leakage fail either group.
- `rag-vector-baseline --plan` reports 21 documents, 63 chunks, 40 questions,
  approximately 3,791 input tokens and at most two embedding API requests.
- `--capture-to` requires explicit spend acknowledgment, a token allowance,
  clean committed source, and hidden operator API-key entry. It makes no DB
  calls, stores no credential or raw text, and does not load `.env`.
- `--execute` validates captured vectors against the current labels/corpus/
  chunker and runs the application's exact SQL against temporary local
  Supabase tables. It rolls back and closes the connection, with no persistent
  ingestion, conversation, or telemetry writes. Comparisons pin the capture
  hash and distinguish SQL execution from saved-ranking replay.
- The production image caches the public tokenizer asset and smoke-tests
  planning with network access disabled. CI includes synthetic-vector local
  SQL integration tests; those scores do not measure real embedding quality.

ADR 0019 records the execution and evidence boundaries. The exact paid and
provider-free commands are in `docs/DATABASE_DEVELOPMENT.md`. No real capture
has yet been executed; neither a working-set count nor synthetic scores
complete objective 4.1b.

### Verification on 2026-09-29

- Locked non-editable installation passed. After caching public tokenizer data,
  the full provider-free suite passed: **281 passed, 6 skipped**. Skips require
  the disposable local database; no remote database was substituted.
- Original dataset hashes and all three draft JSON files are unchanged. The
  new 16-case set validates against the corpus and frozen human checkpoint.
  A regression test checks that exactly the approved six were copied, with
  unchanged content and honest review provenance.
- All offline dataset checks and the original synthetic replay passed. No
  real vector quality is inferred from that replay.
- Local image build stalled while resolving the pinned Docker frontend image
  from the registry and was canceled; the local smoke test did not run. The PR
  workflow also builds and smoke-tests the production image.
- No paid calls, hosted writes, deployment, or real vector measurement occurred.

### Current verification on 2026-09-30

- Separate-group/scorer tests pass, including reviewed-only regression gates,
  provisional failure/leakage, accepted-draft deduplication, and review-status
  hash changes.
- Local database execution tests pass against disposable Supabase, exercising
  the real search query, authorized internal access, an empty second tenant,
  deterministic ordering, rollback, and unchanged persistent chunk counts.
- Local schema contract tests: 27 passed; schema lint found no errors.
- Local production image build and smoke checks passed, including offline
  vector planning with the network disabled.
- Full provider-free suite: **313 passed, 8 database tests skipped**. All eight
  database integration tests passed separately against local Supabase.
- Original checkpoint, reviewed-set, Week 3, and triage hashes are unchanged.
  No paid calls, hosted writes, deployment, or measured embedding quality has
  been claimed. CI status is attached to the implementation PR.

### Remaining acceptance steps

1. Finish CI on the stacked implementation PR; merge PR #35 first and leave
   merge decisions with the owner. No deployment is necessary.
2. Immediately before the paid step, obtain approval for one capture of the
   current 103 fictional inputs (63 chunks + 40 questions), at most two API
   requests, with a 4,000-input-token preflight limit. The user runs the hidden
   API-key prompt; Codex never reads, requests, or enters the key itself.
3. After capture, run `rag-vector-baseline --execute` against disposable local
   Supabase, repeat the execution with baseline comparison, and inspect misses.
   Record real captured vectors, exact rankings, separate metrics, usage and
   limitations as fictional baseline evidence before proceeding to 4.2.
4. Choose thresholds from evidence. The reviewed relevance denominator is only
   seven answerable cases; provisional results are diagnostic. A changed
   chunker invalidates the old vector mapping and requires its own experiment.

## Broader objective: 4.1 golden retrieval dataset and baseline

Create a versioned retrieval working set with at least 40 examples, a preserved
human-reviewed reference subset, explicitly provisional additional cases, and
a reproducible, provider-free vector-only evaluation baseline. ADR 0018 records
the approved adjustment from forty golden labels to separately reported groups.

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

- How much real captured-vector evidence to commit after the paid run. Current
  CI uses synthetic vectors to execute the shared SQL and saved rankings to
  test scoring; neither is presented as the measured baseline.
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

- At least 40 valid working cases are committed with explicit review status;
  reference and provisional counts and metrics are reported separately.
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
Continue objective 4.1b with 16 reviewed cases and 24 provisional cases.
The original ten are frozen; the owner has reviewed source slots 15, 19, 26,
27, 30, and 40. Separate-group scoring and the vector capture/local execution
workflow are implemented on codex/week4-vector-baseline, stacked on PR #35.
Paid capture and measured evidence remain pending; no more batch review is required.

Read AGENTS.md, docs/CURRENT_MILESTONE.md, the Week 4 section of
PRODUCTION_AI_SELF_LEARNING_GUIDE.md, LEARNING_PROGRESS_TRACKER.md, relevant
ADRs, and recent Git history.

Before making changes:
1. Run rag-golden-dataset --require-complete and record the canonical hash.
2. Verify that the first ten slots retain human-authored provenance, but do not
   create, rewrite, or silently repair any of those labels.
3. Inspect the scorer, ADR 0016, and retrieval code; distinguish replayed
   synthetic metrics from actual measured vector quality.
4. Read ADRs 0018–0019 and the six-case review record. Use the reviewed worksheet
   plus the remaining draft case IDs without duplicating the accepted six.
   Preserve provenance; report human-reference and provisional metrics separately.
5. Validate the capture plan and implementation. Obtain approval immediately
   before paid capture; the user enters any secret at a hidden prompt. Then
   execute and record the baseline locally. Paid calls, hosted
   writes, destructive actions, and cloud changes need separate approval.

Never read any secret value. If secret setup becomes necessary, give me exact
commands that use hidden input so I enter the value without exposing it to you,
shell history, logs, or Git. Never commit secrets to GitHub.
```
