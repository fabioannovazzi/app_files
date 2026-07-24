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

Status: complete on 2026-07-23.

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

Status: complete on 2026-07-23.

Promote only the mechanically common boundary proven by M1 and M2. M3 adds
`clara.preparation_audit_envelope.v1`, exact Decimal and canonical JSON helpers,
strict local artifact receipts, declared remote-source receipts, reviewed
decision receipts, reconciliation checks, explicit lineage levels, and
independent gate statuses.

The two audit-only adapters preserve the case-owned M1 and M2 schemas and
outputs. Each adapter deterministically replays its registered producer and
requires the complete supplied report or producer-owned output set to match;
M2 failure envelopes preserve the failure-only output set rather than requiring
success artifacts. The adapters bind those artifacts into one reproducible
envelope without promoting either fixture's crosswalk, formula, relationship,
tolerance, scale, precision, or business meaning into a universal model.
Source authority, decision quality, reviewer authorization, semantic
compatibility, row lineage, downstream readiness, and publication remain
unproven or withheld.

Exit criterion: both frozen cases produce schema-valid, byte-deterministic
envelopes; stale and internally resealed results, decision-status promotion,
role-only lineage, and isolated contract, digest, path, numeric, reference,
reconciliation, and publication mutations fail closed; genuine failed runs
remain representable; tests remain offline.

### M4 — Reporting and evidence handoff

Status: complete on 2026-07-23.

Attach prepared evidence to a reviewed dataset semantic layer, render through
the existing capability boundary, and seal the complete numeric transport into
`clara.evidence_bundle.v1`.

The frozen WD-40 case now:

- replays the M3 preparation envelope and requires the exact prepared
  `monthly_pnl.csv` bytes;
- binds an exact model-reviewed semantic layer, its hashed review notes, the
  explicit statement analysis request, and the source-key-only render recipe;
- invokes `statement.pnl_table` without automatic analysis or chart selection;
- compares all 168 addresses and values across the prepared CSV, rendered
  chart-data CSV, chart-context JSON, serialized HTML table, and cell ledger;
- validates the renderer's title, scope, source note, row/column grid, control
  manifests, context metadata, and implementation receipts;
- seals prepared values, rendered values, serialized HTML cells, and a portable
  publication-boundary receipt in one evidence bundle;
- emits the final ready-for-review receipt only after an independent fresh
  render reproduces every portable output.

The M4 result is a deterministic reporting-transport handoff, not a report.
`report_ready` remains `false` and publication remains `withheld`. Serialized
HTML checking does not prove browser-computed visibility, and the standalone
statement HTML is not an HTML-deck evidence ledger. The 168 cells therefore do
not yet satisfy the report-ready requirement for downstream source bindings.
Source authority, semantic correctness, row lineage, interpretation, visual
approval, and publication authorization remain outside this milestone.

Exit criterion: two fresh output directories produce byte-identical canonical
receipts and evidence bundles; every prepared, rendered, context, serialized
HTML, and ledger address closes exactly; semantic, recipe, evidence,
implementation, display-copy, control-manifest, and publication mutations fail
closed; no complete-looking receipt survives a failed fresh-render gate; tests
remain offline.

### M5 — Additional due-diligence slices

Status: complete on 2026-07-23.

Freeze two public-source preparation sub-slices that introduce different
judgement and reconciliation pressures without extending M4 into report
production:

1. **Universal Display Corporation FY2025 customer concentration.** Preserve
   the anonymous customer aliases, annual whole-percentage revenue shares, and
   disclosed accounts-receivable amounts from the reviewed Form 10-K
   extraction. Deterministic preparation may reproduce disclosed subtotals,
   calculate accounts-receivable coverage where a reviewed denominator exists,
   and calculate the contribution from squared *reported* shares. It must not
   identify an alias, turn a rounded percentage into precise customer revenue
   dollars, describe the incomplete squared-share contribution as a full HHI
   or guaranteed HHI lower bound, or invent monthly, quarterly, churn, or
   retention facts.
2. **WD-40 FY2025 working capital.** Apply a reviewed operating-net-working-
   capital perimeter to exact public balance-sheet stocks, de-cumulate
   year-to-date cash-flow disclosures into discrete fiscal quarters, and bridge
   each stock movement to its expected cash impact. Any difference between the
   discrete cash-flow movement and the stock-based expectation remains an
   explicit unexplained stock/flow residual; deterministic code may neither
   allocate it nor force it to zero.

The reviewed alias boundary, metric meaning, working-capital perimeter, sign
conventions, caption relationships, and validity of each analysis remain
judgement. Exact input validation, reviewed-formula execution, de-cumulation,
aggregation, ratio arithmetic, residual calculation, reconciliation, hashing,
and abstention enforcement are deterministic.

Exit criterion: both frozen cases have registered offline producers, exact
expected outputs, audit envelopes, and targeted adversarial tests; identical
inputs produce identical canonical evidence; forbidden inferences remain
absent; `report_ready` remains `false` and publication remains `withheld`.
Neither sub-slice selects a visualization, invokes an orchestrator, interprets
commercial implications, or authorizes a report. Headcount and retention are
deferred until these two pressures are proven.

### M6 — Real-data pilot

Status: source-qualification pilot completed with a fail-closed negative result;
successful real-data preparation remains unmet.

One exact commercial general journal was inspected after explicit authorization
and private intake binding. It was a paginated presentation export whose
posting amounts and debit/credit roles were not all uniquely row-bound in the
source. Exact controls detected disagreements but could not safely classify
postings. A private reviewed qualification therefore classified the source as
`unsupported_source_layout`; the official producer recorded
`semantic_review_blocked` and stopped before invoking the parser or reading
source rows. It emitted no prepared facts, reconciliation success artifact,
plot, or report.

The next pilot now requires a native row-wise journal-detail export: one posting
per row, stable posting identity, explicit date and source account, explicit
debit/credit fields or a source-owned side convention, exact one-to-one fact
locators, and complete monetary-field disposition. Embedded, detached,
cross-row, residual-derived, or equation-selected postings are ineligible for
that pilot. Controls validate a complete candidate population; they never fill
or classify it. This is a reviewed eligibility policy, not a claim that the
current experimental parser mechanically qualifies arbitrary exports.

The implementation checklist is
[M6 real-data pilot checklist](./m6-real-data-pilot-checklist.md). File presence
or previous processing is not reuse consent. M6 keeps raw and row-level
material in an ignored local run root and permits only separately reviewed
sanitized summaries and receipts to move into a case-approved confidential
evidence store. Those receipts remain pseudonymous and linkable, and stay
outside the plugin and source repository by default. M6 does not relax or
relabel M2's synthetic producer. The unresolved private reconstruction
evidence and exception or equation machinery are not a reusable parser or
Marketplace contract. The bundled v5 parser is a bounded experimental pilot
scaffold whose synthetic tests still exercise reviewed multiline, embedded,
and cross-row locator paths; it is not the row-wise eligibility gate and was
not invoked for this negative pilot. A dedicated adapter should be reopened
only when representative independent cases establish the same export family,
every movement and amount closes uniquely, and an independent line-level
oracle shows a quality advantage over requesting a normalized export.

### M7 — Orchestrator decision

Status: deferred; the entry gate is not met.

M1–M5 prove several bounded preparation slices and one deterministic reporting-
transport handoff using public or synthetic fixtures, while preserving
`report_ready: false` and publication `withheld`. M6 now also proves on one
authorized commercial source that a reviewed semantic gate can stop an
unsupported layout before parser or source-row processing and without
producing plausible numbers. It does not prove a generic source-layout
classifier or successful real-data preparation: no eligible native row-wise
export has completed preparation and reconciliation. Do not begin orchestrator
design or implementation.

Reopen this decision only after an eligible source satisfies M6's successful-
preparation branch, retained M1–M5 regressions, privacy validation, release
checks, and Marketplace package verification pass, and the open decisions
relevant to the first orchestration scope are resolved or explicitly excluded.
Passing this gate permits only a scoped design decision. It does not authorize
implementation, report readiness, publication, automatic semantic mapping, or
authoritative calculation by an orchestrator.

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

These decisions do not block the completed M1–M4 benchmarks. They do block
promotion from an audit envelope to semantically approved, report-ready
evidence where the relevant decision is unresolved.
