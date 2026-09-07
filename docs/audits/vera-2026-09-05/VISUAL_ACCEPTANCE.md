# Retained report visual checks

These checks cover selected synthetic pipeline outputs, not all report formats
or independent professional acceptance. Temporary artifacts and previews are in
`/private/tmp/vera-remediation-01a07083/`.

## Report Builder spreadsheet

The actual generated `report_tables.xlsx` from
`retained-report-runs/test_plugin_inspects_and_build0/out/report/` was imported
read-only with the bundled spreadsheet renderer. Its summary sheet clips
section names, assigned-table references and headers at the exported default
column widths. Source inspection confirms that `write_tables_workbook` writes
cells without setting column widths or wrapping in the original revision.

A candidate generator change sizes columns, wraps long values, sizes rows and
distinguishes headers with readable typography. All five candidate sheets were
rendered and visually inspected. A separate cell comparison confirms preservation
of all 83 values, data types, number formats and coordinates. The candidate is
retained in `workbook-review/workbook-layout.patch` and has now been incorporated
into canonical source. All **150 Report Builder tests pass** in the verified
validation snapshot, including generation, replay and exact output closure.
Evidence: `report-builder-visual-snapshot.xml` and its companion log.

The component is now 0.1.36 and its privacy binding has been reviewed and refreshed.
Affected package variants have been rebuilt; all nine stable-snapshot package drift checks pass. Literal-string handling and the
existing numeric-evidence authority rules remain unchanged.

## Report Builder document

The same synthetic run's `report.docx` was rendered with the bundled Documents
renderer and bundled headless LibreOffice. All three pages were inspected.
The source tables, missing-section notices and audit appendix are legible; no
clipping or broken tables were observed. This validates this retained document's
layout under that renderer, not native Word behavior or professional conclusions.

## Centrale Rischi and excluded inputs

The generated `analysis.xlsx` from
`retained-report-runs/test_renderers_create_reviewab0/` was rendered and its first
sheet inspected. Amounts, metric labels and unavailable-value explanations are
legible in the inspected range; technical metric IDs wrap. A subsequent all-sheet review is recorded below; larger cases remain unqualified.

The neighboring `cr.xlsx` and Management Control's `management.xlsx` are input
fixtures, not generated deliverables. Their plain layouts are excluded from the
output-quality finding. The previously blocked HTML browser opening remains
unresolved; none of these checks reopened that HTML through another route.

## Packaged trend export correction

The fresh Clara 0.1.173 packaged runtime produced correct January/February
current values (405,000/426,000) and prior values (360,000/379,500), but its
2800×1800 PNG clipped the first title row and left excessive empty canvas.
The single-panel period-comparison trend export now renders at 2800×1080,
keeps the title and month labels within the image, and uses the normal chart
font size for the title. The zero-anchored scale and numerical marks are
unchanged. The corrected PNG was directly inspected and is retained at
`/private/tmp/vera-remediation-01a07083/trend-after/year_over_year_line.png`.

The fixed cached UniformChart direct-line reference was inspected for title
spacing and readable labels; it was not incorporated into generated outputs.
The gallery packet helper is unavailable because the generated gallery
manifest is absent. This is one-chart acceptance, not all reporting outputs or
actual Cowork agent acceptance. The corrected renderer postdates the first recorded ZIP. The subsequent
`clara-0173-final-runtime` run passes all 21 steps on the final candidate and
produces a PNG byte-identical to the visually inspected correction; the current
ZIP hash matches that final run.

## Centrale Rischi all-sheet review

All 18 sheets of the retained synthetic `analysis.xlsx` were imported read-only
and reviewed in 25 bounded rendered ranges, including all KPI rows and the full
width of the category/exposure tables. The populated tables are legible; numeric
and unavailable-value fields remain distinct. The exposure sheet deliberately
hides source-row/source-region metadata columns; the rendered omission matches
the saved hidden-column settings. No formula-error strings were found by the
renderer inspection API. These checks do not independently validate amounts or
professional conclusions.

Four empty-data sheets initially rendered their header fill without the labels.
A fresh process was used once per affected sheet. Garanti intestatario and
Richieste informazioni then rendered their labels; Debitori ceduti and Prospetto
sintetico remained blank. Both saved XLSX inspection and the artifact-tool public
`range.values` API report `Stato` and `Nessun dato disponibile` for all seven
empty-data sheets. Thus **16 sheets have readable previews and two have an
unresolved renderer failure**. The workbook and production generator were not
modified to compensate. No complete visual pass or native Excel behavior is
claimed.

Evidence: `workbook-review/cr-all/manifest.json`, the four fresh-process
manifests/previews, `review-result.json`, and `cr-empty-import-inspection.json` in
the temporary evidence directory. The result records the exact workbook SHA-256.
The initial blank previews are preserved rather than replaced by the successful
rerenders.

A native LibreOffice follow-up was attempted read-only against the same synthetic
workbook. The sandboxed `soffice --view` command returned 134 with no diagnostic
output; the subsequent native-app inspection reported that the Mac was locked
and automatic unlock failed. Manual unlock was requested. No native visual
result or workbook change is claimed, and neither blank preview is closed by
this attempt.

After the user confirmed unlock, native LibreOffice opened the exact retained
workbook. The KPI screenshot was readable, and keyboard navigation reached
Durata originaria. During subsequent sheet navigation, LibreOffice crashed and
displayed “LibreOffice 26.2 Document Recovery” for `analysis.xlsx`.
No recovery/discard action was taken. The two target sheets were not visually
verified. Evidence is under `workbook-review/native-unlocked/`; despite its
attempt-oriented filename, `debitori-final.png` depicts the recovery dialog,
not Debitori ceduti. Earlier `debitori*.png` screenshots depict KPI, not the
target sheet. Workbook SHA-256 after the attempt remains
`b18ac61bdfd4d718a09503e6f74cc39eff9ce923a7a9b3bea13f0ee120a63264`.

## Cold packaged reporting after release reconciliation

The actual full-date, USD cold-package trend and distribution PNGs were inspected
after the month parsing, currency, scatter hook and title integration. The trend
shows all three title lines, Jan/Feb/Mar, distinct current/prior lines and visible
110/130 endpoint labels without clipping. The distribution shows both periods,
the USD title, numeric axis and medians without clipping. The tiny three-row
populations per period do not qualify statistical inference.

Separate literal checks against the six synthetic source rows confirm current
sales 360, prior sales 330, delta 30, and monthly current/prior pairs 110/100,
120/110 and 130/120. Distribution means and medians are 110/120, sample standard
deviations 10/10, and ranges 100–120/110–130. These are mechanical checks of this
synthetic example, not independent professional acceptance or financial health
judgments. No model was called by these checks.

Evidence and exact inspected file hashes are in
`/private/tmp/vera-remediation-01a07083/reporting-release-integration/cold-numeric-visual-review.json`.
The retained output directories are under `remaining-cold-cases/`. Other chart
artifacts in that run require their own inspection; successful process exit or
HTML/PNG signatures alone do not establish visual acceptance.

### Scatter/bubble title clipping found by image inspection

The full-date scatter PNG and month-only bubble PNG both clip the first title
row at the top edge. Their process tests pass; those tests prove that rendering
completed, not that all text is readable. Both use `_write_legacy_figure` in
`plugins/scatter-bubble-analysis/scripts/legacy_scatter_bubble_charting.py`.
A scoped source correction positions the title 24 logical pixels below the
canvas top and uses the chart's existing base font size for title text. It does
not change chart data, axes, dimensions, marks or report claims. The four fresh renders and before/after comparisons below close this finding
for the tested single-panel cases.

The gallery packet helper could not run because the generated gallery manifest
is absent. The exact runtime PNGs and their data sidecars were used instead.
The reference manifest validates; cached UniformChart `scatter_bubbles_002.jpg`
and `bubbles_001.jpg` were inspected for title clearance, labels and axes. They
remain reference material and are not included in generated outputs.

Four fresh runs from the rebuilt Cowork ZIP now produce readable PNGs: scatter
and bubble, each with full dates/USD and month-only dates/no currency. All four
were directly inspected with their original `Synthetic Sales` title. Each title
row is inside the canvas, with the same visible text size as chart labels.
Chart-data, normalized-data and summary CSV rows match the pre-fix versions in
all four comparisons; row order is excluded from comparison.

The first restricted rerun retained HTML fallbacks: Kaleido reported that Chrome
closed immediately, and the screenshot fallback exited -6. Its exit-zero report
was not treated as a PNG visual pass. An approved headless-Chrome retry produced
PNGs, followed by an exact-input-filename run for direct title comparison. No
package source was patched after extraction, no undeclared packages were added,
and no model was called. The component tests pass: 25 passed, one optional skip.

Evidence: `reporting-release-integration/scatter-title-verification.json`,
`title-rerender-final/results.json`, `scatter-title-source-tests.xml`, and
`title-final-package-identities.json`. The full 12-case cold rendering matrix
passes across two batches (2 plus 10), predating this title-only delta. The four
fresh runs verify the changed scatter/bubble path; this does not claim every
chart variant or independent professional acceptance.

## Retained histogram review — 2026-09-06

Directly inspected remaining-cold-cases/test_cowork_zip_renders_throug3/output/
histogram.png and its histogram_chart_context.json / histogram_chart_data.csv.
The chart shows readable sales/USD and period labels, but no visible frequency
axis or count labels. With three observations per period, the overlay appears
as full-height adjoining gray rectangles; the reader cannot recover frequencies
from the image. This is an actionable reporting-readability gap, not a process
failure or proof of wrong source numbers. The sidecar preserves two histogram
traces with100/110/120 and110/120/130, matching the six CSV observations.
No title-clipping claim is made: the sidecar title itself begins with a blank
line and the two populated title lines are visible.

The gallery review helper still cannot create a packet because
runs/png_examples/png-gallery/manifest.json is absent. Used the exact retained
runtime PNG and sidecars; no gallery/reference image was substituted. Before a
renderer edit, inspect the fixed histogram references and current axis/binning
code, then verify a readable frequency scale and unchanged source populations.
This case is not visually accepted yet; no source change was made in this review.

Histogram source diagnosis refinement: draw_distribution.py sets both
histnorm='probability density' and barnorm='fraction', with overlay bars;
update_histogram_layout explicitly sets y-axis visible=False,
showticklabels=False and an empty title. Therefore the earlier phrase “missing
frequency scale” was too specific: no count/frequency interpretation has been
established. The verified defect is a hidden, unexplained normalized vertical
measure. Do not add count labels to this output without resolving its actual
normalization semantics. The full-height rectangles require checking the dual
normalization, not merely revealing ticks.

The fixed reference manifest validates. Its distribution family has no reference
example IDs, so there is no matching cached histogram example to inspect or use
as authority. No unlisted reference was substituted. Next verify Plotly's
normalization behavior against an unequal-count synthetic population, then choose
and test an explicit distribution measure without silently changing source data.

Candidate histogram correction implemented in the plugin's captured-figure path,
not legacy UI: removes the second cross-series barnorm normalization and exposes
the existing per-population probability-density axis. Cumulative histograms use
“Cumulative probability”. Axis label/tick sizes follow the chart's base font.
The correction runs before both context capture and rendering, preserving input
observations and histogram traces. Plotly primary references used:
https://plotly.com/python/histograms/ and
https://plotly.com/python/reference/layout/#layout-barnorm .

Distribution component regression suite passes (histogram-density-tests.xml/log).
This is candidate implementation, not visual closure: unequal-count render,
explicit density/cumulative assertions, retained-input comparison, visual review
and affected package rebuilding remain required before acceptance.

Two explicit public-pipeline regressions now pass for ordinary and cumulative
histograms. Unequal bin populations10/10/30 versus10/30/30 retain every
observation in the captured chart context, keep histnorm=probability density,
remove barnorm, expose ticks and the correct density/cumulative label, and use
the base font size. Initial assertion incorrectly treated Plotly binary-encoded
trace arrays as ordinary lists; corrected the test to inspect the pipeline's
decoded chart context, with no production change for that test failure.
Fresh image inspection and package reconciliation remain outstanding.

Fresh density and cumulative PNGs rendered through the corrected source path and
were directly inspected. Density shows the labeled0–0.035 scale and distinct
approximately0.0167/0.0333 heights; cumulative shows the labeled0–1 scale and
approximately1/3,2/3,1 levels. The authored distributions each contain three
observations in two20-unit bins. Axis titles/ticks are readable. This closes the
hidden-normalized-scale defect for these two examples, not every facet/variant.
Exact PNG hashes are in histogram-density-review/visual-review.json.

Sandbox Chrome initially exited immediately and retained HTML fallbacks. The
approved host-Chrome rerun produced actual PNGs; HTML success was not counted as
image verification. Render logs: histogram-density-render.log and
histogram-density-render-host.log. Source/package reconciliation remains pending.

## Variance product-grain ladder — 2026-09-06

Directly inspected actual1640x580 pvm_decomposition_ladder.png from
variance-source-current/test_variance_plugin_uses_bott0/variance. Three panels
show baseline300, decline50 and comparison250; rounded delta-17% agrees with
-50/300. The final panel assigns-50 to Units consistently with the independently
verified product-grain decomposition. Titles, amounts and panel labels are not
clipped. However title/panel text is visibly larger than row/value labels,
violating the project's single-visible-font-size reporting requirement.

Source route: variance-analysis/scripts/legacy_plotting.py,
write_pvm_decomposition_ladder_png -> draw_pvm_decomposition_ladder ->
_apply_ibcs_title -> _write_rendered_png. Diagnose both native and fallback font
settings before correction; do not alter the verified decomposition to fix
presentation. This image is not accepted as fully compliant yet. It is an actual
PNG from the retained run, not the test's mocked export-failure fixture.

### 2026-09-06 — Variance PVM ladder, numeric-year fixture

- Source: public `test_variance_plugin_uses_bottom_up_mix_for_coarser_reporting`,
  2023/2024, two products, sales300→250, product-grain units contribution-50.
- Native artifact: `/private/tmp/vera-remediation-01a07083/variance-native-spacing-fixed/test_variance_plugin_uses_bott0/variance/pvm_decomposition_ladder.png`.
- Direct visual review: title fully visible; white background; seven category
  rows and three panels present; totals300/250, contribution-50 and rounded
  percentage-17% readable. Single13px font set across visible text.
- Earlier native failure was hidden by successful Pillow fallback: percentage
  annotations used numeric-looking year strings as category coordinates. Fixed
  with explicit category type and final-row index. Native title moved inward;
  audit title-coordinate metadata follows the actual figure.
- PASS for this native example. This is not full locale, long-label, installed
  Cowork, or release qualification. Updated package verification remains pending.

### 2026-09-06 — Centrale Rischi synthetic gold HTML draft

Rendered the actual final HTML with host Chrome at1440px and390px widths;
retained full-page screenshots in `/private/tmp/vera-remediation-01a07083/centrale-gold-synthetic/html-{1440,390}.png`.
Desktop inspection shows draft status, missing financial-ratio reasons, six
observations, distinct populations and limitations. At390px the page has no
horizontal overflow; all nine680px-minimum tables scroll within their358px
containers. Actual scrollLeft reached322px, exposing rightmost columns. Clicked
the first evidence disclosure: its three metric references became visible and
wrapped within the viewport. Six evidence disclosures are present. Retained
`html-controls.json` and `mobile-controls.png` prove those interactions.
The long mobile screenshot alone cannot prove table coverage; the separate
scroll/disclosure check supplies that evidence. PASS for this HTML example's
layout and controls; no independent professional approval is implied.
