---
name: mparanza-apertura-pratica
description: Use when Lucia must open a new client matter or a new matter for an existing client, organize intake evidence, map parties, prepare conflict-search candidates, define engagement scope, surface possible deadlines, assess conditional AML posture, propose a folder plan, and create a lawyer-reviewable opening package.
---
<!-- MPARANZA_REPORTING_BEGIN -->
## Task reporting and recovery

For every substantive user mandate, follow
`skills/mparanza-lucia/references/workflow-usage.md` from this installation's root.
Start one primary task before preparation, using `usage/pipelines.json`; nested
specialists, retries and Studio Archive infrastructure reuse that task. Record
only the observed whole-task outcome. Build and show the readable local model-data
report under `skills/mparanza-lucia/references/model-data-report-contract.md`, link its
actual signed receipt, and ask once for the user's 1–5 stars after delivery.
Only user-authored feedback is submitted; tests remain explicitly marked.
Follow `skills/mparanza-lucia/references/incident-recovery.md` for automatic technical
reporting, evidence requests and targeted remedies. Use `luciaIncidents` if
local execution is unavailable. Never ask the user to relay logs or repeat consent
for technical reporting. Recovery requires an observed successful retry of the
original task and inputs, bound to the original report and current remedy.
Tutorials remain local-only and are excluded from task usage and ratings.
<!-- MPARANZA_REPORTING_END -->


# Fascicolo nuova pratica

Resolve `../../modules/apertura-pratica` from this skill directory when it
exists; otherwise resolve `../../../apertura-pratica` in the repository. Read
that module's `skills/mparanza-apertura-pratica/SKILL.md` completely and follow it. Treat
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
