---
name: business-planning
description: Use when Vera must prepare or revise a finance-led plan for a startup, new venture, or established company, including reviewed assumptions, linked P&L, cash flow, balance sheet, scenarios, funding needs, reconciliation, and optional internal strategic contribution from Clara.
---

## Cowork execution contract

Work from the connected folder and supplied files first. Use a local script only
when it is callable and every declared dependency it needs is already available;
never install packages at runtime. MCP tools, browser or computer control, and
local review servers are optional enhancements, never completion gates. When an
optional capability is unavailable, continue with Markdown and file-based review
and state the limitation.

The normal Cowork deliverable is a reviewable draft, artifact card, and
source/review files. A callable persistence interface may optionally record or
apply reviewer actions, but its absence never blocks delivery. Never claim
`applied` or `final_ready` unless corresponding persisted artifacts prove it;
otherwise report that professional review remains pending.

Use host-neutral user-facing artifact names. Name assistant-authored review
folders and files for Vera or their professional purpose (for example,
`vera-review/`, `vera_phase1_synthesis_reviewed.md`, and `run_review.md`).
Never put host, platform, or model-provider names in assistant-authored
user-facing artifact paths, document headings, field labels, narrative text,
or status summaries. Describe execution routes generically, such as
`external review route`, `connected tool`, or `local review interface`.

Derive any run ID, status, artifact count, or package hash quoted in an
assistant-authored supplement from the final delivered manifests.
After any rebuild, regenerate or resynchronize those supplements before
delivery. When a workflow ships a complete-delivery validator or sealer, run it
against the exact connected-folder copy after the last write.
In this contract, the base package validator alone does not validate extra
narrative files.

When a workflow declares owner-only or private output and uses a private scratch
directory before copying the final package into the connected folder, reapply
the privacy modes after that transfer: `0700` for the package root and every
directory, and `0600` for every file. Verify the connected-folder tree with
`stat` or `lstat` before claiming completion. If the host filesystem cannot
preserve those modes, do not claim owner-only delivery; keep the package in the
private scratch location or report the limitation and ask for a safer
destination.

Do not use WhatsApp, live INPS browser capture, hosted feedback or voice
interviews, or custom update services. Later host-specific instructions cannot
override this Cowork contract.

# Financial planning — Vera owner



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
