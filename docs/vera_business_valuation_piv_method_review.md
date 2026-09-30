# PIV company-method review — local engineering record

Inspected 30 September 2026 against code
`b463ddedfb5348f372f38b9af986ab1bf116b2ad`. Reviewer: **unassigned**.
Status: **candidate interpretation; no professional approval or activation**.

This record connects a focused primary-source reading to observed implementation.
It is not a substitute for the standards or a completed PIV conformity review.
The source/edition boundary is in [the research log](vera_business_valuation_piv_research.md).

## Reading evidence

The [Principles](https://www.sfogliami.it/fl/331518/bg1gy2s9by8gvfb8613s32r1pt7k2q9)
were consulted at printed pp. 73–90, including all III.1.1–III.1.57. I.4.4–I.4.10
and I.5.4–I.5.11 were reread at pp. 34–35 and 37–38. The
[Rationale](https://www.sfogliami.it/fl/331519/cs65n8uchbdr71syt4q2ygz3vesmmh)
was consulted at printed pp. 1, 15–19 and 100–109. Its discussion of I.5.9 and
III.1.43 continues beyond those ranges and has not been read completely here.
Viewer page numbers differ from printed pagination; references use the latter.
No source-volume files or page images are included in this repository.

The Rationale is explanatory. The wording observations below concern the named
Principles individually. A reference containing both obligations and suggestions
is not treated as one mandatory checklist. Interpretation and applicability remain
for the responsible professional to review.

## Reference-to-implementation decisions

| Review ID / primary anchor | Reading observation to confirm professionally | Observed code and remaining decision |
| --- | --- | --- |
| RV-A — I.5.8, p. 38; Rationale I.5.8, p. 19 | The four assumption characteristics are not a single exclusive classification. Materiality and susceptibility to future change are different questions. | Inputs have only `fact`, `assumption`, `hypothesis`. Claims add `opinion`; neither is a record of the four characteristics. Preserve explicit judgments and their reasons/evidence; do not infer them from input names, numerical sensitivity or the existing `kind`. |
| RV-L — I.4.4–I.4.7, pp. 34–35 | Mandate restrictions, objective constraints and legally imposed limitations have different contexts. I.4.7 addresses their possible effect; it does not make software capable of measuring every effect. | Case/method limitations are text lists. A reviewer can describe these matters in text today, but their origin and effect are not separately recorded or bound. Any extension must preserve unknown effects and the professional decision; a populated record cannot establish conformity. |
| RV-F — III.1.16, p. 78; III.1.20–III.1.21, pp. 79–81 | III.1.16 combines an overall professional judgment with suggested considerations. Forecast foundation and scenario conditioning are distinct axes; flow/rate risk consistency needs interpretation. | The upstream plan is replayed and explicit assumptions/claims are retained. No dedicated two-axis forecast characterization or expected-flow/rate coherence assessment exists. Never turn a scenario label automatically into a rate premium, probability or accepted forecast. |
| RV-H — III.1.36–III.1.37, p. 84 | Horizon and cyclical behavior require a reasoned assessment. Changing the number of forecast periods must not serve as an unexplained source of value. | Dated DCF verifies dates and conventions. Whole-month plan selection verifies lineage. Neither establishes that the chosen horizon reaches an economically sustainable state. Record a case-specific explanation and compare revised cases when the horizon changes. |
| RV-T — III.1.38, p. 84; Rationale III.1.37–III.1.38, pp. 102–105 | The Principle mixes mandatory cautions, recommended estimation work and an optional market comparison. Sustainable terminal assumptions require analysis; a cross-check is not an instruction to average conflicting estimates. | DCF takes terminal next flow independently and checks the rate/growth denominator. It does not estimate that flow or automatically grow the last forecast. A dedicated terminal-basis record and evidence of reinvestment, growth and risk coherence are missing; generic rationale can carry text but does not force those decisions to be explicit. |
| RV-C — III.1.40–III.1.41, p. 85; Rationale III.1.39–III.1.41, pp. 105–109 | Sample construction, measurement context and differences between quoted prices and transaction prices require explanation. The different price contexts cannot silently be treated as equivalent evidence. | The workpaper preserves the initial universe, inclusions/exclusions and reconciliations. It has no dedicated observation-type, transferred-rights, transaction-premium or related-party context. These can be discussed in existing explanations; that is not evidence that a user actually addressed them. |
| RV-P — III.1.42, pp. 85–86; Rationale III.1.42, p. 109 | Target positioning and dispersion need analysis; regression is an available technique, not a compulsory model. | Each peer ratio is calculated while the applied multiple is supplied separately. No automatic mean, trim or range is selected. Add explicit reasoning where necessary; do not add an automatic peer-ranking or statistical acceptance threshold merely to fill this gap. |
| RV-S — III.1.43, p. 86; Rationale III.1.43, p. 109, partial | The synthesis requires a reasoned conclusion. Reading the beginning of the commentary does not complete its interpretation. | The conclusion has separate source/method dependencies and review. Those mechanisms retain the decision; they do not establish the quality of its economic reasoning. Complete the commentary and review an actual conclusion. |

## Inspected code and tests

The following assertions were inspected, not rerun for this documentation change.
They prove bounded software behavior, not the economic adequacy of a case.

| Area | Implementation | Existing test evidence / boundary |
| --- | --- | --- |
| Input classification | [`_inputs`](../plugins/business-valuation/scripts/valuation_case.py) and [`$defs.input`](../plugins/business-valuation/references/valuation-case.schema.json) allow the three input kinds, source IDs, a locator and proposed/confirmed status. | The inspected schema has no assumption-characteristics record; there is consequently no test proving one. Missing semantic classifications must not be represented as passing checks. |
| Terminal arithmetic and timing | [`calculate_method`](../plugins/business-valuation/scripts/valuation_engine.py), DCF branch, keeps the independent terminal amount and horizon factor. | [`test_invalid_terminal_growth_is_blocked`, `test_midperiod_cash_does_not_shift_terminal_value_to_midperiod`, `test_changed_timing_invalidates_only_its_method_review`](../tests/plugins/test_business_valuation.py) inspect denominator rejection, terminal timing and review expiry. None tests economic sustainability. |
| Comparable measurement | [`comparable_evidence`, `_reconcile`, `calculate_comparables`](../plugins/business-valuation/scripts/valuation_comparables.py). | [`test_peer_ratios_reconcile_without_selecting_the_applied_multiple`, `test_unaligned_peer_basis_or_lookahead_is_not_silently_used`, `test_missing_inconsistent_or_negative_peer_amount_blocks_only_that_method`](../tests/plugins/test_business_valuation_comparables.py) check explicit amounts, dates and basis labels; they cannot establish semantic comparability. |
| Comparable decisions | The same module retains excluded candidates and declared evidence. [`build_valuation`](../plugins/business-valuation/scripts/valuation_case.py) incorporates the workpaper into method dependencies. | [`test_unconfirmed_peer_decisions_or_evidence_keep_method_partial`, `test_changed_peer_dependency_expires_its_review_but_preserves_independent_method`](../tests/plugins/test_business_valuation_comparables.py) verify incomplete decisions and selective review expiry. Review state is a local attestation, not authenticated professional identity. |
| Existing explanation capacity | [Case contract](../plugins/business-valuation/references/case-contract.md): method rationale, input descriptions, source-bound claims and comparable explanations. | A dedicated field's absence does not mean the reasoning cannot be recorded today. Conversely, having free text does not prove that every issue was considered. Real-case review must inspect the actual content. |

## Proposed acceptance cases for subsequent implementation

These are engineering candidates, not implemented tests or an approved standards
interpretation. The core calculation remains usable for a supervised development
pilot while gaps stay explicit. The pilot must not claim professional activation.

1. **Assumptions and limitations (RV-A/RV-L).** Keep the existing input kind
   separate from characteristics; allow more than one characteristic and an
   explicitly unresolved judgment. A significant, stable tax assumption must not
   become sensitive solely because it moves the result. Record limitation origin,
   evidence, expected effect or why the effect is unknown. A changed explanation
   must expire dependent reviews even if amounts are unchanged. Do not classify
   a legally imposed restriction or its permissibility from keywords.
2. **Forecast context (RV-F).** Preserve separate judgments about the forecast's
   foundation and scenario conditions, plus plan approval/evidence and flow/rate
   reasoning. A conditional management scenario must not silently become a
   probability-weighted expected forecast. No rate change may occur merely because
   a label changes. Missing interpretation remains visible.
3. **Terminal basis (RV-H/RV-T).** Record evidence for terminal flow, reinvestment,
   growth, risk and horizon choice. A numerically valid high-growth case with an
   unresolved terminal rationale must not be described as economically qualified.
   Keep valid arithmetic visible and distinguish an unresolved review from a
   denominator error. Changed basis should expire the relevant method/conclusion
   reviews. Preserve one canonical record across JSON, HTML, Markdown, DOCX, PDF
   and workbook outputs, then inspect their actual rendering.
4. **Comparable price context (RV-C/RV-P).** Retain whether the observation comes
   from a quote or transaction and the evidence about its rights, perimeter and
   special conditions. Identical numerical ratios with different rights/premiums
   must remain separate observations; no automatic control-premium adjustment is
   justified. Preserve excluded peers, dispersion/positioning reasoning and the
   independently selected multiple. A context-only change must expire the
   relevant review without modifying the supplied ratio.

For each candidate the reviewer still needs to decide applicability, terminology,
acceptable evidence and whether a missing record blocks professional acceptance.
Presence, valid references, arithmetic and dependency invalidation can be checked
mechanically; semantic adequacy cannot be inferred from those checks. No threshold,
rule-based classifier or new compliance flag was added in this review.

## Outstanding release and acceptance boundary

The source map is partial. Rights-specific, intangible-specific, distress and
legal-purpose chapters still require their own reading and implementation review;
incidental references in the company chapter do not complete those topics.
All 21 purpose profiles remain development-only. The real SME source folder,
independent reference valuation and responsible reviewer are still unsupplied.
The [pilot protocol](vera_business_valuation_pilot.md) remains the next real-case
acceptance step. This local documentation increment does not change packages,
installed plugins, privacy data paths or numerical behavior. Publication is held
by the user's explicit instruction.
