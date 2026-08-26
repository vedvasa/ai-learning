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

Stop the stack without deleting its local volumes:

```bash
supabase stop
```

None of these commands use OpenAI or Anthropic, and none make a paid model
call.

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
