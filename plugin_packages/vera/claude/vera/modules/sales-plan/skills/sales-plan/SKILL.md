---
name: sales-plan
description: Use when Vera must create a reviewed forward-looking sales Plan from monthly Actuals and confirmed commercial or FX assumptions.
---

## Cowork execution contract

For journal-sampling, open-item-reconciliation, journal-bank-reconciliation,
concordato-plan-review, report-builder and check-entries only, optional cache
cleanup is available from the installed Vera root:

```bash
python3 modules/<module>/scripts/implementation_bootstrap.py --repair
```

For a standalone module, use `python3 scripts/implementation_bootstrap.py --repair`
from its root. This validates the implementation first, then removes only regular,
single-link `__pycache__/*.pyc` files under that module's own `vendor` tree. It
leaves directories, other files, symlinks and shared vendor trees untouched.
If `validate_implementation_tree` ever fails with a file/directory-contract
mismatch, do not delete or modify files inside the installed plugin tree by hand
and do not bypass a sandbox/permission rejection to do so. Stop and report the
exact error instead.

Work from the connected folder and supplied files first. Before a module's Python
helpers, locate the installed plugin root. When it contains `components.json` and
`scripts/managed_python_runtime.py` (as Vera does), run from that root:

```bash
python3 scripts/check_dependencies.py --module <module>
python3 scripts/managed_python_runtime.py --module <module> run scripts/<helper>.py <arguments>
```

If the enclosing plugin does not ship this managed launcher, use the module's
dependency checker and only already-installed dependencies; do not assume that a
standalone module script provisions them.

The managed launchers provision and reuse an isolated environment containing only the
module's published requirements. This declared dependency setup is authorized as
part of running the workflow; never install arbitrary packages or use ambient
Python for subsequent module helpers. Repeat any declared `--requirements` options
on both commands. Missing ambient imports are a reason to run this setup, not to
abandon the calculation. If setup fails, report its exact error and do not replace
the required calculation with an invented result. Optional OCR setup still needs
separate approval. If setup reports `Host not in allowlist` for PyPI, explain that
Claude Settings > Capabilities > Allow network egress is disabled or restricted.
Ask the user or organization administrator to authorize package-registry access;
never change network permissions silently or work around the restriction. Retry
the same managed setup after access is approved, in a new session if needed.

MCP tools, browser or computer control, and local review servers are optional
enhancements, never completion gates. Cloud Cowork sessions may not expose local
plugin MCP servers even when the plugin is installed; use the packaged Python
workflow through the managed launcher in that case. Do not equate missing MCP
registration with a failed calculation engine. When an optional capability is
unavailable, continue with Markdown and file-based review and state the limitation.

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

## Client engagement gate

Select one Studio Archive client and engagement, import the reviewed Actuals
and case inputs, then call `prepare_studio_client_workflow` with workflow ID
`sales-plan`. Pass the returned `client_engagement_path` as
`--client-engagement` to preparation and execution. Use only the context's run
folder; cross-engagement inputs and arbitrary outputs are rejected.

Start the prepared run before preparation. After the last output write, call
`finalize_studio_client_workflow` and declare every physical file with a stable
artifact ID, relative path, concrete purpose, audience, and media type. Review
the closed declaration, then call `complete_studio_client_workflow`; record
`failed` or explicitly cancel an abandoned run instead of treating a partial
directory as a result.

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
6. Read `model_use_manifest.json` after the run. For ordinary model-led review,
   use the assumption ledger, summary, reconciliation, and prepared-evidence
   lineage listed there. Do not load the complete row-level scenario by
   default. When a professional question requires row detail, request exact
   matches and only the needed prepared-scenario columns:

```bash
python scripts/model_use.py \
  --manifest <client-run-output>/plan/model_use_manifest.json \
  --reason <specific-professional-question> \
  --source-row-id <exact-source-row-id> \
  --where <column=exact-value> \
  --column <needed-output-column> \
  --client-engagement <client_engagement_path>
```

   Supply at least one exact row ID or filter and at least one output column.
   The helper scans the complete sealed scenario locally and returns every
   exact match without sampling. It never reopens the raw Actual file.
7. Deliver the Plan scenario and review artifacts. A passed run proves exact
   execution and reproducibility; it does not approve the assumptions or the
   resulting Plan.

## Natural outputs

- `sales_plan_scenario.csv`;
- `assumption_application_ledger.csv`;
- `scenario_summary.csv`;
- `reconciliation.json`;
- `prepared_evidence_manifest.json`;
- `model_use_manifest.json` and any explicitly requested
  `model_drilldowns/scenario_rows_*.json` artifacts;
- `plan_execution_receipt.json`.

Every result remains `report_ready=false` until professional review.
