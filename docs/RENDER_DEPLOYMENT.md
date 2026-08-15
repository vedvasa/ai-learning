# Deploy PromptBench to Render

This runbook creates the Week 1 learning deployment after the deployment-readiness
pull request has been merged. The repository's `render.yaml` is the source of
truth for service configuration. API key values remain outside Git and are
entered only in Render's secret-value prompts.

## What the Blueprint creates

The Blueprint defines one stateless Python web service:

- Free instance in Render's Oregon region.
- Locked production dependency installation with `uv`.
- One Uvicorn process bound to `0.0.0.0:$PORT`.
- `/health/ready` as the deployment and runtime health check.
- Automatic deployment only after the linked commit's CI checks pass.
- A 30-second graceful shutdown window for in-flight streams.
- Secret prompts for `OPENAI_API_KEY` and `ANTHROPIC_API_KEY`.

Pull request previews are intentionally not enabled. Each preview would need
separate provider secrets and could create additional model and hosting usage.

## Current free-instance constraints

Render's Free instance type is appropriate for this learning deployment, not a
real customer-facing production service. As of August 2026:

- A Free web service spins down after 15 minutes without inbound traffic.
- The next request wakes it, and the cold start can take about one minute.
- Each workspace receives 750 Free instance-hours per calendar month.
- The filesystem is ephemeral and is cleared on deploy, restart, or spin-down.
- Bandwidth and build pipeline usage still count toward workspace allowances.
- Free services can be restarted by Render and cannot scale beyond one instance.

PromptBench does not persist local state, so the ephemeral filesystem is safe.
Do not add a keep-awake monitor: observing the real cold start is part of the
Week 1 exercise and spun-down time does not consume Free instance-hours.

Official references:

- [Render Free instances](https://render.com/docs/free)
- [Render Blueprint specification](https://render.com/docs/blueprint-spec)
- [Render web-service port binding](https://render.com/docs/web-services#port-binding)
- [Render health checks](https://render.com/docs/health-checks)

## Before creating the service

1. Merge the deployment-readiness pull request to `main` and confirm CI passes.
2. Confirm the repository is still public and contains no `.env` file or key.
3. Have the OpenAI and Anthropic project keys available from a secure local
   secret store.
4. Confirm provider project budgets and usage alerts are set to learning-scale
   values. The application cap of 64 output tokens reduces usage but is not a
   billing cap.
5. Review Render's workspace usage page and understand whether a payment method
   or workspace spend limit could permit charges beyond included allowances.

## Create the Blueprint

1. Sign in to the Render Dashboard.
2. Select **New → Blueprint** and connect GitHub if prompted.
3. Choose the `vedvasa/ai-learning` repository.
4. Keep `render.yaml` as the Blueprint path and start the creation flow.
5. When Render prompts for environment values, paste the two API keys into:

   - `OPENAI_API_KEY`
   - `ANTHROPIC_API_KEY`

6. Verify the selected instance type is **Free** before applying the Blueprint.
7. Create the service and watch the build and deploy logs.

The key values must not be added to `render.yaml`, a shell command, a screenshot,
a GitHub Actions secret, an issue, or a pull request. `sync: false` tells Render
to request each value during initial Blueprint creation without storing it in
the repository. If a new secret is added after creation, add it manually in the
service's Environment page because later Blueprint syncs ignore new
`sync: false` values.

## Understand the deploy sequence

Render performs these important steps:

1. Wait for the GitHub CI check because `autoDeployTrigger` is `checksPass`.
2. Run `uv sync --locked --no-dev --no-editable`.
3. Start `scripts/start-production.sh` with the platform-provided `PORT`.
4. Request `/health/ready`; it must return a 2xx response within five seconds.
5. Route public traffic only after the new instance becomes healthy.

Readiness checks configuration presence without making paid provider calls. A
missing key therefore prevents deployment, while a syntactically present but
invalid key is detected safely on the first provider request.

## Verify the live service

Copy the service's public `https://...onrender.com` URL, then use a task-specific
shell variable for the checks below:

```bash
PROMPTBENCH_URL="https://your-service-name.onrender.com"

curl --fail --show-error "$PROMPTBENCH_URL/health/live"
curl --fail --show-error "$PROMPTBENCH_URL/health/ready"
curl --fail --show-error "$PROMPTBENCH_URL/"
```

Open the URL in a browser and make one short, 64-token-capped streaming request
to each provider. Confirm that:

- Partial text becomes visible before the completion metadata.
- Cancel stops an in-flight stream.
- Latency, token counts, finish reason, and request IDs appear.
- Browser developer tools contain no API key.
- Render logs contain provider metadata but not prompts or response text.

Record the URL, screenshot, deploy revision, CI run, and call cost in
`LEARNING_PROGRESS_TRACKER.md` only after the checks pass.

## Cold-start exercise

1. Leave the service without inbound traffic for at least 15 minutes.
2. Request `/health/live` and measure how long the first response takes.
3. Request it again and compare the warm response.
4. Record both observations as the known Free-tier limitation.

Do not continuously ping the service to keep it awake. That would hide the
behavior this exercise is meant to teach and consume Free instance-hours.

## Controlled invalid-key drill

Do this only after the valid deployment and evidence are captured:

1. In Render's Environment page, replace one provider key with a clearly invalid
   placeholder and redeploy. Never type the real key into a terminal command.
2. Send a non-streaming request to that provider from the browser or API docs.
3. Confirm the response is HTTP 502 with code
   `provider_authentication_failed`, without provider internals or credentials.
4. Confirm the safe failure is visible in logs by request ID, without the prompt.
5. Restore the real key from the secure secret store and redeploy immediately.
6. Repeat the health and one-call smoke checks.

This drill demonstrates an intentional readiness limitation: checking whether a
secret exists is cheap and side-effect free, while validating it would require a
provider call on every health check.

## Roll back a bad deploy

1. Open the service's **Deploys** page in Render.
2. Select a recent successful deploy and choose **Rollback**.
3. Wait for `/health/ready` to pass, then repeat the live and UI smoke checks.
4. Fix the underlying problem in a new pull request.
5. Re-enable automatic deploys in service settings only after the fix is ready.

A Dashboard rollback reuses the prior build artifact and disables automatic
deploys so the bad commit is not immediately redeployed. It does not rewrite Git
history or replace current service settings permanently.

Official reference: [Render rollbacks](https://render.com/docs/rollbacks).

## Stop or remove the learning service

When the deployment is no longer needed, delete the service from Render rather
than merely deleting the Git branch. Removing a service is destructive: first
capture any evidence needed for the tracker, then confirm the exact service name
and ensure no later week depends on its URL.
