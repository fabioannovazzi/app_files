# Vera business valuation implementation

Source: Francesco Giraldo's Valutazioni PMI v0.1.0 proposal, recovered from
https://discord.com/channels/1550191335917625474/1554383249646813294/1554533476928200749
on 29 September 2026. ZIP SHA-256:
`cf7ee90de4a3ae4d04682399c1b00cb217252db2ccd8daa33c038e044ef42d2d`.
All 52 manifest entries verified; 53 archive files retained without executing
the supplied launchers. Original attachments and conversation are retained in
the primary checkout's ignored `outputs/vera-valuations-discord` directory.

## Implementation contract

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

- 49 valuation regressions pass; component coverage is 91.05%. These exercise
  all seven methods, failure preservation, review/conclusion freshness, exact
  receipts, full-year plan replay and real native lesson input runs.
- Mypy passes for all six scripts; Bandit reports no findings. Formatting and
  import-order checks pass.
- LibreOffice independently recalculated all 75 cells of the seven-method
  calculation register and matched the engine within floating-point tolerance.
- All four rendered DOCX pages were inspected. The HTML function page was
  inspected in the browser in Italian and English. Public copy exists in five
  languages and states that generated reports currently use Italian.
- Vera 0.1.278 builds for Codex, ChatGPT upload and Cowork; packaged MCP startup
  initializes all 18 configured servers. Exact source/package parity passed
  again after the final partial-report robustness correction.
- The shared workflow ID addition changes source fingerprints in existing
  lessons. Their content and input records were compared with origin/main and
  are identical; the recorded refresh covers that registry change only.
- The new Italian lesson ships fictional mandate notes and a separate 12% rate
  revision, not a preapproved case or precomputed result. Native demo/practice
  runs produce respectively 750,000 and 583,333.33 EUR equity indications and
  retain review-pending status. No live learner, voice or installed-plugin
  acceptance is claimed.

The publisher page under the Mparanza organization displayed only “Untitled
Plugin / No versions yet” during this run. Vera's existing Marketplace listing
and Published version were unavailable; no upload or publication occurred.
Merge, deployment and installed-session acceptance remain separate steps.

One release check exposed a dependency-checker integration gap: the new helper
does not yet accept the standard `--requirements` option or enforce declared
version ranges. A concrete correction was prepared and user approval requested
under the repository's instruction to stop before production changes prompted
by a failed test. Do not treat this pending check as release acceptance.
