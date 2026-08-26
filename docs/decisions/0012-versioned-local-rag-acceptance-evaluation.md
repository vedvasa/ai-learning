# ADR 0012: Use a versioned, guarded local RAG acceptance evaluation

## Status

Accepted.

## Context

The citation-Q&A path now ingests documents, retrieves exact vector matches,
generates grounded answers, validates citations, persists exchanges, and serves
the workflow in the browser. Individual examples demonstrate functionality but
cannot show how reliably retrieval finds the intended evidence or how often the
system abstains when the corpus lacks an answer.

Generative output is variable, so traditional unit tests alone are insufficient.
OpenAI's evaluation guidance recommends application-specific structured tests
and combining numerical metrics with human judgment. Week 3 needs a small
acceptance baseline; Week 4 will add deeper human labels, experiment tracking,
and retrieval comparisons.

Evaluation can create paid provider calls and persistent database records. It
must remain impossible for CI or a routine validation command to spend money or
write to a hosted database accidentally.

## Decision

- Commit one strict JSON dataset with exactly 20 fictional questions: 12
  answerable, four ambiguous, and four intentionally unanswerable.
- Label expected relevant document keys only for answerable questions. Treat the
  private `escalation-policy` document as forbidden evidence so a run also
  observes the server-owned public-visibility boundary.
- Validate case uniqueness, category counts, expectation consistency, corpus
  references, forbidden-document visibility, and a canonical SHA-256 hash before
  loading application settings.
- Add `rag-evaluation --validate-only` as a provider-free, database-free mode.
  Make a live run require `--allow-paid-calls`, cap the default at a deterministic
  category-balanced three-case sample, and require `--max-cases 20` for the full
  set.
- Use the actual retrieve-generate-validate-persist service for live local runs.
  Refuse a non-local database unless the operator separately supplies
  `--allow-remote-database`.
- Write an atomic aggregate-only JSON report under ignored `artifacts/`. Report
  completion, answerable retrieval hit rate at k, answerable answer rate,
  ambiguous and unanswerable abstention rates, citation validity, forbidden
  retrieval leakage, p50/p95 end-to-end latency, token totals, attempts, and
  normalized failure counts.
- Omit case IDs, questions, answers, source text, document keys, chunk and
  conversation identifiers, provider request identifiers, raw errors, database
  details, and credentials from the report.
- Keep CI provider-free. Test loading, gates, metrics, privacy, and the command
  with fake services; also run validation inside the container smoke test.

## Consequences

- The Week 3 release has a reproducible acceptance input and an attributable
  result through the dataset hash.
- A full run can use up to 20 paid query embedding calls and usually 20 paid
  generation calls. Successful cases intentionally write fictional exchanges to
  the configured database.
- Retrieval hit rate checks whether at least one expected document was returned;
  it is not recall over every relevant chunk.
- Citation validity confirms citations belong to retrieved chunks. It does not
  by itself prove that the answer is correct, complete, or faithful.
- Ambiguous abstention rate is descriptive. The current output contract does not
  separately label a clarification request.
- Aggregate-only output reduces data duplication but requires a deliberate local
  debugging session when an individual fictional case fails.

## Out of scope

This decision does not add LLM-as-judge scoring, human correctness labels,
hybrid retrieval, reranking, approximate indexes, baseline regression gates, a
dashboard, a production deployment, or a hosted database evaluation run. Those
are Week 4 concerns or separately approved operations.

## References

- [OpenAI evaluation best practices](https://developers.openai.com/api/docs/guides/evaluation-best-practices)
