# Develop the KnowledgeDesk database locally

Week 3 uses Supabase Postgres with pgvector. The repository owns the database
schema through ordered SQL migrations in `supabase/migrations/`; the hosted
dashboard is not the source of truth.

## Prerequisites

- Docker is running.
- Supabase CLI `2.115.0` is installed.
- Commands run from the repository root.

The local stack uses development-only credentials printed by the CLI. It must
not be exposed to another network or used for real customer data.

## Rebuild and verify locally

Start the local Supabase stack:

```bash
supabase start
```

Recreate the database from committed migrations and the deterministic seed:

```bash
supabase db reset
```

Run database contract tests and lint the local schema:

```bash
supabase test db
supabase db lint --local --schema knowledge --level warning --fail-on error
```

## Validate and ingest the fictional corpus

The committed corpus lives in `datasets/knowledge-base/`. Validate its front
matter, normalize its Markdown, and preview deterministic chunk counts without
using the database or an API key:

```bash
uv sync --locked --no-editable --reinstall-package ai-learning
uv run --no-sync ingest-documents --dry-run
```

The explicit package reinstall matters after switching branches or changing
source code: `--no-sync` intentionally executes the already-installed wheel
and will not rebuild it.

For live local ingestion, put the local Postgres connection in the ignored
`.env` file. The standard Supabase local stack uses:

```dotenv
DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres
```

Start with one document. This command can make a paid OpenAI embeddings call,
so the spend acknowledgement is mandatory:

```bash
uv run --no-sync --env-file .env ingest-documents \
  --max-documents 1 \
  --confirm-spend
```

After inspecting that document in local Studio, ingest the complete corpus:

```bash
uv run --no-sync --env-file .env ingest-documents --confirm-spend
```

Re-running the command records unchanged documents as `skipped` before making
an embeddings request. Changed documents reuse tenant-scoped cached embeddings
for chunks with the same content hash. The command never prints document text,
provider keys, or the database URL.

## Exercise exact semantic retrieval locally

The retrieval endpoint requires the local `DATABASE_URL`, an OpenAI key, and an
ingested corpus. Reinstall the current branch as a non-editable wheel, then run
FastAPI in one terminal:

```bash
uv sync --locked --no-editable --reinstall-package ai-learning
uv run --no-sync --env-file .env uvicorn app.main:app --reload
```

In another terminal, send a retrieval request:

```bash
curl --fail-with-body http://127.0.0.1:8000/api/retrieve \
  --header 'Content-Type: application/json' \
  --header 'X-Request-ID: local-retrieval-001' \
  --data '{"question":"How long does a password reset link last?","top_k":5}'
```

Sending this request deliberately makes one paid OpenAI embeddings call and
writes best-effort operational telemetry. It performs exact cosine search over
active, model-compatible chunks for the server-configured tenant. Because the
application is not authenticated yet, the endpoint returns only documents
marked `public`; the request cannot select a tenant or visibility.

The default similarity floor is provisional. Inspect the returned scores, but
do not tune the threshold from one example. Week 4 will use a labeled question
set to measure and calibrate retrieval behavior.

## Exercise citation-grounded answers locally

The grounded endpoint requires the same local database and OpenAI embedding
configuration as retrieval, plus the key for the selected generation provider.
With FastAPI still running, send a question through OpenAI:

```bash
curl --fail-with-body http://127.0.0.1:8000/api/answer \
  --header 'Content-Type: application/json' \
  --header 'X-Request-ID: local-answer-001' \
  --data '{"provider":"openai","model":"gpt-5.6-luna","question":"How long does a password reset link last?","top_k":5}'
```

To use Anthropic, change `provider` to `anthropic` and `model` to the configured
`ANTHROPIC_MODEL`. The request normally makes one paid OpenAI embeddings call
and one paid generation call through the selected provider. If retrieval finds
no evidence, the application skips generation and returns a fixed abstention.

The response includes only application-verified sources whose chunk IDs were in
the retrieved set. The database stores the submitted question, answer, verified
citation metadata, and successful generation telemetry in one transaction.
Application logs and `knowledge.model_calls` do not contain question, answer, or
evidence text. The default browser workspace exercises the same endpoint and
renders application-verified citations as numbered links to source cards. A
browser submission has the same paid-call boundary as the `curl` example.

Citation validation is part of the bounded generation attempt. If a provider
returns a structurally valid draft with missing, malformed, or unretrieved
citations, the application categorizes it as invalid output and may retry within
the existing `LLM_MAX_ATTEMPTS` and total `LLM_TIMEOUT_SECONDS` budget. A
successful response reports and stores the combined known provider latency and
token usage from every schema-valid attempt, including rejected citation drafts.
Provider failures that do not return usage can still make those totals a lower
bound. Exhausted invalid output fails closed and stores no conversation.

## Validate and run the Week 3 acceptance set

The committed acceptance set contains exactly 20 fictional questions: 12
answerable, four ambiguous, and four intentionally unanswerable. Validate its
schema, deterministic hash, category counts, and corpus references for free:

```bash
uv sync --locked --no-editable --reinstall-package ai-learning
uv run --no-sync rag-evaluation --validate-only
```

Validation exits before settings are loaded. It cannot read `.env`, open a
database connection, or construct an OpenAI or Anthropic client.

A live evaluation uses the same retrieval, grounding, citation validation, and
atomic persistence path as `POST /api/answer`. It therefore makes a paid OpenAI
embedding call for every selected case, usually makes a paid generation call,
and can make additional bounded generation attempts after invalid citations. It
stores each completed fictional exchange in the configured database. Start
with the default category-balanced three-case sample against local Supabase:

```bash
uv run --no-sync --env-file .env rag-evaluation \
  --provider openai \
  --allow-paid-calls
```

Run the complete acceptance set only when you deliberately want up to 20 query
embedding calls, generation calls, and local conversation writes:

```bash
uv run --no-sync --env-file .env rag-evaluation \
  --provider openai \
  --max-cases 20 \
  --allow-paid-calls
```

The ignored `artifacts/rag-evaluation.json` report contains aggregate metrics,
the dataset hash, provider, model, and run configuration. It omits case IDs,
questions, answers, evidence, document keys, citation IDs, conversation IDs,
and provider request IDs. The command reports retrieval and grounding behavior,
not human-judged answer correctness; that deeper golden-set work belongs to
Week 4.

The command refuses a non-local `DATABASE_URL` unless
`--allow-remote-database` is also supplied. Do not use that flag during routine
pull-request testing. It authorizes hosted conversation and telemetry writes;
the paid-call flag alone does not.

Stop the stack without deleting its local volumes:

```bash
supabase stop
```

Database reset, pgTAP, lint, and repository integration tests make no OpenAI or
Anthropic calls. Live ingestion and `/api/retrieve` make paid OpenAI embeddings
calls. `/api/answer` also makes a paid generation call unless retrieval returns
no evidence; the corresponding instructions identify each boundary.

## Author the first ten Week 4 retrieval labels

Objective 4.1a deliberately commits an incomplete worksheet at
`datasets/rag-evaluation/week4_human_labels.json`. Its ten `"label"` values are
all `null`. The project owner must author those ten reference labels without
model assistance before the dataset is expanded or any model-assisted labeling
begins.

Install the current branch and confirm that the blank scaffold and corpus are
valid without loading settings, opening Postgres, or constructing a provider
client:

```bash
uv sync --locked --no-editable --reinstall-package ai-learning
uv run --no-sync rag-golden-dataset
```

Print copyable stable document-reference objects plus their visibility. This
command reports committed metadata and normalized-content hashes, but omits
document content:

```bash
uv run --no-sync rag-golden-dataset --print-corpus-manifest
```

Read the fictional Markdown files in `datasets/knowledge-base/` yourself. For
each slot, replace `"label": null` with this shape, supplying your own question,
relevance judgment, answer facts, category, difficulty, and notes:

```json
{
  "case_id": "<human-authored-stable-case-id>",
  "question": "<human-authored fictional question>",
  "context": {
    "tenant_id": "knowledgedesk-demo",
    "principal_id": "fictional-public-user",
    "principal_type": "anonymous",
    "allowed_visibilities": ["public"]
  },
  "expected_relevant_documents": [
    {
      "tenant_id": "<copy from the corpus manifest>",
      "document_key": "<copy from the corpus manifest>",
      "document_version": 1,
      "content_sha256": "<copy from the corpus manifest>"
    }
  ],
  "key_answer_facts": ["<human-authored fact required for a correct answer>"],
  "should_abstain": false,
  "category": "direct_fact",
  "difficulty": "easy",
  "adversarial_notes": null,
  "label_provenance": {
    "origin": "human",
    "annotator_role": "project_owner",
    "labeled_on": "<YYYY-MM-DD>",
    "human_reviewed": true
  }
}
```

Copy each manifest `reference` object exactly; declared document versions vary
across a corpus even though the example shape above shows version `1`.

Use only fictional principal IDs beginning with `fictional-`; do not add a
name, email address, account ID, or other personal provenance. Available
categories are `direct_fact`, `multi_document`, `ambiguous`, `unanswerable`,
`adversarial`, and `privacy_boundary`, and all six must appear at least once.
`direct_fact` requires exactly one relevant document and `multi_document`
requires at least two. `adversarial` and `privacy_boundary` require notes.
Cases that should abstain must leave both `expected_relevant_documents` and
`key_answer_facts` empty. An anonymous user may reference only public documents;
a privacy-boundary request for internal data should expect abstention rather
than naming the internal document as retrievable evidence.

Run the strict completion gate after all ten slots are authored:

```bash
uv run --no-sync rag-golden-dataset --require-complete
```

The command must report ten validated labels and a canonical dataset SHA-256.
At that point, stop and record the hash for review. Do not ask a model to create,
rewrite, or complete these first ten labels, and do not expand toward 40 cases
until the human reference batch has been reviewed as its own increment.

## Hosted-project boundary

Do not run `supabase link`, `supabase db push`, paste a database connection
string, or apply SQL in the hosted dashboard merely to test a pull request.
Linking is local credential/configuration state, while `db push` changes the
hosted database.

After a migration PR is reviewed and merged, the developer may explicitly link
the repository and inspect the pending migration with:

```bash
supabase link --project-ref <project-reference>
supabase db push --dry-run
```

Applying the migration requires a separate, deliberate `supabase db push`.
The ingestion command additionally refuses a non-local `DATABASE_URL` unless
the developer passes `--allow-remote-database`; that flag is authorization to
write corpus data and must not be added to routine local commands.
Database passwords, access tokens, connection strings, and service-role keys
must never be pasted into chat, command history, source files, or pull-request
text.
