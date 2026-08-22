# ADR 0007: Stage Cloud Run revisions before promotion

## Status

Accepted on 2026-08-21.

## Context

Week 2 needs to prove that the production container can run on a managed cloud
platform with secrets, health checks, cost controls, deployment evidence, and a
rollback path. The existing Render service installs the Python project directly
and remains the working Week 1 fallback.

Deploying a mutable image tag directly to 100% traffic would make provenance
and recovery harder to explain. Giving GitHub Actions a long-lived cloud key
would also create an unnecessary credential before the manual boundary is
understood.

## Decision

- Cloud Build receives only a whitelist of required build files.
- The Google-maintained Docker build image is pinned by digest and BuildKit is
  enabled explicitly.
- Every image is tagged with the full Git commit SHA, resolved in Artifact
  Registry, and deployed to Cloud Run by immutable image digest.
- Cloud Run uses a dedicated runtime service account with accessor permission
  on only the two provider secrets.
- Secret version numbers are explicit; `latest` is not accepted by the release
  script.
- After the first service bootstrap, a new revision receives a unique traffic
  tag but zero production traffic.
- A provider-free public smoke test must pass on the tag URL before the release
  moves 100% of traffic to it.
- Request-based billing, zero minimum instances, one maximum instance, bounded
  CPU/memory/concurrency, and health probes are explicit release settings.
- The service is public for the learning UI. This is not an authorization
  boundary and remains unsuitable for real customer data.
- Cloud deployment is manual for this release. GitHub CI retains read-only
  repository permission and no cloud or provider credential.

## Consequences

- A clean Git commit, registry digest, Cloud Run revision, and public behavior
  can be connected in one evidence chain.
- A candidate failure does not replace the serving revision.
- Cloud Run does not allow `--no-traffic` while creating a service. The first
  revision is an explicit exception because no serving revision exists to
  protect; it is smoke-tested immediately.
- Rollback changes traffic immediately without rebuilding or rewriting Git.
- The first release cannot prove rollback until a second revision exists.
- Manual deployment depends on the developer's local Google login and is not
  yet continuous delivery.
- Public unauthenticated access can still cause model usage. Instance limits,
  application budgets, provider budgets, and eventual authentication/rate
  limiting are separate required controls.

## Follow-up

After the manual workflow is understood, use Workload Identity Federation and
a dedicated deployer service account for approved GitHub deployments. Do not
create a downloaded service-account key.
