+++
document_key = "notification-delivery"
title = "Troubleshoot email notifications"
canonical_path = "/support/notifications/email-delivery"
source_url = "https://support.knowledgedesk.example/notifications/email-delivery"
version = 1
updated_at = "2026-08-20T21:00:00Z"
tenant_id = "knowledgedesk-demo"
visibility = "public"
+++
# Troubleshoot email notifications

Notification delivery depends on workspace rules, individual preferences, and the recipient mail system. First confirm that the ticket event appears in the activity log and that the recipient has not disabled that notification type.

## Missing messages

Check spam and quarantine folders, verify the profile email address, and allow-list the KnowledgeDesk sending domain. Repeated notification rules are deduplicated, so one event may intentionally produce only one message.

## Escalating delivery issues

Provide the workspace identifier, recipient domain, notification type, event time, and activity-log event identifier. Do not forward authentication links or include mailbox passwords. Support can inspect delivery metadata but cannot access the recipient’s mailbox.
