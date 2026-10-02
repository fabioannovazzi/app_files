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
three agreeing studios. No central promotion mechanism is implemented here.

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
4. Authenticated professional approval bound to exact case, front page, results,
   reviewed anomalies and current source bytes before any real XML export.
5. Importer acceptance on at least two selected accounting/submission systems
   and checks with the current Agenzia Entrate control software. No tax return
   may be sent merely to test this implementation.
6. Native Codex/Cowork workflow acceptance, including the readable privacy
   disclosure and resumed case corrections. Installed-package behavior is not
   established by source tests or ZIP parity.

The prototype's 26 scenarios are requirements evidence, not an inherited test
certificate. New automated tests use wholly synthetic evidence and independent
expected figures; professional scenarios retain their actual pending status.
