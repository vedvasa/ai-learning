+++
document_key = "api-rate-limits"
title = "API rate limits and retries"
canonical_path = "/support/integrations/api-rate-limits"
source_url = "https://support.knowledgedesk.example/integrations/api-rate-limits"
version = 1
updated_at = "2026-08-22T05:00:00Z"
tenant_id = "knowledgedesk-demo"
visibility = "public"
+++
# API rate limits and retries

KnowledgeDesk applies workspace-level request limits to protect service reliability. Pro workspaces receive 120 requests per minute. A response with HTTP 429 means the current window has been exhausted.

## Retry behavior

Clients should honor the `Retry-After` header and use exponential backoff with jitter. Do not retry validation errors or authentication failures. Retrying every failed request immediately can extend an outage and may cause additional throttling.

## Request identifiers

Record the response request identifier in application logs and include it in support tickets. Do not log API keys, authorization headers, or full payloads containing customer data. Support can use the identifier to trace safe operational metadata.
