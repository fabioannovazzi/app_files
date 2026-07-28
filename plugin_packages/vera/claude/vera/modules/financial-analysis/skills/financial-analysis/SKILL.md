---
name: financial-analysis
description: Use when Vera must prepare controlled accounting analysis or fixed financial due-diligence calculations from reviewed inputs. This workflow validates case-level contracts and reproducible calculations; it does not replace professional accounting or deal judgment.
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

Never write run outputs inside this Git workspace, `static/shared`,
`protected_downloads`, or any GitHub Pages/static-site folder unless the task is
explicitly plugin packaging/release. For user-data runs, choose an output
directory outside the repo, preferably a sibling
`output/financial-analysis-<run-id>` folder next to the user-provided input
folder, and pass that path to every output argument.

# Vera Financial Analysis

Use this workflow for financial-analysis preparation owned by Vera:

Accounting preparation:

- `monthly_pnl`: monthly P&L or trial-balance/general-ledger preparation;
- `working_capital`: working-capital analysis from reviewed accounting
  datasets and relationships;
- `customer_concentration`: accounting/revenue/receivables concentration and
  customer-parent identity preparation.

Fixed financial due-diligence calculations:

- `quality_of_earnings`: reported EBITDA plus reviewed, included adjustments
  to adjusted EBITDA;
- `net_debt`: reviewed debt, debt-like, cash, cash-like, and excluded items at
  one explicit as-of date;
- `normalized_working_capital`: reviewed monthly balances and normalization
  adjustments, an explicit closing period, and a reviewed selected target;
- `capex`: reviewed items by measurement basis and classification;
- `deal_bridges`: EBITDA-to-cash and Enterprise-to-Equity bridges from sealed
  upstream metric receipts and reviewed bridge items.

Clara may later consume reviewed customer-concentration evidence for commercial
analysis, but Vera owns its accounting source, identity, currency, period,
reconciliation, and preparation controls.

This is one financial-analysis workflow, not an orchestrator. Do not generate
calculation code. Select one named and versioned deterministic recipe with
explicit parameters. The component includes eight registered engines. They are
deliberately narrow: input files must satisfy the exact reviewed case contract,
and unsupported layouts or meanings fail closed.

The five due-diligence recipes calculate only over reviewed prepared inputs
bound to the full case contract stack. They do not classify accounting items,
create adjustments, select a target, or make a deal decision. Reporting periods
and as-of dates come from the case; never assume fixed years such as 2023–2025.

## Boundary between checks and judgment

Deterministic code may verify exact source hashes, canonical identifiers,
dataset keys, declared cardinality, reference closure, exact Decimal
reconciliation, output hashes, and replay receipts. Claude and the professional
reviewer own accounting meaning, reporting perimeter, account classification,
customer-parent identity, period alignment policy, materiality/tolerances, and
conclusions.

Never silently infer a judgmental mapping. Record it in a reviewed, hashed
crosswalk. Never treat `prepared_evidence_manifest.json` as a report-ready or
professionally approved result; its `report_ready` field must remain `false`.
For due-diligence results, `source_tie_out.status` must remain `not_assessed`
because source tie-out is outside this calculation result. A passed calculation
proves exact arithmetic, contract closure, and deterministic replay—not
accounting correctness, source tie-out, completeness, or approval.

## Cowork-native Run UX

Before running helper scripts, identify the material choices that would change
the analysis: pack, reporting perimeter, period, currency, accounting meaning,
relationships, mappings, tolerances, and audience. Ask only for unresolved
choices. Ask only those unresolved choices in chat and wait when their answer
would materially change execution. Generate choices from the actual inputs; do
not offer named frameworks, regulators, output packages, or issue categories
unless the facts cue them.

Default output policy: produce the complete normal pack, contract stack,
reconciliation, execution receipt, and audit whenever the evidence supports
them. Natural outputs are not choices to propose.

1. Start with a visible markdown checklist covering intake, dependency check,
   contract review, deterministic pack run, reconciliation, case validation,
   professional review, and delivery.
2. Show a Run Intake table with the pack, case and source paths, output folder,
   perimeter, period, currencies, reviewed mappings, assumptions, and
   unresolved items.
3. Show a compact Decision Table for unresolved accounting meanings,
   crosswalks, relationship policies, tolerances, exclusions, or evidence
   limitations.
4. Before long-running or write-heavy work, show an execution checkpoint with
   the command intent, inputs, output folder, and expected artifacts. Seek
   approval only under the approval boundary stated below.
5. End with an Artifact Card listing every delivered file, its purpose, pack
   and reconciliation status, unresolved professional-review items, and next
   action. When useful, write `run_review.md` beside the run artifacts.
   Never edit plugin source or generated ZIPs during a user-data run.

## Run workflow

1. Establish the pack, entity/perimeter, period, currencies, source files, and
   intended review audience. Ask only for unresolved choices that materially
   alter the work.
   Explicit approval is reserved for external, destructive,
   approval-sensitive, or material steps; ordinary local inspection and
   deterministic validation do not require a separate approval ceremony.
2. Run the dependency check from the financial-analysis module root:

```bash
python scripts/check_dependencies.py
```

The workflow has no third-party requirements. If dependency validation fails,
do not install undeclared packages; report the missing vendored assurance
module.
3. Run exactly one registered pack:

```bash
python scripts/run_pack.py \
  --pack <registered-pack-id> \
  --case <case.json> \
  --output-dir <output-dir>/prepared
```

   Registered pack IDs are `monthly_pnl`, `working_capital`,
   `customer_concentration`, `quality_of_earnings`, `net_debt`,
   `normalized_working_capital`, `capex`, and `deal_bridges`.

   Read `pack_execution_receipt.json`, `reconciliation.json`, and
   `prepared_evidence_manifest.json`. Stop on a failed reconciliation. The
   execution receipt binds the exact case, engine, recipe, and output bytes and
   always keeps `report_ready=false`.
4. Create or inspect these versioned case-level JSON contracts:

   - `data_package_manifest.json`;
   - one or more `dataset_contract.json` files;
   - zero or more `relationship_contract.json` files;
   - zero or more `crosswalk_manifest.json` files;
   - `analysis_pack_request.json`;
   - `reconciliation_result.json`;
   - `prepared_evidence_manifest.json`.

5. For a judgmental relationship or classification, stop and obtain a reviewed
   crosswalk rather than generating one from labels alone.
   For a due-diligence pack, also require a reviewed FDD case containing the
   same complete contract stack, reviewed decisions, evidenced inputs, explicit
   period, currency, unit, and perimeter. `deal_bridges` must consume sealed,
   replayable upstream metric receipts rather than detached values.
6. Validate the complete case:

```bash
python scripts/validate_case_contracts.py \
  --package <data_package_manifest.json> \
  --dataset <dataset_contract.json> \
  --relationship <relationship_contract.json> \
  --crosswalk <crosswalk_manifest.json> \
  --request <analysis_pack_request.json> \
  --reconciliation <reconciliation_result.json> \
  --prepared-manifest <prepared_evidence_manifest.json> \
  --output <financial_analysis_contract_audit.json>
```

Repeat `--dataset`, `--relationship`, or `--crosswalk` as needed. Omit the
optional relationship and crosswalk arguments only when the reviewed pack does
not require them.
7. If validation fails, preserve the original contracts and correct the
specific stale hash, missing reference, relationship policy, or reconciliation
failure in a new reviewed version. Do not reseal an old result to hide a
failure.
8. Deliver the pack outputs, execution receipt, case audit, and underlying
   contracts. A passed pack and contract audit means the prepared evidence is
   internally bound and reproducible; it does not mean the financial conclusion
   is correct or approved.

## Reviewed due-diligence registers

When the work requires them, use the module's validated builders for:

- `vera.contingent_liability_register.v1`, which binds reviewed contingent
  items to a validated FDD case, evidence, decisions, and review;
- `vera.financial_issue_register.v1`, which binds reviewed financial issues to
  the same case context, sealed metric receipts, evidence, owners, open
  questions, and deal implications.

Do not use either register as evidence that the population is complete. Their
completeness status must remain `not_assessed`, and `report_ready` must remain
`false`. The financial-issue register records reviewed implications; it does
not decide the transaction.

## Natural outputs

- the seven contract types listed above;
- `financial_analysis_contract_audit.json`;
- pack-specific prepared tables, ledgers, reconciliations, and replay evidence
  only when an implemented deterministic pack produced them;
- for due-diligence packs, `fdd_result.json`, `fdd_metrics.json`,
  `fdd_line_items.json`, `reconciliation.json`, and
  `prepared_evidence_manifest.json`;
- a sealed contingent-liability or financial-issue register only when that
  reviewed register is in scope.
