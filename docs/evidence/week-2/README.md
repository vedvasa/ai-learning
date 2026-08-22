# Week 2 Cloud Run deployment evidence

Evidence date: 2026-08-21

Live service: [ai-learning-3y5vyfqynq-uw.a.run.app](https://ai-learning-3y5vyfqynq-uw.a.run.app/)

Current application revision: `0a9e55479ea2ffdc48f238b526bb936500d9d43c`

Initial bootstrap revision: `1df717f07ab34dd76130907886fbad294f3acce3`

## Initial bootstrap release chain

| Boundary | Verified value |
|---|---|
| Cloud Build | `673abc74-4452-4ab2-80d2-8daf79c34dd4` (`SUCCESS`) |
| Build duration | 2026-08-22 01:05:04Z to 01:06:07Z |
| Artifact Registry image | `us-west1-docker.pkg.dev/ai-learning-ved-2026/ai-learning/ai-learning` |
| Image digest | `sha256:c5ab8adad4fe0bec167164176251c7074be27330aa0c01c0fa83c2db75a71800` |
| Cloud Run revision | `ai-learning-git-1df717f07ab3` |
| Candidate tag | `git-1df717f07ab3` |
| Serving traffic | 100% to the verified revision |

Cloud Build ran the offline 30-case validation without provider credentials
before it published the image. Cloud Run then deployed the immutable digest,
not a mutable tag.

## Public service checks

These warm, read-only checks made no model-provider calls.

| Endpoint | HTTP status | Response time |
|---|---:|---:|
| `/` | 200 | 0.106 s |
| `/health/live` | 200 | 0.086 s |
| `/health/ready` | 200 | 0.090 s |
| `/openapi.json` | 200 | 0.097 s |

The initial release smoke script verified homepage text, fetched JavaScript
directly, checked the Ticket Triage API contract, and matched the deployed
application version against both the tagged revision URL and the default
service URL. It never called a generation, streaming, triage, or provider model
endpoint. Those checks established endpoint availability, not browser usability.

## Browser acceptance finding

A later real-browser check failed. The HTTPS homepage rendered these absolute
asset URLs:

```text
http://ai-learning-3y5vyfqynq-uw.a.run.app/static/styles.css
http://ai-learning-3y5vyfqynq-uw.a.run.app/static/app.js
```

The browser blocked the mixed-content assets. The computed body font remained
the unstyled browser default, and selecting the Prompt Playground tab did not
change the active tab or visible panel. The original smoke test missed the bug
because it requested `/static/app.js` directly and did not validate the asset
references emitted by the homepage or fetch the stylesheet.

PR 17 changed those references to same-origin root-relative URLs and strengthened
the smoke test to reject absolute HTTP asset references and fetch both assets.
The strengthened script was run read-only against the existing bootstrap URL
and rejected that revision as expected, without calling a provider endpoint.

## Corrected release chain

The user merged PR 17 and explicitly ran the documented deployment command. The
corrected release produced this traceable chain:

| Boundary | Verified value |
|---|---|
| Cloud Build | `41242a0e-6d29-4a8d-ba5f-a4b456c20407` (`SUCCESS`) |
| Build duration | 2026-08-22 01:40:09Z to 01:41:15Z |
| Application commit | `0a9e55479ea2ffdc48f238b526bb936500d9d43c` |
| Artifact Registry image | `us-west1-docker.pkg.dev/ai-learning-ved-2026/ai-learning/ai-learning` |
| Image digest | `sha256:255d3203ce972005f25c679dbfc61bdbb79b5ca886053eff34ac73e115b16d1a` |
| Cloud Run revision | `ai-learning-git-0a9e55479ea2` |
| Candidate tag | `git-0a9e55479ea2` |
| Serving traffic | 100% to the corrected revision |
| Previous revision | `ai-learning-git-1df717f07ab3`, retained at 0% traffic |

The strengthened provider-free smoke test passed against the public service and
matched the full application commit. A real-browser acceptance check then
confirmed:

- CSS and JavaScript resolved over HTTPS;
- the stylesheet changed the browser-default typography to the application font
  stack;
- the header displayed the full corrected application commit; and
- selecting Prompt Playground changed its `aria-selected` value to `true`, hid
  Ticket Triage, and displayed the Prompt Playground panel.

Neither check submitted a generation or triage form. Measured provider calls and
model spend for the corrected release verification remained zero.

## Runtime boundary

The live service configuration was inspected after promotion:

- dedicated `ai-learning-runtime` service identity;
- OpenAI and Anthropic secrets injected from explicit Secret Manager version
  `1`, with no secret values in the service definition;
- one vCPU, 512 MiB memory, concurrency `4`, and a 60-second timeout;
- request-based CPU throttling;
- minimum instances `0` and maximum instances `1`;
- startup probe on `/health/ready` and liveness probe on `/health/live`; and
- image pinned to the recorded Artifact Registry digest.

Up to 200 recent corrected-revision Cloud Run log entries were checked for
provider-key patterns after verification. No OpenAI or Anthropic key pattern or
key assignment was found. The check reports only pass/fail and does not copy log
payloads into the repository.

## Cost and rollback notes

The build, deployment, and smoke tests made zero provider model calls, so
measured model spend for this release is `$0.00`. Cloud usage is constrained by
scale-to-zero, a one-instance maximum, a project budget alert, and the active
free trial/free-tier allowances. This evidence does not claim a reconciled cloud
invoice.

Cloud Run could not create the service with a zero-traffic first revision, so the
bootstrap revision received traffic immediately. The corrected release used the
intended candidate gate and now leaves the bootstrap revision available at 0%
traffic. An actual rollback drill is possible but has not been exercised; it
requires a separate explicit traffic-change authorization. Every later release
uses a zero-traffic candidate before promotion.
