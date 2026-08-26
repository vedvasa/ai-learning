+++
document_key = "account-password-reset"
title = "Reset a forgotten password"
canonical_path = "/support/account/password-reset"
source_url = "https://support.knowledgedesk.example/account/password-reset"
version = 1
updated_at = "2026-08-18T10:30:00Z"
tenant_id = "knowledgedesk-demo"
visibility = "public"
+++
# Reset a forgotten password

Select **Forgot password** on the sign-in page and enter the email address attached to the account. KnowledgeDesk sends a single-use reset link when the account uses password authentication.

## Reset link behavior

Reset links expire after 30 minutes and stop working immediately after a successful password change. Requesting another link invalidates every earlier link. Check the spam folder and allow up to five minutes for delivery before requesting another email.

## Single sign-on accounts

Users whose workspace enforces SSO must reset credentials with their identity provider. KnowledgeDesk password reset emails are not sent for SSO-only accounts. A workspace administrator can confirm which sign-in method is required without seeing the user’s password.
