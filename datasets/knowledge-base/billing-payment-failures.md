+++
document_key = "billing-payment-failures"
title = "Resolve a failed subscription payment"
canonical_path = "/support/billing/payment-failures"
source_url = "https://support.knowledgedesk.example/billing/payment-failures"
version = 1
updated_at = "2026-08-21T12:00:00Z"
tenant_id = "knowledgedesk-demo"
visibility = "public"
+++
# Resolve a failed subscription payment

A payment can fail because of an expired card, an issuer decline, an incorrect billing address, or a regional restriction. KnowledgeDesk displays the processor’s safe failure category but never the full card number.

## Retry schedule

KnowledgeDesk retries an eligible subscription payment after 24 hours and again after 72 hours. Updating the payment method triggers a new attempt within several minutes. Repeatedly selecting retry does not bypass an issuer decline.

## Service access

The workspace enters a seven-day grace period after the first failure. Existing data remains available during that period. If payment is still unsuccessful at the end of the grace period, the workspace becomes read-only until the balance is resolved.
