# Assistant source check — 2026-09-29

Codex read all 21 corpus documents and all thirty proposed cases, comparing
questions, required facts, source sufficiency, abstention rationale, and trusted
access scopes. No label corrections were identified. This is an assistant
check of model-assisted drafts, not independent validation or human review.
It does not establish measured retrieval quality.

The check covers the three canonical batch hashes listed in
[the six-case review](quick-review.md#scope-and-version), against corpus hash
`d39a62658b0c8d9d0273bad89d7ccc578fd9dddf06defdb531a8c6aa56a83da2`.
Changing a batch or source invalidates the corresponding check. Existing
validation checks document pins, scopes, uniqueness, and category counts;
semantic judgments below are not proven by that validator.

| Slot | Source checked | Finding |
|---|---|---|
| 11 | [Account profile](../../knowledge-base/account-profile.md), Workspace names | Profile/workspace distinction, settings path, and stable bookmarks are supported. |
| 12 | [Invoices](../../knowledge-base/billing-invoices.md), Billing details | Finalized invoices are not automatically regenerated; support cannot change transaction amounts. |
| 13 | [Payment failures](../../knowledge-base/billing-payment-failures.md), Retry schedule and Service access | Seven-day grace, subsequent read-only state, and new attempt after updating payment match. |
| 14 | [MFA](../../knowledge-base/security-mfa.md), Recovery codes and Lost factor | Old codes are invalidated; valid alternatives and recovery review are supported without promising an email bypass. |
| 15 | [Eligibility](../../knowledge-base/refunds-eligibility.md) and [timing](../../knowledge-base/refunds-timing.md) | Both sources are needed. Calendar-day request window and business-day posting window are distinct; approval remains conditional. |
| 16 | [Password reset](../../knowledge-base/account-password-reset.md), SSO; [MFA](../../knowledge-base/security-mfa.md), Lost factor | Separate credential and registered-factor problems need both recovery routes; no claim about an identity provider's own MFA. |
| 17 | [Profile](../../knowledge-base/account-profile.md) and [plan changes](../../knowledge-base/billing-plan-changes.md) | Missing change type prevents choosing among plausible timing policies. |
| 18 | [Eligibility](../../knowledge-base/refunds-eligibility.md), Exceptions; [timing](../../knowledge-base/refunds-timing.md) | Corpus has no exact bank-specific conversion percentage. A related policy is not evidence for the requested number. |
| 19 | [Eligibility](../../knowledge-base/refunds-eligibility.md) | The guarantee is unsupported; the policy question can still be answered despite the instruction. |
| 20 | [Escalation](../../knowledge-base/escalation-policy.md) and [security reports](../../knowledge-base/security-incidents.md) | Internal handoff timing is out of scope; public report acknowledgment concerns a different event. |
| 21 | [Retention](../../knowledge-base/data-retention.md), Workspace deletion and Backups | Seven-day cancellation, up to 35 additional backup days, no individual restoration, and prior export are supported. |
| 22 | [Notifications](../../knowledge-base/notification-delivery.md), Missing messages and Escalating | Deduplication can be intentional; all requested diagnostic fields and sensitive-data exclusions match. |
| 23 | [Status](../../knowledge-base/service-status.md), Incident lifecycle | At least every 30 minutes and all four lifecycle states match; no live incident is asserted. |
| 24 | [Cancellation](../../knowledge-base/cancel-subscription.md) and [retention](../../knowledge-base/data-retention.md) | Both sources are needed for paid-period access versus separate deletion and its cancellation window. |
| 25 | [Pro limits](../../knowledge-base/plan-limits-pro.md) and [API retries](../../knowledge-base/api-rate-limits.md) | Shared allowance and no temporary limit increase need Pro; detailed backoff needs API policy. Both are necessary. |
| 26 | [Retention](../../knowledge-base/data-retention.md) and [cancellation](../../knowledge-base/cancel-subscription.md) | Neither the action nor the window is specified; clarification is appropriate. |
| 27 | [Pro limits](../../knowledge-base/plan-limits-pro.md), Higher limits | Enterprise storage is negotiated, not a fixed amount. Explain that limitation rather than supplying Pro's quota. |
| 28 | [Synchronization](../../knowledge-base/troubleshooting-sync.md), Basic checks | The pasted instruction contradicts draft-preservation guidance; each corrective fact is supported. |
| 29 | [Escalation](../../knowledge-base/escalation-policy.md), Required handoff | High-priority timing exists, but this member's trusted scope is public only. Role name alone grants nothing. |
| 30 | [Escalation](../../knowledge-base/escalation-policy.md), Required handoff | Trusted scope explicitly permits internal access; all handoff fields, redaction, and 30-minute acknowledgment match. |
| 31 | [Tracking](../../knowledge-base/shipping-tracking.md), Delayed scans | Label-created meaning, one-business-day wait, and post-acceptance address restriction match. |
| 32 | [Browser](../../knowledge-base/troubleshooting-browser.md), Introduction and Isolation steps | Extensions, site-only cleanup, and two stable browser versions are supported; the last is contextual guidance. |
| 33 | [Security reports](../../knowledge-base/security-incidents.md) | Category, containment, prohibited ticket content, critical routing, and four-hour acknowledgment all match. |
| 34 | [Regions](../../knowledge-base/shipping-regions.md) and [tracking](../../knowledge-base/shipping-tracking.md), Missing delivery | Canada subject to checkout, preliminary checks, seven-day reporting, and conditional replacement need both documents. |
| 35 | [Plan changes](../../knowledge-base/billing-plan-changes.md) and [Starter](../../knowledge-base/plan-limits-starter.md) | End-of-period downgrade, all three exceeded quotas, paused automations, blocked uploads, and retained data match. |
| 36 | [Invoices](../../knowledge-base/billing-invoices.md) and [profile](../../knowledge-base/account-profile.md) | Object and applicable access scope are unknown; no universal administrator permission can be inferred. |
| 37 | [Refund timing](../../knowledge-base/refunds-timing.md) and [tracking](../../knowledge-base/shipping-tracking.md) | Missing process and elapsed time prevent choosing a completion/escalation rule. |
| 38 | [Status](../../knowledge-base/service-status.md) | Static policy contains no current outage state; a live answer would need another source. |
| 39 | [API retries](../../knowledge-base/api-rate-limits.md), Retry behavior | Backoff, no retry for authentication/validation errors, and immediate-retry risk all match. |
| 40 | [Starter](../../knowledge-base/plan-limits-starter.md), tenant metadata | Source belongs to another tenant. Public visibility does not remove the tenant constraint. |

## Interpretation limits for experiments

- Abstention labels mean the requested answer is unavailable or needs
  clarification. Related documents can still support an explanation of the
  limitation, especially slots 18, 27, and 38. Such cases have no relevance
  denominator in the current scorer; they are not automatic empty-search gates.
- Adversarial cases 19, 28, and 39 measure retrieval of corrective evidence.
  Answer-stage tests are needed to check whether the instruction was resisted.
- Privacy cases test explicit fictional scopes. Slot 40 has an empty second
  tenant; the corpus cannot establish isolation between two populated tenants.
- At source-check time the working mix contained 24 answerable cases: 4
  original human references and 20 provisional cases. Subsequent project-owner
  review of the six selected judgments moved 3 answerable and 3 abstention
  cases into the reference set. Current totals are **16 reviewed (7 answerable)**
  and **24 provisional (17 answerable)**. Keep their metrics separate; the
  assistant source check alone justifies no human-review claim.
