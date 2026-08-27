---
name: business-planning
description: Use when Clara must prepare or revise the strategic and commercial business plan of a startup, new venture, or established company, including evidence-linked findings, options, recommendation, initiatives, milestones, KPIs, risks, and a controlled handoff to Vera.
---

# Business Planning — Clara lens

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

When a reviewed Vera `business_planning_handoff.json` is available, use it as
bounded financial evidence. Compare its shared assumption IDs and descriptions
with Clara's case, show any divergence, and return material inconsistencies for
professional resolution. Never reinterpret reconciled figures, change Vera's
accounting assumptions, or present statement closure as strategic validation.
