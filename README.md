# AI Learning

A project-based path from notebook experiments to production AI applications.
The repository will grow into **KnowledgeDesk**, a deployed support and research
assistant built through ten incremental releases.

## Curriculum

- [Production AI self-learning guide](PRODUCTION_AI_SELF_LEARNING_GUIDE.md)
- [Learning progress tracker](LEARNING_PROGRESS_TRACKER.md)

## Local setup

This project uses [uv](https://docs.astral.sh/uv/) for Python and dependency
management.

```bash
uv sync --locked --no-editable
uv run --no-sync ai-learning
```

The Python version is pinned in `.python-version`, while exact dependency
versions are recorded in `uv.lock`.

## Week 1: run PromptBench

Install the locked development environment and start the FastAPI server:

```bash
uv sync --locked --no-editable
uv run --no-sync uvicorn --app-dir src app.main:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) for the browser UI or
[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) for the generated API
documentation.

The browser UI can stream a prompt through either configured provider. API keys
remain on the server; the browser sends only the selected provider, configured
model, and prompt to `POST /api/stream`. FastAPI converts both native provider
streams into the same server-sent event contract:

- `start` identifies the application request, provider, and model.
- `delta` contains one incremental text fragment.
- `complete` reports latency, token usage, finish reason, and provider request ID.
- `error` safely reports a failure after streaming response headers were sent.

PromptBench currently exposes:

- `GET /health/live` confirms that the web process can serve requests.
- `GET /health/ready` confirms that both provider keys are configured,
  without making a paid provider request.
- `POST /api/generate` validates a prompt and makes one non-streaming provider
  call through the selected direct SDK adapter.
- `POST /api/stream` validates the same request and streams normalized SSE events
  from the selected direct SDK adapter.

The readiness endpoint returns HTTP `503` until both `OPENAI_API_KEY` and
`ANTHROPIC_API_KEY` are available. The application reads local development
values from the ignored `.env` file and uses normal environment variables in
deployed environments.

Generation requests have an 8,000-character prompt limit, a configured total
provider deadline, a model allowlist, and a stable error response. The output
limit remains 64 tokens by default to control learning costs. Default application
logs include provider, model, latency, usage, finish reason, and request IDs, but
exclude API keys, prompts, and model response text. Cancelling the browser request
closes the upstream provider stream.

### Streaming request flow

```mermaid
sequenceDiagram
    participant B as Browser
    participant A as FastAPI
    participant P as Provider adapter
    participant M as OpenAI or Anthropic

    B->>A: POST /api/stream
    A->>B: SSE start
    A->>P: stream(prompt)
    P->>M: Native streaming request
    loop For each text fragment
        M-->>P: Provider delta
        P-->>A: Normalized text delta
        A-->>B: SSE delta
    end
    M-->>P: Provider completion + usage
    P-->>A: Normalized completion
    A-->>B: SSE complete + metrics
    opt Browser cancels or disconnects
        B-xA: Connection closes
        A-xP: Cancel async generator
        P-xM: Close provider stream
    end
```

## Week 1: deployment readiness

PromptBench is configured for a Render Free Python web service through the
repository's [`render.yaml`](render.yaml). The Blueprint installs only locked
production dependencies, starts Uvicorn on the platform-provided port, uses
`/health/ready` as the health check, and waits for GitHub CI before automatically
deploying a commit.

Follow the [Render deployment runbook](docs/RENDER_DEPLOYMENT.md) after the
deployment-readiness pull request is merged. The runbook covers:

- creating the Blueprint and entering provider keys as Render secrets;
- validating health, streaming, cancellation, logs, and cold starts;
- deliberately exercising the safe invalid-key path;
- rolling back a failed deployment; and
- recording Week 1 evidence without committing credentials.

The current Free instance type spins down after 15 minutes without inbound
traffic and can take about one minute to wake. It is suitable for this learning
deployment, not an availability-sensitive production service.

## OpenAI connectivity check

Create a local environment file and add your project API key to it:

```bash
cp .env.example .env
```

Never commit `.env`. Once `OPENAI_API_KEY` is set, install the locked project
and run the low-cost connectivity check:

```bash
uv sync --locked --no-editable
uv run --no-sync --env-file .env openai-check
```

The command uses the Responses API with the model configured by
`OPENAI_MODEL` and does not store the response.

## Anthropic connectivity check

Add `ANTHROPIC_API_KEY` to the same ignored local `.env` file, then run:

```bash
uv sync --locked --no-editable
uv run --no-sync --env-file .env anthropic-check
```

The command sends a minimal Messages API request using the model configured by
`ANTHROPIC_MODEL`.

## Repository hygiene

Commit source code, project configuration, migrations, tests, documentation,
and `uv.lock`. Do not commit virtual environments, secrets, local caches,
logs, or generated build artifacts; these are covered by `.gitignore`.
