---
name: management-control-pack
description: Use when Vera must turn reviewed accounting exports into one connectorless management-control pack covering the supported P&L, budget, working-capital, cash, concentration, and profitability sections.
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

## Output location

Never write run outputs inside this Git workspace or a published folder. In
Claude, use only the exact Studio Archive run output for workflow ID
`management-control-pack`.

# Management Control Pack

Use this workflow when the requested outcome is one recurring management pack,
not one isolated variance, reconciliation, due-diligence schedule, or generic
report. The workflow accepts user-supplied `.xlsx`, `.xlsm`, `.csv`, or `.zip`
exports and does not require an ERP connector.

Set the reviewed recipe `language` to `it` for an Italian report and `en` for
an English report. This controls presentation only; source text and exact
accounting values remain unchanged.

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

Read `execution_receipt.json`, `model_context_receipt.json`, and
`model_context.json` before opening the Excel or HTML render. Do not read
`management_control_pack.json` into model context by default. The local runner
has already rebuilt the bounded context from that complete pack, verified exact
projection equality, and bound both files by hash in the receipt. Stop on a
blocked core pack, a failed declared control total, or a failed context receipt.
The default model context contains calculated metrics, bounded monthly series,
top-ranked exceptions, coverage, lineage IDs, and limitations; it does not
contain the raw source population or original filenames.

Write `management_commentary.json` from `commentary_template.json`. Every
observation or hypothesis must reference existing metric IDs. Separate:

- calculated observations;
- hypotheses that require more evidence;
- questions for management or the professional;
- limitations and unavailable sections.

For the run-level model-data report, record the exact bounded
`model_context.json` read as the post-calculation model-visible phase. Do not
record the local finalizer's read of `management_control_pack.json` as a model
phase. If the same model session uses the already-read bounded context for both
review and commentary, record one phase rather than inventing a duplicate
transmission; a genuinely separate model read remains a separate phase.

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
- `model_context.json`, `model_context_receipt.json`, and `commentary_template.json`;
- after interpretation, `management_control_report.md`,
  `management_control_dashboard_reviewed.html`, and
  `commentary_receipt.json`.

Visually inspect the final HTML. Open the generated XLSX in Excel when the
current runtime can operate it and check sheet names, number formats, frozen
headers, widths, totals, and visible review status.

## Budget, forecast and Sites delivery

For monthly budget monitoring, use this pack rather than routing the assignment
into a business plan. Prepare Actual/Budget comparisons for each complete month
and the cumulative window. The HTML uses the existing reporting-table renderer:
Budget and Actual or Forecast values, amount-variance bars and percentage pins,
with a common scale across period selections. Keep both deltas visible. Costs
are displayed positive and lower costs are favorable. A zero or negative base
has an unavailable percentage; retain its amount variance. Do not claim IBCS
certification. Interactivity changes the visible compiled view, never the figures.

For a full-period latest estimate, map a reviewed `forecast` table with the same
explicit date, category/account and signed amount columns as Budget. Set the
reporting end to the forecast horizon and cutoff to the last closed month.
`forecast_basis` records the model/professional-authored assumptions and source
basis. The engine combines Actuals to cutoff with only subsequent forecast
months. It does not infer run rates, seasonality or future costs. Missing whole
months prevent cumulative/full-period comparisons; a monthly view with both
sources remains available. Do not fill missing exports with zeros. Forecast
control totals cover only the remaining period. Review assumptions and material
mapping changes before recalculating; retain earlier run folders.

Set the reviewed recipe `audience` to `internal`, `client` or `public_demo`
(default `internal`). Audience is an authored delivery decision, not an automatic
confidentiality classifier. Only synthetic demonstration data may use
`public_demo`. Review all report content for the intended readers, including
customer/supplier names in optional tables. Professional review remains explicit.

When the user requests a shareable HTML site, read
`references/sites-delivery.md` and prepare the exact report with
`scripts/prepare_report_site.py`. The Sites route uses the existing local report;
never replace it with a generic dashboard or rewrite its numbers in the browser.
An explicit publication request authorizes the chosen route; honor host approvals.
