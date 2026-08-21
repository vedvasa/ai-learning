# ADR 0006: Ship a pinned, non-root production container

- Status: Accepted
- Date: 2026-08-20

## Context

The Render deployment currently installs and starts the Python project directly.
Week 2 also needs a portable image whose runtime is the same locally, in CI, and
on the planned Cloud Run service. A container is not a security boundary by
itself: an overly broad build context can copy secrets, a mutable base tag can
change underneath a release, and a root process gives an application more
privilege than it needs.

The image must keep the existing browser UI, API, and guarded evaluation command
without requiring development dependencies or uv at runtime.

## Decision

Use a two-stage Dockerfile based on the official Python 3.14.7 slim Bookworm
image. Pin both the Python image and the uv 0.12.3 build image by multi-platform
digest. Pin local Python to the same 3.14.7 patch release.

In the builder stage:

1. copy only `pyproject.toml`, `uv.lock`, and the package README;
2. install locked production dependencies without the application so that layer
   remains cacheable across source changes;
3. copy `src` and install the application non-editably; and
4. compile Python bytecode while uv is available.

In the runtime stage:

- copy only the completed virtual environment, the fictional evaluation dataset,
  and a small startup script;
- omit uv, the source tree, tests, documentation, Git history, and local files;
- keep the virtual environment root-owned and non-writable by the application;
- run as the explicit unprivileged UID/GID `10001:10001`;
- bind Uvicorn to `0.0.0.0` and the platform-provided `PORT`, defaulting to 8080;
- use `exec` so Uvicorn receives termination signals directly; and
- do not declare provider secrets, a Docker `HEALTHCHECK`, or mutable storage.

Use a whitelist `.dockerignore` so `.env`, `.git`, virtual environments, caches,
tests, and unrelated workspace files never enter the build context. Provider
credentials are supplied only as runtime environment variables.

CI builds the same production target and runs a credential-free smoke script.
The script verifies the non-root user, immutable minimal runtime, absence of
provider secret names in image configuration, offline dataset validation,
liveness, expected unready state without keys, homepage, and static JavaScript.
It does not call a model.

## Consequences

- The application artifact is portable across a local Docker engine, CI, and
  Cloud Run without changing its code or startup contract.
- Exact image digests improve reproducibility but require deliberate security and
  patch updates rather than silently following a mutable tag.
- Separating dependency and project installation improves rebuild caching.
- The runtime image is smaller and has fewer tools available to an attacker, but
  image size alone is not a security guarantee.
- Readiness returns HTTP 503 during credential-free smoke tests because it checks
  provider-secret presence. This is expected and tested without a provider call.
- Cloud Run startup/liveness configuration belongs to the platform deployment in
  PR 17; Dockerfile `HEALTHCHECK` is intentionally absent.
- Render continues using its existing native Python deployment until a later
  migration decision; this PR does not change the live service.
