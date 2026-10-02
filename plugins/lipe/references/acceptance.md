# LIPE acceptance register

Baseline: 2026-10-02. User-facing name: **LIPE**. Internal component: `lipe`.

## Observed requirements

The Discord channel `dai-registri-iva-alla-lipe` supplied
`Vera_LIPE_Developer_Pack_v0.1.0.zip` and a written review. The pack contains
aggregate examples from three real clients, provisional vendor codes and tax
rules, a small engine and an XML prototype. It contains no original registers.
Its 68 bundled tests passed locally. Its 26 professional acceptance scenarios
were recorded as NOT_RUN; they remain unexecuted professional UAT.

The goal is reconstructing the path from registers to VP figures, comparing
liquidations and payments, preserving code confirmations and preparing review
outputs. A central vendor-code promotion requires curator review, never merely
three agreeing studios. Central-reference entries remain local and require
attributed curator and disclosure reviews; no remote promotion service exists.

## Corrections established from official evidence

- VP3 uses the registration period; moving a deduction does not also move the
  taxable base. Instructions PDF pages 9–10.
- Deductibility is not necessarily 100%, including reverse charge. VP5 records
  the tax for which deduction is exercised. Instructions page 10.
- An unknown opening balance is not a confirmed zero. Unconfirmed codes and
  unreconciled source totals block calculation.
- VP14 reports the amount due, not the amount paid. A small debit is not carried
  again when already paid. No automatic carry into December or Q4 VP7.
- Quarterly by option and quarterly special periodicity differ. For ordinary
  option Q4, period 5 is used and VP11, VP12 and VP14 are absent. Instructions
  pages 9–11 and technical blocking specifications.
- A local reviewer string does not authenticate a professional. An approval
  cannot be inferred from the assistant setting a JSON field.
- The full official XSD bundle and complete W3C signature schema replace the
  supplied stub. Validation is required and offline. It does not prove importer
  or tax-authority acceptance.

## Implemented boundaries

Supported: ordinary VAT for 2024–2026, monthly or quarterly periodicity, complete
quarter coverage, confirmed case-scoped mappings, signed amounts/credit notes,
separate tax periods, partial deduction, reverse-charge mirrors, reviewed
opening balances and manual adjustments, payment differences, content-bound
revisions and source-text/PDF-page evidence. Text extraction requires visual
review. Real cases require Studio Archive identity and unchanged input receipts.
Case contract 1.3 also requires reviewed liquidation sections for each period.
Code-level comparisons preserve their explicit date and VAT-measure bases,
unmatched codes and unknown amounts. The three-tab Excel workpaper exposes
source contributions, VP formulas, carry steps, engine comparison and F24 checks.
The portable exporter uses the already-supported Python XlsxWriter library;
the desktop artifact-tool library is used for independent development validation,
not required in the installed Python runtime.

Structured semantic proposals now preserve invoice/protocol references, source
quotations, proposed VP6 effects and attributable local decisions. Changed facts
or proposals invalidate the matching decision; proposed effects are never
automatically added to VP. The per-client unsent draft follows the specification's
sections, keeps missing facts explicit and uses only source-backed recorded
deadlines. A paginated PDF summary retains the same draft/blocked status and
source references. These output checks do not authenticate reviewers or establish
the tax validity of their explanations.

The persistent local catalog now covers exact vendor/version lookup, client and
studio overrides, local central-reference entries, original-source preservation,
revision history, confidence policy, revocation and curator disputes. Bound case
mappings are rechecked at every validity boundary within the quarter. Catalog
classification, disclosure and reviewer roles remain attributed judgments, not
authenticated decisions or proof that a central source is free of private data.

First-pass measurements now preserve code populations and initial catalog/model
proposals per client/engagement/quarter. Repeated reads cannot reset an existing
unit; later professional responses retain history. Reports separate real and
synthetic cohorts, expose denominators and missing review, and leave empty rates
null. Literal class changes include textual edits and are not a measured tax-
error rate. No real recognition performance has been established.

The front-page contract checks ordinary identifiers and source-bound registry
review declarations. The approval adapter binds the case, sources, output files,
front page, result, runtime and run disclosure. It verifies external CMS signatures
under a host-configured firm policy and signed mandate, including chain and CRLs.
The policy needs independent host administration; certificate subjects do not
establish professional powers. Qualified-signature status is not tested. No real
studio has configured or accepted this path, and it does not enable XML export.

Development validation includes independent workbook recalculation and changed-
input checks for monthly values, partial reverse-charge deduction, credit and
small-debt carry, quarterly interest rounding and Q4 exclusions, plus visual
inspection of all three sheets. This is not native Excel, professional or
submission-system acceptance.

Unsupported features block a VP calculation: group/mixed VAT, extraordinary
operations, subcontracting, special determination methods, cross-year timing,
and unqualified tax interpretations. Quarterly option small-debit carry remains
blocked until the principal/interest basis is independently reviewed.

## Outstanding acceptance (not passed by unit tests)

1. Professional review of the current sources, implemented arithmetic and scope,
   including the basis for quarterly interest and manual VP9–11 adjustments.
2. Original Reviso/Mexal PDF and scan extraction tests, with source pages and
   totals independently verified. The channel ZIP does not contain these files.
3. Additional unseen cases, including period boundaries, partial deduction,
   pro-rata/special cases explicitly excluded, Q4/acconto and missing sections.
4. Live acceptance of the implemented source-bound front page and signed approval
   path with the actual studio authority, professional mandate and current CRLs.
   Synthetic cryptographic tests do not establish this real authority.
5. Importer acceptance on at least two selected accounting/submission systems
   and checks with the current Agenzia Entrate control software. No tax return
   may be sent merely to test this implementation.
6. Native Codex/Cowork workflow acceptance, including the readable privacy
   disclosure and resumed case corrections. Installed-package behavior is not
   established by source tests or ZIP parity.

## Remaining implementation from the developer specification

- Authenticated catalog roles and optional shared central-catalog distribution. Current central
  reference records are local and do not synchronize between studios.
- Real XML serialization with current approval re-verification and supplied-receipt
  processing. The front-page contract and external CMS/mandate approval adapter
  are implemented; the synthetic XML command is not the real export workflow.

These are engineering gaps, separate from the missing original-register and
professional acceptance evidence above. The overall goal remains in progress.

The prototype's 26 scenarios are requirements evidence, not an inherited test
certificate. New automated tests use wholly synthetic evidence and independent
expected figures; professional scenarios retain their actual pending status.
