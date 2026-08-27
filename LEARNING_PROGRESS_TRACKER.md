# Production AI Learning Progress Tracker

Use this with the detailed curriculum in PRODUCTION_AI_SELF_LEARNING_GUIDE.md. Update it at the end of every week; do not wait until the capstone.

## Program dashboard

| Week | Release | Status | Live URL | Git tag | Key evaluation | Model spend | Main lesson |
|---:|---|---|---|---|---|---:|---|
| 1 | PromptBench | Complete | [Live](https://ai-learning-promptbench.onrender.com/) | [`v0.1.0`](https://github.com/vedvasa/ai-learning/tree/v0.1.0) | 5/5 sample calls; safe 502 and recovery | $0.00070 measured | HTTP/SSE boundaries, direct SDKs, safe errors, deployment, and cold starts |
| 2 | Ticket Triage API | Complete | [Live](https://ai-learning-3y5vyfqynq-uw.a.run.app/) | [`v0.2.0`](https://github.com/vedvasa/ai-learning/tree/v0.2.0) | 136 tests; 2/2 deployed calls; schema-valid but policy-label disagreement | $0.001634 measured | Typed output, guarded evaluation, staged recovery, and semantic evaluation |
| 3 | Citation Q&A | Complete | [Live](https://ai-learning-3y5vyfqynq-uw.a.run.app/) | [`v0.3.0`](https://github.com/vedvasa/ai-learning/tree/v0.3.0) | 20/20 completed; 100% retrieval hits and citation validity | Tokens recorded; price not reconciled | Data-first RAG, guarded ingestion, retrieval evaluation, and citation validation |
| 4 | RAG Quality Lab | Not started |  |  |  | $0.00 |  |
| 5 | Support Action Agent | Not started |  |  |  | $0.00 |  |
| 6 | Deep Research Jobs | Not started |  |  |  | $0.00 |  |
| 7 | Multimodal Intake | Not started |  |  |  | $0.00 |  |
| 8 | Multi-tenant KnowledgeDesk | Not started |  |  |  | $0.00 |  |
| 9 | Operated AI Service | Not started |  |  |  | $0.00 |  |
| 10 | Capstone release | Not started |  |  |  | $0.00 |  |

Total model spend: **At least $0.00234 measured; Week 3 price not reconciled**

Cloud spend: **Not yet reconciled; budget alert and free-trial/free-tier guardrails are active**

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

### Week 2 — Ticket Triage API

- **Dates:** 2026-08-17 to 2026-08-21
- **Release tag:** [`v0.2.0`](https://github.com/vedvasa/ai-learning/tree/v0.2.0)
- **Live URL:** [ai-learning-3y5vyfqynq-uw.a.run.app](https://ai-learning-3y5vyfqynq-uw.a.run.app/)
- **Deployment revision:** `ai-learning-git-0a9e55479ea2`
- **Schema/migration version:** Strict `TicketTriage` Pydantic contract; no database migration
- **Prompt/evaluation dataset version:** 30 fictional cases, SHA-256 `334f962322f5845b23c18c19e4ae5e7b83682f723818512d40d8d7a104a52c63`

#### Intended outcome

A user can submit a fictional support ticket through either provider and receive
one validated, provider-neutral classification contract from the deployed
browser application.

#### Architecture change

Added native structured-output adapters, fail-closed Pydantic validation,
application-owned bounded retries, privacy-safe in-memory usage telemetry, a
guarded 30-case evaluation command, a pinned non-root container, and staged
Cloud Run delivery through Cloud Build, Artifact Registry, Secret Manager, and a
dedicated runtime identity.

#### Evidence

- CI runs: [PR #17](https://github.com/vedvasa/ai-learning/actions/runs/32543840189) and
  [PR #18](https://github.com/vedvasa/ai-learning/actions/runs/32544540776)
- Test summary: 136 deterministic tests passed without provider credentials
- Evaluation report: [Week 2 evidence](docs/evidence/week-2/README.md)
- Dataset validation: 30/30 fictional cases; hash recorded above
- Deployment: corrected immutable revision at 100% traffic with the failed
  bootstrap revision retained at 0%

#### Quality and operations

| Signal | Result | Target | Pass? |
|---|---:|---:|---|
| Unit/integration tests | 136/136 | All pass | Yes |
| Deployed functional calls | 2/2 successful; one attempt each | 2/2 | Yes |
| Schema validity | 2/2 responses passed the shared contract | 100% | Yes |
| Semantic agreement | Category and review flag agreed; priority and sentiment disagreed | Baseline only | — |
| Observed latency | 4.49 s and 4.88 s | Baseline only | — |
| Estimated cost per task | $0.0001918 OpenAI; $0.0014420 Anthropic | At most $0.01 | Yes |

Two calls cannot establish accuracy, latency percentiles, or an SLO. The
disagreement is recorded as evidence that structured output and high confidence
do not establish semantic correctness.

#### Cost

| Provider/service | Calls or usage | Estimated cost |
|---|---:|---:|
| OpenAI | 1 deployed acceptance call; 425 input / 89 output tokens | $0.0001918 |
| Anthropic | 1 deployed acceptance call; 917 input / 105 output tokens | $0.0014420 |
| Embeddings | 0 | $0.00 |
| Web/search/tools | 0 | $0.00 |
| Cloud | Free trial/free-tier guardrails; invoice not reconciled | Not claimed |
| **Measured model total** | **2 calls** | **$0.0016338** |

#### Failure drill

The first Cloud Run bootstrap generated absolute HTTP asset URLs on an HTTPS
page, so the browser blocked CSS and JavaScript even though endpoint smoke checks
passed. Browser acceptance exposed the gap. Root-relative assets and a stronger
smoke gate fixed the failure, and the user explicitly deployed the corrected
revision. An actual traffic rollback is deferred until two known-good application
revisions exist.

#### Security/privacy check

- Provider keys remained in versioned Secret Manager references and never
  entered Git, the image, Cloud Build arguments, or browser code.
- Ticket text and model output were processed in memory and omitted from logs and
  usage records.
- This evidence omits request IDs, provider IDs, ticket identifiers, ticket text,
  generated summaries, actions, and rationales.
- The public learning service remains unauthenticated and has no rate limiting.

#### What I learned

Production structured output has two separate quality gates. Schema validation
makes data safe for application code, while labeled evaluation and policy rules
are still needed to decide whether the data is correct.

#### Known limitations

- Two live calls are a functional check, not a statistically useful evaluation.
- The full 30-case paid provider comparison has not been run.
- Usage telemetry is process-local and disappears when the instance stops.
- The service has no authentication, rate limit, durable database, tenant
  isolation, or availability guarantee.
- The rollback command is documented and a previous revision exists, but the
  traffic drill is intentionally deferred.

#### Next decision

Week 3 should introduce durable Postgres storage and citation-grounded retrieval
without coupling API routes directly to a specific database or vector engine.

### Week 3 — Citation Q&A

- **Dates:** 2026-08-22 to 2026-08-26
- **Release tag:** [`v0.3.0`](https://github.com/vedvasa/ai-learning/tree/v0.3.0)
- **Live URL:** [ai-learning-3y5vyfqynq-uw.a.run.app](https://ai-learning-3y5vyfqynq-uw.a.run.app/)
- **Deployment revision:** `ai-learning-git-b09ff2a40b6a`
- **Schema/migration version:** `20260825045940_create_knowledge_schema.sql`
- **Prompt/evaluation dataset version:** 20 fictional questions, SHA-256 `7cd6be7d6af670adf4b9accab489d9cb1bcb154561cce61339c2a4dfb3e3d775`

#### Intended outcome

A user can ask a support question in the deployed browser application and
receive an answer grounded only in public chunks retrieved from the fictional
knowledge base, with inline citations that map to verified source cards.

#### Architecture change

Added a private Supabase Postgres/pgvector schema, versioned and idempotent
document ingestion, exact semantic retrieval, provider-neutral grounded-answer
generation, fail-closed citation validation, atomic conversation persistence,
bounded grounding retries, a versioned acceptance evaluator, and the default
Citation Q&A browser workspace. Cloud Run now receives a pinned database secret
through its dedicated runtime identity.

#### Evidence

- CI run: [PR #28 checks](https://github.com/vedvasa/ai-learning/actions/runs/33043202937)
- Test summary: 207 tests passed locally; both GitHub test jobs passed
- Evaluation and deployment report: [Week 3 evidence](docs/evidence/week-3/README.md)
- Dataset validation: 20/20 fictional cases; hash recorded above
- Cloud Build: `ed03400f-8882-4404-97ed-796b12f387b3` (`SUCCESS`)
- Browser acceptance: [grounded answer with three verified sources](docs/evidence/week-3/grounded-answer.png)
- Architecture decisions: ADRs 0008 through 0014

#### Quality and operations

| Signal | Result | Target | Pass? |
|---|---:|---:|---|
| Unit/integration tests | 207 passed locally; 6 DB tests skipped locally and exercised in CI | All configured tests pass | Yes |
| Evaluation completion | 20/20; 0 failures | 20/20 | Yes |
| Answerable retrieval hit rate at k | 100% | Relevant source for most answerable questions | Yes |
| Answerable answer rate | 100% | Baseline | — |
| Ambiguous abstention rate | 75% | Descriptive baseline | — |
| Unanswerable abstention rate | 100% | Usually abstain | Yes |
| Citation validity | 100% | 100% | Yes |
| Forbidden-document leakage | 0 cases | 0 | Yes |
| p50 / p95 duration | 2.00 s / 3.45 s | Baseline only | — |
| Deployed browser acceptance | 1/1 successful; 3 verified sources | 1/1 | Yes |

These results measure the application contract on a small fictional set. They
do not establish semantic answer quality, a production SLO, or behavior on
real customer questions.

#### Cost

| Provider/service | Calls or usage | Cost |
|---|---:|---:|
| OpenAI embeddings, 20-case evaluation | 266 input tokens | Not reconciled |
| OpenAI generation, 20-case evaluation | 18,749 input / 1,995 output tokens | Not reconciled |
| OpenAI deployed acceptance | 1 embedding plus 939 input / 176 output generation tokens | Not reconciled |
| Anthropic | 0 Week 3 acceptance calls | $0.00 |
| Cloud and Supabase | Guardrails active; invoices not reconciled | Not claimed |

The report deliberately records usage without hardcoding prices that can change
independently of the repository.

#### Failure drill

Application-detected invalid citations are classified as retryable invalid
model output. Tests prove that rejected answers are neither returned nor
persisted, retries remain inside the shared attempt/deadline budget, and only a
validated answer can commit. No destructive live failure was injected into the
public service. The release retained the known-good Week 2 revision and printed
an exact rollback command.

#### Security/privacy check

- Provider and database credentials remained in explicit Secret Manager
  versions and out of Git, Cloud Build input, images, browser code, and logs.
- The browser cannot override the server-owned tenant or database connection.
- Unauthenticated retrieval permits only public documents; the acceptance set
  observed zero forbidden-document leakage.
- The committed corpus and evaluation questions are fictional.
- Conversation content is persisted intentionally for the learning exercise;
  the public service must never receive real customer data.

#### What I learned

Production RAG is a data and validation system around model calls. Reproducible
schema, versioned ingestion, embedding compatibility, retrieval filters,
verifiable citations, abstention, atomic writes, and measured acceptance gates
matter as much as prompt construction.

#### Known limitations

- The corpus and 20-question evaluation are too small for broad quality claims.
- Retrieval uses an exact scan; approximate and hybrid retrieval are deferred
  until Week 4 has measurements that can justify them.
- Answer correctness was not human-scored.
- Readiness proves configuration presence, not live database connectivity.
- The public service has no authentication or rate limit.
- A new revision cold-started against persistent data, but an explicit
  same-revision restart drill was not performed.
- Provider and cloud bills were not reconciled.

#### Next decision

Week 4 should measure retrieval quality before adding hybrid search,
reranking, or approximate indexing, and should adopt only changes that improve
a chosen metric.

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
| Structured output and error handling | 2 | Strict provider-neutral output, validation, retries, and failures tested |
| RAG retrieval and citations | 0 |  |
| Offline evaluation | 2 | Guarded 30-case evaluator with aggregate-only metrics and fake-provider CI |
| Tool safety and idempotency | 0 |  |
| Async jobs and retries | 0 |  |
| Multimodal/file lifecycle | 0 |  |
| Authentication and tenant isolation | 0 |  |
| Observability and cost tracking | 2 | Privacy-safe usage events and measured Week 1/2 cost records |
| CI/CD and rollback | 1 | GitHub CI, automatic Render deployment, and rollback runbook |
| Threat model and runbook | 2 | Secret boundary, failure hygiene, Cloud Run runbook, and UI failure recovery documented |
| **Total out of 33** | **11** |  |

A high score is not the purpose. The evidence and honest limitations are.
