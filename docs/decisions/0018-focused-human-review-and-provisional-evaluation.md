# ADR 0018: Focus human review and separate provisional evaluation

## Status

Accepted on 2026-09-29 after the project owner approved reducing human review
to six instructive judgments and keeping the remaining cases provisional.
This updates the review requirements in ADRs 0015–0017, not the strict golden
label schema or the original ten labels.

## Context

The first ten labels already satisfy the roadmap's human-authorship checkpoint.
Requiring approval of every additional draft before running experiments adds
work without yet teaching retrieval failure analysis. Model-checked labels
still have correlated errors and must not be presented as human ground truth.

## Decision

- Preserve the first ten human-authored labels exactly. Only actual human
  review can add a model-assisted case to a golden worksheet, with its original
  origin and real reviewer role/date. Passing CI, merging a PR, or accepting
  this workflow is not review of any label.
- Have Codex check all thirty drafts against the pinned corpus. Record that
  check as an assistant source check, not independent or human validation.
- Start human review with slots **15, 19, 26, 27, 30, and 40**. These cover
  multiple required sources, adversarial instructions, ambiguity, unsupported
  precision, authorized internal access, and cross-tenant exclusion. Review
  applies only to the specific content shown; partial feedback does not imply
  approval of the whole label or other cases in its batch.
- Keep unreviewed cases provisional with `human_reviewed=false`. The current
  batch status `awaiting_human_review` describes provenance, not a blocking
  task queue. Full-batch review is optional. Preserve the JSON and generated
  full sheets as supporting detail.
- Allow the 40-case working set to combine human references and provisional
  cases. Report their counts, denominators, relevance metrics, and category
  breakdowns separately. Never advertise a blended score as golden quality or
  call this a 40-case human-reviewed golden dataset. Identify and hash the
  exact inputs and review status so comparisons cannot silently change labels.
- Apply relevance-regression acceptance to the human-reviewed reference set.
  Provisional relevance scores are diagnostic until reviewed; investigate
  disagreements before changing retrieval to satisfy them. Execution failures
  and unauthorized results fail checks in either group.
- Further review is driven by uncertain labels, competing retrieval results,
  and failures. The six-case sample is purposive, not a statistical estimate
  of accuracy across the other cases. Preparation and provisional experiments
  can proceed while review is pending.

## Consequences and implementation boundary

Objective 4.1b now targets 40 versioned working cases with explicit provenance,
separate reference/provisional results, and a measured reproducible vector
baseline. It does not require all forty to become golden labels. The guide
and current milestone reflect this adjustment.

This increment checks sources and simplifies the review package. The owner's
review is recorded for the selected six, giving 16 reviewed cases and
24 provisional cases. The original draft snapshots remain unchanged. The
existing scorer still rejects drafts and `--minimum-cases 40` checks the supplied
golden worksheet. A following code increment must add explicit provisional
input/report support alongside real vector capture and local re-execution;
do not bypass the schema, fabricate reviewed provenance, or count a synthetic
replay as the baseline. Paid calls and hosted mutations retain their separate
approval boundaries.
