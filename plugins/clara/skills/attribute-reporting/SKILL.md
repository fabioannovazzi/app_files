---
name: attribute-reporting
description: Use when a user wants Clara to map retail product attributes, preserve the existing new-versus-rest or best-seller-versus-other analysis, create a private local HTML report, or answer whether that report is correct.
---
<!-- MPARANZA_REPORTING_BEGIN -->
## Task reporting and recovery

For every substantive user mandate, follow
`skills/clara/references/workflow-usage.md` from this installation's root.
Start one primary task before preparation, using `usage/pipelines.json`; nested
specialists, retries and Studio Archive infrastructure reuse that task. Record
only the observed whole-task outcome. Build and show the readable local model-data
report under `skills/clara/references/model-data-report-contract.md`, link its
actual signed receipt, and ask once for the user's 1–5 stars after delivery.
Only user-authored feedback is submitted; tests remain explicitly marked.
Follow `skills/clara/references/incident-recovery.md` for automatic technical
reporting, evidence requests and targeted remedies. Use `claraIncidents` if
local execution is unavailable. Never ask the user to relay logs or repeat consent
for technical reporting. Recovery requires an observed successful retry of the
original task and inputs, bound to the original report and current remedy.
Tutorials remain local-only and are excluded from task usage and ratings.
<!-- MPARANZA_REPORTING_END -->


<!-- CLARA_OPENAI_ONBOARDING_BEGIN -->
Onboarding is optional. Continue ordinary professional work immediately,
including direct specialist invocation, without checking or completing a local
onboarding profile. Missing, unfinished, inaccessible or corrupt onboarding state,
or unavailable voice/window controls, must never block ordinary work. Do not
automatically start, resume or repeatedly offer onboarding.
Only for a user-requested tutorial or a native teaching handoff, read
`../clara/references/local-onboarding.md`. A verified paired lesson worker
executes only its bound lesson and token; never bypass tutorial validation.
Tutorial profiles, progress, examples and feedback remain local; never send a
change request, stamp a tutorial receipt or call hosted interviews for a tutorial.
Current user requests take precedence over saved preferences.
<!-- CLARA_OPENAI_ONBOARDING_END -->

# Attribute Reporting

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../clara/SKILL.md`.

Resolve `../../modules/attribute-reporting` from this skill directory when it
exists; otherwise resolve `../../../attribute-reporting` in the repository.
Read that component's `skills/attribute-reporting/SKILL.md` completely and
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
Codex reads may enter model context through the user's existing ChatGPT plan;
the component helper scripts make no separate model API call. The authenticated
retail-data bridge remains a distinct Mparanza-hosted service.

Do not use this workflow for Brand Fit. When the user wants to compare completed
retailer signals with both a brand's current presence at that retailer and the
brand-owned catalogue, route to Clara's distinct `brand-fit` skill.
