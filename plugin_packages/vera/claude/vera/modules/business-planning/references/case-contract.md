> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Shared Business Planning case v3

Both registered commands consume the same JSON schema
`mparanza.business_planning_case.v3`. The case and report have no product owner
or product-specific contributors. Both commands run the same analysis contract. Legacy financial/strategic v1 and product-labelled v2
contracts remain inspection/calculation internals, not finalization interfaces.

The sanitized developer fixture is `tests/fixtures/business_planning/case.json`
in repository source. Its three invented text sources contain no client names or
documents. It models the contradiction classes specified in the task; it is not
proof that any earlier client report executed the registered workflow.

## Case fields

All listed fields are required; unknown top-level fields are rejected:

| Field | Contract |
| --- | --- |
| schema_version | `mparanza.business_planning_case.v3` |
| case_id, entity_name, company_stage, planning_objective | Reviewed identity and plain-language mandate; no stage classifier |
| audience | Exact audience key used in source restrictions |
| reporting_currency | Three uppercase letters; normalize source units before comparison |
| periods | One to sixty contiguous, ordered `YYYY-MM` months |
| review | `status=reviewed`, named `reviewer`, timezone-aware `reviewed_at` after the complete read-back |
| sources | Every selected file, including contradictory evidence |
| evidence | Source-backed facts and evidence; distinct from accepted assumptions |
| assumptions | Confirmed assumptions or explicitly labelled hypotheses |
| decisions | Professional decisions, including conflict resolution and audience release |
| observations | Reviewed source-figure alignments, including conflicting figures |
| resolutions | Explicit observation selections backed by professional decisions |
| financial | Opening position and scenarios below; `null` means no supported financial model |
| narrative | Typed, reviewed model-authored findings, options, initiatives, risks and recommendations |
| limitations | Plain-language limitations; do not hide missing inputs here instead of marking them null |
| required_sections | `financial` and/or `business_analysis`, selected from the mandate, identically for either entry point |

## Source and review register

Each source has a unique `id`, relative `path` below `--source-root`, actual
`sha256`, explicit `version`, `role`, `review_status`, `intended_audience` list,
and `confidentiality={classification, allowed_audiences}`. Roles are
`client_document`, `professional_review`, `financial_model`, `external_evidence`,
`model_hypothesis`. Review statuses are `reviewed`, `confirmed`, `unverified`.
Every selected file is rehashed at execution and again before report compilation.
Vera additionally checks every input against exact Studio Archive receipts;
Clara checks the selected case-workspace boundary.

Evidence/assumption records have unique disjoint `id`, `kind` (`fact`,
`assumption`, `hypothesis`), `description`, nonempty `source_ids`, `status`,
`reviewer`, `reviewed_at`. Assumptions also require `rationale` and
`effective_periods`. All selected sources must have a record. A review is an
assertion recorded by the operator; the software cannot authenticate the human
or establish the substantive correctness of the review.

Professional decisions have unique `id`, `kind`, `rationale` and review metadata.
An `audience_release` also has `source_ids`, exact `source_sha256` and `audience`.
A release applies only to the specified source version/hash and audience. Without
it, all selected files must permit the report audience in both audience lists.
The full report contains provenance and excerpts, so permissions govern the whole
package, including JSON and CSV. Nothing is silently redacted or republished.

## Figure comparison

An observation has `id`, `scenario`, `period`, `metric`, canonical decimal-text
`value`, `unit`, `source_ids`, `basis` (e.g. `reported`, `adjusted`) and a reviewed
boolean `material`. Align metrics and units using model/professional judgment.
Different values in the same scenario/period/metric form a visible conflict.

A resolution is `{calculation_id, observation_id, decision_id}`. The selected
observation must belong to that comparison and the decision must be reviewed.
The authoritative result must equal an accepted material observation exactly.
No resolution means partial; an accepted-value mismatch means blocked.
Reported EBITDA is separately projected into the calculation register for charts,
labelled as reported evidence, and never substitutes for calculated EBITDA.

## Financial input and methods

All values are finite canonical decimal strings. Unknown required amounts are
`null`, never zero. The model does not calculate any financial scenario when a
required input is missing; it retains every missing coordinate in the report and
withholds capital recommendations. Draft unconfirmed inputs may be calculated
for review, but cannot reach readiness.

`financial` has `opening_balance`, `opening_refs`, `scenarios`, and optional
`channels` as described below.
Opening keys are `cash`, `accounts_receivable`, `inventory`,
`other_current_assets`, `net_fixed_assets`, `other_non_current_assets`,
`accounts_payable`, `debt`, `other_liabilities`, `equity`. Every key has a nonempty
list of evidence/assumption IDs in `opening_refs`. Only equity may be negative.
The opening balance must reconcile exactly; no balancing plug or arbitrary
reconciliation tolerance is introduced.

Each scenario has `id`, `label`, `schedule`. Each schedule row has `period`,
`input_refs` and every field below. `input_refs` maps every amount to nonempty
reviewed evidence/assumption IDs, effective in that period:

- `revenue`, `cogs`, `operating_expenses`, `depreciation_amortization`,
  `interest_expense`, `tax_expense`, `capital_expenditure`;
- `ending_accounts_receivable`, `ending_inventory`,
  `ending_other_current_assets`, `ending_accounts_payable`,
  `ending_other_liabilities`;
- `debt_draws`, `debt_repayments`, `equity_contributions`, `dividends`;
- `variable_cogs`, `variable_operating_expenses` (each reconciles to its total).

The shared Decimal statement engine calculates P&L, cash flow and balance
sheet, with exact opening/period reconciliation. Revenue less COGS gives gross
profit; less operating expense gives EBITDA; less D&A gives EBIT; less cash
interest and tax gives net income. Operating cash flow adds back D&A and subtracts
operating working-capital investment. Debt, equity and fixed assets roll forward.
Negative debt or fixed assets are rejected; negative cash remains visible.

The shared register additionally exposes:

- gross and EBITDA margins as ratios to revenue;
- contribution margin in currency and as a ratio, after both variable cost classes;
- break-even revenue = fixed operating costs / positive contribution ratio;
  margin of safety = (revenue - break-even revenue) / revenue;
- operating working capital = receivables + inventory + other current assets
  minus payables and other operating liabilities;
- monthly cash before financing = closing cash minus cumulative new debt/equity;
- minimum cash including opening and all month ends through the stated month;
- funding requirement = maximum pre-financing cash deficit through that month;
  residual funding gap = maximum deficit after scheduled financing;
- runway = complete modeled months from the start of the stated month until
  first negative month-end cash, zero once exhausted; null means no exhaustion
  in the remaining horizon, not infinite runway;
- debt service = cash interest + principal repayment; CFADS = operating cash flow
  + cash interest - capex; DSCR = CFADS / debt service, null if no debt service;
- sources = opening period cash + positive OCF + debt draws + equity;
  uses = operating cash deficit + capex + principal repayments + dividends +
  signed closing cash. The difference must be zero. A negative closing balance
  remains a disclosed deficit, not a fictitious funding source.

Each calculation has stable `scenario/period/metric` ID, exact value (or null
with reason), units, formula, evidence/assumption IDs and source IDs. The latter
include prior periods/opening position where roll-forwards depend on them.
Ratios are fractions, not percentages. Zero revenue and nonpositive contribution
ratios do not yield invented margins or break-even points. DSCR is not asserted
to equal a lender covenant definition. Monthly cash cannot establish intramonth
minimum liquidity. No channel economics are invented without channel inputs.

## Typed narrative and reporting

Each narrative record has exactly `id`, `kind`, `text`, `claims`,
`basis_ids`, `rubric_id`, `review`. Kinds are `finding`, `option`, `risk`,
`limitation`, `initiative`, `capital_recommendation`, `score`, `benchmark`, `kpi`.
Text references numbers via `{{claim-name}}`; `claims` maps each token to
`{calculation_id, value}`. Exact value equality is mandatory. Numeric literals in
prose are rejected; dates/financial figures belong in referenced structured data.
The professional checks semantic and implied financial claims, including written
number words. Code must not pretend to infer meaning from keyword matching.

Scores, benchmarks and numeric KPIs require `rubric_id` referencing reviewed
support with a nonempty `rubric`; otherwise they are rejected. Rubric permission
does not create new numbers: every numeric claim still requires an existing
canonical calculation. Capital recommendations must bind a complete scenario's
last-period funding requirement and are withheld while any material issue remains.

The HTML compiler validates the entire plan by replaying the case, hashes,
calculations, charts and narrative. It rejects altered derived values even if
an attacker recomputes a superficial output hash. Charts retain axis labels,
units, periods, scenarios, zero lines and ID-linked data tables. HTML escaping
also covers the embedded JSON structure.

`write_package` produces one controlled HTML, the validated structure, source
manifest, canonical JSON/CSV figures, reconciliation, validation and a SHA-256
output receipt. It refuses an occupied output folder. Optional `--pdf` uses only
freshly validated HTML and requires `requirements-pdf.txt`; no arbitrary HTML is
accepted by the PDF API. Only ready reports can be exported as PDF.

`ready_for_professional_review` describes mechanical completeness, not healthy
financial performance or final professional approval. Missing reviews/conflicts
are partial; accepted/narrative figure mismatches and reconciliation failures
are blocked. The CLI returns 2 for a non-ready result. Input/hash/audience errors
reject report publication; they cannot be bypassed by marking a case reviewed.

The explicit `internal_only` confidentiality class permits the `internal`
audience directly; any other audience requires a reviewed hash-bound release,
even if it was added to an audience list. If optional PDF rendering fails, the
validated HTML and JSON remain available and the execution receipt records the
PDF failure and partial package status.

Optional `financial.channels` supports unit economics where channel inputs exist.
Each record has `id`, `channel`, `scenario`, `period`, `unit_label`, canonical
nonnegative `units`, `revenue`, `variable_costs`, and `input_refs` for those three
amounts. Within each supplied scenario/period, channel revenues and variable costs
must reconcile to the authoritative aggregate scenario; duplicate channels and
mixed unit labels are rejected. The engine calculates revenue, variable cost and
contribution per unit with calculation IDs. Zero units leave those metrics null.
A channel contribution chart is generated only for supported calculated values.
