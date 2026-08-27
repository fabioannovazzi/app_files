---
name: business-planning
description: Use when Vera must prepare or revise the accounting and financial business plan of a startup, new venture, or established company, including reviewed assumptions, linked P&L, cash flow, balance sheet, scenarios, funding needs, reconciliation, and a controlled handoff to Clara.
---

# Business Planning — Vera lens

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.

Resolve `../../modules/business-planning` from this skill directory when it
exists; otherwise resolve `../../../business-planning` in the repository. Read
that module's `skills/business-planning/SKILL.md` completely and follow it.
Treat the resolved module root as the plugin working directory for dependency checks
and helper commands.

Vera fixes `professional_lens=accounting_financial`. Do not ask the user to
choose the Clara lens and do not use the strategic finalizer as Vera's output.
The same route supports startups and established companies; record the company
stage in reviewed plain language and do not classify it with deterministic
rules.

When a reviewed Clara `business_planning_handoff.json` is available, use it as
bounded strategic evidence. Compare its shared assumption IDs and descriptions
with Vera's case, show any divergence, and return material inconsistencies for
professional resolution. Never convert strategic statements into numbers or
silently alter Clara's recommendation. Pass the file to the financial finalizer
with `--counterpart-handoff`; do not finalize until its durable handoff review
reports `aligned_for_counterpart_use`.
