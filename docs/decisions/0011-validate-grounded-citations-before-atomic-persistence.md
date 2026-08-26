# ADR 0011: Validate grounded citations before atomic persistence

## Status

Accepted.

## Context

Exact semantic retrieval now returns stable chunk identifiers and evidence, but
retrieval alone does not produce a user-facing answer. A language model can
still ignore supplied context, invent a citation, cite a chunk that was not
retrieved, or return structurally valid output whose grounding is invalid.

The database already contains conversations, messages, and model-call tables.
Saving those records independently could leave partial conversation history or
telemetry that refers to a missing assistant message.

## Decision

- Add `POST /api/answer` as a provider-neutral retrieve-then-generate endpoint.
  The caller chooses an allowlisted OpenAI or Anthropic model, but cannot choose
  the tenant or document visibility.
- Reuse the server-owned exact retriever. Only public evidence from the
  configured tenant can enter the grounded-answer prompt.
- Serialize the question and evidence as untrusted JSON, separate from the
  system instructions. Evidence content can inform an answer but cannot issue
  instructions.
- Ask each provider for the same closed Pydantic draft containing `answer` and
  `abstained`. OpenAI uses Responses API structured output with provider-side
  storage disabled; Anthropic uses its native structured-output helper.
- Require every supported claim to carry an inline
  `[source:<retrieved-chunk-uuid>]` marker. Treat provider-produced markers as
  untrusted data: parse them in application code, require at least one marker
  for a non-abstaining answer, reject malformed or unretrieved identifiers, and
  derive the response's source objects from the verified identifiers.
- If retrieval returns no evidence, use a fixed application-owned abstention
  and skip the generation call. A provider may also abstain after seeing
  insufficient evidence, but an abstention cannot contain citations.
- Persist the conversation, user message, assistant message with verified
  citation metadata, and successful generation telemetry in one Postgres
  transaction. A no-evidence abstention has no generation telemetry row.
- Keep question, answer, and evidence text out of application logs and
  `model_calls`. Conversation messages intentionally store the submitted
  question and completed answer.
- Cap grounded generation separately at 512 output tokens by default. Keep
  application-owned retry and total-deadline behavior; CI uses fake provider
  and embedding clients and makes no paid calls.

## Consequences

- A valid structured provider response is necessary but not sufficient for
  success; citation validation remains an application responsibility.
- Source metadata returned to the client and stored with the assistant message
  can refer only to chunks that the server actually retrieved.
- Conversation history and generation telemetry cannot be partially committed.
- A live answer request normally makes one paid embedding call and one paid
  generation call. An empty retrieval makes only the embedding call.
- This increment uses the existing schema and requires no migration.

## Out of scope

This decision does not add a Q&A browser interface, authentication, direct
browser database access, streaming answers, multi-turn context, hybrid search,
reranking, retrieval evaluation, a production deployment, or any hosted
database change.

## References

- [OpenAI GPT-5.6 Luna model](https://developers.openai.com/api/docs/models/gpt-5.6-luna)
- [OpenAI Responses create reference](https://developers.openai.com/api/reference/cli/resources/responses/methods/create)
