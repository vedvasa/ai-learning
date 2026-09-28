# ADR 0017: Keep model-assisted drafts outside golden data

## Status

Accepted on 2026-09-27 after the project owner authorized thirty drafts in three
batches of ten for human review.

## Context

The first ten labels are a frozen human-authored checkpoint. The approved next
step is to draft thirty additional cases and review them before acceptance.
The golden schema correctly rejects unreviewed labels. Relaxing it to store
drafts would let incomplete provenance enter evaluation, while temporarily
setting `human_reviewed=true` would falsely claim a review that did not happen.

## Decision

- Store drafts under `datasets/rag-evaluation/week4_drafts/` in three ten-case
  batches for slots 11–40. Use a distinct `retrieval_label_drafts` purpose and
  `awaiting_human_review` status. Draft provenance is explicitly model-assisted,
  records its draft date, and must have the strict boolean `human_reviewed=false`.
  It cannot claim a human annotator or reviewer identity.
- Share question, context, reference, category, fact, and abstention validation
  between draft and golden cases through a common content model. Golden
  provenance validation remains unchanged; drafts cannot be loaded as golden
  datasets or passed to the retrieval evaluator.
- Bind every batch to the preserved ten-label canonical hash. Validate unique
  questions and IDs across the checkpoint and all drafts, exact batch positions,
  pinned corpus references, and the agreed category composition. The original
  human checkpoint and the Week 3 dataset are not rewritten.
- Distinguish reviewer references from expected relevant documents. A reviewer
  may inspect a fictional internal policy to check a public-only abstention
  label; the policy must not become an expected retrievable document in that
  case. Reviewer references must also be version/hash valid.
- Generate readable review sheets from JSON, including a batch hash. CI checks
  that the sheets match their source so human reviewers do not approve stale
  text. The draft validator reports structural validity, never human approval
  or semantic correctness, and does not create accepted labels.
- Require explicit project-owner review of the actual batch version. A merged
  draft PR or passing validator is not label approval. Later acceptance copies
  only reviewed cases into a separate expanded golden worksheet with
  `origin=model_assisted`, the actual human reviewer role/date, and
  `human_reviewed=true`; it retains the original first ten cases exactly.

## Consequences

The review package is reproducible and usable without provider calls, secrets,
or database access. Pending drafts cannot inflate the accepted dataset count.
Category balance is enforced for this specifically approved draft package, not
as a universal golden-schema constraint. Human review may lead to explicit
revisions of the labels or this target mix.

The thirty drafts include public and authorized-internal cases, a negative case
for a tenant with no corpus documents, near-match unanswerable questions, and
answerable questions containing adversarial instructions. These broaden input
coverage but do not prove production isolation, prompt-injection resistance,
answer correctness, or real search quality. Those claims require later tests
and measured evidence. No paid capture, database change, UI change, deployment,
or automatic label-promotion command is part of this increment.
