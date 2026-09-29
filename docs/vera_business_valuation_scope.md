# Contributor scope and implementation coverage

Reviewed 29 September 2026 against the recovered Valutazioni PMI Developer Pack
v0.1.0 (archive hash and discussion provenance are in
`vera_business_valuation_implementation.md`). Source requirements are
`HANDOFF_SVILUPPATORE.md`, `docs/01-specifica-funzionale.md`,
`docs/02-metodi-e-modelli.md`, `docs/04-piv-e-finalita.md`,
`docs/06-architettura-e-sviluppo.md`, `registry/purposes.json` and
`qa/acceptance-cases.md`. Contributor code was inspected, not executed.

The implemented common workpaper core is **not the complete requested product**.
The original pack expressly permits delivering the common core in development
before professional activation. It does not permit treating calculation tests
as PIV review or purpose-specific professional approval. No profile is currently
professionally enabled. Specialist extensions remain part of the proposed scope.

## Original backlog

| ID | Observed implementation | Remaining acceptance work |
| --- | --- | --- |
| P0-01 PIV and rights | No conformity claim; original 18 proposed topics have no verified principle/page references or real reviewer | Read definitive Principles and Rationale under their applicable access/reuse terms; record exact references, interpretation, edition rationale, reviewer and resolved conflicts |
| P0-02 Purpose profiles | All 21 profiles have explicit semantic intake, source binding and development-only coverage in `purpose-profiles.json` | Primary research, specialist implementation, purpose-specific synthetic and professionally reviewed case for each activated profile; none is activated |
| P0-03 Studio Archive | Exact case and nested-source receipts, same-engagement upstream plan, immutable revisions and idempotent replay; native fixture coverage | Installed host/user acceptance; retain explicit cross-client coverage in shared archive tests |
| P0-04 Business plan v3 | Actual compiler replays the original plan; selected contiguous whole months or complete calendar years reconcile taxes, working capital and capex; monthly amounts bind exact dated FCFF flows | Separately qualified intramonth evidence and additional professionally reviewed real-case evidence |
| P0-05 Engine | Ten explicit Decimal variants including finite-duration equity income, clean-surplus residual income with changing equity capital and holding/SOTP; annual and explicitly dated DCF with stub/monthly/mid-period timing, ACT/365F and ACT/ACT_ISDA, flat/spot/interval-forward rates, effective annual/continuous compounding; formula ledger and EV/equity separation | Distinct dated/capital-varying mixed-income conventions, further sector models, alternative terminal conventions and curve-specific scenario comparison |
| P0-06 Public sources | Versioned NYU country-risk HTML and explicitly selected ECB AAA spot CSV acquisition from observed links; immutable originals, exact percent conversion and missing-date diagnostics; parser replay for eligible imported records | ECB publication/vintage evidence and eligible binding, regional/historical workbooks and other adapters; semantic source qualification and independent historical availability |
| P0-07 Guided experience | Native skill builds technical inputs, opens report and asks focused professional questions; user does not author JSON | Witnessed accountant completion of an end-to-end case; synthetic teacher execution does not establish this |
| P0-08 Outputs | One replayed register produces HTML/MD/DOCX/PDF/XLSX/JSON/CSV and the named JSON workpapers; explicit claim bindings, numeric equality and review invalidation; independent LibreOffice formula comparison and visual QA | Semantic support review across actual cases and broad layout cases; recheck layout whenever report content changes |
| P0-09 Review | Input/source/method/mandate/audience/plan dependency hashes; per-adjustment review and transitive method bindings; independent conclusion review; affected reviews expire and unrelated branches survive | Additional purpose, full statement and benchmark-revision acceptance cases; local attestations do not authenticate humans |
| P0-10 Privacy/release | Vera privacy record, routes, Italian teaching material, component and three host package projections; dedicated CI job | Dependency-checker and page-breadcrumb corrections await owner approval; all CI gates, professional release prerequisites and authoritative existing-listing publication remain pending |
| P1-01 Specialist methods | Holding/SOTP composes explicitly valued interests, parent exposures and signed eliminations with evidence-bound review; unsupported-method diagnostics remain explicit | Holding professional cases and semantic duplication/rights review; circular holdings, crisis, PPA, rights/waterfalls and damages models with fixtures and specialist review |
| P1-02 Historical regressions | Synthetic old/new acquisition snapshots preserve original bytes; later releases reject earlier cutoffs; dependent reviews expire | Authentic archived datasets, independently established availability dates and reviewed historical cases |

## Additional functional gaps retained from the specification

Holding/SOTP now accepts three explicit part bases: operating enterprise value
with a full subsidiary equity bridge, full equity with a declared ownership
denominator/ratio and signed rights adjustment, or an already-valued specific
interest. It adds parent-only assets and signed intragroup eliminations and
deducts parent liabilities, cost present values and an explicitly signed tax
adjustment. Negative equity remains visible. Common and part-specific bases
retain source, locator, date, currency and proposed/confirmed review state.
The workbook links `Partecipazioni`, `Base holding` and `Eliminazioni` to the
same calculation register. Exact duplicate identities, declared over-ownership,
second subsidiary debt deductions and reused elimination amounts are rejected.
These structural checks do not establish complete economic perimeters,
valuation of legal rights, tax recoverability or absence of economic duplication.
Circular cross-holdings and rights waterfalls remain outside this workpaper.

The holding extension adds 61 regression cases. The complete valuation/transport
suite has 474 passes and 95.13% component coverage. Four synthetic examples,
including a receipt-bound run, independently reconcile 428 calculation cells
and 108 holding links in LibreOffice. Three fresh native workflow/lesson cases
pass, and all 82 rendered DOCX/PDF pages across six output sets were inspected.
Each set retains 18 hashed artifacts. This verifies local arithmetic and output
generation, not professional activation, installed delivery or publication.

The case contract now has structured, evidence-linked engagement/report dates,
commissioning party, expert activity, participant perspective, recipients, use
restrictions, competencies and conflicts. Rights records retain class/description,
ownership basis, economic/administrative rights, statute, agreements, restrictions
and thresholds. Nulls and unconfirmed evidence make the case partial while valid
calculations remain visible. Explicit ratio inputs never automatically scale equity
or apply discounts. A separate current mandate attestation is required before
case/conclusion acceptance; data changes invalidate dependent reviews. Filled
fields and local attestations do not establish legal validity, qualifications,
independence, semantic adequacy or human identity. Those professional decisions
and purpose-specific acceptance remain unfinished.

The structured normalization journal now records year, line, signed amount,
reason, source, accounting/economic explanations, tax treatment, reversibility
and local reviewer attestations. Each line reconciles reported and adjusted
inputs and feeds transitive formulas/review dependencies into affected methods.
Missing or inconsistent amounts block those methods. Explicit statement records
now verify assets against liabilities plus equity, all declared closing lines
against independently supplied opening amounts and signed movements, and
comparable prior-period closing/opening balances. Period, perimeter and basis
checks prevent silently mixing different records. Formula, source and review
dependencies include linked normalizations; failing statements stop dependent
methods and sensitivities while unrelated branches survive. A balance-only check
is labelled separately and absent statement workpapers are visible in reports.
Complete source mapping/classification review, converted comparative perimeters,
linked multi-line tax effects and semantic duplicate treatment across flows/equity
remain to implement or review. No automatic
annualization or semantic accounting classifier is provided.

Rate/growth sensitivities are implemented for annual and flat dated DCF. A
single-rate sensitivity cannot flatten a curve; use a separate revision. Margin, reinvestment and scenario
changes require revised inputs/plans; an integrated scenario comparison remains
to implement. Benchmark metadata is not a comparability decision. Peer-level
inclusion/exclusion, LTM/forward alignment and IFRS 16 reconciliation are not
specialist models in the common engine. Tax shields and terminal flow are
explicit supplied assumptions, not independently estimated tax/sustainability
opinions. Negative equity is allowed; share percentages, special rights, premiums
and discounts are not automatic multipliers.

The pack's additional acceptance catalogue also requires branch accounts,
special rights, seasonality/nonaligned periods, capitalization conversions,
variable WACC, IFRS 16/TFR/deferred taxes/shield limits, unsustainable terminal
values, consolidated minorities, unsuitable peers, missing public sources and
download threats. Existing tests establish bounded local input/hash/audience,
formula-injection and HTML-escaping behavior; they do not establish every one of
those wider scenarios. The new acquisition helper has explicit download-threat
tests and accepts bounded HTML from its supported NYU hosts, and HTML/CSV from
the separately scoped ECB hosts. It rejects
archive/office content without extracting archives or executing macros.

The dated-DCF extension has independent numerical cases for stub/monthly flows,
mid-period timing, leap-year day counts, continuous compounding and separate spot
versus interval-forward curves. A plan's annual flow cannot be relabelled monthly.
Three exported workbooks were recalculated with LibreOffice: all 300 calculation
cells agree with the Decimal ledger within 1e-12 relative/1e-9 absolute tolerance.
The current dated report's five pages were inspected. This establishes arithmetic
and explicit convention handling; it does not establish forecast seasonality,
economic suitability, curve estimation or an official PIV methodology.

The plan bridge now selects existing contiguous whole months, including a partial
year or a horizon crossing calendar years. The opening working-capital amount is
explicitly evidenced at the preceding month end; earlier plan forecasts never
silently become actual balances. The complete upstream plan is replayed, and every
selected month's taxes and calculation lineage must be present. Monthly bound
amounts feed only a dated FCFF DCF in the same order and at the actual month ends;
the annual terminal flow remains separate. No intramonth proration, forecast
extension or automatic annualization is introduced. Final monthly and annual
workbooks independently match the engine across 255 calculation, bridge and
linked-input cells; all six DOCX and five PDF pages per example were inspected.
Tests cover missing taxes, gapped/reordered horizons, leap-year month ends,
incorrect dates, terminal reuse, input cycles and dependent review invalidation.
These establish mechanical consistency, not professional forecast acceptance.

Normalization acceptance includes positive and negative adjustments, missing
amounts, mismatched totals, changed tax/accounting/economic/reversibility review
explanations, unrelated review preservation, duplicate amount prevention and
literal/escaped exports. All 82 cells in the separate normalization workbook were
recalculated by LibreOffice with the same tolerance; all six DOCX pages were
visually inspected. These are synthetic mechanical cases, not field acceptance.

The narrative claim registry now records explicit evidence/calculation references,
exact stated numbers and units, dependency closure, conditional scenario identity,
and separate claim/conclusion review. Missing or inconsistent support blocks the
claim without altering a valid calculation. No semantic truth classifier is
implemented. Five DOCX and four native PDF pages of the claim example were
inspected; LibreOffice checked its 75 calculation cells and linked claim value.

All named calculation workpapers in `contracts/workflow.json` are now separate
JSON exports from the canonical report, including mandate, evidence, adjustments,
forecast binding, method decisions, benchmarks, calculations, sensitivity,
conclusion and professional review. The additional claim register brings the
helper output to 18 artifacts. Actual model-data JSON/Markdown remain a separate
host responsibility; a numerical helper cannot invent what the model read.

The contributor's requested production JSON Schema validation now uses the
declared `jsonschema>=4.23,<5` dependency and bundled Draft 2020-12 case schema.
The runtime validates the envelope before nested-source discovery, then selected
method payloads inside their individual diagnostic boundaries. Unsupported or
incomplete methods remain blocked alongside usable methods; excluded specialist
methods retain their explanation. Only bundled internal schema references are
used. Schema checks cover structure and explicit representations; semantic
suitability, cross-record integrity, receipts and review freshness remain separate
checks. Invalid review records are retained without granting acceptance.

The first public-source adapter is `nyu-country-risk-html/v1`. It preserves a
captured landing page, observed dataset link, usage terms, redirects, original
document hash, selected row, original percent and exact ratio conversion. Raw
files use inert `.source` names. Same-day identical retries preserve the first
record; changed source releases receive new snapshots. Errors retain their actual
state without falling back to old cached values. Imported observations replay
the parser against exact Studio Archive evidence before calculation.

The live 29 September NYU run retrieved all three public documents and parsed the
selected row, but remained `metadata_or_value_missing`: the table's displayed
release date does not establish its exact observation date. No date or current
parameter adoption was invented. That live evidence proves acquisition and
parsing, not full historical availability, professional suitability or coverage
of other providers.

The `ecb-aaa-spot-csv/v1` adapter now preserves the exact selected AAA spot
series/date, original row and continuous-compounding definition from the official
40-column CSV. It converts percent to a ratio without changing compounding or
selecting a maturity. Publication and vintage remain null; HTTP Last-Modified,
retrieval time and the release schedule cannot fill those fields. The live
29 September run captured the official landing page, linked terms and 1,287,450-byte
CSV and parsed the selected 28 September observation. It correctly remains
`metadata_or_value_missing` and is ineligible for automatic case binding.
A first request used a web-rendered URL spelling that differed from the literal
href; that explicit failure is retained. The second used the exact link inspected
in captured HTML. No endpoint or historical date was guessed.

Forty-four additional ECB regressions cover missing/invented publication evidence,
continuous versus other rate definitions, signed/missing values, exact selection,
changed units/status/CSV shape, duplicate observations, revisions, URL/MIME
boundaries and the refusal to replay an invented vintage. The combined valuation
and shared-transport suite has 336 passing tests at 94.31% component coverage.
All 14 component scripts pass Mypy, Black, isort and Bandit. These checks establish
bounded parsing and evidence handling, not economic suitability or historical
availability.

Mandate acceptance covers missing fields, invalid dates, source/ownership
references, rights without a percentage, missing/out-of-range proportions,
review invalidation and untrusted export text. The synthetic 40% interest retains
750 EUR enterprise-equity reference output rather than multiplying it. All 75
calculation cells match an independent LibreOffice recalculation; 19 mandate data
rows remain visible. All six DOCX and five native PDF pages of that example were
inspected. Both final teaching cases retain their numerical indications and 18
artifacts but are now explicitly partial because the note is not a complete
engagement letter. All four DOCX and three native PDF pages per teaching case were
inspected. This is mechanical and document QA, not professional acceptance.
The three rebuilt Vera ZIP layouts reproduce all three complete report objects
outside the repository, including their different mandate statuses. Fifteen
governed source files per archive match byte-for-byte; 108 focused privacy,
teaching and package/release checks pass. Full CI and installed acceptance remain
separate requirements.

The finite-duration equity-income extension is a separate `INCOME_EQUITY_FINITE`
variant. It requires exact dated periods, supplied income amounts, a separate
horizon equity residual and a source-bound basis explaining capital maintenance,
reinvestment, distributions and residual double-counting. It never equates income
with cash, infers a residual/perpetuity, relabels plan FCFF or deducts debt again.
The residual remains at period end with mid-period income timing. Missing basis
or source structure blocks that method; unconfirmed assumptions remain partial.
Changed explanations and evidence invalidate its review while independent methods
survive. This is an explicit calculation contract, not professional validation of
income availability, residual sustainability or method suitability. Thirty-seven
new cases bring the combined suite to 373 passes at 94.43% component coverage.
All 14 component scripts pass static, formatting and Bandit checks.
LibreOffice independently matches all 315 calculation cells across annual,
mid-period and continuous examples; each workbook retains four basis rows.
All seven DOCX and five native PDF pages of the annual and archive-bound examples
and four DOCX/three PDF pages per teaching case were visually inspected.

## Purpose coverage and release evidence

The separate `RESIDUAL_INCOME_EQUITY` variant now handles changing common-equity
book capital with exact clean-surplus roll-forwards. Opening/closing equity,
income, distributions, contributions and terminal equity are supplied separately.
The period equity charge is implied by the same discount factors used for residual
income; terminal continuation is terminal equity less final book equity. A second
calculation reconciles the result to net owner payments and terminal equity.
Flat, spot and interval-forward curves, effective/continuous compounding and
explicit short periods are covered. Owner transactions remain end-period; no
balancing plugs, inferred OCI adjustments, automatic terminal value, FCFF relabeling
or second debt deduction is provided. The source-bound accounting and economic
basis needs professional review. This does not qualify a PIV purpose or substitute
for the distinct mixed-method conventions still listed above.

Forty new cases bring the valuation/acquisition/shared-transport suite to 413
passes at 94.66% component coverage. All 15 scripts pass Black, Isort, Mypy and
Bandit; a Mypy cache internal error was resolved by rerunning with a fresh isolated
cache, without source or dependency changes. LibreOffice independently matches
400 calculation and 66 linked clean-surplus cells across annual, spot and short
period examples. All eight DOCX and six PDF pages per example and per native
archive-bound residual case were inspected. Both fresh teaching outputs retain
the prior text except receipt IDs and expected partial results; all four DOCX and
three PDF pages per teaching output were inspected. These are synthetic technical
checks, not accountant or enabled-host acceptance.

The three rebuilt Vera layouts contain 18 byte-identical executable/schema/transport
files and each reproduces six full report objects outside the repository. Full
Vera/Clara/Lucia package alignment passes. The broader required check run has 504
passes, two installed-Marketplace skips and the same two unresolved failures:
dependency-checker arguments and the uncommitted-source version guard. Committing
does not waive either the release-version decision or current-head CI.

Statement acceptance adds 28 regressions, including wrong dates/perimeters/bases,
independent opening evidence, duplicate movement prevention, negative equity,
signed movements, missing/unit-invalid amounts, linked adjustments, method and
claim review invalidation, sensitivity blocking and literal/escaped exports.
The formula workbook independently matches the engine in 112 calculation and
24 reconciliation cells; all seven DOCX and six native PDF pages were inspected.
The two teaching outputs state the absence of statement checks and preserve
their numerical indications, 18 artifacts and incomplete mandate status.
All four DOCX and three native PDF pages per lesson output were inspected.
These facts establish explicit arithmetic and document QA, not semantic
completeness, a real professional review or an enabled-host acceptance case.

`plugins/business-valuation/references/purpose-profiles.json` retains all 21
source IDs, including inheritance, family and exclusion. Its shared coverage
record applies to **each** profile: designed, common core implemented, shared
arithmetic/intake tested, professional review pending, professional use disabled.
Selection is explicit and source-bound. There is no automatic method selector,
case-acceptance shortcut or keyword classification. A profile-specific future
release must replace this shared development-only state with inspected evidence
for that exact profile. The 21 routing tests are not 21 professional cases.

The 18 source PIV topics remain proposed review topics, not established PIV
requirements: mandate/independence, basis, dates, rights, information quality,
fundamental analysis/plan, methods, capital cost, terminal value, comparables,
assets/intangibles, premiums/discounts, crisis/liquidation, legal purposes,
synthesis, reporting, SME proportionality and review/limitations. Exact principle
and page references and professional reviewer remain unknown. Do not invent them.

## Migration and preservation

There is no server database migration. The new archive workflow ID is registered
in shared contracts and MCP input choices. Use a fresh immutable valuation case
and run; never mutate imported sources or completed reports. The contributor's
prototype JSON is reference material, not an accepted production case: map it
from inspected evidence into `vera.business_valuation.case.v1`, register sources
and receipt paths, then verify independent expected results. Purpose selection
is optional for old development cases and visibly unclassified if omitted.
Adding it changes the mandate dependency digest and invalidates old acceptance.
Old output directories are preserved; retrying an old revision against changed
compiler output stops rather than overwriting its artifacts.

The source ZIP, response document, complete recovered messages and hash
inventory remain in the primary checkout's ignored
`outputs/vera-valuations-discord`. No client evidence or contributor attachment
is published through this pull request.
