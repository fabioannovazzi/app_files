# M5 additional due-diligence slices checklist

Status: complete on 2026-07-23

This checklist freezes the scope and acceptance boundary for two public-source
preparation cases. It does not authorize an orchestrator, visualization
selection, interpretation, report readiness, or publication.

## Frozen sub-slice A — UDC FY2025 customer concentration

### Observed controls

- The frozen source receipt is Universal Display Corporation's FY2025 Form
  10-K, filed on 2026-02-19, with a reviewed extraction from Note 19,
  “Concentration of Risk.”
- The extraction contains exactly 18 natural keys: anonymous aliases A, B, and
  C; fiscal years 2025, 2024, and 2023; and the two disclosed metrics
  `revenue_share` and `accounts_receivable`.
- Revenue shares are reported as whole percentages. They are not precise
  customer-revenue amounts.
- Customer accounts-receivable amounts are reported in USD thousands. Total
  accounts-receivable controls are frozen for 2025 and 2024, so coverage ratios
  are bounded to those years.
- Total-revenue controls are frozen for 2025, 2024, and 2023.
- The three reported shares sum to 79%, 82%, and 76% for 2025, 2024, and 2023.
- The disclosed customer accounts-receivable subtotals are USD 103,481
  thousand for 2025 and USD 76,908 thousand for 2024. Against the frozen total
  receivables, the expected coverage ratios are 86.267955% and 67.672110%.
- Squaring and summing the reported whole-percentage shares produces
  contributions of 2,515, 2,634, and 2,114. Because the shares are rounded and
  customers outside A–C are omitted, those values are neither full HHI nor a
  guaranteed lower bound for full HHI.
- The filing aliases remain anonymous. No reviewed contract maps A, B, or C to
  a named customer.

### Deterministic-versus-judgement boundary

Judgement owns:

- whether the filing and reviewed extraction are authoritative for the case;
- continuity and meaning of the anonymous aliases;
- the annual population, metric definitions, and materiality of concentration;
- whether a derived ratio or incomplete squared-share contribution is useful;
- interpretation of customer dependency or credit exposure.

Deterministic preparation may:

- require the exact schema, row count, natural-key set, units, increments,
  source ID, locator, and non-negative canonical integers;
- preserve the disclosed aliases and values without enrichment;
- reject aliases outside the reviewed exact set mechanically, without inferring
  whether an unknown label is a named-customer identity claim;
- reject an alias-identity claim only when the input contract declares that
  claim explicitly;
- reproduce the disclosed top-three revenue-share and receivables subtotals;
- calculate receivables coverage using the reviewed numerator and denominator;
- calculate only the explicitly labelled squared-reported-share contribution;
- fail closed on missing, duplicate, extra, stale, or internally inconsistent
  facts.

Deterministic preparation must not:

- infer an alias-to-customer identity;
- infer precise customer revenue dollars from a rounded share;
- label the incomplete contribution as full HHI or a guaranteed HHI lower
  bound;
- produce monthly or quarterly concentration, churn, or retention claims.

### Acceptance items

- [x] Implement the registered offline customer-concentration producer.
- [x] Emit exact prepared output, reconciliation, exception, and evidence
  manifest artifacts.
- [x] Reproduce all frozen subtotals, coverage ratios, and squared-reported-
  share contributions with exact arithmetic.
- [x] Record unavailable 2023 total-receivables coverage as unavailable rather
  than inventing a denominator.
- [x] Enforce every forbidden claim and inference in the reviewed boundary.
- [x] Add an audit-only adapter that replays the producer and binds exact
  source, decision, engine, and output receipts.
- [x] Add clean, byte-determinism, schema, duplicate, omission, extra-row,
  alias, unit, increment, source, locator, rounded-share, denominator, digest,
  and publication-boundary tests.
- [x] Keep all normal tests offline and independent of a live SEC request.

## Frozen sub-slice B — WD-40 FY2025 working capital

### Observed controls

- The frozen public-source set contains WD-40's FY2025 Q1, Q2, and Q3 Forms
  10-Q and FY2025 Form 10-K receipts.
- Balance-sheet stocks are frozen at 31 August 2024, 30 November 2024,
  28 February 2025, 31 May 2025, and 31 August 2025.
- The reviewed operating-NWC perimeter includes trade and other accounts
  receivable net, inventories, and other current assets; it subtracts accounts
  payable, accrued liabilities, and accrued payroll and related expenses.
- Cash, income taxes payable, and short-term borrowings are explicitly
  excluded. Total current assets and total current liabilities are controls,
  not formula terms.
- The resulting operating-NWC controls are USD 115,455, 125,962, 137,812,
  131,921, and 126,226 thousand at the five respective balance-sheet dates.
- The cash-flow disclosures are cumulative year-to-date values. Q2, Q3, and Q4
  discrete movements therefore equal the current cumulative amount minus the
  preceding cumulative amount; Q1 uses zero as the prior cumulative amount.
- Balance-sheet “Other current assets” is not declared identical to cash-flow
  “Other assets.” Cash-flow “Accounts payable and accrued liabilities” remains
  a combined source caption and is not split deterministically.
- The expected cash impact is the negative change in operating NWC. The
  discrete cash-flow movement less that expectation is an unexplained
  stock/flow residual.
- The frozen quarter residuals are USD -298, -1,827, 3,866, and -1,575 thousand
  for Q1–Q4. The full-year residual is USD 166 thousand. No causal allocation
  is reviewed.
- DSO, DIO, DPO, normalization, and target-setting are outside this case.

### Deterministic-versus-judgement boundary

Judgement owns:

- source authority and the meaning of each reported caption;
- the operating-NWC perimeter, formula membership, and exclusions;
- sign conventions and any cross-statement caption relationship;
- whether a stock/flow bridge is analytically valid;
- explanation, allocation, materiality, and treatment of a residual;
- interpretation and any normalized working-capital target.

Deterministic preparation may:

- require exact source receipts, fact schema, natural keys, periods, units,
  increments, signs, and reviewed policy digest;
- execute the reviewed operating-NWC formula with exact decimal arithmetic;
- de-cumulate each year-to-date cash-flow component into the declared fiscal
  quarter without changing source captions;
- calculate balance movements, expected cash impacts, discrete cash-flow
  movements, and residuals;
- reconcile the quarter schedule to the full-year controls at zero tolerance;
- retain every non-zero residual as `unexplained`.

Deterministic preparation must not:

- equate differently captioned balance-sheet and cash-flow facts without a
  reviewed relationship;
- split a combined cash-flow caption;
- allocate a residual, force it to zero, or infer its cause;
- calculate days metrics, normalization adjustments, or targets.

### Acceptance items

- [x] Implement the registered offline working-capital producer.
- [x] Emit exact operating-NWC schedule, discrete cash-flow schedule,
  stock/flow bridge, reconciliation, exception, and evidence manifest
  artifacts.
- [x] Reproduce the five operating-NWC controls, four quarter bridges, and
  full-year bridge with exact arithmetic and zero tolerance.
- [x] Preserve the reviewed formula perimeter, exclusions, sign convention,
  combined captions, and non-equivalence boundary.
- [x] Leave every stock/flow residual explicit, non-zero where observed,
  unallocated, and unexplained.
- [x] Add an audit-only adapter that replays the producer and binds exact
  source, policy, engine, and output receipts.
- [x] Add clean, byte-determinism, schema, duplicate, omission, extra-row,
  period, unit, increment, sign, perimeter, caption, de-cumulation, residual,
  digest, and publication-boundary tests.
- [x] Keep all normal tests offline and independent of live SEC requests.

## Shared milestone and release acceptance

- [x] Prove identical inputs and reviewed contracts produce byte-identical
  canonical outputs and audit envelopes for both sub-slices.
- [x] Require a dedicated producer output root and reject every unregistered
  entry before an audit adapter can describe the replayed artifact set as
  complete.
- [x] Prove targeted mutations fail at the intended gate before a downstream
  handoff is emitted.
- [x] Preserve `report_ready: false`, publication `withheld`, and explicit
  unproven source-authority, semantic, lineage, and interpretation boundaries.
- [x] Confirm neither producer invokes chart selection, the Reporting Engine,
  an orchestrator, or an interpretation model.
- [x] Run the focused M5 tests and the retained M1–M4 regression suite.
- [x] Run formatting, static analysis, security, schema, privacy, and package
  checks required by the Clara release process.
- [x] Update Clara's user-facing documentation only after the executable
  behavior and limitations are verified.
- [x] Bump the plugin version and rebuild the Marketplace upload package only
  after every M5 implementation and validation gate passes.
