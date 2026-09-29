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

- 124 valuation regressions pass; component coverage is 93.47%. These exercise
  all seven methods, failure preservation, review/conclusion freshness, exact
  receipts, full-year plan replay, all 21 explicit purpose intake routes and real
  native lesson input runs. Purpose routing tests do not enable professional use.
- Dated DCF tests cover stub/monthly/mid-period flows, two day-count conventions,
  leap years, flat/spot/interval-forward curves, effective annual and continuous
  rates, horizon terminal discounting, invalid timing, review invalidation and
  rejection of monthly relabelling of annual plan flows.
- The structured adjustment journal preserves reported values, signed changes,
  accounting/economic reasoning, tax/reversibility explanations and individual
  review dependencies. Missing or inconsistent values block dependent methods;
  unrelated method reviews survive. It does not classify accounting treatments
  or establish a full statement balance or roll-forward.
- Mypy passes for all seven scripts; Bandit reports no findings. Formatting and
  import-order checks pass.
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
- All five current rendered DOCX pages were inspected after adding purpose
  availability. The HTML function page was
  inspected in the browser in Italian and English. Public copy exists in five
  languages and states that generated reports currently use Italian.
- Vera 0.1.278 builds for Codex, ChatGPT upload and Cowork; packaged MCP startup
  initializes all 18 configured servers. Exact source/package parity passed
  again after the dated-DCF extension, including all three products' projections.
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
