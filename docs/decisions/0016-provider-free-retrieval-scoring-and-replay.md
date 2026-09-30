# ADR 0016: Separate retrieval scoring from vector execution

## Status

Accepted for the first objective 4.1b increment on 2026-09-27.

[ADR 0018](0018-focused-human-review-and-provisional-evaluation.md) updates the
remaining dataset/review plan to permit separately reported provisional
experiments. The current scorer still accepts golden worksheets only.

## Context

The ten human reference labels are complete, but the Week 3 evaluator generates
answers and persists conversations. Reusing it would mix retrieval and answer
quality, make routine checks paid, and hide partial multi-document retrieval
behind a hit-rate score. The semantic retriever also writes embedding telemetry.

The next increment needs deterministic scoring before collecting new vector
evidence or expanding labels through an agreed human-review workflow.

## Decision

- Add a provider-free `rag-retrieval-evaluation` command with explicit
  `--validate-only` and `--results` modes. Neither loads application settings,
  creates provider clients, nor accesses a database. The runtime retriever and
  public API are unchanged.
- Preserve the ten-label file and its canonical hash. Every evaluation dataset
  must retain those exact first ten labels. `--minimum-cases 40` is a separate
  completion check, not a change to the ten-case checkpoint contract.
- Score saved ranked chunk references against document-level relevance labels.
  Top k means the original k chunks, with no deduplication or backfilling before
  ranking. Hit@k asks whether any relevant document occurs. Recall@k counts
  distinct relevant documents divided by the case's expected documents. MRR@k
  uses the rank of the first relevant chunk, or zero if none occurs. Average
  these scores equally across cases with nonempty relevance labels.
- Keep failed answerable cases in relevance denominators as zero. Exclude cases
  without relevant-document labels from these averages and report their result
  counts separately. Returning chunks for an ambiguous or unanswerable question
  does not itself establish incorrect answer abstention.
- Require exactly one outcome per case and reject duplicate chunks, too many
  results, unknown/stale document references, invalid timing values, and
  content-bearing extra fields. Resolve visibility from the corpus rather than
  trusting a recorded result. Count out-of-tenant or out-of-visibility results
  as leakage and fail the gate; do not silently filter them out of the report.
- Bind inputs to canonical dataset and corpus hashes. The corpus hash includes
  all document identities, versions, body hashes, and visibility. Record the
  embedding and chunking configuration, top k, similarity threshold, and the
  per-case tenant/visibility policy. Recorded vector evidence requires its
  source Git revision. A hash identifies an input; it does not attest that a
  claimed capture actually ran correctly.
- Emit aggregate-only JSON and Markdown without questions, answers, document
  contents, case IDs, principal IDs, document/chunk identifiers, or raw errors.
  Source search/embedding timings and token counts remain separate from free
  replay execution. Unknown values stay null; timings include sample counts.
  No source-run cost estimate is claimed.
- Identify synthetic rankings explicitly as `synthetic_test`. They are scoring
  fixtures, not generated golden labels or measured vector quality evidence.
  Replaying real rankings likewise does not rerun search or detect changed
  chunking, SQL, or embedding behavior.
- Optionally compare against another saved run after checking dataset, corpus,
  configuration, and evidence-kind compatibility. Reject failing baselines.
  Compare overall hit@k, recall@k, and MRR@k with an explicit absolute drop
  allowance (default zero). A failure or leakage always fails regardless of the
  allowance. Report category metrics descriptively; category thresholds and
  measured-vector release thresholds remain undecided.

## Consequences

The scorer can be verified with hand-calculated examples before spending on
embeddings. A deliberate removal of relevant evidence fails the comparison,
but this is an evaluator test, not the Week 4 degraded-chunker acceptance test.
Saved rankings cannot prove actual chunk existence, vector ordering, capture
configuration, or latency. That requires the subsequent capture/re-execution
adapter and evidence review.

The corpus currently contains one tenant and no restricted documents. Synthetic
tests exercise a second tenant and visibility violations; this does not amount
to measured multi-tenant production evidence. Evaluation contexts describe
fictional authorization scopes and do not add authentication to the public API.

## Remaining objective 4.1b work

Add explicit provisional inputs with separate human-reference and provisional
reports under ADR 0018, capture query/corpus vectors through an approved
workflow, rerun exact search against
the disposable local database, choose evidence-backed thresholds, and commit
the actual vector baseline and its limitations. Paid calls and hosted writes
retain their separate approval boundaries. No keyword/hybrid retrieval,
reranker, index, or deployment is introduced here.
