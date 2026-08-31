# Reusable Codex session prompts

Use a fresh Codex task for each coherent engineering objective. The repository,
not an earlier conversation, is the durable source of truth. Replace the angle-
bracketed placeholders, paste the opening prompt into the new task, and let
Codex inspect the repository before approving implementation.

## Opening prompt

```text
We are starting <OBJECTIVE_ID>: <OBJECTIVE_GOAL> in the ai-learning project.

Repository: /Users/ved/Documents/ChatGPT/ai-learning

Read AGENTS.md, docs/CURRENT_MILESTONE.md, the relevant section of
PRODUCTION_AI_SELF_LEARNING_GUIDE.md, LEARNING_PROGRESS_TRACKER.md, relevant
ADRs and runbooks, and recent Git history. Treat those repository files as the
durable context; do not rely on an earlier chat.

Before making changes:
1. Inspect the current implementation and tests relevant to this objective.
2. Explain the existing baseline and dependencies in clear, short language.
3. Identify any discrepancy between the milestone, guide, and current code.
4. Propose a focused, PR-sized implementation and validation plan.
5. Identify anything that requires my explicit approval.

Never read, display, request, copy, or log any secret value. Do not inspect
.env files, process environment variables, local credential stores, or Secret
Manager payloads. If secret setup is necessary, give me exact commands that use
hidden interactive input so I enter the value myself without exposing it to
you, shell history, logs, or Git. Verify only non-secret metadata such as the
secret's existence, version number, permissions, or configuration state.
Ensure secrets and generated credentials are never staged or committed to
GitHub.

A request to change code or prepare a PR does not authorize a deployment,
remote database migration, secret or IAM change, paid provider call, traffic
change, destructive action, release, or tag. Ask me before any such action.
Prefer provider-free local tests first. Do not make implementation changes until
you have reported the baseline and proposed plan.
```

## Closing and handoff prompt

Use this before ending an objective or when a task has accumulated too much
context:

```text
Prepare a durable handoff for the ai-learning objective we just worked on.

1. Review the diff for correctness, scope, privacy, and secret hygiene.
2. Run the relevant provider-free validation and report the exact results.
3. Update the appropriate existing documentation, including
   docs/CURRENT_MILESTONE.md, with what is complete, what remains, decisions,
   limitations, and the exact next starting point.
4. Record durable architectural or operational decisions in the relevant ADR
   or runbook; do not create a duplicate roadmap or diary.
5. Prepare or update the focused PR, but do not deploy, migrate a remote
   database, make paid calls, change secrets/IAM/traffic, or create a release or
   tag without my explicit approval.
6. Give me a short summary and the exact prompt to use for the next Codex task.

Never inspect .env files, environment variables, credential stores, or secret
payloads. Never stage or commit a secret. If a future step needs a secret, give
me hidden-input commands to run myself and verify only non-secret metadata.
```

The active milestone may include a more specific opening prompt. Prefer that
version when present, while keeping the security and approval boundaries above.
