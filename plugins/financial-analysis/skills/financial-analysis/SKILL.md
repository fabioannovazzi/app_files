---
name: financial-analysis
description: Use when Vera must prepare source-bound monthly P&L, working-capital, or customer-concentration evidence from accounting datasets. This workflow validates the case-level contracts and prepared-evidence closure; it does not replace professional accounting judgment or generate conclusions automatically.
---

## Output Location Rule

Never write run outputs inside this Git workspace, `static/shared`,
`protected_downloads`, or any GitHub Pages/static-site folder unless the task is
explicitly plugin packaging/release. For user-data runs, choose an output
directory outside the repo, preferably a sibling
`output/financial-analysis-<run-id>` folder next to the user-provided input
folder, and pass that path to every output argument.

# Vera Financial Analysis

Use this workflow for financial-analysis preparation owned by Vera:

- `monthly_pnl`: monthly P&L or trial-balance/general-ledger preparation;
- `working_capital`: working-capital analysis from reviewed accounting
  datasets and relationships;
- `customer_concentration`: accounting/revenue/receivables concentration and
  customer-parent identity preparation.

Clara may later consume reviewed customer-concentration evidence for commercial
analysis, but Vera owns its accounting source, identity, currency, period,
reconciliation, and preparation controls.

This is one financial-analysis workflow, not an orchestrator. Do not generate
calculation code. Select one named and versioned deterministic recipe with
explicit parameters. The component includes the three registered v1 engines.
They are deliberately narrow: input files must satisfy the exact reviewed case
contract, and unsupported layouts or meanings fail closed.

## Boundary between checks and judgment

Deterministic code may verify exact source hashes, canonical identifiers,
dataset keys, declared cardinality, reference closure, exact Decimal
reconciliation, output hashes, and replay receipts. Codex and the professional
reviewer own accounting meaning, reporting perimeter, account classification,
customer-parent identity, period alignment policy, materiality/tolerances, and
conclusions.

Never silently infer a judgmental mapping. Record it in a reviewed, hashed
crosswalk. Never treat `prepared_evidence_manifest.json` as a report-ready or
professionally approved result; its `report_ready` field must remain `false`.

## Codex-Native Run UX

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
   action. When useful, write `codex_run_review.md` beside the run artifacts.
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
  --pack <monthly_pnl|working_capital|customer_concentration> \
  --case <case.json> \
  --output-dir <output-dir>/prepared
```

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

## Natural outputs

- the seven contract types listed above;
- `financial_analysis_contract_audit.json`;
- pack-specific prepared tables, ledgers, reconciliations, and replay evidence
  only when an implemented deterministic pack produced them.

## Plugin Improvement Feedback

After completing substantive work, note technical defects or workflow gaps
without client or source details. Keep the improvement note local to chat or run artifacts.
