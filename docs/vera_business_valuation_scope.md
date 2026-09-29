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
| P0-04 Business plan v3 | Actual compiler replays a complete calendar-year plan; FCFF bridge reconciles monthly taxes, working capital and capex; missing tax blocks | Partial periods and additional reviewed real-case evidence |
| P0-05 Engine | Seven independently tested Decimal methods, annual end-year DCF/mixed calculations, formula ledger and EV/equity separation | Stub, mid-year, monthly discounting, day-count, variable curves and further income/sector variants |
| P0-06 Public sources | Host-led official research instructions; imported bytes/hash and explicit observation/publication/retrieval/vintage metadata; cutoff and age checks | Versioned parsers and tested observed-link acquisition, availability failures, redirects/host validation and historical revised-release cases |
| P0-07 Guided experience | Native skill builds technical inputs, opens report and asks focused professional questions; user does not author JSON | Witnessed accountant completion of an end-to-end case; synthetic teacher execution does not establish this |
| P0-08 Outputs | One replayed register produces HTML/MD/DOCX/PDF/XLSX/JSON/CSV; independent LibreOffice formula comparison and visual QA | Structured narrative-claim bindings and broad layout cases; recheck layout whenever report content changes |
| P0-09 Review | Input/source/method/mandate/audience/plan dependency hashes; independent conclusion review; affected reviews expire and unrelated branches survive | Additional purpose/normalization and benchmark-revision acceptance cases; local attestations do not authenticate humans |
| P0-10 Privacy/release | Vera privacy record, routes, Italian teaching material, component and three host package projections; dedicated CI job | Dependency-checker and page-breadcrumb corrections await owner approval; all CI gates, professional release prerequisites and authoritative existing-listing publication remain pending |
| P1-01 Specialist methods | Intake scope and unsupported-method diagnostics are explicit | Holding/SOTP, crisis, PPA, rights/waterfalls and damages models with fixtures and specialist review |
| P1-02 Historical regressions | Publication/observation ordering, cutoff and explicit age policy | Historical revised datasets and preserved release vintages demonstrated end to end |

## Additional functional gaps retained from the specification

The current case contract has a free-text mandate and selected evidenced inputs.
It does not yet provide dedicated structured fields for every mandate date,
commissioning party, expert activity, market-participant perspective, conflicts,
competencies, share-class instruments and restrictions. Supporting documents and
the skill preserve these issues for review; that is not structured completion.

Normalizations currently live in supporting source workpapers and separate
reported/adjusted inputs. The full structured adjustment journal (year, line,
signed amount, reason, tax, reversibility and reviewer), statement reconciliation
and balance roll-forward remain to implement. No automatic annualization or
semantic accounting classifier is provided.

Rate/growth sensitivities are implemented. Margin, reinvestment and scenario
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
those wider scenarios. Download-threat tests become required with acquisition;
there is currently no helper URL fetcher, archive extractor or macro executor.

## Purpose coverage and release evidence

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
