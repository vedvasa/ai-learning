# Week 2 Cloud Run deployment evidence

Evidence date: 2026-08-21

Live service: [ai-learning-3y5vyfqynq-uw.a.run.app](https://ai-learning-3y5vyfqynq-uw.a.run.app/)

Application revision: `1df717f07ab34dd76130907886fbad294f3acce3`

## Traceable release chain

| Boundary | Verified value |
|---|---|
| Cloud Build | `673abc74-4452-4ab2-80d2-8daf79c34dd4` (`SUCCESS`) |
| Build duration | 2026-08-22 01:05:04Z to 01:06:07Z |
| Artifact Registry image | `us-west1-docker.pkg.dev/ai-learning-ved-2026/ai-learning/ai-learning` |
| Image digest | `sha256:c5ab8adad4fe0bec167164176251c7074be27330aa0c01c0fa83c2db75a71800` |
| Cloud Run revision | `ai-learning-git-1df717f07ab3` |
| Candidate tag | `git-1df717f07ab3` |
| Serving traffic | 100% to the verified revision |

Cloud Build ran the offline 30-case validation without provider credentials
before it published the image. Cloud Run then deployed the immutable digest,
not a mutable tag.

## Public service checks

These warm, read-only checks made no model-provider calls.

| Endpoint | HTTP status | Response time |
|---|---:|---:|
| `/` | 200 | 0.106 s |
| `/health/live` | 200 | 0.086 s |
| `/health/ready` | 200 | 0.090 s |
| `/openapi.json` | 200 | 0.097 s |

The release smoke script also verified the homepage assets, Ticket Triage API
contract, and deployed application version against both the tagged revision URL
and the default service URL. It never called a generation, streaming, triage, or
provider model endpoint.

## Runtime boundary

The live service configuration was inspected after promotion:

- dedicated `ai-learning-runtime` service identity;
- OpenAI and Anthropic secrets injected from explicit Secret Manager version
  `1`, with no secret values in the service definition;
- one vCPU, 512 MiB memory, concurrency `4`, and a 60-second timeout;
- request-based CPU throttling;
- minimum instances `0` and maximum instances `1`;
- startup probe on `/health/ready` and liveness probe on `/health/live`; and
- image pinned to the recorded Artifact Registry digest.

The 200 most recent Cloud Run log entries were checked for provider-key patterns
after verification. No OpenAI or Anthropic key pattern or key assignment was
found. The check reports only pass/fail and does not copy log payloads into the
repository.

## Cost and rollback notes

The build, deployment, and smoke tests made zero provider model calls, so
measured model spend for this release is `$0.00`. Cloud usage is constrained by
scale-to-zero, a one-instance maximum, a project budget alert, and the active
free trial/free-tier allowances. This evidence does not claim a reconciled cloud
invoice.

Cloud Run cannot create a service with a zero-traffic first revision. This
bootstrap revision therefore received traffic immediately and was smoke-tested
before the release command reported success. No older revision exists yet, so an
actual rollback drill becomes possible after the next healthy revision is
promoted. Every later release uses a zero-traffic candidate before promotion.
