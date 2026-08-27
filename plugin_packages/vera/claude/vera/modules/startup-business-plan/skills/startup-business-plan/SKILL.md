---
name: startup-business-plan
description: Use when Vera must prepare or revise one integrated forward-looking business plan for a startup or new venture, including linked profit and loss, cash flow, balance sheet, scenarios, funding needs, and an assumption ledger. Do not use for an established-company strategic plan, a sales-only Plan, historical analysis, recurring management reporting, or concordato review.
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

## Output location

Never write run outputs inside this Git workspace or a published folder. In
Claude, use only the exact Studio Archive run output for workflow ID
`startup-business-plan`.

# Startup Business Plan

Use this workflow for startups and new ventures, including idea, pre-revenue,
pilot, and early-revenue stages. Record the reviewed `venture_stage` in plain
language. Use pilot evidence and early actuals when they exist. When they do
not, start from explicitly confirmed opening balances, available funding,
assumptions, and milestones. Never interpret missing history as zero.

Do not use this workflow for an established company's strategic, corporate,
turnaround, or investment business plan. Vera currently has no equivalent
established-company workflow. State that boundary instead of silently adapting
this startup workflow or claiming that a Clara workflow already exists.

This workflow prepares an integrated planning case. Route a request limited to
sales volumes, prices, revenue, discounts, COGS, or FX to `sales-plan`; route
historical analysis to `financial-analysis`; route recurring reporting to
`management-control-pack`; and route insolvency-plan review to
`concordato-plan-review`.

## Judgment boundary

Model-led and professional judgment own the business objective, evidence
meaning, source selection, scenario meaning, commercial and operational
drivers, assumption classification, market interpretation, risks, narrative,
and approval. Do not infer numerical values from qualitative statements. Read
back every material assumption and obtain confirmation before calculation.

Deterministic code owns the reviewed case shape, canonical Decimal parsing,
period order, assumption-reference closure, exact statement arithmetic,
working-capital roll-forward, debt and equity roll-forward, reconciliation,
funding-gap calculation, artifact hashes, and replay receipt. These mechanics
are fixed because their correctness is mechanically verifiable and the three
statements must close exactly. They do not prove that assumptions are probable,
market evidence is sufficient, or the plan is professionally approved.

## Client-bound run

In Claude:

1. Select one Studio Archive client and engagement.
2. Import the exact reviewed evidence as immutable `source` receipts. A startup
   may have no historical accounts, but it still needs reviewed opening facts
   and confirmed assumptions.
3. Prepare and start workflow ID `startup-business-plan` from the exact selected
   inputs and any finalized same-engagement upstream artifacts used.
4. Pass the returned `client_engagement_path` unchanged to the helper and write
   only below its `output_dir`.
5. Finalize every physical output with a stable artifact ID, relative path,
   purpose, audience, and media type. Review the declaration and complete the
   run. Record failure or cancellation instead of treating partial files as a
   result.

In Cowork, use only explicitly connected files and folders and state that no
portable Studio Archive run was created.

## Cowork-native Run UX

Before helper scripts, identify the material choices that can change the plan:
entity, venture stage, objective, audience, currency, periods, opening position, evidence,
scenarios, assumption bases, tolerance, and output folder. Ask only those unresolved choices in chat and wait only when the answer would materially
change execution. Generate options from the actual inputs; do not propose named
methods, scenario taxonomies, or output variants unless the facts cue them.

Default output policy: produce the complete normal planning package described
below. Natural structured, spreadsheet, factual-review, model-context, and
receipt outputs are not choices to propose.

1. Start with a visible checklist for intake, dependency check, evidence and
   assumption review, calculation, reconciliation, interpretation, visual
   inspection, and delivery.
2. Show a Run Intake table with client, engagement, venture stage, objective, audience,
   currency, periods, evidence, opening position, scenarios, output folder,
   and unresolved choices.
3. Show a compact Decision Table only for material unresolved choices grounded
   in the actual inputs. Keep evidence, assumptions, hypotheses, unknowns, and
   professional decisions separate.
4. Before a long or write-heavy step, show an execution checkpoint with command
   intent, inputs, output folder, and expected artifacts. Explicit approval is
   reserved for external, destructive, approval-sensitive, or material steps;
   local inspection, calculation, and authorized run-output writes do not add
   an approval ceremony.
5. End with an Artifact Card listing every output path, purpose, evidence
   coverage, scenario coverage, reconciliation status, funding gaps, review
   status, unresolved items, and next action. When useful, write
   `run_review.md` beside the run artifacts. Never edit plugin source or
   generated ZIPs during a client-data run.

## Intake and assumption review

Start with a checklist and a Run Intake table covering the entity, venture
stage, planning purpose, audience, currency, periods, available evidence, opening position,
scenarios, output folder, and unresolved choices. Adapt the questions to the
case without exposing internal modes.

Keep these classes separate:

- source-supported historical or opening facts;
- external evidence;
- management assumptions;
- model-proposed hypotheses;
- calculated results;
- missing information and professional judgments.

For every material numerical assumption, show its ID, description, evidence
or hypothesis basis, effective periods, scenario scope, rationale, and status.
Ask only about unresolved choices that can change the result. The professional
must confirm the complete assumption read-back and opening position before the
case receives `review.status=reviewed`. A model-proposed hypothesis may enter
the case only after it is clearly labelled and explicitly confirmed.

The planning horizon and period labels come from the reviewed case. Do not
hard-code annual or monthly granularity. The initial deterministic contract
supports up to 60 ordered periods and eight scenarios.

Read [the case contract](../../references/case-contract.md) before writing or
reviewing `business_plan_case.json`.

`requirements.txt` is the complete core dependency declaration. Run
`python scripts/check_dependencies.py` before calculation. Do not install
arbitrary packages at runtime. If a dependency is missing, install only the
published declaration when the environment and user authority permit it;
otherwise report the unavailable capability.

## Calculation

From the module root:

```bash
python scripts/check_dependencies.py
python scripts/run_business_plan.py \
  --case <run-output>/business_plan_case.json \
  --client-engagement <context.json> \
  --output-dir <run-output>/plan
```

The reviewed case uses canonical Decimal strings. Each scenario supplies the
same ordered periods and references confirmed assumptions effective for those
periods. The runner calculates linked P&L, cash flow, balance sheet, break-even
period, minimum cash, and funding requirement. It does not forecast demand,
select assumptions, search the market, or create a balancing plug.

Stop on an invalid case, missing confirmation, unknown evidence or assumption
reference, impossible fixed-asset or debt roll-forward, changed run context,
or failed statement reconciliation. A negative cash balance is not hidden: it
becomes an explicit funding requirement.

## Interpretation and delivery

Read `business_plan.json`, `reconciliation.json`, `model_context.json`, and
`execution_receipt.json` before drafting conclusions. Use the bounded model
context for interpretation; do not reopen complete source populations merely
because they are available. When a claim needs source detail, retrieve only the
specific evidence required and record the reason.

Separate calculated observations from hypotheses, questions, evidence gaps,
risks, and professional decisions. The generated workbook and factual review
remain `draft_pending_professional_review`. A reconciled plan proves only that
the confirmed schedules were applied consistently.

Normal outputs are:

- `business_plan.json`;
- `business_plan.xlsx`;
- `assumption_ledger.csv`;
- `reconciliation.json`;
- `model_context.json` and `commentary_template.json`;
- `business_plan_facts.md` and `business_plan_review.html`;
- `execution_receipt.json`.

After every model-visible phase, follow the Vera run-level model-data report
contract. End with an Artifact Card listing coverage, reconciliation status,
funding gaps, unresolved evidence, professional-review status, and next action.
