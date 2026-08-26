+++
document_key = "security-mfa"
title = "Multi-factor authentication"
canonical_path = "/support/security/mfa"
source_url = "https://support.knowledgedesk.example/security/mfa"
version = 1
updated_at = "2026-08-24T07:30:00Z"
tenant_id = "knowledgedesk-demo"
visibility = "public"
+++
# Multi-factor authentication

KnowledgeDesk supports authenticator applications and FIDO2-compatible security keys. SMS is not offered as an MFA method. Users configure MFA from **Settings → Security**.

## Recovery codes

Ten single-use recovery codes are displayed when MFA is enabled. Store them outside KnowledgeDesk in a protected password manager. Generating a new set invalidates every unused code from the previous set.

## Lost factor

Try a saved recovery code or another registered security key. If neither is available, a workspace administrator can start an account-recovery review. Support agents cannot disable MFA based only on an email request, and recovery may require additional identity evidence.
