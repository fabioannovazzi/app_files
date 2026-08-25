---
name: management-control-pack
description: Use when Vera must turn reviewed accounting exports into one connectorless management-control pack covering the supported P&L, budget, working-capital, cash, concentration, and profitability sections.
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
`management-control-pack`.

# Management Control Pack

Use this workflow when the requested outcome is one recurring management pack,
not one isolated variance, reconciliation, due-diligence schedule, or generic
report. The workflow accepts user-supplied `.xlsx`, `.xlsm`, `.csv`, or `.zip`
exports and does not require an ERP connector.

The normal pack includes every section supported by the supplied evidence:

- monthly P&L and head metrics from the general ledger or management accounts;
- Actual-versus-Budget variance when a reviewed Budget table is supplied;
- receivables and payables aging at one explicit cutoff date;
- monthly bank inflows, outflows, net movement, and latest reported balances;
- customer concentration from revenue rows with reviewed customer identity;
- service or product profitability when revenue and direct cost are authoritative.

Missing optional evidence makes the affected section `unavailable` and the
overall pack `partial`; it never triggers invented values. A missing or invalid
general-ledger mapping blocks the pack.

## Judgment boundary

Deterministic code owns stable file inventory, explicit-column extraction,
date and canonical Decimal parsing, exact aggregation, aging buckets, source
control-total checks, metric-reference closure, output rendering, and hashes.
Those fixed rules are justified because arithmetic, period membership after a
reviewed mapping, schema shape, and artifact identity are mechanically
verifiable and must replay exactly.

Claude and the professional own source roles, accounting perimeter, account and
category meaning, sign convention, fiscal calendar, customer identity,
materiality, interpretation, hypotheses, follow-up questions, and approval.
Never infer a source role from a filename or sheet name. Never turn a calculated
movement into an asserted business cause.

## Client-bound run

In Claude:

1. Select one Studio Archive client and engagement.
2. Import the exact exports as immutable `source` receipts.
3. Prepare and start workflow ID `management-control-pack` from those inputs.
4. Pass the returned absolute `client_engagement_path` unchanged to every
   helper and write only below its `output_dir`.
5. Finalize every physical output with a stable artifact ID, path, purpose,
   audience, and media type; review the declaration and complete the run.
   Record a failed or cancelled run instead of treating partial files as final.

In Cowork, use only explicitly connected files and folders. State that no
portable Studio Archive run was created.

## Cowork-native Run UX

Before helper scripts, identify the material choices that can change the pack:
entity, period, cutoff, currency, source roles, columns, category mapping,
signs, control totals, aging buckets, customer identity, and audience. Ask only those unresolved choices in chat and wait only when the answer would materially
change execution.
Generate options from the actual evidence; do not propose named methods,
categories, or output variants unless the facts cue them.

Default output policy: produce every supported section and all normal
structured, spreadsheet, narrative, dashboard, context, and receipt artifacts.
Natural outputs are not choices to propose.

1. Start with a visible checklist for intake, dependency check, inspection,
   mapping review, calculation, control review, commentary, visual inspection,
   and delivery.
2. Show a Run Intake table with client, engagement, sources, period, cutoff,
   currency, output folder, confirmed mappings, and unresolved items.
3. Show a compact Decision Table only for material unresolved choices generated
   from the actual inputs. Keep calculated facts, hypotheses, professional
   decisions, and unavailable evidence distinct.
4. Before a long or write-heavy step, show an execution checkpoint with the
   command intent, inputs, output folder, and expected artifacts. Apply the
   approval boundary below.
5. End with an Artifact Card listing every delivered path, purpose, coverage,
   control status, review status, unresolved items, and next action. When useful,
   write `run_review.md` beside the run artifacts. Never edit plugin
   source or generated ZIPs during a client-data run.

## Intake and mapping

Establish or ask only for unresolved material choices:

- entity and reporting perimeter;
- reporting start, end, cutoff date, fiscal calendar, and currency;
- source table roles and exact column mappings;
- whether amounts are already normalized or require a reviewed debit/credit
  rule or sign multiplier; use `amount_multiplier` for mapped ledger, Budget,
  or bank movements, `balance_multiplier` for bank balances, and the separate
  `revenue_multiplier` and `direct_cost_multiplier` for sales lines;
- reviewed mapping from source categories to `revenue`, `cogs`,
  `operating_expense`, `other_operating`, `depreciation_amortization`,
  `interest`, `tax`, or `other`;
- any source control totals and tolerance;
- customer-parent identity, top-customer count, aging buckets, and materiality
  only when they change the requested output.

Start with a visible checklist and Run Intake table. Run the dependency check,
then inspect the complete files locally:

```bash
python scripts/check_dependencies.py
python scripts/inspect_inputs.py \
  --input <bound-export> [--input <bound-export> ...] \
  --client-engagement <context.json> \
  --output-dir <run-output>/inspection
```

`requirements.txt` is the complete core dependency declaration. Do not install
arbitrary packages at runtime. If the check reports a missing requirement,
install only that published declaration when the environment and user authority
permit it; otherwise report the unavailable capability.

Explicit approval is reserved for external, destructive, approval-sensitive,
or material steps. Ordinary local inspection, deterministic calculation, and
writing inside the authorized run output do not add an approval ceremony.

Read `inspection.json` and `suggested_recipe.json`. The inspector inventories
tables, columns, types, row counts, and at most ten bounded preview rows. It
does not choose semantic source roles. Fill the recipe in the run output with
the reviewed decisions and set `mapping_review.status` to `reviewed` only after
the mappings have actually been reviewed. Every multiplier defaults to `1` and
must be changed only to encode a sign convention the professional has reviewed;
the deterministic runner never infers one from the source values.

## Calculation and interpretation

Run the fixed calculation and rendering pipeline:

```bash
python scripts/run_pack.py \
  --input <bound-export> [--input <bound-export> ...] \
  --recipe <run-output>/inspection/reviewed_recipe.json \
  --client-engagement <context.json> \
  --output-dir <run-output>/pack
```

Read `execution_receipt.json`, `management_control_pack.json`, and
`model_context.json` before opening the Excel or HTML render. Stop on a blocked
core pack or a failed declared control total. The default model context contains
calculated metrics, bounded monthly series, top-ranked exceptions, coverage,
lineage IDs, and limitations; it does not contain the raw source population or
original filenames.

Write `management_commentary.json` from `commentary_template.json`. Every
observation or hypothesis must reference existing metric IDs. Separate:

- calculated observations;
- hypotheses that require more evidence;
- questions for management or the professional;
- limitations and unavailable sections.

Then validate and assemble the reviewed draft:

```bash
python scripts/finalize_pack.py \
  --pack <run-output>/pack/management_control_pack.json \
  --commentary <run-output>/pack/management_commentary.json \
  --client-engagement <context.json> \
  --output-dir <run-output>/pack/final
```

The final HTML and Markdown remain `draft_pending_professional_review`. Exact
arithmetic and a valid commentary schema do not prove accounting correctness,
source completeness, business causation, or approval.

## Natural outputs

- `inspection.json`, private `inspection_control.json`, and a recipe skeleton;
- `management_control_pack.json` and `execution_receipt.json`;
- `management_control_pack.xlsx`;
- `management_control_facts.md` and `management_control_dashboard.html`;
- `model_context.json` and `commentary_template.json`;
- after interpretation, `management_control_report.md`,
  `management_control_dashboard_reviewed.html`, and
  `commentary_receipt.json`.

Visually inspect the final HTML. Open the generated XLSX in Excel when the
current runtime can operate it and check sheet names, number formats, frozen
headers, widths, totals, and visible review status.
