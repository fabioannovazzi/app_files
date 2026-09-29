# Business valuation case v1

The model authors this file from inspected evidence and professional choices.
The user does not write JSON. `scripts/run_valuation.py` requires a current
portable Studio Archive context. Every source and the case must be an exact
receipted input; an upstream plan must be a finalized same-engagement artifact.

The published structural contract is `valuation-case.schema.json` (JSON Schema
Draft 2020-12). The helper uses the declared `jsonschema` runtime dependency to
validate the case envelope before source-path discovery or nested file reads.
It then validates `$defs.selectedMethod` independently for each selected method:
malformed or unsupported method payloads become blocked workpapers while other
methods remain calculable. Excluded methods retain their rationale without
requiring a complete numeric payload. All schema references are bundled local
definitions; case files cannot select a schema or trigger remote retrieval.

Schema checks enforce field shape, bounded lists, canonical dates/decimal text
and the documented method payloads. Reference existence, date ordering, receipts,
hashes, unit relationships, arithmetic and economic judgment need the separate
runtime or professional checks below. Raw local review records are deliberately
retained, including incomplete ones; only the exact runtime attestation checks
can grant review status. Schema validity never proves professional acceptance.
Diagnostics identify the field path and failed rule without echoing field values.

## Case and source records

Required top-level fields: `schema_version=vera.business_valuation.case.v1`,
`case_id`, `entity_name`, `currency` (one ISO-style three-letter code), `audience`,
`synthetic` (boolean), `mandate`, `sources`, `inputs`, `methods`, `limitations`.
Optional fields: `conclusion`, `plan_binding`, `sensitivity`, `purpose_profile`,
`normalizations`, `claims`.
Unknown fields reject.
All monetary/rate/multiple values are canonical decimal strings, with no thousands
separator, exponent or implicit percent conversion. Rates are fractions. Missing
values are `null`; they block only dependent methods. Internal precision is 40
significant digits. Display rounding does not change stored results.

`mandate` has `purpose`, `subject`, `valuation_date`, `information_cutoff`,
`basis_of_value`, `premise`, `rights`, `professional_limitations`. Dates use
YYYY-MM-DD. The professional interprets the mandate; software does not infer the
governing law or edition of a standard from a date. A later permitted cutoff
requires an explicit mandate explanation, not automatic historical availability.

`purpose_profile` records the model/professional's explicit semantic choice with
`id`, `selection_reason`, nonempty `source_ids` and a mandate `locator`. Select
the ID from `purpose-profiles.json`; use `custom` with the actual purpose explained
in the mandate when necessary. No keyword classifier chooses it. If omitted,
the report says the purpose has not been classified. The registry covers all 21
families in the supplied proposal, with individual intake focus and explicit
coverage states. All currently share the common development core only; no
purpose-specific professional review or availability is claimed. Case acceptance
cannot activate a profile. A change to the selected profile, reason or mandate
source invalidates method/conclusion reviews that depend on that mandate.

Each source has `id`, `path`, `sha256`, `description`, `allowed_audiences` (list),
`status` (`reviewed` or `unverified`). Paths are relative to run `inputs`, including
the actual `imports/<input_id>/<filename>` or upstream execution path. Sources
must be regular files without symlinks; traversal, changed hashes and audience
mismatches block export. Maximum selected file size is 100 MiB, case size 8 MiB.
Evidence identity is not evidence truth. The sources describe intended audience;
classification and authority to permit that audience remain professional decisions.

## Inputs

Each input has `id`, `value`, `unit` (currency, `ratio` or `multiple`),
`description`, nonempty `source_ids`, `locator` (page/cell/paragraph), `kind`
(`fact`, `assumption`, `hypothesis`) and `status` (`confirmed`, `proposed`).
Stable IDs use lower-case letters, digits, underscores and hyphens, beginning
with a letter, at most 80 characters. Unknown source references reject.
Record original and adjusted inputs separately and preserve normalization
workpapers as sources. The engine does not automatically extract or normalize
arbitrary statements. `plan_calculation_ids` is optional upstream lineage.

A benchmark input also has `benchmark` with `source_url`, `observed_on`,
`published_on`, `retrieved_on`, `vintage`, `definition`, `geography`,
`max_age_days` and `selection_reason`. The dates must be ordered and publication
must not exceed the information cutoff. The explicitly selected age policy must
be satisfied. These are metadata checks, not authenticity or comparability
checks. URLs are citations only; no URL fetcher runs inside the helper.

## Methods

A method has `id`, `kind`, `selected` (boolean), `rationale`, `inputs`,
`limitations` (list); optional `bridge`, `review`, `timing`. Every monetary parameter below
is an input ID, not an inline amount. Unselected methods retain their rationale.

| Kind | Required inputs | Meaning |
| --- | --- | --- |
| DCF_FCFF / DCF_FCFE | flows (ordered list), discount_rate, terminal_next_flow, terminal_growth; optional terminal_rate | Annual end-year discounting; terminal flow is supplied independently; terminal rate must exceed growth; FCFE is already equity |
| INCOME_EQUITY | normalized_equity_income, cost_equity | Positive constant equity income divided by positive Ke |
| NAV | assets (nonempty list), liabilities (possibly empty list), tax_adjustment | Adjusted assets less liabilities less signed tax adjustment |
| MIXED_EQUITY | adjusted_equity, incomes (ordered list), normal_return, excess_discount | Constant adjusted equity plus discounted annual excess incomes |
| MULTIPLE | metric, selected_multiple, kind | Positive metric times selected multiple; kind is EV_EBITDA, EV_EBIT, EV_REVENUE or P_E |
| APV | unlevered_value, pv_tax_shields, pv_financing_costs | Supplied unlevered PV plus shield PV less financing-cost PV |

An enterprise-side method can supply `bridge` with input IDs `financial_debt`,
`debt_like`, `excess_cash`, `non_operating_assets`, `signed_adjustments`.
All except signed adjustments are nonnegative. Equity-side methods reject any
bridge, preventing repeated debt deduction. No quota multiplier or premium is
automatic. Check leases, TFR, minority interests and cash classification in the
workpapers; the numerical helper cannot establish economic consistency.

Optional `sensitivity` is a list with `id`, `method_id`, `discount_rate`,
`terminal_rate`, `terminal_growth`; each rate/growth is an input ID. It reuses a
selected DCF's flows and bridge, labels each result conditional, and retains
invalid rate/growth combinations as blocked rows without inventing values.

## Review and revisions

Optional `normalizations` is an explicit adjustment journal. Each group has a
stable `id`, integer `year`, professionally named `line`, `reported_input`,
`adjusted_input` and nonempty `adjustments`. The input IDs refer to distinct
declared amounts in the case currency. A year/line and adjusted output may appear
only once. Chained adjusted outputs and overwriting replayed plan outputs are
unsupported: revise the original workpaper or plan instead.

Each adjustment has `id`, `amount_input` (signed change to that line), `reason`,
`accounting_check`, `economic_rationale`, `tax_treatment`, `reversibility`,
`source_ids`, `locator`, and optional `review`. All explanations are explicit
nonempty text; the model and professional judge their substance. A positive or
negative amount is not selected because of its effect on the valuation. Tax
treatment is descriptive, never an inferred rate or tax formula. Any separate
cash/deferred tax effect or impact on another line needs its own evidenced
amount and reconciliation; do not add it twice or hide it in the signed amount.

The helper replays `reported + sum(signed adjustments) = adjusted` at Decimal
precision and retains the original amount, total, computed amount, independently
declared adjusted amount and difference. An absent or mismatched amount blocks
only dependent methods, while the journal and other methods remain visible.
One amount input cannot be added twice to the same line. This arithmetic is not
a complete statement balance, roll-forward, accounting treatment or semantic
double-counting test across different lines.

Each adjustment exposes its own dependency digest for the standard local review
attestation below. It binds the year, line, input/source bytes and metadata,
mandate, audience, tax/reversibility explanations and other declared choices.
Arithmetic reconciliation alone does not approve an adjustment. Unreviewed or
stale adjustments prevent dependent method acceptance; unrelated method reviews
survive. The method formula register and workbook link back to the computed
adjusted amount and transitive evidence. The `Rettifiche` worksheet and every
report format retain the journal and its actual review state.

The result supplies a `dependency_sha256` for each method. Review records contain
`dependency_sha256`, `decision=accepted`, `reviewer`, `reviewed_at` with timezone.
They are local attestations, never authenticated identity or digital signatures.
Record only explicit professional decisions. Changed mandate, audience, currency,
method configuration, referenced input/source or dependent plan bridge invalidates
the method review. An unrelated input change does not invalidate other methods.
Selected unverified inputs/sources prevent acceptance; stale records stay visible.

Optional `conclusion` has `text`, nonempty `method_ids`, `review`. Its independent
dependency digest binds the prose, referenced method versions and case limitations.
The compiler never creates a conclusion or average. All numerical claims in prose
require model/professional comparison against the calculation IDs. Code validates
identity and dependencies, not semantic truth of the narrative.

## Narrative claim register

Optional `claims` records substantive authored statements. Each has `id`, `kind`
(`fact`, `assumption`, `hypothesis`, `opinion`), `text`, report `location`, `basis`
explaining evidence support, `source_ids`, `input_ids`, `calculation_ids`,
`method_ids`, `limitations` and optional `review`. Reference arrays are explicit,
unique and may be empty individually; at least one evidence reference is required.
The model and professional select the kind and relevant evidence. Code does not
classify prose or infer semantic support from a link.

For each numerical assertion, supply a `values` entry with `calculation_id`,
canonical decimal `value`, and exact `unit`. The calculation must be explicitly
listed. Equality is checked without currency conversion, percentage scaling or
rounding tolerance; reader-facing rounding is separate. A mismatch or unresolved
reference blocks the claim, preserves both stated and calculated amounts, and
does not alter a valid valuation calculation. Missing evidence is never fabricated.
Free-text numbers are not parsed: the host must map each material numerical
statement and review the prose against its explicit numeric bindings.

The register resolves the whole arithmetic dependency chain and binds exact input,
source, method, normalization and conditional-sensitivity versions. Claims about
normalization calculations retain their adjustment review dependencies. A changed
tax explanation can invalidate its claim without changing the sum. Conditional
scenario claims retain their scenario IDs and are not statistical intervals.

Claim review uses the standard explicit local attestation. Referenced methods and
adjustments must first have their own current acceptance; this does not establish
truth, authenticate a reviewer or activate a professional purpose. Conclusion
`claim_ids` optionally names reviewed claim records; its separate review binds
those exact records and the prose. Missing structured conclusion links are shown
as missing, never inferred. Register records and their actual status appear in
the report, `Affermazioni` workbook sheet and `claim_registry.json`.

Every new case revision is imported as a new immutable input and run. Outputs use
`valuation-<case-hash>` directories. Repeating the exact request replays the case
and verifies every existing artifact's hash. Incomplete or changed exports are
retained and not overwritten. All-blocked cases retain a diagnostic report;
individual blocked methods can coexist with valid methods in a partial package.
Never describe either case as professionally complete.

## Existing business plan

`plan_binding` has `source_id`, `source_map` (original source ID to current source
ID), `scenario_id`, `cash_operating_taxes` (month to input ID),
`opening_operating_nwc` (input ID), `annual_input_ids` (ordered FCFF input IDs),
`operating_classification` (reviewed explanation), `tax_refund_basis` (text or
empty when no refund). The upstream file uses `mparanza.business_planning_plan.v3`.
Its source bytes and complete canonical report are replayed using the existing
compiler. Supporting sources are temporarily reconstructed at original relative
paths in a scratch directory under the exact run output; the final bridge persists
hashes and lineage. The source plan and original evidence are never modified.

Only complete calendar-year periods and a preceding December 31 valuation date
are accepted. The bridge uses reviewed operating current assets/liabilities,
explicit operating cash taxes and capex, preserving annual closing stocks and
summing monthly flows. Annual inputs must equal the computed FCFF and contain
the exact bridge `plan_calculation_ids`. No stale plan, source-hash mismatch,
arbitrary imported plan or cross-engagement plan can pass the CLI gate.

## Outputs and limits

HTML, Markdown, DOCX/PDF, formula XLSX, JSON, CSV and an artifact hash list share
one replayed register. The workbook has source inputs, formula calculations,
method summaries and source provenance. Excel uses its own numeric precision;
the authoritative exact decimal result is retained alongside each formula.
Opening/recalculation is required to populate formula caches. Changing the workbook
does not amend the approved JSON case or its recorded professional reviews.

Named JSON workpapers project the same canonical result into `mandate.json`,
`evidence.json`, `normalizations.json`, `forecast_binding.json`,
`method_decisions.json`, `benchmark_observations.json`, `calculations.json`,
`sensitivity.json`, `valuation_conclusion.json`, `professional_review.json` and
`claim_registry.json`. Each carries `case_sha256`, `report_sha256`, `kind`,
`schema_version=vera.business_valuation.workpaper.v1` and `data`. Unused plan or
conclusion data stays null; absent observations remain empty. The archive manifest
hashes all 18 exported artifacts. The host separately prepares the two model-data
reports from its actual reading/context evidence; the numerical helper cannot
fabricate that account from the case inputs.

The function prepares workpapers. PIV conformity and purpose-specific legal
qualification remain explicitly not assessed. No automatic signing, filing,
communication, market-data feed, special-rights model, PPA, crisis distribution,
curve estimation/interpolation or automatic period proration is provided.

## Explicit dated DCF

DCF may instead include `timing`. In that form its `inputs` are exactly `flows`,
`terminal_next_flow`, `terminal_growth`, `terminal_rate`; there is no hidden
fallback `discount_rate`. The latter two terminal assumptions are **effective
annual** rates and the terminal flow is an independently supplied **annual**
amount, including when explicit forecast cash flows are monthly.

Required timing fields:

- `valuation_date`: exact mandate date; canonical YYYY-MM-DD.
- `period_end_dates`: one strictly increasing date per supplied flow, after the
  valuation date. Periods begin at that date and then the previous end. Supply
  the actual remaining stub/monthly amounts; code never prorates an annual flow.
- `cash_flow_timing`: `end_period` or `mid_period`. Mid-period uses the arithmetic
  midpoint of the start/end year fractions, not an inferred payment date.
- `day_count`: `ACT/365F` (actual days divided by 365) or `ACT/ACT_ISDA` (calendar
  year segments divided by their own 365/366 days, start included/end excluded).
- `rate_compounding`: `effective_annual` or `continuous`. All rate IDs in this
  schedule share that declared convention. Percentages must already be fractions.
- `rate_model`: `flat`, `spot_curve` or `forward_curve`.
- `rate_ids`: one ID for flat, one ID per flow/period for either curve.
- `rationale`: professional explanation of periods, timing and rate assumptions.

Only `spot_curve` also requires `terminal_discount_rate`, an input ID for the
spot rate at the final period end. Its cash-flow rates are spot rates at the
actual cash times. Forward rates instead apply to each complete interval; earlier
interval factors accumulate before the current full/half interval. They are not
instantaneous point observations or par yields. The engine does not construct,
interpolate or choose a market curve.

The divisor for effective annual rates is `(1+r)^t`; continuous rates use
`exp(r*t)`. Forward models multiply interval divisors. The terminal value is an
annual end-period perpetuity valued at the final period end and discounted from
that horizon, even with mid-period operating cash flows. This is an explicit
terminal convention; it does not assert that continuing cash is distributed
uniformly through future years. A different continuation model requires its own
validated contract. Days, denominators, times, rates, factors and PVs appear in
the formula ledger and workbook; the report exposes the schedule.

Limits: at most 1,200 explicit periods and 36,600 days; dates before year 9999.
The EXP primitive accepts exponents in [-100, 100] as an explicit numerical
capacity limit, not a suitability rule. The existing annual plan bridge still
requires full calendar years: dated use must retain all annual flow IDs and their
actual December 31 ends. A single-rate sensitivity supports flat dated schedules;
curve revisions require a separate case and are never silently flattened.

Methodological implementation references checked on 29 September 2026:
[Strata day counts](https://strata.opengamma.io/day_counts/) for the two day-count
definitions; [ECB technical notes](https://www.ecb.europa.eu/stats/financial_markets_and_interest_rates/euro_area_yield_curves/shared/pdf/technical_notes.pdf)
for the distinction between spot, forward and par curves and continuous
discounting. These references do not prescribe a company's cost of capital or
establish PIV conformity. No market datasets or protected standard text are bundled.
