# Vera business valuation implementation

Source: Francesco Giraldo's Valutazioni PMI v0.1.0 proposal, recovered from
https://discord.com/channels/1550191335917625474/1554383249646813294/1554533476928200749
on 29 September 2026. ZIP SHA-256:
`cf7ee90de4a3ae4d04682399c1b00cb217252db2ccd8daa33c038e044ef42d2d`.
All 52 manifest entries verified; 53 archive files retained without executing
the supplied launchers. Original attachments and conversation are retained in
the primary checkout's ignored `outputs/vera-valuations-discord` directory.

## Implementation contract

This is the common development core. See
[`vera_business_valuation_scope.md`](vera_business_valuation_scope.md) for the
complete contributor requirements, observed coverage and unfinished acceptance
work. The goal is not complete and no purpose is professionally activated.

Implement a client-bound `business-valuation` workflow for preparing reviewable
PMI valuation workpapers. The supported methods are FCFF and FCFE DCF, constant or finite-duration
equity income, clean-surplus residual income with changing equity capital,
adjusted NAV, constant-capital mixed income, holding/SOTP composition, selected
multiples, and APV composition. Method selection, source relevance, normalizations,
terminal sustainability, benchmark comparability and conclusion are model and
professional judgments. Decimal arithmetic, evidence identity, formula lineage,
receipt boundaries, audience restrictions and approval invalidation are
mechanically verifiable and belong in code.

Reuse Studio Archive and the authoritative business planning v3 compiler. Do not
introduce a second forecast. Retain sources, assumptions, exact calculation
records, independent method outputs, scenario/sensitivity assumptions and
professional review. Changing a dependency must invalidate its review.
Produce review HTML, DOCX/PDF, a formula workbook, JSON and CSV from the same
register. Never average methods or apply quota discounts automatically.

## Availability boundary

The function prepares valuation workpapers for professional review. It does not
sign, file, certify PIV compliance or qualify every legal-purpose profile.
Further specialist methods, rights waterfalls, crisis distributions and legal-purpose
opinions remain outside the calculation contract. Missing evidence is visible;
unsupported dependent calculations stop rather than substitute invented values.

On 29 September 2026 the official OIV page identifies PIV 2026 with application
from 1 January 2027 and restricted reproduction. This implementation does not
redistribute that text or claim a principle-by-principle professional review.
Source: https://www.fondazioneoiv.it/piv/ . Public methodological cross-check:
https://pages.stern.nyu.edu/adamodar/New_Home_Page/valuationtools.html .

## Verification

Independent numerical fixtures; failure cases for missing data, incompatible
units, double debt deduction, terminal growth, source changes and stale review;
real v3 plan replay; Studio Archive cross-client and receipt checks; workbook
formula comparisons; report rendering; privacy coverage and package parity.

### Combined CNC integration checkpoint — 30 September 2026

Integrated upstream main `8f662195f00bac3b605ac73077e1a0bd31d30253` on the
valuation feature branch. Valuation source is byte-identical to the holding
checkpoint; the CNC component and new archive snapshot implementation are
byte-identical to upstream. Both routes and CI jobs are retained. The merged
catalogue has 47 kits / 211 localized kits and 43 Geneva entries. Existing
professional and jurisdiction dispositions are preserved. Thirty-six lesson
review records bind changed source inventories; their lesson content matches
one or both merge parents outside those inventories.

Valuation retains 474 passing cases and 95.13% coverage. CNC and shared archive
checks have 144 passes after correcting one test-only workflow list, including
ten native CNC lesson cases. The complete deduplicated local matrix has 1,589
passes, five failures and three skips after test-only catalogue-count corrections.
All correction runs and original failures are retained in the local evidence.

Two failures concern the already proposed valuation dependency-checker argument
and breadcrumb corrections, still awaiting owner approval. Three others concern
the Fusione page's shared model-data component, run-report note and typography;
they reproduce on an exported untouched `8f662195` source snapshot. That upstream
snapshot also fails its breadcrumb check for Fusione. This does not waive any
release gate or imply green remote CI. The skips are two unavailable installed
Marketplace caches and an empty retained-published-lesson parameter set.

All three product source/version/package checks pass at Vera `0.1.288`, Clara
`0.1.225` and Lucia `0.1.65`. Each Vera package has the same 19 governed source
files and reproduces 12 saved complete report objects outside the repository
(36 exact replays). Both Vera and Clara privacy registers are current; Lucia's
affected opening-matter privacy binding is verified by its package tests.
No public push, merge to main, deployment, Marketplace publication or enabled-host
acceptance occurred. The full contributor scope and professional activation
remain open.

### Holding/SOTP checkpoint — 30 September 2026

Candidate source Vera `0.1.287` / component `0.1.1` adds explicit holding
composition to the nine previous calculation variants. The full 474-case
valuation/transport suite passes at 95.13% coverage, including 61 new holding
cases. Black, Isort, Mypy and Bandit pass across all 16 component scripts.
Three fresh native holding and Italian lesson runs pass. The existing lesson
content is unchanged; only its source inventory/fingerprints changed.

LibreOffice independently matches all 428 calculation cells and 108 linked
holding cells across four examples. All 48 DOCX and 34 native PDF pages across
six output sets were inspected, with 18 verified artifact hashes per set.
Scenario-specific source notes and tax wording were clarified in new immutable
example revisions; production source did not need a test-driven repair.

Each of the three Vera packages contains 19 byte-identical executable/schema/
transport files and reproduces 12 full saved report objects outside the
repository, for 36 exact replays. Source/version/package checks pass for Vera
`0.1.287`, Clara `0.1.221` and Lucia `0.1.61`. Both full privacy registers are
current. All 345 workflow filesystem and website-journey checks pass.
The package/privacy/teaching/routing suite has 551 passes, two installed-cache
skips and the previously recorded dependency-checker `--requirements` failure.
The checker correction remains unapplied pending owner approval under AGENTS.md.
The combined current local matrix has 1,370 distinct passing cases, one failure
and two skips; it is not a claim of green remote CI.

This checkpoint is based on integrated main `f09267a16fc906f813de80675b2b8328f33c979d`.
During final checks, remote main advanced to
`8f662195f00bac3b605ac73077e1a0bd31d30253`, adding the composizione negoziata
workflow. That newer baseline requires integration and renewed package/release
checks before publication. No current-main alignment, merge to main, deployment,
Marketplace publication or installed-host acceptance is claimed here.

### Integration checkpoint before holding/SOTP — 30 September 2026

The active valuation branch incorporates upstream main
`f09267a16fc906f813de80675b2b8328f33c979d`, including the synthetic transformation
prototype and assetti construction workflow. Both routing entries and CI jobs are
retained. Vera candidate `0.1.286` is above main's `0.1.283` and every inspected
open candidate (highest `0.1.285`); it is not a published version. Recheck main,
open release candidates and the authoritative listing before publication.

All 413 valuation/transport regressions still pass at 94.66% component coverage;
68 construction, 46 transformation and ten native assetti lesson cases pass.
The assetti lesson differs from both merge parents only in source fingerprints;
its prior editorial reviews and development limits are retained. The regenerated
42-entry Geneva inventory preserves existing dispositions and explicitly leaves
valuation and transformation unresolved. It does not qualify construction for
Swiss mandates.

All three product source/version/package checks pass (Vera 0.1.286, Clara
0.1.221, Lucia 0.1.61). Each Vera archive has 18 exact valuation source files and
reproduces six complete saved reports outside the repository, for 18 exact
replays. The valuation implementation and lesson source bytes are unchanged by
this integration. Rebuilding the public lesson also incorporates its previously
reviewed mandate-completeness wording.

The current 508 package/privacy/teaching checks have 505 passes, two installed
Marketplace-cache skips and the known dependency-checker argument failure.
The earlier development version-guard failure no longer occurs in this run;
remote current-head CI and publication checks remain outstanding. Both workflow
registry checks and all 44 Cowork package checks pass. Initial expanded commands
omitted the shared fixture or bundled Node path; the corrected commands used the
repository setup without production changes. Three additional workflow-test
assumptions were corrected only in tests: prototype exclusions, public benchmark
acquisition classification, and the construction CLI's indirect archive loader.
All 167 final workflow-boundary and public-catalogue checks pass after those
test-only corrections.

The integration evidence is retained alongside the recovered source in
`integration-package-verification.json` and the `valuation-integration-*.xml`
and `.log` records. Dependency-checker and breadcrumb corrections still await
owner approval. Public GitHub push was previously denied by automatic approval
review and has not been retried; the remote draft remains at its older head.
No merge to main, deployment, publication or enabled-host acceptance is claimed.

Local evidence on 29 September 2026:

- 292 valuation/acquisition/shared-transport regressions pass; component coverage is 94.12%. These exercise
  all seven methods, failure preservation, review/conclusion freshness, exact
  receipts, annual and selected-month plan replay, all 21 explicit purpose intake routes and real
  native lesson input runs. Purpose routing tests do not enable professional use.
- Dated DCF tests cover stub/monthly/mid-period flows, two day-count conventions,
  leap years, flat/spot/interval-forward curves, effective annual and continuous
  rates, horizon terminal discounting, invalid timing, review invalidation and
  rejection of monthly relabelling of annual plan flows.
- The monthly plan bridge selects only existing contiguous whole months, including
  partial years and leap-year month ends. It requires a separately evidenced
  opening working-capital amount at the preceding month end, exact monthly taxes,
  original plan replay and a dated FCFF method with the same ordered flows.
  The annual terminal flow stays separate; intramonth proration is unsupported.
  Report text and the formula workbook expose every monthly reconciliation.
  LibreOffice independently recalculated 255 calculation, bridge and linked-input
  cells across final monthly and annual examples, all within 1e-12 relative /
  1e-9 absolute tolerance. Each example's six DOCX and five native PDF pages were
  inspected. Evidence is retained in `monthly-plan-acceptance/final-workbook-verification.json`
  under the recovered-source output directory. Both fresh annual teaching reports
  retain 750,000 / 583,333.33 EUR equity indications and pending review.
- After rebuilding the monthly extension, all three extracted Vera package
  layouts replay both examples outside the repository. Their case hashes,
  monthly/annual bridges, method records and complete calculation registers
  match the source results exactly. Fourteen Python/schema/transport files per
  archive also match source bytes. Full three-product release alignment passes;
  77 privacy/teaching-review and 31 course-package/release checks pass. This is
  extracted-package evidence, not enabled-host or professional acceptance.
- The structured adjustment journal preserves reported values, signed changes,
  accounting/economic reasoning, tax/reversibility explanations and individual
  review dependencies. Missing or inconsistent values block dependent methods;
  unrelated method reviews survive. It does not classify accounting treatments
  or establish accounting classification or completeness. Separately supplied
  statement records now support the balance and movement checks below.
- Statement records preserve periods, declared perimeters/bases, independently
  supplied opening and closing amounts, signed movements and exact evidence.
  The helper reconciles assets with liabilities plus equity, all declared closing
  lines with their movements, and comparable prior closing/opening balances.
  Different periods, bases/perimeters, missing amounts and nonzero differences
  remain visible; dependent methods/sensitivities stop while unrelated branches
  survive. Adjustment formulas and separate statement reviews bind transitively.
  There is no automatic annualization, balancing plug or semantic classifier.
  LibreOffice independently reproduced 112 calculation cells and 24 linked
  `Quadrature` cells. All seven DOCX and six native PDF pages were inspected.
  Both fresh teaching cases retain their figures and partial status, explicitly
  stating that no statement checks were supplied; all four DOCX and three native
  PDF pages per teaching case were inspected. Evidence is retained in
  `outputs/vera-valuations-discord/statement-acceptance`. These are synthetic
  workpapers, not professional statement completeness or classification review.
  After rebuilding, all three Vera ZIP layouts contain sixteen byte-identical
  Python/schema/transport files. Each extracted compiler reproduces the complete
  statement report and both fresh teaching reports outside the repository,
  including their exact review states: nine case replays. Full source/package
  alignment passes for Vera 0.1.284, Clara 0.1.221 and Lucia 0.1.61. Evidence is
  in `statement-package-verification.json` and `statement-release-alignment.log`.
  The broader current package/privacy/teaching run has 504 passes, two skips
  (installed Marketplace cache unavailable) and two failures. All 108 focused
  privacy/teaching/release cases in that run pass. One failure is the already
  pending dependency-checker correction. The other is the uncommitted-source
  version guard comparing against the previous local development commit; this
  update retains the unpublished Vera 0.1.284 / component 0.1.0 candidate.
  Neither failure is waived. Final release-version selection and current-head CI
  remain required; committing work alone does not prove release acceptance.
- Explicit claim records bind narrative, selected evidence, full calculation
  dependency chains, exact numeric values/units and separate reviews. Invalid
  claims remain visible without changing valid calculations. The named JSON
  workpapers project the same report hash; the helper exports 18 artifacts and
  does not fabricate the host's model-data reports.
- Mypy passes for all thirteen scripts; Bandit reports no findings. Formatting and
  import-order checks pass.
- Structured mandate fields now preserve the commissioning party, distinct dates,
  expert activity, perspective, recipients, restrictions, competencies, conflicts
  and class-specific rights with their evidence. Missing values remain null and
  make the case partial. A separate current mandate attestation is required for
  conclusion/case acceptance and changes invalidate dependent reviews. A synthetic
  40% right does not scale the 750 EUR equity reference result. LibreOffice matches
  all 75 calculation cells; the workbook retains 19 readable mandate data rows.
  All six DOCX and five native PDF pages of this example were inspected. Both
  fresh teaching cases preserve their 750,000 / 583,333.33 EUR indications and 18
  artifacts, now with partial status because eight mandate fields are absent from
  the supplied note. All four DOCX and three native PDF pages per lesson output
  were inspected. No real expert competence, independence or case approval is
  inferred. Evidence is in `outputs/vera-valuations-discord/mandate-acceptance`.
- After the mandate extension, all three rebuilt Vera package layouts contain
  fifteen byte-identical Python/schema/transport files. The extracted compilers
  replay the rights example and both partial teaching cases outside the
  repository with identical complete reports: nine successful case replays.
  All 108 focused privacy, teaching and package/release checks pass. Evidence is
  retained in `mandate-package-verification.json`; these checks do not establish
  installed-host acceptance or replace the outstanding release gates.
- The bundled JSON Schema validates the case envelope before nested-source reads
  and individual selected-method payloads inside partial-workpaper diagnostics.
- The versioned NYU country-risk HTML adapter follows observed links, preserves
  original bytes/terms/release metadata and exact percent conversion, and binds
  imported records to parser replay. Synthetic revised-release tests preserve
  earlier snapshots, reject look-ahead and invalidate only dependent reviews.
  Public-host/DNS/redirect, MIME, size, archive/office rejection, missing values,
  parser drift, reuse decisions and visible source failures are covered. The live
  NYU run retrieved three documents but retained an unknown observation date;
  it is not a professionally adopted benchmark or proof of other source adapters.
- All five DOCX and four native PDF pages of the synthetic acquisition-bound
  report were inspected, including source paths and the separate public-network
  disclosure. Both fresh native teaching reports retain their expected values,
  18 artifacts, development-only purpose coverage and pending review.
- LibreOffice independently recalculated all 75 cells of the seven-method
  calculation register and matched the engine within floating-point tolerance.
- It also recalculated three dated-model workbooks (300 calculation cells) and
  matched the Decimal ledger at 1e-12 relative/1e-9 absolute tolerance. Evidence is
  retained in `outputs/vera-valuations-discord/dated-acceptance/workbook-verification.json`.
- All five final dated-report DOCX pages were inspected. The timing schedule uses
  Italian convention labels and six-place displayed factors; exact values remain
  in the formula register. Both fresh annual teaching examples retain their
  expected results and pending professional review. The corresponding teaching
  record preserves earlier evidence hashes and binds the newly inspected files.
- LibreOffice also recalculated all 82 cells in the normalization workbook,
  preserving the independent 90 +20 -10 =100 reconciliation and linked method
  formulas. All six pages of its DOCX were inspected. The complete 124-test run
  includes absent adjustment values and untrusted-prose export checks.
- The claim example's 75 calculation cells and linked 750 EUR claim value agree
  after LibreOffice recalculation. All five DOCX and four native PDF pages were
  inspected. The current 140-test run adds numeric mismatch, unavailable support,
  stale claim/conclusion review, normalization-tax dependency and conditional
  scenario cases. Semantic support and human approval are not inferred from tests.
- All five current rendered DOCX pages were inspected after adding purpose
  availability. The HTML function page was
  inspected in the browser in Italian and English. Public copy exists in five
  languages and states that generated reports currently use Italian.
- The earlier Vera 0.1.278 candidate built for Codex, ChatGPT upload and Cowork; packaged MCP startup
  initializes all 18 configured servers. Exact source/package parity passed
  again after the dated-DCF extension, including all three products' projections.
- Upstream merger foundation `bbc94c37a` is now integrated without changing its
  execution source. Both functions are retained in the combined registries,
  router and 37-function public catalogue. The new candidate is 0.1.284, above
  the inspected 0.1.279 main version and other open candidates through 0.1.283.
  Geneva dispositions for both additions remain unresolved. This version is a
  build candidate, not a claim of Marketplace publication.
- All three 0.1.284 Vera ZIP layouts include the acquisition helper and its
  shared HTTP transport. Fourteen Python/schema source files in each were
  checked byte-for-byte, and the extracted helper ran in a separate directory
  with a reference-only request, correctly preserving status without network
  reads. The full product release alignment check passes for Vera, Clara and
  Lucia. This is package execution evidence, not enabled-installation acceptance.
- Reviewed service-source changes from integration consist of the combined
  router/catalogues, new valuation lesson, version identity and source inventory.
  Existing DATEV, runtime, feedback, update and receipt execution code is
  unchanged. Their privacy fingerprints are refreshed for those exact changes.
- The dated source delta adds local formulas and timing metadata, without a new
  network call or external recipient. Vera and Clara privacy registers validate
  after reviewing the affected valuation, teaching and shared page sources; all
  41 focused Vera/Clara privacy tests pass.
- The shared workflow ID addition changes source fingerprints in existing
  lessons. Their content and input records were compared with origin/main and
  are identical; the recorded refresh covers that registry change only.
- Clara's `learn-with-clara` and `research-video-voice` records were refreshed
  after reviewing their governed-source diff against `6f26f0e8241a0fe3027c162e2c2cae4d97395465`.
  The changes add Vera valuation copy, synthetic teaching material and catalogue
  entries, and update shared lesson fingerprints. Clara teaching/narration
  execution, payloads, recipients and retention behavior are unchanged. The
  complete Clara privacy register validates and all 13 focused tests pass.
- Lucia's `apertura-pratica` privacy fingerprint also includes the shared Studio
  Archive MCP source. Its only changed governed line adds `business-valuation`
  to the workflow enum. No legal-matter payload, access, retention or external
  boundary changed; the reviewed fingerprint was refreshed for that addition.
  All 26 Lucia plugin tests pass locally.
- The new Italian lesson ships fictional mandate notes and a separate 12% rate
  revision, not a preapproved case or precomputed result. Native demo/practice
  runs produce respectively 750,000 and 583,333.33 EUR equity indications and
  retain review-pending status. No live learner, voice or installed-plugin
  acceptance is claimed.

The publisher page under the Mparanza organization displayed only “Untitled
Plugin / No versions yet” during this run. Vera's existing Marketplace listing
and Published version were unavailable; no upload or publication occurred.
Merge, deployment and installed-session acceptance remain separate steps.

Release checks exposed two integration gaps: the new dependency helper does not
yet accept the standard `--requirements` option or enforce declared version
ranges, and the valuation page lacks its work-area breadcrumb mapping. Concrete
corrections are prepared and user approval requested under the repository's
instruction to stop before production changes prompted by a failed test. Do not
treat these pending checks as release acceptance.

The broader page suite also fails its shared typography assertion on the existing
`browser-automation` page. The identical failure was reproduced against untouched
base commit `6f26f0e8241a0fe3027c162e2c2cae4d97395465` using a temporary tracked-source
snapshot; no unrelated production page was changed. In the current focused
privacy/Lucia/page run, 94 tests pass and these two page assertions fail. Both
complete privacy-register validators pass. A package build is not a green full
release gate.

The earlier schema commit's teaching CI finished with 1325 passes, three skips
and three failures caused by stale expected course counts (32/143 instead of
33/144 after adding the Italian valuation lesson). Only test expectations were
updated. All ten affected archive/course checks pass locally, including the
actual preparation of every Vera Cowork lesson and language. Current-head CI
must still run after the next authorized public PR update.
