---
name: business-planning
description: Use when Vera must prepare or revise a finance-led plan for a startup, new venture, or established company, including reviewed assumptions, linked P&L, cash flow, balance sheet, scenarios, funding needs, reconciliation, and optional internal strategic contribution from Clara.
---

# Financial planning — Vera owner

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

Vera remains the visible owner of the request and final deliverable. Do not ask
the user to invoke Clara, move a JSON file, choose an internal lens, or interpret
internal compatibility statuses. When the user requests a complete cross-lens
plan and Clara is callable, obtain Clara's bounded strategic contribution
internally and include it in Vera's final review package. For a finance-only
request, do not create collaboration ceremony.

When a Clara `counterpart_contribution.json` is available, compare its source
readiness, exact case identity, shared context and shared assumption IDs and
descriptions with Vera's case. Pass it to the financial finalizer with
`--counterpart-contribution`. The runner binds mechanically compatible strategic
content into the Vera-owned plan and writes one combined assumption register.
It keeps the plan `partial` and shows unresolved differences when owner review
is needed. Never convert strategic statements into numbers or silently alter
Clara's recommendation. Mechanical compatibility is not semantic or
professional agreement.
