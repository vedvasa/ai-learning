# From Notebooks to Production AI Apps

## A 10-week, project-based self-learning guide

Last source verification: August 11, 2026

This program is designed to bridge the exact gap left by a notebook-based applied AI course: how to turn model calls, RAG pipelines, agents, reasoning workflows, and multimodal features into tested software that runs in the cloud.

The central idea is simple: build one product in ten production releases. Every week ends with a live cloud deployment, a test/evaluation result, and an operational artifact such as a dashboard, runbook, migration, or threat model.

The product is **KnowledgeDesk**, a fictional multi-tenant support and research assistant. It starts as a small model gateway and grows into an authenticated AI application that can answer questions over documents, call tools safely, process uploads, run long jobs, and be operated in production.

---

## 1. Working assumptions

This guide assumes:

- You understand Python, Jupyter notebooks, prompts, embeddings, RAG, and the basic idea of agents.
- You have not yet built much with HTTP APIs, web frameworks, containers, CI/CD, managed databases, authentication, or cloud operations.
- You can spend approximately 8–10 focused hours per week.
- Python is your primary language.
- You are willing to use small amounts of paid model API usage, while keeping cloud hosting and databases free wherever practical.
- You will use fictional or public data, never confidential employer or customer data.

You do **not** need React, Kubernetes, microservices, LangChain, or Terraform to begin. Those can all be useful later, but they would obscure the production fundamentals this course is meant to teach.

### Expected outcome

At the end of ten weeks, you should be able to:

1. Build and deploy a Python/FastAPI AI application.
2. Call both OpenAI and Anthropic through direct SDKs.
3. Stream model output to a browser.
4. Validate model output with typed schemas.
5. Handle timeouts, retries, rate limits, and provider errors.
6. Store relational and vector data in managed Postgres with pgvector.
7. Build and evaluate a citation-grounded RAG pipeline.
8. Implement a bounded tool-calling agent with approval gates.
9. Run long AI tasks asynchronously.
10. Authenticate users and isolate tenant data.
11. Containerize and continuously deploy the application.
12. Observe latency, quality, errors, and model cost.
13. Write a threat model, runbook, rollback plan, and production readiness review.

---

## 2. The default stack

| Layer | Default choice | Why it is in the curriculum |
|---|---|---|
| Language | Python 3.12+ | Builds directly on notebook experience |
| Web application | FastAPI, Pydantic, Jinja templates, small amounts of HTMX/JavaScript | Teaches real HTTP APIs and a usable UI without adding a full frontend framework |
| Model providers | OpenAI Responses API and Anthropic Messages API | Learn two native APIs and avoid framework lock-in |
| Database | Supabase Postgres | Managed Postgres, SQL, authentication, object storage, and a free learning tier |
| Vector search | pgvector inside Supabase | Keeps metadata, permissions, text, and vectors transactionally close |
| Optional vector comparison | Qdrant Cloud or Pinecone Starter | Learn how a specialized vector service differs from pgvector |
| First deployment | Render Free | Fastest path from a Git repository to a public URL |
| Main cloud deployment | Google Cloud Run | Teaches containers, revisions, IAM, scaling, logs, secrets, and jobs |
| Long-job queue | Google Cloud Tasks | Production queue semantics with a generous learning allowance |
| Secrets | Local .env only for development; Google Secret Manager in cloud | Keeps credentials out of source and deployment configuration |
| CI/CD | GitHub Actions | Automated linting, tests, evaluation gates, image build, and deploy |
| Testing | pytest, pytest-asyncio, HTTPX, provider fakes | Fast, deterministic tests without spending model tokens |
| Quality | Ruff and a type checker | Makes notebook-style code maintainable as an application |
| Observability | Structured JSON logs, Cloud Logging/Monitoring, custom LLM usage records | Teaches vendor-neutral operational signals first |
| Packaging | A modern Python project file and locked dependencies | Reproducible environments and builds |

### Why direct provider SDKs come first

Use the OpenAI and Anthropic SDKs directly for the first six weeks. Frameworks can make a demo shorter, but they can also hide:

- the HTTP request and response contract;
- streaming event types;
- token usage;
- retry behavior;
- tool-call state;
- provider-specific errors;
- serialization and persistence decisions.

After you have implemented both providers, an abstraction layer will make sense because you will know what it is abstracting. In Week 10, optionally rebuild one workflow with an orchestration framework and compare complexity, observability, portability, and behavior.

---

## 3. Target architecture

~~~mermaid
flowchart LR
    U["Browser"] --> A["FastAPI UI and API<br/>Cloud Run"]
    A --> P["Provider adapters"]
    P --> O["OpenAI Responses API"]
    P --> C["Anthropic Messages API"]
    A --> S["Supabase"]
    S --> DB["Postgres and pgvector"]
    S --> AU["Auth and row-level security"]
    S --> ST["Object storage"]
    A --> Q["Cloud Tasks"]
    Q --> W["Worker endpoint or Cloud Run job"]
    W --> P
    W --> S
    A --> L["Structured logs and metrics"]
    G["GitHub Actions"] --> A
    SM["Secret Manager"] --> A
~~~

This is intentionally a modular monolith, not a collection of microservices. One deployable application is easier to understand and operate. The boundaries inside it—providers, retrieval, agents, jobs, and persistence—can later become separate services if scale or team ownership actually requires it.

---

## 4. Repository structure to grow toward

~~~text
knowledgedesk/
├── app/
│   ├── main.py
│   ├── api/
│   │   ├── health.py
│   │   ├── chat.py
│   │   ├── documents.py
│   │   └── jobs.py
│   ├── core/
│   │   ├── config.py
│   │   ├── errors.py
│   │   ├── logging.py
│   │   └── security.py
│   ├── providers/
│   │   ├── base.py
│   │   ├── openai_provider.py
│   │   └── anthropic_provider.py
│   ├── retrieval/
│   │   ├── chunking.py
│   │   ├── embeddings.py
│   │   ├── search.py
│   │   └── citations.py
│   ├── agents/
│   │   ├── loop.py
│   │   ├── tools.py
│   │   └── approvals.py
│   ├── workers/
│   │   ├── ingestion.py
│   │   └── research.py
│   ├── templates/
│   └── static/
├── migrations/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── evals/
│   └── fixtures/
├── docs/
│   ├── architecture.md
│   ├── threat-model.md
│   ├── runbook.md
│   └── decisions/
├── scripts/
├── .github/workflows/
├── .env.example
├── Dockerfile
├── pyproject.toml
└── README.md
~~~

Do not create every directory on day one. Add a boundary when a week creates a real responsibility for it.

---

## 5. Cost and free-tier strategy

Free tiers are excellent learning environments, but they are not production service-level agreements. They can sleep, pause, throttle, change, or disappear. Treat “production” in this program as **production engineering practice on learning-scale infrastructure**.

### Recommended two-track approach

#### Track A: lowest-friction and nearly zero cloud cost

- Render Free for the web service.
- Supabase Free for Postgres, pgvector, Auth, and Storage.
- GitHub Actions for CI.
- Paid model APIs with strict usage caps.

Trade-offs: Render Free sleeps after inactivity and has an ephemeral filesystem. Supabase Free projects can pause after inactivity and do not include production backup guarantees. Long-running jobs require a simplified learning implementation.

#### Track B: more realistic cloud engineering

- Google Cloud Run with request-based billing and zero minimum instances.
- Google Secret Manager.
- Google Cloud Tasks.
- Supabase Free.
- GitHub Actions.
- Paid model APIs with strict usage caps.

Trade-offs: Google Cloud requires an active billing account. Free usage is an allowance, not a hard guarantee of a zero invoice. Set a spend cap where available, a budget alert, maximum Cloud Run instances, and provider spend limits before deploying.

### Verified learning-scale allowances

These figures were verified on August 11, 2026 and can change. Recheck the linked page before creating resources.

| Service | Learning-scale allowance or caveat |
|---|---|
| Render Free | Free web services; spin down after 15 minutes idle; 750 running instance-hours per workspace each month; ephemeral filesystem; Render explicitly says not to use the free tier for production |
| Supabase Free | Two active projects; 500 MB database per project; 1 GB file storage; free projects pause after one week of inactivity |
| Qdrant Cloud Free | No card required; one node, 1 GB RAM, 0.5 vCPU, 4 GB disk; idle clusters suspend and can later be deleted |
| Pinecone Starter | Free; up to five indexes, 2 GB database storage, monthly read/write allowances, one project |
| Cloud Run request-based free tier | 2 million requests, 180,000 vCPU-seconds, and 360,000 GiB-seconds per month; billing account required |
| Cloud Tasks | First 1 million billable operations per month are free |
| Secret Manager | Six active secret versions and 10,000 access operations per month are free |
| GitHub Actions | Standard hosted runners are free for public repositories; private repositories receive an included quota based on account plan |

### Model API budget

Assume that model API use is paid:

- A ChatGPT subscription does not pay for OpenAI API calls.
- A Claude subscription does not include Anthropic API usage.
- Anthropic documents API billing as prepaid usage credits.
- Account availability, introductory credits, and rate limits can vary.

For this curriculum:

1. Add only a small initial balance.
2. Disable automatic reload until you understand usage.
3. Set a provider/project spend limit where supported.
4. Default to a low-cost, current model through configuration rather than hardcoding a model name throughout the app.
5. Use deterministic fakes for unit tests.
6. Use 10–30 cases for development evaluations, not thousands.
7. Cache embeddings by content hash.
8. Record input tokens, output tokens, estimated cost, provider, model, latency, and outcome for every call.
9. Reserve expensive reasoning, web search, and image generation for a handful of explicit tests.

A reasonable learning target is **$10–$30 total in model calls across ten weeks**, but it is not a guarantee. Web research, large documents, repeated evaluation runs, images, and high-capability models can exceed it quickly.

OpenAI currently recommends its Responses API for new projects. Its small embedding model is priced at $0.02 per million input tokens at the time of verification, which makes a small course corpus inexpensive. Always check the live pricing pages before a batch job.

---

## 6. Weekly operating rhythm

Use the same cadence every week:

| Session | Time | Activity |
|---|---:|---|
| A | 60–90 min | Learn the production concepts and sketch the request/data flow |
| B | 2 hours | Build the thinnest end-to-end vertical slice |
| C | 2–3 hours | Add reliability, persistence, or security requirements |
| D | 2 hours | Test, evaluate, deploy, and deliberately trigger one failure |
| E | 45–60 min | Document cost, architecture decisions, failures, and the next improvement |

### The rule that prevents endless tutorials

Do not watch or read for more than 90 minutes without changing the project. Every concept must become one of:

- a code path;
- a test;
- a database migration;
- a cloud configuration;
- an evaluation;
- a runbook entry;
- an architecture decision record.

---

## 7. Ten-week roadmap

| Week | Deployed project release | Main production lesson |
|---:|---|---|
| 1 | PromptBench: multi-provider streaming playground | HTTP, FastAPI, direct SDKs, configuration, secrets, deployment |
| 2 | Ticket Triage API | Structured outputs, reliability, tests, Docker, CI/CD |
| 3 | Citation Q&A | Managed Postgres, pgvector, ingestion, semantic retrieval |
| 4 | RAG Quality Lab | Hybrid search, indexing, retrieval evaluation, release gates |
| 5 | Support Action Agent | Tool calling, bounded loops, approval, idempotency, audit |
| 6 | Deep Research Jobs | Queues, background work, polling/streaming, cancellation, webhooks |
| 7 | Multimodal Intake | File storage, image/PDF processing, provenance, lifecycle |
| 8 | Multi-tenant KnowledgeDesk | Authentication, row-level security, rate limits, AI security |
| 9 | Operated AI Service | Observability, SLOs, load tests, fallbacks, cost and incident response |
| 10 | Capstone release | Staging/production, rollback, runbook, architecture review, demo |

---

# Week 1 — PromptBench: from Python function to deployed service

## Goal

Build a small web application that can send a prompt to either OpenAI or Anthropic, stream the answer, and report latency and token usage. Deploy it to Render Free.

## Concepts to learn

- What an HTTP request contains: method, URL, headers, JSON body, status code.
- Client versus server responsibilities.
- Environment variables and why an API key must never reach browser JavaScript.
- FastAPI routes, Pydantic request/response models, dependency injection.
- Sync versus async I/O.
- Server-sent events for streaming.
- Provider SDK request and response objects.
- Process startup, ports, health checks, and stateless deployment.

## Build

Create:

- GET /health/live returning process liveness.
- GET /health/ready checking required configuration without calling a paid API.
- POST /api/generate for a non-streaming response.
- POST /api/stream for server-sent events.
- A small page with prompt, provider, model, and output controls.
- One OpenAI adapter using the Responses API.
- One Anthropic adapter using the Messages API.
- A normalized result containing text, provider, model, latency, input tokens, output tokens, finish reason, and request ID.

Keep provider-specific response objects inside provider modules. The route should depend on a small internal interface, not SDK types.

## Reliability requirements

- Reject an empty prompt and an excessive input length.
- Apply a total request timeout.
- Return a stable application error shape.
- Do not include API keys, prompts, or full model responses in default logs.
- Generate or accept a correlation/request ID.
- Handle a client disconnect during streaming.

## Tests

- Unit-test both provider adapters with fake SDK clients.
- Test validation and error mapping.
- Test the two health endpoints.
- Test the API route without a real provider call.
- Run one manual smoke test against each paid provider.

## Deploy

1. Push the repository to GitHub.
2. Create a Render Free web service from the repository.
3. Store provider keys as Render environment secrets.
4. Bind the server to 0.0.0.0 and the platform-provided port.
5. Configure the readiness endpoint as the health check.
6. Verify that a cold service recovers after spin-down.

## Acceptance test

The week is complete when:

- A public URL renders the UI.
- Both providers work through server-side calls.
- Streaming visibly delivers partial output.
- A missing/invalid key produces a safe error.
- No secret appears in Git history, source, browser developer tools, or logs.
- The README documents local start, deployment, and one known free-tier limitation.

## Evidence to keep

- Live URL.
- Screenshot of a streamed response.
- Test output.
- One request/response sequence diagram.
- A note showing the cost of five representative calls.

## Stretch goal

Add a “compare” mode that runs both providers concurrently and shows quality, latency, and cost side by side. Do not declare a universal winner; record results for a defined task.

---

# Week 2 — Ticket Triage API: reliability and continuous delivery

## Goal

Turn free-form support tickets into validated structured data, then package and deploy the service as a container to Cloud Run.

## Product behavior

Given a support ticket, return:

- category;
- priority;
- summary;
- sentiment;
- requested action;
- whether human review is required;
- a confidence value;
- a short rationale safe for end-user display.

## Concepts to learn

- JSON Schema and typed structured output.
- Schema validation versus trusting model prose.
- Retries with exponential backoff and jitter.
- Which errors are retryable: rate limits, overload, connection failure, selected 5xx responses.
- Why invalid requests and most 4xx responses are not retryable.
- Deadlines, timeouts, and cancellation.
- Idempotency and duplicate request handling.
- Unit, integration, smoke, and evaluation tests.
- Container images, layers, build context, and non-root execution.
- CI versus CD.

## Build

- Define a provider-neutral TicketTriage Pydantic model.
- Request schema-conforming output from both providers.
- Validate every response before storing or returning it.
- Map provider errors to stable internal exceptions.
- Add a retry policy with a strict total deadline.
- Add request-level maximum output tokens.
- Add an in-memory development usage recorder, behind an interface that will move to Postgres next week.
- Add a command-line batch mode for a folder of ticket fixtures.

## Container requirements

- Pin runtime and dependencies.
- Use a small base image.
- Run as a non-root user.
- Copy dependency metadata before application code to improve build caching.
- Include a container health check only if the target platform uses it correctly.
- Do not bake secrets into image layers or build arguments.
- Verify that the image starts with only documented environment variables.

## CI pipeline

On every pull request:

1. install locked dependencies;
2. run linting;
3. run type checks;
4. run unit and API tests;
5. build the Docker image;
6. run a container smoke test;
7. fail without calling a paid model.

On an approved merge:

1. build or deploy the revision;
2. inject secrets from Secret Manager;
3. direct traffic to the new revision;
4. run a public smoke test;
5. retain a documented rollback command.

Use GitHub-to-cloud identity federation when you are ready; do not create a long-lived cloud administrator key just to make CI convenient.

## Cloud cost controls before deployment

- Create a small budget or spend cap where available.
- Remember that an alerts-only Google Cloud budget does not itself stop spending.
- Set Cloud Run minimum instances to zero.
- Set maximum instances to a small number such as one or two.
- Use request-based billing.
- Keep the service in an eligible region.
- Store only the small number of active secret versions needed.

## Evaluation

Create 30 synthetic tickets with expected categories and priorities.

Report:

- category accuracy;
- priority accuracy;
- schema-valid response rate;
- human-review recall for high-risk examples;
- p50 and p95 latency;
- mean input/output tokens;
- estimated cost per 100 tickets.

## Acceptance test

- The same container runs locally and on Cloud Run.
- All invalid model output is caught before it reaches the API client.
- A simulated 429 retries, honors the deadline, and emits one final error.
- CI runs without provider credentials.
- A tagged release is reproducible.
- The previous Cloud Run revision can be restored.

## Stretch goal

Batch the 30-case evaluation through an asynchronous provider batch API and compare price, latency, and implementation complexity with synchronous calls.

---

# Week 3 — Citation Q&A: production RAG foundations

## Goal

Build an ingestion and question-answering application over 20–50 fictional support documents using Supabase Postgres and pgvector.

## Corpus

Create small Markdown documents for a fictional product:

- account and billing;
- refunds;
- shipping;
- security;
- data retention;
- plan limits;
- troubleshooting;
- service status;
- escalation policy.

Each document must have an ID, title, source URL or canonical path, version, updated timestamp, tenant ID, and visibility.

## Concepts to learn

- Data modeling before embeddings.
- Chunking as an information retrieval decision.
- Content hashes and idempotent ingestion.
- Embedding model/dimension compatibility.
- Exact versus approximate nearest-neighbor search.
- Cosine distance, inner product, and L2 distance.
- Database migrations and reproducible schema.
- Connection pooling in serverless applications.
- Citation grounding and abstention.
- The difference between retrieval failure and generation failure.

## Database schema

At minimum, model:

- documents;
- document_versions;
- chunks;
- ingestion_jobs;
- conversations;
- messages;
- model_calls.

Each chunk should store:

- document/version foreign key;
- chunk index;
- text;
- token count;
- metadata;
- content hash;
- embedding;
- embedding model;
- embedding dimension;
- created timestamp.

Do not silently mix embeddings from different models in one searchable column.

## Ingestion pipeline

Implement a command or worker that:

1. reads a document;
2. normalizes the content;
3. calculates a content hash;
4. skips an unchanged document;
5. creates semantic chunks with overlap only where justified;
6. batches embedding calls;
7. stores text, metadata, and embeddings in a transaction;
8. marks the version active;
9. records failures without leaving a half-active version.

Cache embeddings by content hash so redeploying does not pay to embed unchanged text.

## Query pipeline

1. Validate the question and tenant.
2. Embed the question.
3. retrieve top candidates with metadata filters.
4. Apply a similarity threshold established through testing.
5. Build context with stable chunk IDs and source metadata.
6. Ask the model to use only supplied evidence.
7. Return answer, inline citations, source list, retrieval scores, and an abstention flag.
8. Store the observable inputs/outputs needed for evaluation, with privacy-aware redaction.

## Tests

- Chunk boundaries preserve headings and source identity.
- Reingesting an unchanged file creates no duplicate active chunks.
- Metadata filtering prevents cross-tenant retrieval.
- The query uses the intended distance operator and index-compatible ordering.
- Missing evidence causes an abstention.
- Every displayed citation refers to a retrieved chunk.

## Deployment

- Enable pgvector through a migration.
- Store the Supabase server credential only on the backend.
- Use the platform connection pooler appropriate for serverless clients.
- Deploy the updated container.
- Run ingestion as an explicit command/job, not on every web-process startup.
- Verify that restarting or scaling the application loses no persistent data.

## Acceptance test

Prepare 20 questions:

- 12 answerable;
- 4 ambiguous;
- 4 intentionally unanswerable.

The release passes when:

- at least one relevant source is retrieved for most answerable questions;
- all citations point to actual stored chunks;
- cross-tenant filtering is tested;
- unanswerable questions usually abstain rather than invent;
- reingestion is idempotent;
- the live application survives a web instance restart.

## Stretch goal

Implement the same collection in Qdrant Cloud or Pinecone Starter. Compare data modeling, filters, local development, index control, operational visibility, pricing, and migration effort. Avoid comparing only query speed on a tiny corpus.

---

# Week 4 — RAG Quality Lab: measure before adding complexity

## Goal

Turn the Week 3 RAG demo into an evaluated retrieval system with hybrid search, appropriate indexing, and a release-quality dashboard.

## Concepts to learn

- Retrieval metrics: hit rate, recall at k, mean reciprocal rank.
- Answer metrics: correctness, faithfulness/groundedness, citation correctness, abstention.
- Latency and cost as quality dimensions.
- Golden datasets and versioning.
- Full-text versus semantic search.
- Reciprocal rank fusion.
- Metadata filtering before and after retrieval.
- HNSW index behavior and the recall/latency/memory trade-off.
- Why an LLM judge needs calibration against human labels.

## Build a golden dataset

Create a versioned JSONL or database dataset with at least 40 examples:

- user question;
- tenant/user context;
- expected relevant document IDs;
- key answer facts;
- whether the system should abstain;
- difficulty and category;
- adversarial notes where applicable.

Write 10 labels yourself before using any model-assisted labeling. Human labels are the reference, not the judge model.

## Retrieval experiments

Run controlled comparisons:

1. vector-only search;
2. keyword/full-text search;
3. hybrid search using reciprocal rank fusion;
4. hybrid search plus metadata filters;
5. optional reranking of the top candidate set.

Change one variable at a time:

- chunk size;
- overlap;
- top k;
- threshold;
- distance measure;
- prompt;
- model;
- reranker.

Record the configuration with each result.

## Index work

- Create the HNSW index in a migration.
- Use an operator class that matches the query distance operator.
- inspect the query plan.
- Measure with and without the index.
- Explain why a 50-document corpus cannot prove production scalability.
- Document how index build time, writes, memory, and recall would change at larger scale.

## Evaluation command

Create one command that:

- runs the fixed dataset;
- can use recorded/fake generation for retrieval-only runs;
- produces machine-readable JSON and a human-readable Markdown summary;
- reports metrics by category;
- records latency, tokens, and estimated cost;
- compares the current result to a checked-in baseline;
- exits nonzero when a critical threshold regresses.

Suggested initial gates:

- retrieval hit rate at 5 does not fall more than five percentage points;
- citation validity is 100 percent;
- cross-tenant leakage is zero in the test set;
- schema-valid results are at least 99 percent;
- total evaluation cost remains below a configured maximum.

Tune the values to the application instead of treating these as universal standards.

## Acceptance test

- A single command reproduces the evaluation.
- The report identifies at least one case where vector search wins and one where keyword search wins.
- Hybrid search improves a chosen metric or is rejected with evidence.
- A deliberately degraded chunker causes CI to fail its quality gate.
- The live deployment exposes its application version and evaluation dataset version.

## Stretch goal

Build a small admin-only page that displays failure cases rather than only aggregate scores. Reviewing failures is more valuable than celebrating a single average.

---

# Week 5 — Support Action Agent: tools without uncontrolled autonomy

## Goal

Add an agent that can answer support questions and propose or execute a small set of fake customer-service actions.

## Tools

Implement a deliberately narrow set:

- get_order_status;
- look_up_account_plan;
- calculate_refund_eligibility;
- create_support_draft;
- request_refund_approval;
- execute_fake_refund.

The first four are read-only or reversible. The last two demonstrate approval and side-effect boundaries.

## Concepts to learn

- Tool schemas and the model/tool contract.
- The application, not the model, executes client tools.
- Agent loop state and termination.
- Tool authorization versus model choice.
- Input validation and output sanitization.
- Idempotency keys for side effects.
- Least privilege.
- Human approval.
- Audit logs.
- Maximum turns, maximum tools, time budget, and spend budget.
- Deterministic workflows versus open-ended agents.

## Build the loop yourself

Implement:

1. send user request, instructions, and allowed tool schemas;
2. inspect the provider response;
3. if it requests a tool, validate the name and arguments;
4. authorize the tool against the authenticated user and current state;
5. require approval for side effects;
6. execute through application code;
7. record the result and audit event;
8. return the tool result to the model;
9. stop on a final answer or a hard limit.

Normalize OpenAI and Anthropic tool events inside the provider adapters, but retain raw provider identifiers for troubleshooting.

## Safety rules

- Never dynamically import or execute a function named by the model.
- Never let the model create SQL, shell commands, or URLs that are executed without a constrained interpreter and validation.
- Authorize every tool in code, even when the system prompt says a user lacks permission.
- Treat retrieved documents and tool results as untrusted data, not instructions.
- Require a fresh approval bound to exact action arguments.
- Hash or sign approval state so arguments cannot change after approval.
- Use an idempotency key for every side effect.
- Record who requested, who approved, what ran, and what result occurred.
- Set a maximum number of loop turns and tool calls.

## Evaluation

Create cases for:

- correct tool selection;
- no tool needed;
- missing required arguments;
- user asks for a disallowed tool;
- malicious document tells the model to issue a refund;
- prompt asks the model to ignore approval;
- duplicate delivery of an approved request;
- tool timeout;
- tool returns malformed data;
- the model repeatedly calls the same tool.

Report:

- task success;
- correct tool rate;
- unauthorized action count;
- duplicate side-effect count;
- average turns;
- average tool calls;
- latency and cost.

The unauthorized and duplicate action counts must be zero.

## Acceptance test

- Read-only tools can run automatically.
- A refund proposal pauses and shows exact arguments.
- Execution requires explicit approval.
- Replaying the same approved request does not repeat the side effect.
- A prompt injection cannot expand the tool allowlist.
- The audit trail reconstructs the full action.
- Both model providers can complete the normalized loop.

## Stretch goal

Implement the same workflow once as deterministic application code with the model used only for classification and parameter extraction. Compare reliability and decide which steps genuinely require an agent.

---

# Week 6 — Deep Research Jobs: asynchronous AI workflows

## Goal

Build a web research feature that can take longer than a normal browser request and still be safe to retry, observe, cancel, and resume.

## User flow

1. User submits a research question.
2. API validates it and creates a job row.
3. API enqueues a small job message containing only identifiers.
4. Worker claims the job.
5. Worker gathers sources through an approved search API/tool.
6. Worker extracts evidence and synthesizes a cited report.
7. UI polls or subscribes to progress.
8. User can cancel before finalization.
9. Finished output is stored and can be reopened.

## Concepts to learn

- Why long work should not remain attached to one browser request.
- Queue delivery is generally at least once, not magically exactly once.
- Idempotent consumers.
- Lease/claim state.
- Retries and dead-letter handling.
- Job states and valid transitions.
- Progress events.
- Polling versus SSE versus webhooks.
- Webhook signature verification.
- Cancellation and cooperative deadlines.
- Fan-out limits and source budgets.

## Suggested state machine

~~~text
queued -> running -> succeeded
   |         |          |
   |         +-> retrying
   |         +-> failed
   |         +-> cancelled
   +-> cancelled
~~~

Prevent impossible transitions at the data/service layer.

## Build

- POST /api/research-jobs returns 202 Accepted and a job ID.
- GET /api/research-jobs/{id} returns state and progress.
- POST /api/research-jobs/{id}/cancel requests cancellation.
- Worker endpoint accepts authenticated queue delivery only.
- Store attempt number, timestamps, error code, last heartbeat, cost, and provider request IDs.
- Use an idempotency key derived from job and stage.
- Put full task data in Postgres/object storage, not the queue payload.
- Limit searches, sources, pages, tokens, wall time, and model spend per job.
- Require source URLs and evidence notes before synthesis.

## Cloud deployment

Use Cloud Tasks for push delivery to a private or authenticated Cloud Run worker endpoint. The first million operations per month are free at the time of verification, but search and model calls are not.

Alternative for the no-billing track: use a Postgres jobs table and a manually invoked worker command. Document clearly that this lacks a managed queue’s delivery, authentication, throttling, and retry guarantees.

## Failure drills

- Kill the worker mid-job.
- Deliver the same queue task twice.
- Return a transient 500.
- Return a permanent validation error.
- Exceed the source budget.
- Cancel during synthesis.
- Make one source unavailable.
- Simulate an invalid webhook signature.

## Acceptance test

- The create request returns quickly.
- Duplicate delivery does not duplicate the report or charges for a completed stage.
- A transient failure retries.
- A permanent failure stops.
- Progress remains visible after a worker restart.
- Cancellation is honored at stage boundaries.
- Every factual paragraph in the final report links to its stored evidence.

## Stretch goal

Add a provider fallback only for a clearly classified transient outage. Record that a fallback can change output quality and must be evaluated, not treated as a transparent network retry.

---

# Week 7 — Multimodal Intake: files, images, and provenance

## Goal

Let a user upload a screenshot or PDF, extract structured support information, and optionally add approved content to the RAG corpus.

## Example behavior

Upload:

- a product error screenshot;
- an invoice image;
- a short PDF manual;
- a scanned troubleshooting sheet.

Return:

- file type and safe metadata;
- extracted text;
- product/error identifiers;
- a short description;
- confidence/warnings;
- page/image references;
- a proposed support ticket;
- an explicit choice to discard or ingest.

## Concepts to learn

- Multipart upload and signed upload URLs.
- Object storage instead of container filesystems.
- MIME sniffing versus trusting a filename.
- File size, page count, and pixel limits.
- Malware scanning boundary and unsupported formats.
- EXIF/metadata privacy.
- OCR/text extraction versus vision-model interpretation.
- Provenance from derived content back to file/page/region.
- Lifecycle deletion.
- Asynchronous processing.
- Multimodal API cost.

## Build

- Store uploads in Supabase Storage under tenant-scoped object paths.
- Use short-lived signed URLs where appropriate.
- Validate actual content type and enforce a small limit.
- Generate a content hash to deduplicate uploads.
- Create a processing job rather than holding the upload request open.
- Extract machine text from PDFs before paying a vision model to inspect pages.
- Use vision only when layout or imagery matters.
- Validate extracted output with Pydantic.
- Store page-level provenance.
- Require user confirmation before new material becomes retrievable.
- On deletion, remove object, derived text, chunks, embeddings, and active references.

## Security tests

- Double-extension filename.
- Claimed image that is a different type.
- Oversized decompression or page count.
- PDF text containing prompt injection.
- Image telling the model to reveal its instructions.
- One tenant guesses another tenant’s object key.
- Deleted file still appears in retrieval.

Treat text extracted from a file as untrusted content. It may be evidence, but it is not a new system instruction.

## Evaluation

Build a 15-file fixture set and score:

- schema validity;
- field accuracy;
- page/source attribution;
- duplicate detection;
- processing time;
- cost per file;
- deletion completeness.

## Acceptance test

- Uploads persist across app restarts.
- Private files are not publicly enumerable.
- One tenant cannot access another tenant’s object.
- Failed processing can retry without duplicate chunks.
- Ingestion requires explicit confirmation.
- Deletion removes derived vectors and source references.
- The UI displays the original source/page for extracted claims.

## Stretch goal

Generate a small visual troubleshooting card from an approved answer. Store model, prompt version, source facts, and generation cost with the asset.

---

# Week 8 — Multi-tenant KnowledgeDesk: identity, isolation, and AI security

## Goal

Turn the demo into a small SaaS-style application with users, organizations, roles, tenant-isolated data, quotas, and an AI-specific threat model.

## Concepts to learn

- Authentication versus authorization.
- Sessions/JWTs and server-side verification.
- Organizations, memberships, and roles.
- Postgres row-level security.
- Service credentials and why they bypass user policies.
- Rate limiting and quotas.
- Abuse prevention.
- Data retention and deletion.
- Prompt injection, sensitive disclosure, improper output handling, excessive agency, vector weaknesses, and unbounded consumption.
- Security controls in code versus instructions in a prompt.

## Data model

Add:

- users/profile mapping;
- organizations;
- organization_members;
- roles/permissions;
- per-tenant projects or knowledge bases;
- quotas;
- audit_events;
- deletion_requests.

Every tenant-owned row must carry a tenant/organization ID or derive it through an enforced relationship.

## Build

- Use Supabase Auth for sign-in.
- Verify identity on the backend.
- Authorize operations server-side.
- Add row-level security policies.
- Test policies using two tenants and multiple roles.
- Make admin/service credentials available only to narrowly scoped backend operations.
- Add per-user and per-tenant request/token budgets.
- Add input length, upload, job, and tool-call limits.
- Redact or avoid logging sensitive content.
- Add a privacy-aware safety identifier where the provider recommends it.
- Create data export and delete flows for the learning app.

## Threat model

Document:

1. assets: API keys, tenant documents, billing, audit trail, user identity;
2. trust boundaries: browser, API, provider, database, storage, queue, external web;
3. attacker capabilities;
4. abuse cases;
5. controls;
6. residual risk;
7. detection and response.

Include at least:

- direct prompt injection;
- indirect injection in retrieved/uploaded content;
- cross-tenant vector retrieval;
- forged approval;
- excessive tool privilege;
- model output rendered as unsafe HTML;
- API key exposure;
- unlimited token/job use;
- poisoned documents;
- deletion gaps.

## Security test suite

- Tenant A cannot query, fetch, cite, or delete Tenant B data.
- User role cannot run admin tools.
- A retrieved instruction cannot change tool authorization.
- Model output is escaped before HTML rendering.
- Rate limit applies even when requests run concurrently.
- Invalid/expired identity is rejected.
- Service-role code paths cannot be reached from arbitrary user input.
- Deleted tenants lose all active access and derived vector data.

## Acceptance test

- Two real test accounts demonstrate isolation.
- RLS tests run in CI against an ephemeral or dedicated test database.
- All high-risk actions use application authorization and approval.
- The threat model maps each major threat to a test or operational control.
- A per-tenant limit stops runaway usage safely.
- Logs can investigate an abuse event without exposing full sensitive content.

## Stretch goal

Replace one static provider API key with workload identity federation if your provider and cloud account support it. Compare secret rotation and blast radius with a long-lived key.

---

# Week 9 — Operated AI Service: observability, SLOs, and failure engineering

## Goal

Make the system operable by someone who did not write it. Add useful telemetry, service objectives, alerts, load tests, model-quality monitoring, and incident drills.

## The four signal groups

### Application

- request rate;
- error rate by stable error code;
- p50/p95/p99 latency;
- active requests;
- deployment version;
- cold starts;
- database/queue latency.

### Model

- provider and model;
- input/output/cached/reasoning tokens where available;
- time to first token and total latency;
- rate-limit/retry count;
- finish/stop reason;
- tool calls and loop turns;
- estimated cost;
- refusal, invalid schema, or fallback outcome.

### Retrieval and quality

- retrieval latency;
- candidate count;
- top scores;
- empty retrievals;
- citation validity;
- answer/abstention rate;
- golden-set metrics by release;
- user feedback as a weak signal, not ground truth.

### Business/abuse

- tasks completed;
- escalations;
- approvals accepted/rejected;
- duplicate side effects prevented;
- per-tenant quota use;
- suspicious prompt/upload/tool patterns.

## Concepts to learn

- Logs, metrics, and traces are different.
- Correlation IDs across API, queue, model, database, and tool calls.
- Structured logging.
- Service-level indicators and objectives.
- Alerting on symptoms rather than every internal event.
- Load testing streaming and long requests.
- Concurrency and downstream saturation.
- Circuit breakers, fallbacks, and graceful degradation.
- Canary release and rollback.
- Online monitoring versus offline evaluation.

## Define initial SLOs

For the learning deployment, choose explicit targets such as:

- 99 percent successful response rate excluding validated user errors;
- p95 non-research API latency below a chosen value;
- 100 percent citation link validity;
- zero unauthorized tool actions;
- zero cross-tenant test leakage;
- monthly model spend below the learning budget.

The numeric values matter less than learning to define, measure, and act on them.

## Build

- Emit JSON logs with request ID, tenant hash, route, version, duration, outcome, and safe provider metadata.
- Propagate one correlation ID into jobs and tool audit events.
- Persist model usage records.
- Create a dashboard for traffic, errors, latency, model cost, and job outcomes.
- Add alerts for error-rate spikes, repeated queue failure, and budget threshold.
- Keep alert cardinality bounded.
- Add a provider health/fallback policy.
- Add load-shedding or a small concurrency limit before downstream providers collapse.
- Add an admin view for recent failures and failed evaluation cases.

## Load tests

Test separately:

- health endpoint;
- non-streaming generation with a fake provider;
- streaming with a fake timed provider;
- database retrieval;
- job creation;
- authenticated rate limiting.

Do not accidentally load-test paid model APIs. Use a fake provider unless the test explicitly has a tiny cost budget.

Measure:

- throughput;
- p95 latency;
- error rate;
- container count;
- DB connections;
- memory;
- queue depth;
- rejected requests.

## Incident drills

Run and document:

1. primary model provider returns 429;
2. provider is slow;
3. database connections are exhausted;
4. bad deployment increases schema errors;
5. retrieval index is missing;
6. queue backlog grows;
7. API key is suspected leaked;
8. cost alert fires;
9. tenant reports a bad citation;
10. rollback is required.

For each: detection, immediate mitigation, diagnosis, recovery, and follow-up prevention.

## Acceptance test

- A dashboard answers “is it working, is it fast, is it good, and what is it costing?”
- Every model call is attributable to a request/job without storing unnecessary raw content.
- The load test finds a capacity limit and the app fails predictably.
- One alert is triggered intentionally and resolved.
- The runbook restores the previous revision.
- A model/prompt change cannot deploy when the golden evaluation regresses beyond its gate.

## Stretch goal

Add distributed tracing with OpenTelemetry and inspect one request across API, retrieval, provider, and tool spans. Avoid recording sensitive prompt bodies as trace attributes.

---

# Week 10 — Capstone: production readiness release

## Goal

Ship a coherent KnowledgeDesk release and defend its architecture, quality, safety, cost, and operational plan.

## Required user capabilities

- Sign in and select an organization.
- Upload and approve a document.
- Ask a question and receive source-grounded citations.
- Switch between configured providers without changing product code.
- Submit a long research job and observe progress.
- Propose a tool action and explicitly approve or reject it.
- View past jobs/conversations allowed for the current tenant.
- Delete an uploaded source and its derived data.

## Required engineering capabilities

- Reproducible local setup.
- Locked dependencies.
- Database migrations from empty state.
- Containerized application.
- Automated CI tests.
- Automated or documented cloud deployment.
- Separate staging and production configuration, even if staging is temporary.
- Secret management.
- Health/readiness endpoints.
- Auth and tenant isolation.
- Offline evaluation gate.
- Structured logs and usage/cost records.
- Bounded concurrency and maximum instances.
- Rollback procedure.
- Backup/restore discussion appropriate to the chosen free tier.
- Threat model.
- Runbook.
- Architecture decision records.

## Production readiness review

Answer in writing:

### Product

- Who is the user?
- Which task is improved?
- When should the system abstain or escalate?
- What is the harm from a wrong answer?

### Model

- Why was each model selected?
- What changes when the configured model alias moves?
- Which workflows require reasoning versus a small/fast model?
- How are prompt and model versions recorded?

### RAG

- What is the source of truth?
- How is stale content replaced?
- How is access control applied before retrieval?
- What metrics show retrieval quality?
- How does deletion reach embeddings and caches?

### Agent

- Why is every tool necessary?
- Which tools have side effects?
- Where are authorization and approval enforced?
- How are duplicate actions prevented?
- What are the loop and cost limits?

### Reliability

- What is retried?
- What is never retried?
- Which operations are idempotent?
- How does the system degrade when a provider is unavailable?

### Security and privacy

- Where are secrets stored?
- What user content is logged?
- How are uploads and retrieved content treated as untrusted?
- How is tenant isolation tested?
- How would a leaked key be rotated?

### Operations

- What are the SLOs?
- Which alerts require action?
- What is the rollback command?
- How are costs capped or detected?
- What happens if the free database pauses or disappears?

## Final evaluation

Run:

- the full unit/integration suite;
- the RAG golden set;
- tool safety cases;
- tenant isolation tests;
- upload security tests;
- container smoke test;
- small fake-provider load test;
- one real-provider end-to-end smoke test per provider.

Publish a release report containing:

- commit and deployment revision;
- schema/migration version;
- prompt/model configuration;
- evaluation dataset version;
- quality metrics;
- p95 latency;
- estimated cost per common task;
- known limitations;
- go/no-go decision.

## Demo format

Prepare a 10-minute demo:

1. 60 seconds: user problem and architecture.
2. 3 minutes: upload, RAG answer, citations.
3. 2 minutes: tool proposal and approval.
4. 1 minute: asynchronous research job.
5. 1 minute: evaluation and operational dashboard.
6. 1 minute: security/failure example.
7. 1 minute: cost, limitations, and next step.

## Capstone acceptance test

The capstone is complete only when a new reader can:

- clone the repository;
- configure it from .env.example without receiving a secret;
- run tests;
- build the container;
- create the schema;
- deploy a revision;
- run the smoke/evaluation commands;
- roll back using the runbook.

---

## 8. Weekly definition of done

Use this checklist every week:

- [ ] A live cloud URL or job exists.
- [ ] The release has a Git tag.
- [ ] README setup works from a clean clone.
- [ ] .env.example lists names, never values.
- [ ] No secret is committed or exposed to the browser.
- [ ] Dependencies are locked.
- [ ] Lint, types, and deterministic tests pass in CI.
- [ ] A health/readiness check exists.
- [ ] A request/correlation ID appears in safe logs.
- [ ] Errors use a stable application shape.
- [ ] At least one paid-provider smoke test is recorded.
- [ ] At least one failure is deliberately tested.
- [ ] Model usage/cost is recorded.
- [ ] Evaluation results are saved and compared with a baseline.
- [ ] Database changes are migrations, not dashboard-only memory.
- [ ] Free-tier limitations are documented.
- [ ] The prior release can be restored.
- [ ] Known limitations and next risks are written down.

If a week runs long, cut a feature—not testing, deployment, cost recording, or failure handling.

---

## 9. Evaluation ladder

The evaluation strategy grows with the product:

| Week | Minimum evaluation |
|---:|---|
| 1 | Provider contract, streaming completion, error mapping |
| 2 | 30-ticket classification set, schema rate, latency, cost |
| 3 | Retrieval hit at k, citation validity, abstention |
| 4 | Versioned golden set and CI regression gate |
| 5 | Tool selection, authorization, duplication, loop limits |
| 6 | Job idempotency, retry, cancellation, evidence coverage |
| 7 | Extraction accuracy, provenance, deletion completeness |
| 8 | Cross-tenant and prompt-injection security suite |
| 9 | SLO dashboard, load test, incident drill |
| 10 | Full release report and go/no-go review |

Three rules:

1. Keep evaluation data separate from prompt examples where possible.
2. Review individual failures, not only aggregate scores.
3. Do not let an LLM judge be the sole authority for safety, authorization, correctness, or tenant isolation.

---

## 10. Production patterns to internalize

### Provider boundary

Normalize only product concepts:

- input messages;
- requested output schema;
- text/events;
- tool requests/results;
- usage;
- finish reason;
- provider error category.

Do not pretend providers are identical. Preserve raw provider request IDs and feature-specific metadata for troubleshooting.

### Retry boundary

Retry only operations known to be safe:

- transient read/model requests under a total deadline;
- idempotent ingestion stages;
- side effects protected by an idempotency key.

Do not retry validation errors, authorization failures, or arbitrary side effects.

### Persistence boundary

Cloud containers have disposable filesystems. Persist documents, job state, approvals, audit events, and results in managed storage before acknowledging durable work.

### Security boundary

Prompts express desired behavior. Code enforces:

- identity;
- authorization;
- tenant filters;
- tool allowlists;
- approval;
- quotas;
- file limits;
- URL/network allowlists;
- output escaping;
- deletion.

### Quality boundary

Unit tests prove software invariants. Evals estimate model/retrieval behavior. Load tests measure capacity. Security tests attempt to violate boundaries. None replaces the others.

---

## 11. What not to add during the core ten weeks

Unless a weekly goal explicitly needs it, defer:

- Kubernetes;
- a service mesh;
- multiple backend microservices;
- a full React/Next.js rewrite;
- fine-tuning;
- self-hosting large language models;
- a custom vector database;
- autonomous browser/computer control;
- many-agent orchestration;
- a framework that replaces the provider/tool loop;
- complex infrastructure-as-code.

These are not bad technologies. They are simply poor substitutes for first learning the application and operational boundaries.

---

## 12. Optional weeks after the capstone

### Planned future specialization

After completing the core curriculum and capstone, the next learning phase will be a deeper specialization in:

1. **Production vector databases** — advanced indexing, HNSW and IVF tuning, filtering, hybrid and sparse retrieval, reranking, multitenancy, scaling, replication, backup/restore, observability, cost modeling, and migration across pgvector, Qdrant, Pinecone, and similar managed systems.
2. **LangChain** — provider and retriever abstractions, runnable composition, structured output, tool integration, callbacks and tracing, testing, evaluation, framework extension points, and deciding when the abstraction is useful versus direct SDK code.
3. **LangGraph** — explicit state graphs, durable execution, checkpoints, retries, interrupts, human approval, memory, parallel branches, recovery, and production deployment of long-running agent workflows.

This specialization is intentionally scheduled **after** the ten-week program. The core course establishes the APIs, retrieval mechanics, tool loops, persistence, queues, evaluation, security, and operations that these technologies abstract. That foundation will make it possible to assess their trade-offs and use them deliberately instead of treating framework behavior as magic.

The specialization should culminate in rebuilding selected KnowledgeDesk workflows with these tools and comparing them with the direct implementations on quality, latency, cost, observability, failure recovery, portability, and maintenance effort.

### Week 11 — Frontend engineering

Split the UI into a typed React/Next.js client, add an API contract, accessibility tests, optimistic job updates, and secure cookie/session handling.

### Week 12 — Infrastructure as code

Represent Cloud Run, service accounts, secret bindings, task queues, budgets, and alerts with Terraform or the provider’s native declarative tooling. Test a clean environment build.

### Week 13 — Specialized vector systems

Migrate the same corpus to Qdrant or Pinecone. Test namespaces/collections, payload filters, hybrid search, snapshots/backups, scaling, and the failure/migration plan.

### Week 14 — Local/open-weight models

Run a small open-weight model locally, implement an OpenAI-compatible or custom adapter, and compare privacy, latency, hardware, operations, quality, and total cost. Do not call “no API invoice” free without pricing the hardware and operations.

### Week 15 — Framework comparison

Rebuild the research or agent loop in one orchestration framework. Compare:

- lines of application code;
- hidden state;
- trace clarity;
- provider portability;
- testing;
- recovery;
- upgrade risk;
- feature velocity.

Keep the framework only if the measured trade-off helps your project.

---

## 13. Suggested portfolio artifacts

By the end, publish:

- an architecture diagram;
- ten tagged releases;
- a short demo video;
- a public-safe evaluation dataset;
- sample evaluation report;
- threat model;
- runbook;
- two or three architecture decision records;
- model/provider comparison based on a defined task;
- cost-per-task table;
- one incident postmortem from a deliberate failure;
- a “not production ready because…” section demonstrating judgment.

The last item is especially valuable. Production engineering is the ability to name and manage limitations, not the absence of limitations.

---

## 14. First-day setup checklist

Before Week 1:

- [ ] Install a current Python, Git, Docker, and a code editor.
- [ ] Create a GitHub repository.
- [ ] Add a Python .gitignore before creating .env.
- [ ] Enable GitHub secret scanning where available.
- [ ] Create OpenAI and Anthropic API projects/keys for learning.
- [ ] Add minimal prepaid credit or billing and configure provider spend controls.
- [ ] Create a Render account.
- [ ] Decide whether to enable Google Cloud billing now or in Week 2.
- [ ] If using Google Cloud, create a dedicated learning project and budget/spend cap.
- [ ] Create a Supabase organization, but wait until Week 3 to create its schema.
- [ ] Create a password manager entry for every account and recovery code.
- [ ] Write .env.example with placeholders only.
- [ ] Make the first CI workflow run a trivial test.

Suggested environment variable names:

~~~text
APP_ENV
APP_VERSION
LOG_LEVEL
OPENAI_API_KEY
OPENAI_MODEL
ANTHROPIC_API_KEY
ANTHROPIC_MODEL
LLM_PROVIDER
LLM_TIMEOUT_SECONDS
LLM_MAX_OUTPUT_TOKENS
SUPABASE_URL
SUPABASE_ANON_KEY
SUPABASE_SERVICE_ROLE_KEY
DATABASE_URL
MAX_MODEL_COST_USD_PER_REQUEST
~~~

Never put the Supabase service role key or either model provider key in public browser code.

---

## 15. Official source map

Use primary documentation as the source of truth. Blog posts and tutorials can help with intuition, but verify changing API and pricing details here.

### OpenAI

- [Developer quickstart](https://platform.openai.com/docs/quickstart/make-your-first-api-request)
- [Responses API migration and rationale](https://developers.openai.com/api/docs/guides/migrate-to-responses)
- [Model catalog](https://developers.openai.com/api/docs/models)
- [API pricing](https://developers.openai.com/api/docs/pricing)
- [Embeddings guide](https://developers.openai.com/api/docs/guides/embeddings)
- [Small embedding model](https://developers.openai.com/api/docs/models/text-embedding-3-small)
- [Production best practices](https://developers.openai.com/api/docs/guides/production-best-practices)
- [Deployment checklist](https://developers.openai.com/api/docs/guides/deployment-checklist)
- [Cost optimization](https://developers.openai.com/api/docs/guides/cost-optimization)
- [Rate limits](https://developers.openai.com/api/docs/guides/rate-limits)

### Anthropic

- [Messages API reference](https://platform.claude.com/docs/en/api/python/messages/create)
- [Streaming](https://platform.claude.com/docs/en/build-with-claude/streaming)
- [Tool use overview](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview)
- [How tool use works](https://platform.claude.com/docs/en/agents-and-tools/tool-use/how-tool-use-works)
- [Errors and retry behavior](https://platform.claude.com/docs/en/api/errors)
- [Authentication](https://platform.claude.com/docs/en/manage-claude/authentication)
- [Rate and spend limits](https://platform.claude.com/docs/en/api/rate-limits)
- [Pricing](https://platform.claude.com/docs/en/about-claude/pricing)

### Data and vector search

- [Supabase pricing and free limits](https://supabase.com/pricing)
- [Supabase vector columns](https://supabase.com/docs/guides/ai/vector-columns)
- [Supabase vector indexes](https://supabase.com/docs/guides/ai/vector-indexes)
- [Supabase hybrid search](https://supabase.com/docs/guides/ai/hybrid-search)
- [Qdrant Cloud free cluster](https://qdrant.tech/documentation/cloud/create-cluster/)
- [Pinecone pricing](https://www.pinecone.io/pricing/)
- [Pinecone quickstart and plan summary](https://docs.pinecone.io/guides/get-started/quickstart)

### Deployment and operations

- [Render Free limitations](https://render.com/docs/free)
- [Render web services](https://render.com/docs/web-services)
- [What is Cloud Run](https://docs.cloud.google.com/run/docs/overview/what-is-cloud-run)
- [Google Cloud free usage](https://docs.cloud.google.com/free/docs/free-cloud-features)
- [Cloud Run pricing](https://cloud.google.com/run/pricing)
- [Cloud Tasks pricing](https://cloud.google.com/tasks/pricing)
- [Secret Manager pricing](https://cloud.google.com/secret-manager/pricing)
- [Google Cloud budgets and their limitations](https://docs.cloud.google.com/billing/docs/how-to/budgets)
- [GitHub Actions billing and usage](https://docs.github.com/en/actions/concepts/billing-and-usage)

### Security

- [OWASP Top 10 for LLM Applications: excessive agency and linked risks](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/)

---

## 16. How to personalize this plan later

The curriculum can be adjusted without changing its core:

- At 5 hours/week, make each listed week two calendar weeks.
- If you prefer TypeScript, use Fastify or a small Next.js server, but retain the same tests, provider boundary, database design, and operational gates.
- If you already know web development, compress Weeks 1–2 and spend more time on evals, security, and operations.
- If you cannot enable cloud billing, stay on Render and explicitly document which queue, identity, scaling, and reliability lessons are simulated.
- If your professional goal is AWS or Azure, keep the app architecture and substitute the equivalent container, secret, queue, logging, and identity services.
- If RAG is your priority, split Week 4 into three weeks: retrieval, evaluation, and scale/operations.
- If agents are your priority, keep Week 5’s bounded safety rules and add deterministic orchestration before multi-agent experimentation.

The sequence should remain: **direct API → reliable service → persistence/RAG → evaluation → tools → async work → multimodal → security → operations → capstone**.
