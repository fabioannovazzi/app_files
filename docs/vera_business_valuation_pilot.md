# Pilot: one ordinary SME valuation

Status: prepared, not executed on a real case. The owner authorized this focused
pilot on 30 September 2026. A local source folder, an existing independent
professional valuation and the responsible reviewer have been requested but not
supplied. The recovered developer pack contains synthetic examples only.

## Scope

Use one anonymized ordinary SME case with an existing professional valuation.
Confirm the actual purpose, perimeter, currency, valuation date and information
cutoff from those materials before selecting methods. Use the documents the
studio already has; do not require it to create an input template or technical
case file. Preserve missing information as an open question. The initial target
is internal valuation workpapers, subject to confirmation that the supplied case
fits that use; this does not activate a legal-purpose profile.

The engine can assist with calculations and traceable outputs. The pilot must
establish whether the normal assisted workflow is usable by the accountant and
whether its workpapers withstand that accountant's review. Existing synthetic
tests and agent-operated command-line runs do not establish either outcome.

## Execution

1. Record the actual enabled plugin version and the skill exposed in the test
   conversation. After an installation update, use a fresh conversation. Preserve
   the current candidate ZIP hash and selected source hashes with the pilot.
2. Import the selected documents into one authorized Studio Archive engagement.
   Inspect statements, adjustments, plans, debt/cash and mandate evidence; show
   the proposed extraction and missing decisions to the accountant. Do not fill
   gaps from the existing valuation's final amounts.
3. Prepare the first workpapers using the confirmed methods, sources and
   assumptions. Preserve that first result before opening the reference valuation
   for comparison; the reference is not a target to fit. Record all operator
   interventions, questions, corrections and elapsed working time.
4. Compare the first result with the reference on matching dates, perimeter,
   currency and value basis. Trace each difference to source data, transformation,
   method, professional assumption, rounding or software error. Record unresolved
   differences explicitly. The reviewer decides materiality and adequacy.
5. Have the accountant request one ordinary assumption change. Keep the prior
   revision, show changed amounts and ensure affected reviews expire. Reopen the
   saved report in a fresh conversation without rerunning the valuation.
6. Review the HTML, DOCX/PDF and workbook together, including source locators,
   formulas, value bridges, limitations and the readable model-data report.

## Acceptance evidence

| Question | Required evidence |
| --- | --- |
| Can the accountant complete the workflow? | Observed session with ordinary document inputs and instructions; no accountant-authored technical case file; interventions recorded |
| Are inputs and transformations supported? | Source locators and explicit confirmations; missing facts remain visible |
| Are amounts consistent and explainable? | Reference comparison with reconciled differences and cross-output checks; no threshold invented by the agent |
| Does an ordinary revision work? | Two retained revisions, affected-review invalidation and successful saved-report reopening |
| Are the workpapers professionally adequate for this purpose? | The named reviewer's explicit decision on the exact case revision, with unresolved issues and limitations |
| Does this save time? | Observed pilot time and a comparable studio baseline, if available; otherwise record the benefit as unmeasured |

A pilot passes only when the observed workflow and professional review support
that result. A case-level decision is not a product-wide PIV attestation and does
not enable other purposes. Update the first-release scope from the accepted
evidence; keep unqualified specialist branches explicitly unavailable.

## Starting request for the pilot conversation

> Prepara le carte di lavoro per valutare questa PMI dai documenti selezionati.
> Prima dei calcoli mostrami oggetto, finalità, data, dati estratti, fonti e
> decisioni mancanti. Proponi i metodi adatti al caso e chiedimi le conferme
> necessarie. Conserva la prima bozza prima di confrontarla con la valutazione
> professionale di riferimento, poi spiegami le differenze. Infine eseguiremo una
> modifica di un'ipotesi e riapriremo il risultato salvato.

## Engineering readiness

The stale Cowork teaching count was corrected from 33 to 34; the installed
teaching suite passed 23 tests with two expected non-Vera receipt-helper skips.
The branch incorporates upstream Fusione P1 from
`c3f09ad78f69a96445762e3772b7c05ec88d5862` and rebuilds Vera as 0.1.291.
The current full CI revision, merged-source package checks and pilot outcome are
separate evidence. No real-case execution, deployment, professional activation or
installed-host acceptance is claimed by this document.


Merged-source verification: 877 integration checks pass across the main run and
the corrected fixture rerun, with four conditional skips. All nine host packages
match source and the Vera privacy register validates. After the owner-approved local Fusione page correction, all 259 page and privacy
regressions pass. The browser verification covers five languages and desktop/mobile
layouts. No plugin source or package changed. The owner instructed **do not
publish**: the local correction is not pushed, merged, deployed or submitted to
Marketplace. CI on the earlier pushed revision does not verify this local delta.


## Beta publication decision — 30 September 2026

The user superseded the earlier publication hold and requested publication if the workflow is useful, with fixes otherwise. The release scope is a beta for valuation workpapers tested against already valued cases: linked source evidence, explicit assumptions, arithmetic, editable workbooks, reports and retained revisions. All purpose-specific professional qualification gates remain unchanged. No real accountant acceptance or PIV conformity is claimed. The Discord message was deleted by the user; this release does not repost it.

The merged valuation suite passed 635 tests at 96.08% coverage. Fresh packaged CLI acceptance and final publication evidence are retained under `outputs/vera-valuations-discord/beta-release/` in the primary checkout. These records distinguish generated workpapers, package parity, live deployment and Marketplace publication.
