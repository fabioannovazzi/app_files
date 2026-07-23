# Clara due-diligence preparation plan

Status: active
Started: 2026-07-23
Owner: Clara

## Objective

Build an auditable preparation layer for a bounded financial and commercial
due-diligence factbook. The layer must turn reviewed source data, mappings, and
relationships into exact prepared evidence that Clara's existing Reporting
Engine and HTML evidence bundle can consume.

This program does not build the report orchestrator. It does not claim to
perform a complete due diligence, audit a company, approve accounting
adjustments, or make an investment decision.

## Observed starting point

- Reporting Engine accepts one prepared input asset for a render.
- The dataset semantic layer describes one logical dataset identity.
- `statement.pnl_table` can render already-prepared statement values.
- Render manifests prove the exact prepared input, request, recipe, and output
  bytes.
- `clara.evidence_bundle.v1` can seal prepared CSV and JSON evidence and bind
  report numbers to exact values.
- None of those contracts proves that an upstream join, account mapping,
  calculation, or reconciliation is correct.
- The current statement component uses floating-point arithmetic and must
  remain a renderer rather than the authoritative financial calculation layer.

The missing boundary is therefore preparation:

```text
immutable source evidence
        ↓
reviewed semantics, mappings, and relationships
        ↓
registered deterministic preparation
        ↓
reconciliations and exceptions
        ↓
prepared evidence manifest
        ↓
Reporting Engine and sealed report evidence
```

## Initial product scope

The first target is the recurring structured core of financial and commercial
due diligence for non-regulated operating companies:

- historical P&L and quality-of-earnings support;
- revenue, margin, concentration, and retention evidence when source contracts
  support those concepts;
- working-capital and cash-conversion evidence;
- budget, forecast, cost, and supplier comparisons in later slices.

Initially excluded:

- legal, tax, regulatory, HR, cyber, IT, ESG, and integrity diligence;
- banks, insurers, loan books, property portfolios, and other specialist
  financial models;
- autonomous approval of EBITDA adjustments, debt-like items, or normalized
  working-capital targets;
- valuation, financing, bid price, or buy/no-buy recommendations;
- automatic analysis selection and report orchestration.

## Deterministic and judgement contract

Deterministic code is justified where correctness is mechanically verifiable or
where auditability requires reproducibility. It owns:

- byte hashes, schemas, types, stable identifiers, and exact arithmetic;
- execution of reviewed mappings, relationships, filters, and formulas;
- periodization, aggregation, ranking, cohort assignment, and aging buckets;
- duplicate, fan-out, unmatched, coverage, and conservation diagnostics;
- accounting identities, tolerance comparisons, and prepared artifacts;
- render invocation, evidence sealing, and equality checks.

Model or human judgement owns:

- source authority and relevance;
- dataset identity, business meaning, and expected grain;
- whether two keys or concepts are equivalent;
- account, customer, employee, and adjustment classification;
- population, perimeter, currency, period, comparison, and materiality choices;
- whether an analysis is economically valid;
- chart choice, interpretation, implications, and caveats.

The operating rule is: judgement authors or reviews a versioned contract;
deterministic code validates and executes it. A heuristic may suggest a mapping,
but it may not approve one.

## Planned contracts

Names remain provisional until their first executable slice proves them.

| Contract | Purpose |
| --- | --- |
| `dd_data_package.v1` | Inventory immutable source assets, scope, and snapshot identity |
| `dataset_relationship.v1` | Record reviewed cross-dataset keys, grain, and cardinality |
| reviewed crosswalk asset | Persist account, entity, or other judgemental mappings as hashed data |
| `prepared_view_recipe.v1` | Select a registered deterministic preparation and explicit parameters |
| `reconciliation_result.v1` | Record tie-outs, tolerances, exceptions, and publication status |
| `prepared_evidence_manifest.v1` | Bind source, contract, recipe, engine, reconciliation, and output hashes |

The existing dataset semantic layer, Reporting Engine render manifest, and
`clara.evidence_bundle.v1` remain the downstream contracts.

## Test strategy

No single test source is sufficient.

1. **Pinned public truth** checks agreement with independently published
   company facts and checks that unavailable detail remains unavailable.
2. **Synthetic exact fixtures** exercise account-level and monthly mechanics
   with frozen expected answers.
3. **Adversarial mutations** prove that one error fails at the intended gate
   before report delivery.
4. **Anonymized real data** later tests whether the contracts survive genuine
   accounting messiness.

Normal tests run offline from small, hashed fixtures. Network refresh is a
separate explicit operation and never changes a test oracle implicitly.

## Milestones

### M1 — Public-truth and abstention benchmark

Use Fastenal Q1 2025 because the issuer published exact monthly net sales while
the SEC filing contains only a complete quarterly P&L. The benchmark must:

- pin the official monthly releases and SEC filing receipts;
- retain amounts as exact Decimal strings with an explicit unit and reported
  increment;
- reconcile monthly sales to the quarterly fact using disclosed precision;
- verify the quarterly P&L identities;
- prove that monthly COGS, SG&A, operating income, tax, and net income are not
  disclosed and must not be manufactured;
- produce an offline deterministic validation report.

Exit criterion: the clean fixture passes, targeted mutations fail, and tests do
not use the network.

### M2 — Monthly P&L fixture from a synthetic trial balance

Create a 12-month trial balance and reviewed chart-of-accounts mapping anchored
to a compact public-company P&L, initially WD-40 FY2025. Public totals remain
real; account codes, monthly phasing, and ledger detail are explicitly
synthetic.

Expected outputs:

- `monthly_pnl.csv`;
- `unmapped_accounts.csv`;
- `reconciliation.json`;
- `prepared_evidence_manifest.json`.

Exit criterion: exact monthly identities and public annual/quarterly tie-outs
pass; duplicate, unmapped, sign, period, unit, and scope mutations fail.

### M3 — Preparation contract kernel

Promote only the common contracts proven by M1 and M2: source inventory,
reviewed crosswalks, exact arithmetic, reconciliation records, and lineage.
Avoid a universal formula language.

### M4 — Reporting and evidence handoff

Attach prepared evidence to a reviewed dataset semantic layer, render through
the existing capability boundary, and seal every published number into
`clara.evidence_bundle.v1`.

### M5 — Additional due-diligence slices

Add customer concentration and working capital, followed by headcount and
retention. Each slice must introduce a genuinely different relationship or
reconciliation pressure.

### M6 — Real-data pilot

Run an anonymized or consented commercial trial balance through the same
contracts. Record semantic errors separately from mechanical errors.

### M7 — Orchestrator decision

Resume orchestrator design only after several independent preparation slices
produce reconciled, source-bound evidence reliably.

## Acceptance gates

A prepared artifact is report-ready only when:

1. every used source has an explicit identity and byte or fact-set digest;
2. every used concept has reviewed meaning;
3. every cross-source join has a reviewed relationship or crosswalk;
4. uniqueness, cardinality, duplicate, null, fan-out, and unmatched policies
   pass;
5. a registered deterministic recipe produces the prepared evidence;
6. required reconciliations pass within a reviewed tolerance;
7. identical inputs and contracts produce identical canonical output;
8. downstream semantic compatibility and rendering pass;
9. every published number is sealed and source-bound;
10. unsupported facts remain absent and visible as unavailable.

## Open decisions

- buy-side versus sell-side workflow priority;
- required support for multiple entities, currencies, and fiscal calendars;
- aggregate versus row-level lineage requirements;
- approval roles for mappings and relationships;
- handling of qualified reconciliation failures;
- storage and access governance for competitively sensitive deal data.

These decisions affect later scope but do not block M1.
