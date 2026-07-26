# Concordato full-population independent review commission

Status: ready to commission; not promotion evidence.

This packet commissions a qualified independent review of the complete
candidate population for the bounded EVIVA source family already recorded in
`representative-evaluation-log.md`. It does not ask the reviewer to endorse a
plan, provide legal advice, or certify audit-evidence sufficiency.

## Source basis

The review uses the separately published plan, attester's report, and judicial
commissioners' report identified in the evaluation log:

| Source | Pages | SHA-256 |
| --- | ---: | --- |
| Plan and proposal | 149 | `37bba99296d759e2e4fffb530e17ee300cc98c0d678edea5ef7a5bf5aff54cd2` |
| Attester's report | 229 | `3831bae9e42a0265dbf1f4a197c676e93e08d6329b47a6d795406d13733c4375` |
| Judicial commissioners' report | 364 | `c4ffeec6c03ccfa28395b26dfd3178f847df4e9ac28bb6220148bd1bce6b286b` |

The source PDFs and working papers remain outside the repository and
Marketplace package. Before review, the commissioner must independently
retrieve or transfer the files, verify all three hashes, and record custody and
rights treatment.

## Reviewer qualification and independence

The reviewer should be a qualified accountant or restructuring professional
with experience reading Italian concordato plans and supporting reports. The
commissioning record must state:

- professional qualification and relevant experience;
- relationship, compensation, and conflict disclosures;
- whether the reviewer participated in the prior three-page evaluation;
- whether the reviewer saw Clara/Vera outputs or the prior comparison table
  before sealing the independent workpaper; and
- the exact source files and instructions received.

The preferred design uses a reviewer who has not seen the prior selected-page
outcomes. If that is impossible, the limitation must be recorded and a
separately prepared workpaper must still be sealed before product comparison.

## Independent workpaper

Without access to product-generated candidate rows or matches, the reviewer
must prepare and seal a machine-readable full-population workpaper that:

1. assigns the source role of every document;
2. identifies every page and table considered relevant to plan amounts,
   historical support, assumptions, creditor classes, assets, liabilities,
   recoveries, distributions, and reconciliation totals;
3. records every in-scope monetary amount using exact canonical Decimal text,
   currency, sign or stated direction, source page, table or paragraph locator,
   row/column label, and surrounding semantic label;
4. records every excluded numeric token with an explicit exclusion reason;
5. distinguishes repeated display of the same amount from independent support;
6. distinguishes historical facts, plan assumptions, estimates, adjustments,
   and professional opinions without asking deterministic code to infer those
   categories;
7. identifies proposed cross-document comparison relationships and explains
   their semantic basis;
8. states exact formulas, units, scales, and tolerances for mechanical
   comparisons;
9. flags split-token, OCR, table-fragmentation, sign, unit, and locator
   uncertainties rather than silently repairing them; and
10. preserves all open items and unsupported relationships.

The workpaper must include its schema, a manifest of every file, and SHA-256
values for source files, extracted schedules, reviewer decisions, and the
sealed root.

## Product comparison

Only after the reviewer workpaper is sealed may the operator run the current
Concordato workflow on the same three exact sources.

The evaluator must compare:

- full candidate-population counts and exact amount values;
- page, table, row, column, and text locators;
- source-role and token-disposition coverage;
- duplicate and repeated-amount treatment;
- formulas, units, scales, signs, tolerances, and exact residuals;
- proposed and accepted relationship perimeters;
- unmatched and explicitly excluded populations;
- receipts, gates, replay, output closure, and native value addresses; and
- whether semantic review, reporting, publication, and `report_ready` remain
  withheld unless separately authorized.

The comparison must report false positives, false negatives, value errors,
locator errors, role/disposition disagreements, relationship disagreements,
and unsupported repairs separately. Aggregate equality cannot compensate for
an omitted or misclassified component.

## Acceptance rule

The full-population mechanical claim is `GO` only if:

- all source hashes match the commissioning record;
- the independent workpaper was sealed before product-output access;
- every in-scope reviewer amount is accounted for as matched, unmatched, or an
  explicitly adjudicated scope disagreement;
- every product candidate maps to a reviewer item or an explicitly adjudicated
  additional valid item;
- exact values, locators, units, signs, formulas, tolerances, and residuals
  agree;
- every unsupported extraction or ambiguous relationship remains withheld;
- source, preparation, reconciliation, output, and replay controls pass; and
- no legal, accounting, feasibility, fairness, or evidence-sufficiency
  conclusion is promoted from the mechanical comparison.

Any unresolved material discrepancy is `NO-GO`. A bounded selected-page pass
remains useful regression evidence but cannot substitute for this population.

## Commissioning record

Complete this table before source review:

| Field | Value |
| --- | --- |
| Commission identifier | pending |
| Commissioner | pending |
| Qualified reviewer | pending |
| Product operator | pending |
| Independent evaluator | pending |
| Qualification/conflict statement | pending |
| Source custody root | pending; do not commit |
| Verified source hashes | pending |
| Workpaper schema/version | pending |
| Review start time | pending |
| Product-output access time | pending |

