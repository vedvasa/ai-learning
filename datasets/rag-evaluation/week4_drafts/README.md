# Week 4: model-assisted retrieval cases

These files preserve thirty original model-assisted draft snapshots. The
project owner reviewed six on 2026-09-29; accepted copies now live alongside
the original ten in [the 16-case reference set](../week4_reviewed_labels.json).
The remaining 24 are provisional. The first ten human labels remain unchanged
in `../week4_human_labels.json`.

The [six reviewed judgments](quick-review.md) are source slots 15, 19, 26,
27, 30, and 40. Codex has [checked all thirty against the sources](source-check.md).
Human review of every case is optional; unchecked cases stay provisional and
can support separately reported experiments under [ADR 0018](../../../docs/decisions/0018-focused-human-review-and-provisional-evaluation.md).

Full details remain in [batch 1](batch-1.md), [batch 2](batch-2.md), and
[batch 3](batch-3.md). They provide the questions, trusted scopes, expected
documents, required facts, categories, difficulty, rationale, and source links.

When a case needs further review, check:

1. Does the question have the proposed answer, or does it need clarification or
   information absent from the corpus?
2. Do all required facts follow from the linked documents, without a guarantee
   or precise number that the corpus does not support?
3. Are the expected documents necessary, sufficient, and allowed by the trusted
   case context? A document linked for review is not automatically an expected
   retrieval result.
4. Is the case meaningfully different from the others, with a sensible category
   and difficulty?

Reply with corrections or feedback by slot number. Review applies only to the
content actually checked, not the rest of its batch. The batch hash identifies
the exact draft version. A source check, structural validation pass, or merged
PR does not constitute human review.

The approved target mix is:

| Category | Preserved human cases | Model-assisted cases | Working total |
|---|---:|---:|---:|
| Direct fact | 2 | 10 | 12 |
| Multi-document | 2 | 6 | 8 |
| Ambiguous | 1 | 4 | 5 |
| Unanswerable | 2 | 3 | 5 |
| Adversarial | 2 | 3 | 5 |
| Privacy boundary | 1 | 4 | 5 |
| Total | 10 | 30 | 40 |

The combined working set has 24 cases with relevant documents,
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

After review of a complete label, it can be copied into a separate expanded
golden worksheet with actual review provenance; its first ten cases must match
the checkpoint exactly. Partial judgment feedback does not approve unreviewed
fields. The six reviewed cases are copied unchanged apart from provenance;
their case IDs map source slots 15, 19, 26, 27, 30, and 40 to reviewed worksheet
slots 11–16. When composing the 40-case working set, use those reviewed copies
and exclude their draft duplicates by case ID.

The reviewed set contains 7 answerable and 9 abstention cases. The remaining
24 provisional cases contain 17 answerable and 7 abstention cases. Keep these
groups separate in future reports.

The scorer accepts the combined set with `--include-provisional`; its default
worksheet in that mode is the 16-case reviewed set. It validates the accepted
copies, excludes their draft duplicates, hashes the exact composition, and
reports reviewed/provisional groups separately. Use
`rag-retrieval-evaluation --include-provisional --minimum-cases 40 --validate-only`.
Without this flag, `--minimum-cases 40` still applies only to the supplied
golden worksheet and fails on a ten- or sixteen-case set.
