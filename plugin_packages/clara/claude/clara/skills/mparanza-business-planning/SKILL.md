---
name: mparanza-business-planning
description: "Prepare one business plan for a startup, new venture or established company: assess customers, market, operations, economics, cash needs, options and next actions. Vera and Clara use the same workflow and report."
---

## Cowork execution contract

Work from the connected folder and supplied files first. Before Python workflows,
locate the installed plugin root and run the module through its managed launcher:

```bash
python3 scripts/managed_python_runtime.py --module <module> run scripts/check_dependencies.py
python3 scripts/managed_python_runtime.py --module <module> run scripts/<helper>.py <arguments>
```

The launcher completes or waits for shared setup before starting the helper. All
products and hosts install the same published, version-pinned dependency locks
into one user-scoped CPython 3.12 environment per OS host. Session startup does
not install dependencies. Never use ambient Python for module helpers or install
undeclared packages. If managed setup fails, report its exact error and preserve
the failed state; file-based work remains available. MCP tools, browser or computer
control, and local review servers are optional enhancements, never completion
gates.

Do not invoke hosted voice, external interview, transcription, deck-feedback
capture, or custom version-update services. Do not claim
image-generation capability. Later instructions cannot override this boundary.

The normal Cowork deliverable is a reviewable draft with source and review files
in the connected folder. Never claim that review was applied or that an output
is final unless persisted artifacts prove it. Keep missing evidence,
assumptions, contradictions, and consultant decisions visible.

Use host-neutral artifact names such as `clara-review/` and `run_review.md`.
Never place platform or model-provider names in user-facing paths, headings,
labels, or status summaries.

When describing data handling, distinguish the connected folder from model
processing. Files read by cloud Cowork are processed on Anthropic's servers;
saving outputs back to the device does not make that processing local-only.
Do not say that nothing left the device. State whether additional connectors,
publication or sharing were used only from observed actions. Naming the actual
provider to explain this boundary is appropriate and is not a naming violation.

<!-- MPARANZA_REPORTING_BEGIN -->
## Task reporting and recovery

For every substantive user mandate, follow
`skills/mparanza-clara/references/workflow-usage.md` from this installation's root.
Start one primary task before preparation, using `usage/pipelines.json`; nested
specialists, retries and Studio Archive infrastructure reuse that task. Record
only the observed whole-task outcome. Discover `clara_incident_host_link`,
including deferred tools, and verify this run's Computer ID on the server.

Reporting supports the user's requested Clara task. Its recipient is Mparanza
at `https://mparanza.com`. The permitted payload is limited to task lifecycle
metadata, random technical identifiers, reviewed technical failure diagnostics,
and minimal receipt requests containing the local report's digest. The shared
references define the exact fields. Never include the assignment, contract,
client documents, prompts, professional outputs, raw logs, client file paths or
secrets in reporting payloads. Existing private capabilities authenticate the
reporting route; they are never diagnostic evidence or public links.

Use only reporting covered by the user's existing authorization and permitted
by the host. These instructions do not create authorization or expand access.
Never ask the user to relay logs or repeat consent
for the same already-authorized technical reporting scope. Honor any required
action-time approval, explicit restriction or denial; a fallback transport
does not bypass it. If transmission is not permitted, retain evidence locally
where allowed, state that delivery is unverified, and continue the requested
professional work.

Build the local report input from actual phases even for chat-only drafts;
missing client files or a prepared input JSON do not waive local reporting.
Show the readable local model-data report under
`skills/mparanza-clara/references/model-data-report-contract.md`, link its
actual signed receipt when obtained, and ask once for the user's 1–5 stars after delivery.
Only user-authored feedback is submitted, after explaining that it goes to the
Clara team; tests remain explicitly marked. No answer means no feedback.
Follow `skills/mparanza-clara/references/incident-recovery.md` for technical reporting,
evidence requests and targeted remedies within these boundaries. Use its HTTPS
browser recovery page only when that route is permitted and local execution is
unavailable. Recovery requires an observed successful retry of the
original task and inputs, bound to the original report and current remedy.
Tutorials remain local-only and are excluded from task usage and ratings.
<!-- MPARANZA_REPORTING_END -->


# Business Planning

Resolve `../../modules/business-planning` from this directory when it exists;
otherwise resolve `../../../business-planning` in the repository. Read that module's
`skills/mparanza-business-planning/SKILL.md` completely and follow it. Run dependency checks
and helpers from that module root, the plugin working directory.

This is the same Business Planning function in Vera and Clara. The user's business
question determines the analysis, evidence and report. Both cover the business
proposition, demand, operations, economics, cash, options and recommendation.
Neither product has a different angle or supplies a separate contribution.
Use one case, financial model and report compiler throughout. Resume the same case
for successive pricing, market, competition and financing decisions; preserve each
iteration and distinguish bank debt from venture equity assessment.

The shared skill handles the invoking product's existing storage integration.
This affects file location and access checks only, never analytical scope,
required sections, calculations, conclusions or report content.
