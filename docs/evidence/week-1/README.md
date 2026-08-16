# Week 1 PromptBench evidence

Evidence date: 2026-08-15

Live service: [ai-learning-promptbench.onrender.com](https://ai-learning-promptbench.onrender.com/)

Repository `main` revision during verification: `b7857e751482`

## Public service checks

Read-only checks made no model-provider calls.

| Endpoint | HTTP status | Warm response time |
|---|---:|---:|
| `/` | 200 | 0.140 s |
| `/health/live` | 200 | 0.134 s |
| `/health/ready` | 200 | 0.111 s |

Readiness reported both server-side provider keys as configured without exposing
their values or making a paid provider request.

## Streaming evidence

The same prompt, `How does a GPU work?`, completed through both provider paths:

- [OpenAI streamed response](openai-stream.png)
- [Anthropic streamed response](anthropic-stream.png)

Both screenshots show the selected provider and configured model, incremental
response UI, completion state, and response metadata. No API key is visible.

## Five-call cost sample

The sample used `POST /api/generate` so final usage metadata could be recorded
without retaining response text. Every request used the application's 64-token
output cap. Application and provider request IDs were returned for every call but
are intentionally omitted from this public evidence record.

| ID | Provider | Reproducible prompt | Latency | Input tokens | Output tokens | Finish reason | Estimated cost |
|---|---|---|---:|---:|---:|---|---:|
| W1-01 | OpenAI | In one sentence, define idempotency in web APIs. | 6,580.80 ms | 18 | 27 | `completed` | $0.000036 |
| W1-02 | Anthropic | In one sentence, explain why API keys stay on the server. | 915.09 ms | 20 | 30 | `end_turn` | $0.000170 |
| W1-03 | OpenAI | List three benefits of request IDs in production APIs. | 2,180.51 ms | 16 | 64 | `max_output_tokens` | $0.000080 |
| W1-04 | Anthropic | Explain server-sent events in two short bullet points. | 1,301.74 ms | 19 | 64 | `max_tokens` | $0.000339 |
| W1-05 | OpenAI | Name two reasons to set an LLM output-token limit. | 2,130.97 ms | 18 | 52 | `completed` | $0.000066 |

### Aggregate

| Signal | Result |
|---|---:|
| Successful calls | 5 / 5 |
| Input tokens | 91 |
| Output tokens | 237 |
| Median provider latency | 2,130.97 ms |
| Mean provider latency | 2,621.82 ms |
| OpenAI estimated cost | $0.000182 |
| Anthropic estimated cost | $0.000509 |
| **Total estimated model cost** | **$0.000691** |

Two of five calls reached the configured output limit. The cap successfully
bounded spend, but it can truncate prompts that request lists or explanations.
This is an explicit quality-versus-cost trade-off, not a universal production
setting.

### Pricing basis

Costs use token counts returned by each provider and the standard first-party API
rates fetched on 2026-08-15:

- GPT-5.6 Luna: $0.20 per million input tokens and $1.20 per million output
  tokens ([official OpenAI model page](https://developers.openai.com/api/docs/models/gpt-5.6-luna)).
- Claude Haiku 4.5: $1 per million input tokens and $5 per million output tokens
  ([official Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing)).

Per-call estimate:

`(input tokens × input rate + output tokens × output rate) / 1,000,000`

These are estimates before any account-specific credits, discounts, taxes,
caching adjustments, or provider billing-rounding behavior.

## Operational exercises

The last cost-sample request completed before the idle window began at
`2026-08-15T19:42:14Z`.

### Cold-start measurement

The service remained without intentional inbound traffic for 19 minutes and 51
seconds. The first `GET /health/live` began at `2026-08-15T20:02:05Z`:

| Signal | Cold request | Immediate warm request |
|---|---:|---:|
| HTTP status | Not captured | 200 |
| Time to first byte | More than 30 s | 0.153 s |
| Total time | More than 30 s | 0.153 s |

The cold request was still pending when the 30-second measurement wrapper
yielded, establishing an honest lower bound but not an exact completion time.
The wrapper then sent the warm probe before the original result was recovered.
No exact cold duration is inferred or invented. The result still demonstrates
the material Free-tier cold-start penalty versus the warm service.

### Controlled invalid-key failure and recovery

The deployed `OPENAI_API_KEY` was temporarily replaced with a nonempty invalid
value. No credential value was entered into Git, the evidence record, or an API
request.

| Check | Result |
|---|---|
| `GET /health/ready` | HTTP 200; both key-presence checks remained `true` |
| OpenAI `POST /api/generate` | HTTP 502 in 0.381 s |
| Application error code | `provider_authentication_failed` |
| Safe public message | `The selected provider rejected the server credentials.` |
| Application request ID | `week1-invalid-openai-drill` |
| Provider internals, key, stack trace, or model text exposed | No |

The readiness result demonstrates an intentional limitation: the health check
verifies presence without making a paid provider call, so it cannot prove that a
credential is valid. The generation boundary mapped the provider authentication
failure to a stable, safe application error.

#### Log hygiene

The user confirmed that the Render log entry associated with
`week1-invalid-openai-drill` contained safe operational failure metadata and
omitted the prompt, API key, raw provider error, stack trace, and response text.
This confirmation was performed in the authenticated Render dashboard.

#### Recovery

The valid key was restored in Render and a new deployment completed.

| Check | Result |
|---|---|
| `GET /health/ready` | HTTP 200; both key-presence checks `true` |
| OpenAI recovery call | Successful 2xx response |
| Expected confirmation returned | Yes |
| Provider latency | 1,673.74 ms |
| Input/output tokens | 12 / 7 |
| Finish reason | `completed` |
| Application request ID | `week1-openai-recovery` |
| Estimated recovery-call cost | $0.0000108 |

The restored credential therefore recovered the OpenAI path end to end.
