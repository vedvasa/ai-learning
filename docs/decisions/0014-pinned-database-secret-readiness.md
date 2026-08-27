# ADR 0014: Require a pinned database secret for the Week 3 Cloud Run release

## Status

Accepted on 2026-08-26.

## Context

Week 3 adds retrieval, grounded answers, and atomic conversation persistence to
the existing container. Those paths need the remote Supabase Postgres database,
while the Week 1 Render fallback does not. Treating the database as globally
required would make the fallback unready even though its earlier features still
work.

A readiness probe that opens Postgres every five seconds would add continuous
database traffic, couple basic instance health to a remote dependency, and make
the learning deployment harder to reason about. Conversely, deploying the Week
3 service without a database credential would produce a healthy-looking UI whose
main workflow fails on first use.

## Decision

- Add an opt-in `RAG_DATABASE_REQUIRED` readiness setting. It defaults to false
  so earlier environments retain their current contract; the Cloud Run release
  sets it to true.
- When enabled, `/health/ready` requires a nonblank `DATABASE_URL` in addition
  to both provider keys. This is configuration readiness, not a connectivity
  query.
- Store the remote Postgres URI in the dedicated Secret Manager secret
  `supabase-database-url`. Inject a reviewed numeric version as `DATABASE_URL`;
  reject `latest`.
- Give only the existing Cloud Run runtime service account accessor permission
  on that secret. The credential never enters Git, Cloud Build, an image layer,
  or a command argument.
- Use the Supabase Transaction pooler URI with TLS for the application's
  short-lived Cloud Run connections.
- Extend the candidate smoke test to verify database configuration, the RAG UI
  wiring, and both RAG routes without calling Postgres or either model provider.
- Keep one real grounded-answer request as an explicit, optional, paid manual
  acceptance check after deployment.

## Consequences

- A candidate missing its database secret fails startup/readiness before it can
  receive production traffic.
- Readiness proves that the secret was injected, not that credentials, network,
  schema, or corpus are valid. The optional grounded-answer check covers the
  complete path without turning health probes into database load.
- The Render fallback continues to report readiness from its two provider keys.
- Every Week 3 revision is traceable to three explicit secret versions and one
  immutable image digest.
- The public unauthenticated service still needs fictional data, provider
  budgets, and the existing one-instance guardrail. Authentication and rate
  limiting remain future work.

## Out of scope

This change does not create the secret, alter hosted database state, build or
push an image, or deploy a Cloud Run revision. Those remain explicit operator
actions after merge. It also does not add a database connection pool, a live
database health probe, Workload Identity Federation, or continuous deployment.

## References

- [Cloud Run secret configuration](https://cloud.google.com/run/docs/configuring/services/secrets)
- [Cloud Run health checks](https://cloud.google.com/run/docs/configuring/healthchecks)
- [Supabase database connection modes](https://supabase.com/docs/guides/database/connecting-to-postgres)
