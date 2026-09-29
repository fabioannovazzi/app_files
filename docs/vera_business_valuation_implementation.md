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
PMI valuation workpapers. The supported methods are FCFF and FCFE DCF, constant
equity income, adjusted NAV, constant-capital mixed income, selected multiples,
and APV composition. Method selection, source relevance, normalizations,
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
Specialist methods, rights waterfalls, crisis distributions and legal-purpose
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

Local evidence on 29 September 2026:

- 235 valuation/acquisition/shared-transport regressions pass; component coverage is 93.35%. These exercise
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
  or establish a full statement balance or roll-forward.
- Explicit claim records bind narrative, selected evidence, full calculation
  dependency chains, exact numeric values/units and separate reviews. Invalid
  claims remain visible without changing valid calculations. The named JSON
  workpapers project the same report hash; the helper exports 18 artifacts and
  does not fabricate the host's model-data reports.
- Mypy passes for all eleven scripts; Bandit reports no findings. Formatting and
  import-order checks pass.
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
