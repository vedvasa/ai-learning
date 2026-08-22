# Deploy Ticket Triage to Cloud Run

This runbook releases the Week 2 container to Google Cloud Run without changing
the existing Render service. The release is deliberately manual while we learn
the cloud boundary. A later release can replace the local user credential with
GitHub Actions and Workload Identity Federation.

## Deployed architecture

The release path is:

1. `gcloud` uploads only the `.gcloudignore` whitelist to Cloud Build.
2. Cloud Build uses the pinned Docker builder in `cloudbuild.yaml`.
3. The build runs the offline 30-case dataset validation without provider keys.
4. Artifact Registry stores an image tagged with the full Git commit SHA.
5. The release resolves that tag to a digest and gives the digest to Cloud Run.
6. Cloud Run creates a tagged candidate revision with zero production traffic.
7. `scripts/smoke-cloud-run.sh` checks the candidate without model calls.
8. Only a successful candidate receives 100% of service traffic.

The application runs as
`ai-learning-runtime@ai-learning-ved-2026.iam.gserviceaccount.com`. That identity
can access only the `openai-api-key` and `anthropic-api-key` secrets. Secret
values are injected when an instance starts and never enter Git, Cloud Build,
the container image, or the deploy command.

## One-time prerequisites

The learning project uses these resources:

- project `ai-learning-ved-2026`;
- region `us-west1`;
- Docker repository `ai-learning`;
- runtime service account `ai-learning-runtime`;
- enabled Cloud Run, Cloud Build, Artifact Registry, Secret Manager, and IAM
  APIs;
- enabled version `1` of each provider secret; and
- a project-scoped monthly budget alert.

The active local `gcloud` configuration must point at the same project:

```bash
gcloud config configurations activate ai-learning
gcloud config get-value project
gcloud config get-value run/region
```

The expected project and region are `ai-learning-ved-2026` and `us-west1`.

## Release a clean commit

Run the full local test suite and push the commit before releasing it. The
release script rejects tracked or untracked worktree changes so the image can be
traced to one Git commit.

```bash
uv run --no-sync pytest

GCP_PROJECT_ID=ai-learning-ved-2026 \
  sh scripts/deploy-cloud-run.sh
```

Optional environment variables change non-secret resource names or select a
new explicit secret version:

| Variable | Default |
|---|---|
| `GCP_REGION` | `us-west1` |
| `GCP_ARTIFACT_REPOSITORY` | `ai-learning` |
| `GCP_IMAGE_NAME` | `ai-learning` |
| `CLOUD_RUN_SERVICE` | `ai-learning` |
| `CLOUD_RUN_SERVICE_ACCOUNT` | `ai-learning-runtime@PROJECT_ID.iam.gserviceaccount.com` |
| `OPENAI_SECRET_VERSION` | `1` |
| `ANTHROPIC_SECRET_VERSION` | `1` |

`latest` is intentionally rejected for secrets. Selecting versions explicitly
makes a revision reproducible and makes rotation a reviewed deployment.

The command prints the service URL, candidate URL, revision, image digest, and
the exact rollback command when a previous serving revision exists. A failed
candidate smoke test exits before traffic changes.

## Runtime and cost controls

The release explicitly configures:

- request-based billing through CPU throttling;
- service-level minimum instances `0` and maximum instances `1`;
- one vCPU, 512 MiB memory, and concurrency `4`;
- a 60-second request timeout;
- second-generation execution;
- startup and readiness checks on `/health/ready`;
- liveness checks on `/health/live`; and
- pinned provider secret versions.

Maximum instances is a guardrail, not a spending cap. The service is public for
the learning UI and has no user authentication or rate limit, so provider-side
budgets and the application token/cost limits remain important. Do not add a
keep-awake monitor; scaling to zero and observing cold starts are part of the
exercise.

## Verify without model calls

Get the public URL and repeat the smoke test at any time:

```bash
CLOUD_RUN_URL="$(
  gcloud run services describe ai-learning \
    --region=us-west1 \
    --project=ai-learning-ved-2026 \
    --format='value(status.url)'
)"

sh scripts/smoke-cloud-run.sh "$CLOUD_RUN_URL"
```

The smoke test checks liveness, readiness, the browser UI, static JavaScript,
and the OpenAPI triage route. It never calls a generation, streaming, or triage
endpoint, so it cannot create provider usage.

After the smoke test passes, one short browser triage request per provider is an
optional paid acceptance test. Record its token usage and cost separately.

## Inspect the deployed boundary

```bash
gcloud run services describe ai-learning \
  --region=us-west1 \
  --project=ai-learning-ved-2026

gcloud run revisions list \
  --service=ai-learning \
  --region=us-west1 \
  --project=ai-learning-ved-2026

gcloud run services logs read ai-learning \
  --region=us-west1 \
  --project=ai-learning-ved-2026 \
  --limit=50
```

Logs may contain request IDs, routes, status, latency, provider, model, and token
metadata. They must not contain API keys, prompts, ticket text, or generated
responses.

## Roll back traffic

List revisions and identify the last known-good revision before changing
traffic:

```bash
gcloud run revisions list \
  --service=ai-learning \
  --region=us-west1 \
  --project=ai-learning-ved-2026
```

Move all traffic to that exact revision:

```bash
gcloud run services update-traffic ai-learning \
  --to-revisions=KNOWN_GOOD_REVISION=100 \
  --region=us-west1 \
  --project=ai-learning-ved-2026
```

Then rerun the public smoke test. Rollback changes routing only: it does not
rebuild an image, mutate Git history, or delete the bad revision. Restore the
fixed revision with another explicit traffic update after it is verified.

The first Cloud Run release has no earlier revision and therefore cannot be
rolled back. Exercise rollback after the second healthy release by moving
traffic to the first revision, smoke testing it, and then restoring the newest
revision.

## Secret rotation

Add a new secret version through standard input, then release with its explicit
number. Do not destroy the previous version until the new revision has passed
its candidate and public checks. Disable or destroy unused versions afterward
to stay within the active-version allowance.

## Current delivery limitation

GitHub CI builds and smoke-tests the container but does not deploy it and has no
Google credentials. This is intentional for the first Cloud Run release. The
next CD hardening step is GitHub-to-Google Workload Identity Federation with a
dedicated deployer identity, approval gate, and no downloaded service-account
key.
