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
evidence text. This increment has an API contract and generated `/docs` entry,
but no Q&A control in the browser UI yet.

Stop the stack without deleting its local volumes:

```bash
supabase stop
```

Database reset, pgTAP, lint, and repository integration tests make no OpenAI or
Anthropic calls. Live ingestion and `/api/retrieve` make paid OpenAI embeddings
calls. `/api/answer` also makes a paid generation call unless retrieval returns
no evidence; the corresponding instructions identify each boundary.

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
