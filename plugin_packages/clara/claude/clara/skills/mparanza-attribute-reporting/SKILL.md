---
name: mparanza-attribute-reporting
description: Use when a user wants Clara to map retail product attributes, preserve the existing new-versus-rest or best-seller-versus-other analysis, create a private local HTML report, or answer whether that report is correct.
---

## Cowork execution contract

Work from the connected folder and supplied files first. Clara's trusted
`SessionStart` hook installs the package's exact declared Python requirements
into Clara's user-scoped plugin data directory and exposes them through
`PYTHONPATH`. Run the dependency check before Python-backed workflows. Do not
run ad hoc package installation or install undeclared dependencies during a
workflow. If the trusted bootstrap or dependency check fails, continue with
file-based work and state the limitation. MCP tools, browser or computer
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
only the observed whole-task outcome. Build and show the readable local model-data
report under `skills/mparanza-clara/references/model-data-report-contract.md`, link its
actual signed receipt, and ask once for the user's 1–5 stars after delivery.
Only user-authored feedback is submitted; tests remain explicitly marked.
Follow `skills/mparanza-clara/references/incident-recovery.md` for automatic technical
reporting, evidence requests and targeted remedies. Use `claraIncidents` if
local execution is unavailable. Never ask the user to relay logs or repeat consent
for technical reporting. Recovery requires an observed successful retry of the
original task and inputs, bound to the original report and current remedy.
Tutorials remain local-only and are excluded from task usage and ratings.
<!-- MPARANZA_REPORTING_END -->


# Attribute Reporting

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../mparanza-clara/SKILL.md`.

Resolve `../../modules/attribute-reporting` from this skill directory when it
exists; otherwise resolve `../../../attribute-reporting` in the repository.
Read that component's `skills/mparanza-attribute-reporting/SKILL.md` completely and
follow it. Treat the resolved component root as a read-only execution root for
its scripts, requirements, references, and vendored modules. Run component
helpers with that root as the working directory, but create every user run and
artifact outside the resolved component root, every Git repository, and every
plugin cache. Never place run artifacts in the packaged component.

Before running component helper scripts, delegate the dependency check from
the Clara root:

```bash
python scripts/check_dependencies.py --module attribute-reporting
```

Attribute Reporting is a self-contained analytical workflow. Do not register
its report in an advisory case, convert it into a 16:9 presentation, or upload
it to Mparanza unless the user separately asks for that follow-on work. If the
user asks for a presentation after the checked HTML report is complete, hand
the finished report to Clara's `html-deck` workflow as a new, explicit step.

Report files and image bytes remain local. Mapping and report evidence that
Claude reads may enter model context through the user's existing Claude plan;
the component helper scripts make no separate model API call. The authenticated
retail-data bridge remains a distinct Mparanza-hosted service.

Do not use this workflow for Brand Fit. When the user wants to compare completed
retailer signals with both a brand's current presence at that retailer and the
brand-owned catalogue, route to Clara's distinct `brand-fit` skill.
