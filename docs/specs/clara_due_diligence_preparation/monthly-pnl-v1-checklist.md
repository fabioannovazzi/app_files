# Monthly P&L v1 implementation checklist

Status: M4 complete
Parent plan: [Clara due-diligence preparation plan](./clara-due-diligence-preparation.md)

## M1 — Pinned public truth

- [x] Select a company with independently published monthly and quarterly facts.
- [x] Record the semantic limitation: Fastenal publishes monthly net sales, not
  a monthly full P&L.
- [x] Pin source URLs, dates, identifiers, byte counts, and SHA-256 receipts.
- [x] Store the three monthly sales facts as exact Decimal values with declared
  units and reported increments.
- [x] Store the Q1 statement facts, XBRL concepts, context, and disclosed
  precision.
- [x] Reconcile monthly sales to quarterly sales with a rounding-interval
  contract.
- [x] Verify quarterly gross profit, operating income, pretax income, and net
  income identities.
- [x] Verify that undisclosed monthly P&L lines contain no facts.
- [x] Emit a deterministic validation report.
- [x] Add clean, malformed-contract, and one-error-at-a-time adversarial tests.
- [x] Keep all automated tests offline.
- [x] Rebuild and verify the Clara plugin package.

## M1 definition of done

- The fixture is immutable unless its pinned digest is deliberately updated.
- Three monthly net-sales facts sum to USD 1,959,429,000.
- The published quarterly net-sales midpoint is USD 1,959,400,000.
- Reconciliation passes only because the disclosed rounding intervals overlap.
- Every quarterly statement identity has zero difference.
- Monthly cost of sales, gross profit, SG&A, operating income, interest, tax,
  and net income are explicitly `not_disclosed`.
- Adding an invented monthly expense fact fails the abstention gate.
- Missing a month, exceeding the rounding interval, breaking a statement
  identity, or corrupting provenance fails before anything is report-ready.
- Passing M1 records a benchmark result, not downstream report readiness;
  render compatibility and evidence sealing remain later gates.

## M2 — Synthetic monthly trial balance

- [x] Freeze a balanced 144-row, 12-month debit-positive synthetic trial
  balance.
- [x] Freeze a reviewed chart-of-accounts mapping with scope, entity, sign,
  effective dates, evidence, version, digest, and status.
- [x] Pin direct WD-40 Q1–Q4 and FY2025 statement controls and their five SEC
  download receipts.
- [x] Keep every monthly value, account, split, mapping, and clearing row
  explicitly synthetic and use scenario `SYN`.
- [x] Execute one registered fixed recipe with controlled exact Decimal
  arithmetic; do not add a formula DSL.
- [x] Produce `monthly_pnl.csv`, `unmapped_accounts.csv`,
  `reconciliation.json`, and `prepared_evidence_manifest.json`.
- [x] Commit byte-exact expected copies of all four outputs.
- [x] Record source-row/contribution conservation, 12 trial-balance checks,
  60 monthly statement identities, and 70 exact public tie-outs.
- [x] Fail duplicate, unmapped, sign, period, unit, currency, scope, mapping
  review/version/effectivity/fan-out, receipt, increment, and public-control
  mutations.
- [x] Prove all 168 prepared cells survive `statement.pnl_table` transport
  without renderer formulas.
- [x] Prove representative synthetic cells seal and resolve through
  `clara.evidence_bundle.v1`.
- [x] Rebuild the Clara plugin ZIP and verify package/source equality.

## M2 definition of done

- Every clean monthly trial balance has exact zero debit-positive difference.
- Every source row resolves to one reviewed include or exclusion, with no
  fan-out or unmatched account.
- All nine mapped leaf lines conserve their source-row occurrence multiset.
- Five statement identities pass in each of 12 months.
- Fourteen statement lines tie exactly for each public quarter and the fiscal
  year.
- The frozen SEC accessions, byte counts, and SHA-256 receipts are test-pinned.
- Identical inputs produce byte-identical artifacts in fresh directories.
- The renderer consumes source-key-only prepared rows and owns no
  authoritative arithmetic.
- Monthly evidence is labelled illustrative and synthetic, never issuer
  actual.
- Passing M2 records `synthetic_benchmark_only`; semantic compatibility,
  complete public-anchor evidence binding, and report readiness remain
  `not_assessed` for M4.
- M2 introduces no semantic layer, automatic analysis selection, or
  orchestrator.

## M3 — Preparation contract kernel

- [x] Freeze `clara.preparation_audit_envelope.v1` as an audit-only schema.
- [x] Add shared strict JSON, exact CSV, canonical JSON, SHA-256 receipt, local
  path, exact Decimal, reference-closure, and status-consistency checks.
- [x] Bind the M1 public-truth fixture through an audit adapter without changing
  its benchmark or candidate data.
- [x] Commit and byte-pin the expected M1 validation report.
- [x] Bind the M2 monthly-P&L fixture and its frozen outputs through an audit
  adapter without changing the preparation engine or expected artifacts.
- [x] Replay both registered producers and reject stale reports, changed output
  bytes, internally resealed forgeries, and contradictory output sets.
- [x] Preserve a genuine failed M2 run with reconciliation and unmapped-account
  outputs only; do not manufacture a manifest or monthly P&L.
- [x] Keep remote sources at `receipt_only`, semantic and downstream gates at
  `not_assessed`, publication at `withheld`, and `report_ready` at `false`.
- [x] Claim artifact lineage for M1 and bind JSON-Pointer/hash-bound aggregate
  dependency metadata plus the exact prepared-output digest for successful M2;
  prohibit row lineage in v1.
- [x] Reject duplicate IDs, path escape, digest drift, unknown references,
  decision-status promotion, inconsistent reconciliation, binary floats,
  non-canonical numeric evidence, aggregate-evidence drift, role-only lineage,
  false row lineage, and publication escalation.
- [x] Validate both adapters against the JSON Schema and runtime validator.
- [x] Prove canonical envelope bytes are stable in offline tests.

## M3 definition of done

- The kernel validates mechanically checkable structure and identity only.
- Case-specific mappings, formulas, relationships, tolerances, and business
  semantics remain hashed inputs or uninterpreted decision content.
- A successful preparation or reconciliation gate cannot promote semantic,
  source, downstream, publication, or report-readiness status.
- Declared remote-source metadata is not represented as authenticated source
  bytes or proof of authority.
- A reviewed-decision receipt preserves an explicit source review status; its
  builder cannot promote a draft.
- Aggregate records bind located dependency metadata and the exact output ID
  and digest without establishing semantic provenance; row lineage is
  unavailable in v1.
- Canonical Decimal syntax is shared; M2 precision and scale limits remain
  case-owned.
- M1 and M2 source contracts, engines, and frozen output bytes remain intact.
- No universal crosswalk, formula DSL, relationship model, semantic layer,
  automatic analysis selection, or orchestrator is introduced.

## M4 — Reporting and evidence handoff

- [x] Freeze one exact model-reviewed semantic layer for the prepared monthly
  P&L and hash its reviewed fixture notes.
- [x] Freeze an explicit case request, analysis policy, capability, role
  bindings, periods, scenario, and source-key-only statement recipe.
- [x] Reject automatic analysis selection, automatic chart selection, renderer
  formulas, weakened synthetic disclosure copy, or publication promotion.
- [x] Replay M3 and require the exact 168-row prepared artifact before render.
- [x] Validate all 168 prepared values against the rendered chart-data CSV,
  chart-context JSON, and serialized HTML table cells.
- [x] Validate exact row labels, prefixes, levels, positions, period/scenario
  headers, title contract, synthetic scope, and source footnote.
- [x] Validate the Reporting Engine artifact manifest, final-artifact manifest,
  invocation boundary, runner receipt, and actual statement implementation.
- [x] Publish a complete serialized-cell ledger with one unique
  `row_key × period × scenario` address and value digest per cell.
- [x] Seal the prepared CSV, rendered CSV, serialized-cell ledger, and portable
  publication-boundary receipt in `clara.evidence_bundle.v1`.
- [x] Pin the M4 builder, preparation kernel/adapter, semantic and render
  helpers, evidence helper, component runner/core, registries, and plugin
  manifests in implementation receipts.
- [x] Emit `reporting_handoff.json` only after a successful independent fresh
  render; leave no ready receipt after a failed final gate.
- [x] Prove canonical receipt and evidence-bundle bytes are identical across
  fresh directories.
- [x] Add offline clean, determinism, malformed-contract, duplicate-key,
  display-grid, control-manifest, context, evidence-metadata, and publication
  adversarial tests.
- [x] Rebuild and verify the Marketplace Clara package.

## M4 definition of done

- `handoff_ready_for_review` is `true`, while `report_ready` remains `false` and
  publication remains `withheld`.
- M4 proves exact sealed prepared → rendered → context → serialized-HTML cell
  transport for this frozen synthetic fixture.
- Serialized HTML parsing does not claim browser-computed visibility.
- The standalone Reporting Engine HTML is not an HTML-deck evidence ledger, so
  the 168 cells are not yet downstream source-bound report numbers.
- Source authority, semantic correctness, row lineage, interpretation, visual
  approval, and publication authorization remain unproven.
- The current statement renderer still uses binary floats; exact equality is
  enforced for this integer-valued fixture, not claimed as a generic Decimal
  rendering guarantee.
- No automatic analysis selection, chart selection, interpretation, report
  composition, or orchestrator is introduced.
