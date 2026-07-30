---
name: sales-plan
description: Use when Vera must create a reviewed forward-looking sales Plan from monthly Actuals and confirmed commercial or FX assumptions.
---

## Output Location Rule

Never write run outputs inside this Git workspace, `static/shared`,
`protected_downloads`, or any GitHub Pages/static-site folder unless the task is
explicitly plugin packaging/release. For user-data runs, choose an output
directory outside the repo, preferably a sibling `output/sales-plan-<run-id>`
folder next to the user-provided input folder.

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
- an explicit discount or COGS change must state whether it applies to the
  `actual_amount` or the `sales_adjusted_amount`;
- v2 preserves observed sparse Actual rows and does not impute zero sales,
  missing customer-months, or seasonality.

For a large assumption set, prepare the same review table in Markdown or case
JSON and review it in batches. A separate HTML workbench is not part of v1.

## Codex-Native Run UX

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
   action. When useful, write `codex_run_review.md` beside the run artifacts.
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
  --case <case.json> \
  --output-dir <fresh-output-directory>
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

## Plugin Improvement Feedback

After completing substantive work, note technical defects or workflow gaps
without client or source details. Keep the improvement note local to chat or run artifacts.
