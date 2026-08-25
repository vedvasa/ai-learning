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
Database passwords, access tokens, connection strings, and service-role keys
must never be pasted into chat, command history, source files, or pull-request
text.
