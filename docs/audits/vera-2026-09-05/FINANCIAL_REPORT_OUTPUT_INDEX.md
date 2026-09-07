# T16 source-to-normal-report index

Observed 6 September 2026. Read-only indexing: no source edits, tests, workflow executions or model reruns. Original T16 card requires source-backed totals/claims, explicit unavailability and readable normal formats across six workflows; it does not require every dimension in every workflow.

Exact physical source/output paths and current SHA256 values for26 retained cases are in [financial-report-output-identities.json](/private/tmp/vera-remediation-01a07083/financial-report-output-identities.json). Its receipt_checks separately compares recorded implementation hashes with current source and retained output hashes with receipts. A computed present-day artifact hash is an identity, not new execution evidence. E below is exactly `/private/tmp/vera-remediation-01a07083`.

## Current delivery follow-up

Sales now has an Italian reader-facing supplement:
`/private/tmp/vera-remediation-01a07083/sales-reader-delivery/codex_run_review_it.md`.
It links both normal CSV/JSON packages and explains sparse months, missing
discount propagation, usable Germany subtotals and the unapproved prospective
assumptions. Its exact source hashes and direct numeric/blank checks are retained
beside it; sealed source outputs are unchanged. This is a newly authored
post-run review supplement, not an artifact retroactively added to a sealed run
or a claim that the original run produced that prose.

The Report Builder numeric gap identified below now has a fresh managed run
`run_c42cafb3a053527737b9ea87`: 28 artifacts sealed/completed; 19 old output files
unchanged. Public numeric review records eleven source-cell dispositions;
aggregates 380/350/2000/200 are independently verified in DOCX, Markdown and
XLSX, with no subtotal double counting. Eleven source literals are verified in
bounded expansion packets. Preview tables remain redacted under the current
template, and six missing sections keep business review draft/pending. EUR is
explicitly defined in the new synthetic test sidecar, not inferred from the old
workbook. See `report-builder-numeric-current/REVIEW.md` and its exact receipts
under the external evidence root.

## Observed coverage and smallest gaps

| Workflow | Source to normal outputs and concrete claims | Original T16 applicability / smallest remaining gap |
|---|---|---|
| Financial Analysis | E/financial-pack-current-evidence/test_registered_pack_engines_r0/case: trial balance + reviewed COA mapping + fiscal controls → first/monthly_pnl.csv + reconciliation.json. Independent168 monthly values/70 controls pass. r1 facts/policy → working_capital_schedule.csv, discrete_cash_flow_schedule.csv, stock_flow_bridge.csv:5 stocks/4 quarters/5 bridges; residuals-298,-1827,3866,-1575 and annual166 stay unexplained. r2 extracted facts/controls → customer_concentration_summary.csv:16 values,2023 missing AR denominator unavailable, HHI explicitly incomplete. | Sign multipliers, fiscal aggregation, de-cumulation, totals/reconciliation and unavailable denominators have exact retained coverage. All3 receipt implementation sets match current source and output hashes match. These are prepared CSV/JSON with report_ready=false; no linked downstream professional narrative or rendered report is established. Do not invent a HTML obligation for preparation files, or treat arithmetic as issuer-filing authentication. |
| Report Builder | E/retained-report-runs/test_plugin_inspects_and_build0/report.xlsx → out/report/used_recipe.json → report_analysis.json/report_tables.json → report.docx, report_tables.xlsx, report_draft.md. Three table sections mapped; six sections explicitly missing. All three numeric sections await measure review and values are withheld. | Explicit missing sections and selected readable DOCX/corrected-XLSX layout are covered. This run cannot qualify numeric source-to-report amounts: the recipe contains no numeric measure decisions. See exact narrow gap below. |
| Sales Plan | E/sales-sparse-boundary/sources and E/sales-missing-discount-after/sources → context-location.json plan directories → sales_plan_scenario.csv, scenario_summary.csv, assumption_application_ledger.csv, reconciliation.json. Independent424 numeric/blank comparisons across both cases pass. Sparse periods2024-12/2025-03 map to2025-12/2026-03;6 rows, no invented period rows. Gross2804→2856.104; margin981.4→999.6364 in complete case. Missing discount propagates unavailable net/margin; Germany net760/margin280 remains usable. | Noncontiguous/fiscal-year periods, FX, scenario lineage, missing data and total reconciliation covered. Natural contract is CSV/JSON, not HTML/PDF/XLSX. Smallest reader-facing gap is retained normal artifact-card/prose explaining blanks and sparse months; reviewed note explicitly found none. Complete sparse run predates one engine-file change; missing-discount run matches all4 current implementation hashes. Retained outputs match receipts. |
| Variance | E/variance-native-spacing-fixed/test_variance_plugin_uses_bott0/sales.csv + recipe.json → variance/variance_results.csv/XLSX, summary and pvm_decomposition_ladder.png. Four source rows sales300→250, product volume effects+50/-100,total-50; unchanged aggregate units20. E/variance-nonfinite-normal: source controls10/20 versus calculated300/330 produce blocked tie-out despite component residual0. | Exact negative changes, grain-dependent reconciliation and invalid/nonfinite tolerance cannot be mistaken for healthy source tie-out. Selected native ladder visually passed in VISUAL_ACCEPTANCE.md. No causal explanation or every locale/long-label variant is inferred. A broader semantic/root-cause professional report is not established by the decomposition. |
| Management Control | E/management-acceptance-current covers blank/empty, uncached formula,NaN/Infinity rejection, zero-revenue costs770/margin-770 with undefined ratios, competing same-day bank balances unavailable in either order,51-service completeness. New E/management-delivery-current/synthetic.xlsx → state.json output directory contains20 declared/sealed artifacts and normal final HTML/Markdown/XLSX. All51 services: revenue5100,cost1020,margin4080; GL revenue2400,EBITDA1000,budget variance130,AR overdue400,cash1700. | Original T01 amount/denominator/order/truncation boundaries have public normal-output evidence. New delivery closes earlier cancelled-fixture lifecycle gap without rewriting it; technical run completed while report stays draft_pending_professional_review. Commentary admits independent Sales/GL fixtures do not reconcile. HTML browser rendering blocked; local content/XLSX structure checked. Do not reopen arithmetic as missing because native rendering is absent. |
| Business Planning | E/resumed-business-after/{baseline,missing-scenario,thin-margin} and E/business-remaining-boundaries/{startup-no-history,zero-denominators,unsupported-benchmark}, E/business-missing-opening/established-missing-opening: each execution-evidence.json identifies receipted source root and normal plan HTML/JSON/calculationCSV. Baseline EBITDA-100/-300, funding330/930,residual60/430. Thin margin15/1.5%,no base funding gap; stale conclusions withheld in blocked report. Missing February repayment withholds base but preserves downside. Startup no history invents no statements. Zero ratios null;54 comparisons pass. Unsupported typed benchmark withheld. Missing opening positionsnull: funding/cash unavailable, separate commercial revenue1000/contribution4/result-100/break-even125units survives. | Original T14 startup/established/thin-margin/negative-cash/missing-opening/missing-scenario/zero-denominator/conflicting-claims/unsupported-benchmark cases now have normal outputs. Four newest boundary runs complete technically with honest partial report status and disclosures. Typed benchmark gate is not semantic detection of disguised benchmark prose. HTML text was inspected, not browser/PDF layout. Source drift limits below prevent blanket same-source claims. |

## Report Builder: exact remaining numerical delivery gap

Input: `/private/tmp/vera-remediation-01a07083/retained-report-runs/test_plugin_inspects_and_build0/report.xlsx`, SHA256 `58c7120499ee09b50e788ed7b633e9abc3fbc1922b6998c79fb4ad6cf81a5f58` (also bound in source_index.json).

Mapping: `/private/tmp/vera-remediation-01a07083/retained-report-runs/test_plugin_inspects_and_build0/out/report/used_recipe.json`.

Normal report: `/private/tmp/vera-remediation-01a07083/retained-report-runs/test_plugin_inspects_and_build0/out/report/report.docx`; adjacent report_draft.md, report_tables.xlsx, report_analysis.json and report_audit.json preserve exact state. Each section has numeric_measure_columns=[] and numeric_measure_decision=null, while Actual/Budget/Amount are candidates. This explains numeric_measure_pending_section_count=3; no parser failure is inferred. Numeric source cells are replaced by `[numeric source value withheld]` in the report. Therefore a readable document is not reviewed numeric-output acceptance.

Direct source-cell inspection gives the smallest available synthetic check:

| Source sheet | Values and independent identity |
|---|---|
| Income Statement | Revenue Actual1000/Budget950; Costs-620/-600; Result380/350.1000-620=380 and950-600=350. |
| Balance Sheet | Assets2000,Equity900,Debt1100;900+1100=2000. |
| Cash Flow | Operating250,Investing-50; supplied two-line net200. This is not a complete statutory cash-flow reconciliation. |

These known synthetic columns and explicit table labels can support a bounded technical numeric-role review, without asserting professional approval. The next concrete evidence would be a normal report retaining those amounts after the actual reviewed numeric-measure workflow. Do not fabricate an existing decision, promote source captions into professional verification, or mutate the old sealed output. The existing recipe prose says “Revenue and result were reviewed” although measure roles remain pending; that authored sentence is not evidence that numeric review occurred.

Visual evidence is separately scoped: VISUAL_ACCEPTANCE.md records three readable DOCX pages, original XLSX clipping, and five corrected candidate sheets preserving all83 cells. The corrected candidate is E/workbook-review/report_tables.candidate.xlsx. It does not itself close the numeric-review gap or prove a new managed full run.

## Original dimensions without a false Cartesian requirement

- Numeric interpretation: Financial P&L explicitly reviewed mapping multipliers; Management rejects invalid/formula/nonfinite inputs. Sales invalid-input receipts are available separately. Numeric locale/formula acceptance is not asserted for every workflow; select any further case only where the workflow's accepted input contract makes it relevant.
- Periods: Financial fiscal-control aggregation and working-capital de-cumulation; Sales sparse cross-year mapping. No need to require a second identical fiscal test in workflows without that period transformation.
- Denominators/missing data: Financial AR coverage; Sales missing discount; Management zero-sales margins/bank conflicts; Business zero ratios/opening/scenario inputs. These are specific abstentions with preserved usable sections, not successful-zero substitutes.
- Totals/claims: Financial168+70 and16 calculations, Sales424 comparisons, Variance product-grain-50, Management51 identities and fixed totals, Business scenario-month comparisons. Original review scripts and receipts document independent exact arithmetic; this index does not rerun them or convert model agreement into an oracle.
- Truncation/readability: Management51 identities retained across all normal formats; Sales all6 scenario/36 summary rows retained; Report Builder numbers deliberately withheld pending review, not truncated; selected Variance PNG and Report Builder DOCX/candidateXLSX visually inspected historically. Browser blocks on Management/Business remain visual limits, not general arithmetic failures.

## Identity and current-source limits

The companion identities file hashes exact26 case source/output inventories and checks receipts where available. Financial3/3 implementation sets and all declared outputs agree. Sales missing-discount4/4 agree; sparse run differs only in prepare_sales_plan_case.py, with all declared outputs intact. Business baseline/missing-scenario/thin-margin differ in planning_presentation.py and planning_commercial.py; newer four boundaries differ only in planning_commercial.py. Retained planning_commercial SHA256 is d6ffb83add0e3745c23adf448d2a1865174d381f56315a9b9d57672b6684c625; current is9e8b11895aec6cdb554dd4e870d7e550da8000bbf1f472ebdc7b44c170e5e4f1. The retained review identifies the presentation binding correction and missing-opening wording follow-up; these differences require source-delta scoping, not silent current-hash certification and not automatically rerunning every case.

Management delivery source hashes and terminal lifecycle are retained in its source_hashes.json/lifecycle.json. Earlier cancelled arithmetic fixtures remain honestly cancelled. Business restricted-network failures in execution-evidence are historical first attempts; normal outputs/finalization/terminal-state document authorized retries. Do not treat the stale first exit code as absence of the retained final report.

No newly reproduced production defect was found by this index. The smallest clear completion gaps are reviewed numeric Report Builder delivery, the Sales normal reader-facing explanation, and actual rendered acceptance for the already-generated Management/Business HTML where required. Financial downstream narrative and Variance professional root-cause interpretation remain separate from their established preparation/decomposition output contracts. Independent professional judgment, issuer truth and installed-host qualification are not replaced by any arithmetic, hash or layout check.

## Current compiler reconciliation of seven Business Planning cases

Re-executed the current public build_plan and compile_html functions using seven
retained synthetic cases and their original source roots. This is a compiler
replay into a separate directory, not a new managed run, review approval or
browser rendering. Original sealed artifacts are unchanged.

Six plans compare exactly at every JSON field and their HTML is byte-identical:
baseline, missing-scenario, thin-margin, startup-no-history, zero-denominators
and unsupported-benchmark. The established-missing-opening case differs only
in two calculation formula labels (Accepted becomes Supplied) and the two
resulting content hashes. All values, nulls, statuses, claims and lineage remain
identical. Its HTML matches exactly after substituting those four recorded
plan differences. The initial label-only equality check correctly failed because
the HTML also carries a changed hash; the full exact comparison includes it.

Recovered prior planning_commercial.py by its exact recorded SHA256 from a
retained package. Its diff contains only those two label edits. No exact older
planning_presentation.py was found in the searched retained .py files; current
public compilation establishes behavior on these seven cases without claiming
whole-module equivalence. The initial compiler import command omitted the
shared assurance path; corrected source-path setup succeeded without modifying
production imports.

Evidence under /private/tmp/vera-remediation-01a07083:
business-current-source-reconciliation.json, business-commercial-retained-delta.diff,
business-current-replay/comparison.json and html-comparison.json. This resolves
the earlier source-delta uncertainty for these exact cases. Native HTML
readability remains unverified.

## Current sparse Sales Plan source reconciliation

Recovered prepare_sales_plan_case.py with the exact engine SHA256 in the old
sparse-period receipt (7dbf2ad57ea649f1726302a48033dc0f65d5b30f449466786e17e0ba7e7ae4a3).
The delta is the separately verified missing-metric correction: unavailable
discount no longer becomes zero; dependent totals stay unavailable and warnings
identify missing source metrics.

Executed the current public prepare_sales_plan_case API on the retained
synthetic source case into a new external output directory. Status is passed.
The sales_plan_scenario.csv, scenario_summary.csv and assumption_application_ledger.csv
are each byte-identical to their retained sparse-run versions. This preserves
the six scenario rows, sparse-month mapping and prior independently checked
amounts through the current engine. It is preparation API evidence, not a new
managed lifecycle or professional forecast approval. Original inputs and sealed
outputs are unchanged.

Evidence: sales-sparse-current-source.diff and
sales-sparse-current-replay/retained-comparison.json under
/private/tmp/vera-remediation-01a07083. The separate missing-discount managed run
already exercises the new unavailable-value behavior; no duplicate rerun was
needed for that unchanged current source.
