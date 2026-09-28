# Week 4: thirty cases for human review

These are **model-assisted drafts awaiting project-owner review**. They are not
accepted golden labels. The first ten human labels remain unchanged in
`../week4_human_labels.json`.

Start with [batch 1: slots 11–20](batch-1.md), then review
[batch 2: slots 21–30](batch-2.md) and [batch 3: slots 31–40](batch-3.md).
Each review sheet contains the question, trusted fictional access scope,
expected documents, required facts, category, difficulty, rationale, and links
to the source documents. No provider call is needed to review them.

For each case, check:

1. Does the question have the proposed answer, or does it need clarification or
   information absent from the corpus?
2. Do all required facts follow from the linked documents, without a guarantee
   or precise number that the corpus does not support?
3. Are the expected documents necessary, sufficient, and allowed by the trusted
   case context? A document linked for review is not automatically an expected
   retrieval result.
4. Is the case meaningfully different from the others, with a sensible category
   and difficulty?

Reply with corrections by slot number, or approve a specific batch after
reviewing all ten cases. The review sheet's batch hash identifies the exact
draft version. A structural validation pass or a merged draft PR does not
constitute human review.

The approved target mix is:

| Category | Preserved human cases | New drafts | Combined after review |
|---|---:|---:|---:|
| Direct fact | 2 | 10 | 12 |
| Multi-document | 2 | 6 | 8 |
| Ambiguous | 1 | 4 | 5 |
| Unanswerable | 2 | 3 | 5 |
| Adversarial | 2 | 3 | 5 |
| Privacy boundary | 1 | 4 | 5 |
| Total | 10 | 30 | 40 |

If accepted unchanged, the combined set has 24 cases with relevant documents,
16 abstention cases, and a difficulty mix of 7 easy, 20 medium, and 13 hard.
Expected references cover all 21 corpus documents. Those counts describe the
draft design, not measured search quality or accepted labels.

Most new contexts allow public documents only. Slot 30 explicitly permits the
internal escalation policy, while slots 20 and 29 test its exclusion. Slot 40
uses a different fictional tenant with no in-scope corpus documents. These
contexts exercise the evaluator's trust boundary; they do not grant access to
the deployed application or change its anonymous public-only policy.

From the repository root:

```bash
uv run --no-sync rag-retrieval-drafts --check-review-sheets
```

The JSON files are the editable draft source. After correcting them, regenerate
their review sheets with `rag-retrieval-drafts --write-review-sheets` and review
the new versions. Both commands remain provider-free and database-free. Drafts
use a separate schema with `origin: model_assisted`, `human_reviewed: false`,
and no claimed human annotator. Neither command approves or promotes labels.

After explicit human review, approved cases can be copied into a separate
expanded golden worksheet with their actual review provenance; its first ten
cases must match the preserved human checkpoint exactly. The dataset's
40-case completion gate still fails until that accepted artifact exists.
