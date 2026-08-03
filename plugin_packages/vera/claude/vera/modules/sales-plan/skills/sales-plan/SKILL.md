---
name: sales-plan
description: Use when Vera must create a reviewed forward-looking sales Plan from monthly Actuals and confirmed commercial or FX assumptions.
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

## Output Location Rule

Never write run outputs inside this Git workspace or a published folder. Use
only the Studio Archive run path described below.

## Client boundary in Cowork

Cowork does not package Studio Archive, so it cannot select or register its
local clients, import controlled snapshots, prepare or start customer-folder
runs, or finalize their artifact manifests. Use a product CLI only when a
compatible local Vera installation supplied a digest-valid, running
`vera.client_workflow_context.v2` for this exact workflow and its complete
customer-folder ledger paths are available. Otherwise work from the exact
connected files, preserve a reviewable file-based handoff, and state that the
sealed customer-folder run remains pending. Never invent an ID, receipt,
lifecycle state, or completed artifact declaration.

# Vera Plan

Use this workflow to create a forward-looking sales Plan from reviewed monthly
Actuals. This is planning and scenario modelling, not historical financial
analysis or financial due diligence.

The deterministic recipe can apply percentage assumptions to:

- units;
- unit price;
- gross sales;
- discount;
- COGS;
- the reporting-currency-per-transaction-currency FX rate.

Vera interprets the commercialista's request and prepares the structured
assumption read-back. The commercialista confirms the meaning, scope, periods,
currency direction, priority, same-driver overlap behavior, and the basis for
explicit discount or COGS changes. The engine owns exact arithmetic, collision
checks, reconciliation, output hashes, and replay evidence.

## Chat-first assumption review

Keep a small assumption set in chat. Inspect the source columns and actual
dimension members before interpreting the request. For example:

> In China unit sales go up 8%, but the dollar weakens 5% against the euro.

Read it back before calculation:

| ID | Driver | Exact scope | Change | Effective periods | Priority |
| --- | --- | --- | ---: | --- | ---: |
| A1 | units | `country=China` | +8% | all mapped Plan periods | 100 |
| A2 | USD/EUR rate | `transaction_currency=USD` | -5% | all mapped Plan periods | 100 |

Show matched source members and affected rows when inspection can establish
them. Ask the commercialista to confirm or correct the table. Do not treat a
broad conversational statement as approval of a materially different
structured assumption.

Resolve only ambiguities that change the result:

- “sales increase” must become units, unit price, or gross sales;
- v2 accepts percentage changes only;
- the FX rate is reporting-currency units per transaction-currency unit;
- source and Plan FX rates must remain exactly `1` when transaction currency
  equals reporting currency;
- a 5% weaker USD against EUR is `-5%` for USD rows when EUR is reporting;
- scopes must match exact source dimension members;
- same-driver overlaps require the reviewed case to choose `priority` or
  `compound`;
- `priority` applies only the highest-priority matching assumption and fails
  closed when multiple winners have equal priority;
- `compound` applies every matching same-driver assumption by multiplying each
  reviewed percentage effect; priority and assumption ID make the ledger order
  deterministic;
- gross-sales changes cannot overlap unit or unit-price changes on one row;
- unit and unit-price assumptions require a positive source Units value;
- an explicit discount or COGS change must state whether it applies to the
  `actual_amount` or the `sales_adjusted_amount`;
- v2 preserves observed sparse Actual rows and does not impute zero sales,
  missing customer-months, or seasonality.

For a large assumption set, prepare the same review table in Markdown or case
JSON and review it in batches. A separate HTML workbench is not part of v2.

## Cowork-native Run UX

Before running helper scripts, identify the material choices that would change
the Plan: source scenario, target periods, reporting currency, dimensions,
driver meaning, exact scope, FX direction, assumption priority, same-driver
overlap behavior, discount and COGS assumption bases, and review audience.
Ask only those unresolved choices in chat and wait when their answer would
materially change execution. Generate choices from the actual inputs; do not
propose dimensions, drivers, currencies, planning rules, or output packages
unless the facts cue them.

Default output policy: produce the complete normal Plan scenario, assumption
ledger, summary, reconciliation, evidence manifest, and execution receipt when
the reviewed case supports them. Natural outputs are not choices to propose.

1. Start with a visible markdown checklist covering intake, source inspection,
   dependency check, assumption review, deterministic Plan run,
   reconciliation, professional review, and delivery.
2. Show a Run Intake table with the case and source paths, output folder,
   Actual and Plan scenarios, period mapping, reporting currency, dimensions,
   reviewed assumptions, and unresolved items.
3. Show a compact Decision Table for unresolved driver meanings, scopes,
   periods, FX direction, priorities, collisions, exclusions, or evidence
   limitations.
4. Before long-running or write-heavy work, show an execution checkpoint with
   the command intent, inputs, output folder, and expected artifacts. Seek
   approval only under the approval boundary stated below.
5. End with an Artifact Card listing every delivered file, its purpose, Plan
   and reconciliation status, unresolved professional-review items, and next
   action. When useful, write `run_review.md` beside the run artifacts.
   Never edit plugin source or generated ZIPs during a user-data run.

## Run workflow

Reserve explicit approval for external, destructive, approval-sensitive, or
materially unresolved steps. The assumption-table confirmation is required
because it fixes a material planning choice; ordinary local inspection and
validation should continue without an extra approval step.

1. Establish the Actual source, reporting currency, Actual-to-Plan period
   mapping, dimensions, assumptions, and review audience.
2. Run the dependency check from the module root:

```bash
python scripts/check_dependencies.py
```

The declared `requirements.txt` is standard-library only. Do not install
undeclared packages.
3. Prepare the reviewed case contract. It must bind the source hash, period
   mapping, scenario codes, reporting currency, dimension columns, default
   discount and COGS behavior, same-driver overlap behavior, explicit discount
   and COGS assumption bases, structured assumptions, and professional-review
   receipt.
4. Run:

```bash
python scripts/run_plan.py \
  --case <client-run-output>/case.json \
  --client-engagement <client_engagement_path> \
  --output-dir <client-run-output>/plan
```

5. Stop on failed reconciliation or any unmatched scope, unsupported driver,
   stale or changed source, ambiguous priority collision, incompatible driver
   combination, or missing metric.
6. Deliver the Plan scenario and review artifacts. A passed run proves exact
   execution and reproducibility; it does not approve the assumptions or the
   resulting Plan.

## Natural outputs

- `sales_plan_scenario.csv`;
- `assumption_application_ledger.csv`;
- `scenario_summary.csv`;
- `reconciliation.json`;
- `prepared_evidence_manifest.json`;
- `plan_execution_receipt.json`.

Every result remains `report_ready=false` until professional review.
