---
name: business-planning
description: Use when Clara must prepare or revise a strategy-led business plan for a startup, new venture, or established company, including evidence-linked findings, options, recommendation, initiatives, milestones, KPIs, risks, and optional internal financial contribution from Vera.
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

# Strategic business planning — Clara owner

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../clara/SKILL.md`.

Resolve `../../modules/business-planning` from this skill directory when it
exists; otherwise resolve `../../../business-planning` in the repository. Read
that component's `skills/business-planning/SKILL.md` completely and follow it.
Treat the resolved component root as the working directory for dependency checks
and helper commands.

Clara fixes `professional_lens=strategic_commercial`. Do not ask the user to
choose the Vera lens and do not use the financial runner as Clara's output. The
same route supports startups and established companies; record the company
stage in reviewed plain language and do not classify it with deterministic
rules.

Use `advisory-brief-planner` first when the assignment itself is still
materially unframed, and keep `advisory-case-director` in charge when this is a
durable advisory case. The business-planning skill retains authority for the
plan's strategic-commercial method and output.

Clara remains the visible owner of the request and final deliverable. Do not ask
the user to invoke Vera, move a JSON file, choose an internal lens, or interpret
internal compatibility statuses. When the user requests a complete cross-lens
plan and Vera is callable, obtain Vera's bounded financial contribution
internally and include it in Clara's final review package. For a strategy-only
request, do not create collaboration ceremony.

When a Vera `counterpart_contribution.json` is available, compare its source
readiness, exact case identity, shared context and shared assumption IDs and
descriptions with Clara's case. Pass the Clara workspace with
`--case-workspace` and the contribution with `--counterpart-contribution`. The
runner binds mechanically compatible financial summaries into the Clara-owned
plan and writes one combined assumption register. It keeps the plan `partial`
and shows unresolved differences when owner review is needed. Never reinterpret
reconciled figures, change Vera's accounting assumptions, or present statement
closure as strategic validation. Mechanical compatibility is not semantic or
professional agreement.
