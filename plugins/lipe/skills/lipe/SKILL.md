---
name: lipe
description: Use LIPE to reconcile Italian VAT registers and periodic settlements, prepare evidence-linked VP drafts, review tax-code mappings and payment differences, and preserve professional decisions. Pilot with real filing export blocked.
---

# LIPE

Say that you are using **LIPE**. Inspect the supplied documents first. Start with
the existing client, year, quarter and periodicity; reuse confirmed answers.
Read `references/sources.json`, `references/rules.json` and
`references/acceptance.md`. The current implementation is a review pilot for
ordinary Italian VAT in 2024–2026. It is not a filing system or a compliance
certification. Do not describe a passing XSD as acceptance by Agenzia Entrate.

## Inspect and qualify

Use Studio Archive for real cases: resolve the client and engagement, import the
source documents and start a `lipe` run using the portable v2 context. Never
invent an engagement or set real or anonymized real data to `SYNTHETIC`.
The bundled example is wholly fictional. Source originals, extractions, reviewed
case JSON and all output revisions stay in the same case. No central code catalog
or cross-client learning is performed.

From Vera run `python scripts/check_dependencies.py --module lipe`; from this
module run `python scripts/check_dependencies.py`. Use the shared managed Python
3.12 runtime and declared requirements. Do not install packages into the case.

Inventory sales, purchases, receipts and integration registers, every section,
the reported liquidation, prior-period balances, annual credit, adjustments and
available F24 evidence. Confirm the accounting software **and version** and any
custom codes. A filename or a generic vendor code catalog is not sufficient.
The professional confirms register completeness and applicable regime. Put
special tax regimes, group/mixed accounting, extraordinary transactions,
subcontracting, foreign or cross-year timing, unresolved rate/deduction issues
and other unsupported features in `unsupported_features`; these block a VP draft.
`QUARTERLY_SPECIAL` denotes periodicity without the 1% option interest; it does
not authorize a special VAT determination method.

## Extract with evidence

```bash
python scripts/lipe.py extract --source /absolute/run/inputs/register.pdf --output /absolute/run/inputs/extractions
```

The helper preserves source bytes, SHA-256 and page text. It does **not** recognize
VAT tables, certify reading order or run OCR. Read the original pages visually
alongside the text. Blank or unreadable pages need a readable source or the
existing explicitly approved OCR route; never treat them as zero. Preserve any
OCR derivative and original separately, including the extraction provenance.

Use the current host model to propose `schemas/case.schema.json`. For each row,
record its source, page, exact quotation, printed base and VAT, deduction amount,
and distinct registration, chargeability and deduction periods. Review line
signs, credit notes, grouped totals, repeated page headings and cumulative
totals. Do not combine detail rows and their subtotal as additional operations.
Whole documents may be necessary; do not assert that only totals reach the model.

The base of a purchase stays in its registration period (VP3); exercising its
deduction in another period changes VP5 only. A vendor's “data IVA” label does
not establish legal entitlement or the relevant period. Qualify those facts
against the current official instructions and actual receipt/registration dates.
Keep all periods within the selected year and periodicity; cross-year cases are
outside this pilot. Include boundary-period registers where needed and explain
the allocation in the row review.

## Confirm mappings and decisions

Propose each `(side, code)` meaning with a reason. The case's software, version,
client and engagement bound its mappings. Use `PROPOSED` until the professional
actually confirms; never manufacture `CONFIRMED` to enable a calculation.
`SALE_NO_OUTPUT_VAT` needs an explicit reason (for example reviewed exempt,
non-taxable or split-payment treatment). `PURCHASE` always uses the explicitly
reviewed `deductible_tax`; it never assumes full deductibility. Reverse charge
adds tax to VP4 and only the reviewed deductible amount to VP5. Sales integration
mirrors contribute nothing a second time and must link to matching purchase rows.

Do not infer exclusion from “other”, “outside scope” or a person’s name. Unknown
codes block calculation. Tax interpretation and anomalies such as incorrect
vendor coding, duplicate import/reverse-charge treatment or closing entries are
model proposals for professional review; matching numbers do not prove a cause.

Prior-period credit and deferred small debt require reviewed evidence, including
a verified zero. Missing balances remain null. For each period explicitly review
VP9–11/13, any credit withheld from carry, payment principal and whether an
eligible small debit was paid or deferred. Payment comparison excludes penalties
and interest on late payment and does not diagnose omission or compute remedies.
Quarterly-by-option small-debt carry is blocked pending qualification of the
principal/interest carry basis. November/December and Q3/Q4 never automatically
carry a small debit into a forbidden next-period VP7.

## Calculate and review

Import the completed case JSON into the archive input inventory, then run:

```bash
python scripts/lipe.py calculate --case /absolute/run/inputs/case.json --client-engagement /absolute/client_engagement.json
```

For the bundled synthetic example only:

```bash
python scripts/lipe.py calculate --case examples/synthetic-case.json --source-root examples --output /absolute/synthetic/output
```

The engine reconciles source totals and performs exact Decimal arithmetic. It
requires three monthly modules or one quarterly module, in order. Quarterly by
option uses 1% in Q1–3; Q4 uses XML period 5 and leaves VP11, VP12 and VP14 blank.
It preserves blocked results and each content-bound revision in a new folder.
Never overwrite earlier evidence or approvals. Rerun from new evidence when
something changes; the case, rules and engine hashes identify the revision.

Open `workpaper.md`, show the VP table, findings and unresolved requirements,
and make the row composition in `result.json` available. Explain each difference
against the customer's liquidation; it does not replace the register source.
Prepare a source-backed colleague message from the model's reviewed findings,
using `review-request.md` as a request template only. Do not send it without an
explicit user request. The named reviewer is an attributed local record, not
an authenticated identity or a tax approval issued by Vera.

## Acceptance and XML boundary

`xml-test` recalculates a **synthetic** case, uses fictional identifiers and
requires the bundled official XSD with the complete W3C signature schema:

```bash
python scripts/lipe.py xml-test --case examples/synthetic-case.json --source-root examples --output /absolute/synthetic/xml
```

Real XML export, signing, submission and receipt processing are unavailable.
Do not work around the block, substitute real identifiers in test XML, invent
authentication or mark professional/importer tests complete from unit tests.
Follow the actual outstanding acceptance register before enabling that path.

## Delivery and privacy

Read Vera's `skills/vera/references/model-data-report-contract.md`. Record actual
extraction, mapping, review and narrative model-visible phases. Local helper
execution cannot measure host model exposure: `local_processing_receipt.json`
explicitly leaves it unknown. Build and show the readable `model_data_report.md`
and its JSON using the shared report helper; declare both and each revision as
Studio Archive run artifacts. Do not close the managed run without them.
Current user restrictions govern any optional external attestation or publishing.

## Codex-Native Run UX

Default output policy: the workpaper, VP table, findings and readable model-data
report are normal outputs. Prepare `codex_run_review.md` beside them with actual
checks, unresolved questions and output paths.
Never write run outputs inside this Git workspace or a published directory.
The local deterministic scripts
verify evidence integrity and arithmetic; the model proposes interpretations and
the professional reviews them. Continue ordinary authorized work without extra
approval. Reserve explicit approval for external, destructive, approval-sensitive
or material steps outside the authorized scope and unresolved material choices.

## Plugin Improvement Feedback

Keep the improvement note local to chat or run artifacts. Use Vera's shared
feedback policy only if the user chooses transmission. Exclude client material
and identifiers from developer feedback; use a synthetic reproduction.

## Quali dati arrivano al modello

The selected Codex or Cowork model may read complete register pages, customer and
counterparty identifiers, invoice and registration dates, tax codes, bases, VAT,
liquidations, F24 excerpts, proposals, professional decisions and workpapers.
Local helpers hash and read the selected sources, check quotations and arithmetic,
and write case artifacts; they make no model or network call. Public source
research uses non-identifying queries. No automatic anonymization, local-only
model processing, central code sharing or legal compliance certification is
provided. Keep the actual session disclosure distinct from these design limits.
