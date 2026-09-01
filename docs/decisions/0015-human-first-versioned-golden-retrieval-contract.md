# ADR 0015: Establish a human-first, versioned golden retrieval contract

## Status

Accepted on 2026-09-01.

## Context

The Week 3 acceptance set measures the complete retrieve-answer-persist path on
20 fictional questions. Its document keys are sufficient for a release smoke
baseline, but they cannot detect when a referenced document changes in place,
do not describe user authorization context or key answer facts, and do not
support retrieval recall or reciprocal-rank metrics.

Week 4 needs deeper reference labels. The curriculum requires the project owner
to author the first ten before any model-assisted labeling. Scaffolding those
answers automatically would contaminate the human calibration set, even if the
generated labels appeared plausible.

## Decision

- Add a separate Week 4 schema rather than changing the frozen Week 3
  acceptance artifact or its recorded canonical hash.
- Represent tenant and fictional user context explicitly, including the
  principal type and allowed document visibilities. Anonymous contexts may
  access only public documents.
- Identify each expected relevant document by tenant, document key, declared
  version, and normalized-content SHA-256. Provider-free validation rejects
  missing, cross-tenant, stale-version, stale-hash, and out-of-scope visibility
  references against the committed corpus.
- Require each completed label to state the question, relevant documents, key
  answer facts, abstention expectation, category, difficulty, adversarial notes
  where applicable, and provenance.
- Keep provenance non-personal through closed enums for label origin and
  annotator role plus a date and human-review flag. Names, emails, and arbitrary
  identifiers are outside the strict schema.
- Require unique case IDs and case-insensitive questions, internally consistent
  abstention labels, and coverage of direct-fact, multi-document, ambiguous,
  unanswerable, adversarial, and privacy-boundary categories.
- Require the first ten golden slots to be human-authored and human-reviewed.
  Model-assisted labels are permitted only after those ten, and only after
  human review.
- Commit a ten-slot worksheet whose label values are all `null`. A completed
  dataset exists only after every slot validates; its SHA-256 is computed over
  strict validated data serialized with sorted keys and compact separators.
- Exercise the completed contract with isolated `contract_test` fixtures. Their
  `synthetic_test` provenance is required in tests and rejected in a real
  golden dataset.
- Keep the validator provider-free and database-free. It may print a corpus
  reference manifest containing identifiers, versions, hashes, and visibility,
  but never document content or credentials.

## Consequences

- Corpus edits make affected labels fail closed until a human reviews and
  deliberately updates their pinned references.
- The first ten labels remain a genuine calibration set rather than model output
  approved after the fact.
- Category coverage is a contract gate, not an informal spreadsheet check.
- The initial worksheet is intentionally incomplete and `--require-complete`
  must fail until the project owner supplies all ten labels.
- The schema can later hold additional human-reviewed, model-assisted labels
  without weakening the first-ten provenance rule.
- A version/hash reference identifies relevant documents, not relevant chunks.
  Chunk-level judgments and retrieval metrics belong to the next increment.

## Out of scope

This decision does not author golden labels, expand the dataset to 40 cases,
call a model, capture a vector baseline, implement retrieval metrics, change the
corpus, write to a database, add keyword or hybrid search, rerank results, add an
HNSW index, deploy the application, or mutate cloud resources.
