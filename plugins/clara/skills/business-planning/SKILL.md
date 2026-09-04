---
name: business-planning
description: Use when Clara must prepare or revise a strategy-led business plan for a startup, new venture, or established company, including evidence-linked findings, options, recommendation, initiatives, milestones, KPIs, risks, and optional internal financial contribution from Vera.
---

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
