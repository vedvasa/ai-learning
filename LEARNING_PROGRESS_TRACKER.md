# Production AI Learning Progress Tracker

Use this with the detailed curriculum in PRODUCTION_AI_SELF_LEARNING_GUIDE.md. Update it at the end of every week; do not wait until the capstone.

## Program dashboard

| Week | Release | Status | Live URL | Git tag | Key evaluation | Model spend | Main lesson |
|---:|---|---|---|---|---|---:|---|
| 1 | PromptBench | Complete | [Live](https://ai-learning-promptbench.onrender.com/) | [`v0.1.0`](https://github.com/vedvasa/ai-learning/tree/v0.1.0) | 5/5 sample calls; safe 502 and recovery | $0.00070 measured | HTTP/SSE boundaries, direct SDKs, safe errors, deployment, and cold starts |
| 2 | Ticket Triage API | In progress |  |  | 61 deterministic tests; fake-backed browser flow | $0.00 | Typed structured output and validation |
| 3 | Citation Q&A | Not started |  |  |  | $0.00 |  |
| 4 | RAG Quality Lab | Not started |  |  |  | $0.00 |  |
| 5 | Support Action Agent | Not started |  |  |  | $0.00 |  |
| 6 | Deep Research Jobs | Not started |  |  |  | $0.00 |  |
| 7 | Multimodal Intake | Not started |  |  |  | $0.00 |  |
| 8 | Multi-tenant KnowledgeDesk | Not started |  |  |  | $0.00 |  |
| 9 | Operated AI Service | Not started |  |  |  | $0.00 |  |
| 10 | Capstone release | Not started |  |  |  | $0.00 |  |

Total model spend: **At least $0.00070 measured**

Cloud spend: **$0.00**

Learning budget: **$_____**

## Weekly release record

### Week 1 — PromptBench

- **Dates:** 2026-08-12 to 2026-08-15
- **Release tag:** [`v0.1.0`](https://github.com/vedvasa/ai-learning/tree/v0.1.0)
- **Live URL:** [ai-learning-promptbench.onrender.com](https://ai-learning-promptbench.onrender.com/)
- **Deployment revision:** `b7857e751482`
- **Schema/migration version:** Not applicable
- **Prompt/evaluation dataset version:** Five-prompt Week 1 sample in the evidence record

#### Intended outcome

A user can select OpenAI or Anthropic, submit a prompt in a browser, and see a
streamed response while all provider credentials remain behind the FastAPI
boundary.

#### Architecture change

Added a browser-to-FastAPI-to-provider flow with direct SDK adapters, one
provider-neutral interface, normalized SSE events, stable errors, health checks,
structured request logging, locked builds, GitHub CI, and a Render Blueprint.

#### Evidence

- CI run: [PR #10 checks](https://github.com/vedvasa/ai-learning/actions/runs/31919804655)
- Test summary: 36 tests passed
- Evaluation report: [Week 1 evidence](docs/evidence/week-1/README.md)
- Dashboard/screenshots: [OpenAI](docs/evidence/week-1/openai-stream.png) and [Anthropic](docs/evidence/week-1/anthropic-stream.png)
- Architecture decision: direct provider SDKs behind a small application-owned
  interface, before introducing orchestration frameworks

#### Quality and operations

| Signal | Result | Target | Pass? |
|---|---:|---:|---|
| Unit/integration tests | 36/36 | All pass | Yes |
| Task-quality metric | 5/5 successful calls | 5/5 | Yes |
| Schema/citation validity | Not applicable in Week 1 | Not applicable | — |
| p95 latency | 6.58 s in the five-call sample | Baseline only | — |
| Error rate | 0% in the five-call sample | 0% | Yes |
| Estimated cost per task | $0.000138 | At most $0.001 | Yes |

The p95 entry uses the slowest observation because five calls are insufficient
for a stable percentile estimate.

#### Cost

| Provider/service | Calls or usage | Cost |
|---|---:|---:|
| OpenAI | 3 sample calls plus 1 recovery call | $0.000193 |
| Anthropic | 2 sample calls | $0.000509 |
| Embeddings | 0 | $0.00 |
| Web/search/tools | 0 | $0.00 |
| Cloud | Render Free | $0.00 |
| Other | 0 | $0.00 |
| **Measured total** | **6 calls** | **$0.000702** |

Earlier manual UI experiments are excluded because their usage metadata was not
retained; the total is therefore a measured lower bound, not a billing total.

#### Failure drill

The deployed OpenAI key was temporarily replaced with a nonempty invalid value.

- Expected behavior: readiness detects configured presence, while generation
  rejects the bad credential through a safe application error.
- Observed behavior: readiness returned HTTP 200 and generation returned HTTP
  502 with `provider_authentication_failed` and no provider internals.
- Detection: the public response carried a stable error code and application
  request ID; the user confirmed the matching Render log was sanitized.
- Recovery: restored the valid Render secret, redeployed, rechecked readiness,
  and completed a minimal OpenAI request.
- Follow-up fix: document that readiness checks presence, not credential validity.

#### Security/privacy check

- Only deliberately supplied learning prompts entered the system.
- API keys were stored in local ignored environment configuration and Render
  secret environment variables, never in Git or browser code.
- Logs contained operational metadata but omitted keys, prompts, raw provider
  errors, response text, and stack traces.
- The browser/server credential boundary and provider-authentication failure
  boundary were tested.
- The public deployment is unauthenticated; no upload, tenant, or tool boundary
  exists yet.

#### What I learned

An AI application is still a networked production system: the model call belongs
behind a server boundary that owns credentials, validation, timeouts, streaming,
error translation, telemetry, deployment, and recovery.

#### Known limitations

- Render Free can cold-start for more than 30 seconds.
- Readiness verifies secret presence but not credential validity.
- The 64-token budget truncated two of five evaluation responses.
- The public app has no authentication, rate limit, persistence, tenant isolation,
  or availability guarantee.
- The small sample is a learning baseline, not a statistically meaningful SLO.

#### Next decision

Week 2 should establish reliable structured model output and validation before
adding persistence or retrieval.

### Weekly release template

Copy this template once per week.

### Week __ — Release name

**Dates:**  
**Release tag:**  
**Live URL:**  
**Deployment revision:**  
**Schema/migration version:**  
**Prompt/evaluation dataset version:**  

#### Intended outcome

What should the user be able to do by the end of the week?

#### Architecture change

What new component, boundary, data flow, or production behavior was added?

#### Evidence

- CI run:
- Test summary:
- Evaluation report:
- Dashboard/screenshot:
- Architecture decision:

#### Quality and operations

| Signal | Result | Target | Pass? |
|---|---:|---:|---|
| Unit/integration tests |  |  |  |
| Task-quality metric |  |  |  |
| Schema/citation validity |  |  |  |
| p95 latency |  |  |  |
| Error rate |  |  |  |
| Estimated cost per task |  |  |  |

#### Cost

| Provider/service | Calls or usage | Cost |
|---|---:|---:|
| OpenAI |  |  |
| Anthropic |  |  |
| Embeddings |  |  |
| Web/search/tools |  |  |
| Cloud |  |  |
| Other |  |  |
| **Weekly total** |  |  |

#### Failure drill

What did you deliberately break?

- Expected behavior:
- Observed behavior:
- Detection:
- Recovery:
- Follow-up fix:

#### Security/privacy check

- What sensitive data entered the system?
- What was stored?
- What was logged?
- Which authorization boundary was tested?
- Did any new tool, URL, upload, or tenant boundary appear?

#### What I learned

Explain one concept in your own words without referring to the code.

#### Known limitations

What would prevent this learning deployment from serving real customers?

#### Next decision

What is the single most important risk or unknown to address next week?

## Capstone readiness score

Score each area from 0 to 3:

- 0: absent;
- 1: demo only;
- 2: implemented and tested at learning scale;
- 3: measured, documented, and recoverable.

| Area | Score | Evidence |
|---|---:|---|
| API and provider integration | 2 | Two direct provider paths deployed, tested, and measured |
| Structured output and error handling | 1 | Stable application errors; structured model output starts in Week 2 |
| RAG retrieval and citations | 0 |  |
| Offline evaluation | 0 |  |
| Tool safety and idempotency | 0 |  |
| Async jobs and retries | 0 |  |
| Multimodal/file lifecycle | 0 |  |
| Authentication and tenant isolation | 0 |  |
| Observability and cost tracking | 1 | Structured request metadata and a measured six-call cost record |
| CI/CD and rollback | 1 | GitHub CI, automatic Render deployment, and rollback runbook |
| Threat model and runbook | 1 | Secret boundary and failure hygiene documented and exercised |
| **Total out of 33** | **6** |  |

A high score is not the purpose. The evidence and honest limitations are.
