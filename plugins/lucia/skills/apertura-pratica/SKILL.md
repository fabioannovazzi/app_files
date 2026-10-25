---
name: apertura-pratica
description: Use when Lucia must open a new client matter or a new matter for an existing client, organize intake evidence, map parties, prepare conflict-search candidates, define engagement scope, surface possible deadlines, assess conditional AML posture, propose a folder plan, and create a lawyer-reviewable opening package.
---
<!-- MPARANZA_REPORTING_BEGIN -->
## Task reporting and recovery

For every substantive user mandate, follow
`skills/lucia/references/workflow-usage.md` from this installation's root.
Start one primary task before preparation, using `usage/pipelines.json`; nested
specialists, retries and Studio Archive infrastructure reuse that task. Record
only the observed whole-task outcome. Discover `lucia_incident_host_link`,
including deferred tools, and verify this run's Computer ID on the server.
Build the report input from actual phases even for chat-only drafts; missing
client files or a prepared input JSON do not waive reporting. Show the readable
local model-data report under `skills/lucia/references/model-data-report-contract.md`, link its
actual signed receipt, and ask once for the user's 1–5 stars after delivery.
Only user-authored feedback is submitted; tests remain explicitly marked.
Follow `skills/lucia/references/incident-recovery.md` for automatic technical
reporting, evidence requests and targeted remedies. Use the HTTPS browser recovery page in that reference if
local execution is unavailable. Never ask the user to relay logs or repeat consent
for technical reporting. Recovery requires an observed successful retry of the
original task and inputs, bound to the original report and current remedy.
Tutorials remain local-only and are excluded from task usage and ratings.
<!-- MPARANZA_REPORTING_END -->


<!-- LUCIA_OPENAI_ONBOARDING_BEGIN -->
Onboarding is optional. Continue ordinary professional work immediately,
including direct specialist invocation, without checking or completing a local
onboarding profile. Missing, unfinished, inaccessible or corrupt onboarding state,
or unavailable voice/window controls, must never block ordinary work. Do not
automatically start, resume or repeatedly offer onboarding.
Only for a user-requested tutorial or a native teaching handoff, read
`../lucia/references/local-onboarding.md`. A verified paired lesson worker
executes only its bound lesson and token; never bypass tutorial validation.
Tutorial profiles, progress, examples and feedback remain local; never send a
change request, stamp a tutorial receipt or call hosted interviews for a tutorial.
Current user requests take precedence over saved preferences.
<!-- LUCIA_OPENAI_ONBOARDING_END -->

# Fascicolo nuova pratica

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../lucia/SKILL.md`.

Resolve `../../modules/apertura-pratica` from this skill directory when it
exists; otherwise resolve `../../../apertura-pratica` in the repository. Read
that module's `skills/apertura-pratica/SKILL.md` completely and follow it. Treat
the resolved module root as the plugin working directory for every command, schema,
reference, script and review asset.

This is Lucia's native legal-matter-opening contract. It reuses Studio Archive
only for private client, engagement, input and run lifecycle. It does not use
Legal/Tax Answer Review as its completion gate and does not inherit Vera's
accounting intake semantics.

Before finalizing a durable Studio Archive run, follow that component's model-data
report contract for the actual model-context evidence and its limits. Build the
readable local report through Lucia's `scripts/workflow_usage.py build-report`
using this primary task ID; it obtains and links the signed receipt. Show the
report with the delivered result. Report creation does not mean that the matter's
professional analysis ran without a model.
