# Business valuation case v1

The model authors this file from inspected evidence and professional choices.
The user does not write JSON. `scripts/run_valuation.py` requires a current
portable Studio Archive context. Every source and the case must be an exact
receipted input; an upstream plan must be a finalized same-engagement artifact.

## Case and source records

Required top-level fields: `schema_version=vera.business_valuation.case.v1`,
`case_id`, `entity_name`, `currency` (one ISO-style three-letter code), `audience`,
`synthetic` (boolean), `mandate`, `sources`, `inputs`, `methods`, `limitations`.
Optional fields: `conclusion`, `plan_binding`, `sensitivity`, `purpose_profile`.
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
`limitations` (list); optional `bridge`, `review`. Every monetary parameter below
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

The function prepares workpapers. PIV conformity and purpose-specific legal
qualification remain explicitly not assessed. No automatic signing, filing,
communication, market-data feed, special-rights model, PPA, crisis distribution,
fractional-period DCF or variable discount curve is claimed.
