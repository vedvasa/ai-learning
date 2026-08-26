+++
document_key = "escalation-policy"
title = "Support escalation policy"
canonical_path = "/support/escalation/policy"
source_url = "https://support.knowledgedesk.example/escalation/policy"
version = 1
updated_at = "2026-08-23T06:00:00Z"
tenant_id = "knowledgedesk-demo"
visibility = "internal"
+++
# Support escalation policy

Support escalates a case when its impact, risk, or required expertise exceeds the current queue’s authority. Escalation changes ownership; it does not guarantee an immediate fix or bypass required security checks.

## Priority criteria

Critical priority covers confirmed security incidents, broad production outages, or complete loss of a paid service for many users. High priority covers major functionality loss without a reasonable workaround. Individual how-to questions and cosmetic defects normally remain medium or low priority.

## Required handoff

The sending agent records impact, affected scope, reproduction steps, timestamps, completed diagnostics, and the requested next action. Secrets and unnecessary customer content must be removed. The receiving team acknowledges critical handoffs within 30 minutes and high-priority handoffs within four business hours.
