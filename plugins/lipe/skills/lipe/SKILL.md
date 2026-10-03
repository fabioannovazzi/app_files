---
name: lipe
description: Use LIPE to reconcile Italian VAT registers and periodic settlements, prepare evidence-linked VP drafts, review tax-code mappings and payments, preserve decisions, and export an unsigned XML after external approval. Professional and importer qualification remain pending.
---

# LIPE

Say that you are using **LIPE**. Inspect the supplied documents first. Start with
the existing client, year, quarter and periodicity; reuse confirmed answers.
Read `references/sources.json`, `references/rules.json` and
`references/acceptance.md`. The current implementation is a review pilot for
ordinary Italian VAT in 2024–2026. It is not a filing system or a compliance
certification. Do not describe a passing XSD as acceptance by Agenzia Entrate.
Read `references/anomaly-review.md` before proposing or resolving observations.
Read `references/code-catalog.md` when recognizing or reusing VAT-code meanings.

## Inspect and qualify

Use Studio Archive for real cases: resolve the client and engagement, import the
source documents and start a `lipe` run using the portable v2 context. Never
invent an engagement or set real or anonymized real data to `SYNTHETIC`.
The bundled example is wholly fictional. Source originals, extractions, reviewed
case JSON and all output revisions stay in the same case. Catalog entries and
their original evidence stay in the selected private studio catalog; no remote
publication or automatic cross-studio learning is performed.

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
Before that confirmation, record the first-pass population following
`references/code-measurements.md`. Preserve unsuccessful recognition and unknown
codes as well as proposals; do not retrospectively label a reviewed case as a
first pass. The measurement ledger never supplies approval or changes a mapping.
Consult the selected catalog in client, studio, then central-reference order.
Preserve exact revisions and case applicability following the catalog guide;
pass `--catalog` when calculating a bound case. Do not remove a binding or switch
to a manual mapping just to evade a revocation, confidence block or dispute.
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
Supply `liquidations` for every period using case contract 1.3. Each sales or
purchase section explicitly declares its taxable-base basis (registration,
chargeability or deduction) and VAT basis (recorded, output or deductible).
Confirm that meaning against the actual print; do not choose a basis merely to
make a difference disappear. Missing lines remain absent, not assumed zero.
The comparison never changes the VP3 registration basis or a reviewed deduction.

Open `workpaper.xlsx`: its three tabs are Riconciliazione, VP and F24. Inspect
per-code discrepancies and source references, the visible VP formulas and their
comparison to the saved engine result, and payment differences. Draft a supported
explanation for each discrepancy from the source evidence; do not infer closing
entries, lateness, omissions or remedies from a numeric difference alone. The
workbook uses standard numeric cells; separators follow the spreadsheet viewer's
locale. It is an inspectable draft, not an approval or a replacement case file.
Change evidence/decisions in the case and rerun to produce a new revision. Never
treat a manually edited workbook as the approved result.
Record supported semantic proposals in `observations`, with invoice/protocol
references, source quotations, proposed VP6 effects (null when unknown), actions
and links to the exact comparison/finding identifiers. Follow the review guide
for `anomaly_review`, professional decisions and their current content bindings.
Open or stale decisions block VP output. A proposed effect never changes the
arithmetic automatically: amend the reviewed inputs and recalculate.

Inspect the generated `anomalies.md`/JSON dossier, `summary.pdf` and per-client
`review-request.md`. The draft preserves unknown recipients, facts and deadlines;
provide `correspondence` with source-backed dates only. Review the rendered PDF,
figures and letter before delivery. Do not send correspondence without an explicit
user request. The named reviewer is an attributed local record, not an
authenticated identity or a tax approval issued by Vera.

## Prepare and verify professional approval

Follow `references/approval.md` for the source-bound front-page contract, the
readable exact-version request and external signature verification. Preserve
actual registry evidence and professional judgments; format/checksum checks do
not establish Anagrafe registration or ownership. Reuse the current Archive run
and complete its actual model-data disclosure before preparing a request.

Only the independently configured firm authority and externally signed mandate
can authorize a signer. Do not create real keys, trusted administrator pins or
mandates, or treat a named reviewer/JSON status as authenticated approval.
`prepare` creates a request; `accept` verifies supplied originals and preserves
proof. The separate export command re-verifies those originals and the current
version. An approval signature is not a signature on the XML return.

## XML export and qualification

`xml-test` recalculates a **synthetic** case, uses fictional identifiers and
requires the bundled official XSD with the complete W3C signature schema:

```bash
python scripts/lipe.py xml-test --case examples/synthetic-case.json --source-root examples --output /absolute/synthetic/xml
```

For an approved case, follow `references/xml-export.md`. Use the independently
configured firm authority and its one filename registry. Obtain the intermediary's
confirmed unused progressive; do not guess the history of filenames generated
outside this registry or create a fresh registry to bypass a collision. Export
re-verifies the original CMS signatures, current mandate/CRLs, sources, disclosure,
catalog and artifacts, then reads the generated XML back against the approved VP.

The delivered XML is unsigned and is not transmitted. No real studio, importer
or Agenzia control-software acceptance is established by development tests.
Keep the actual outstanding acceptance register visible; do not invent identity,
test real filing by transmission, or substitute real identifiers in `xml-test`.
If a transmitted XML is supplied, use the comparison command and retain all
metadata, period and amount differences. Equal VP values do not approve changed
front-page data or flags and do not authenticate the supplied file.

## Inspect a supplied receipt

Follow `references/receipts.md` when the professional supplies a receipt. Preserve
the original, read its official XML structure and declared outcome, and optionally
compare its filename to a supplied transmitted file. The helper does not verify
XAdES authenticity, connect receipt bytes to transmitted bytes, compare VP figures
or query a tax portal. An ES01, a successful command or an XSD pass must never be
reported as verified filing acceptance. Keep ES02 warnings and ES03 rejection
visible; interpretation and follow-up require professional review.

## Delivery and privacy

Read Vera's `skills/vera/references/model-data-report-contract.md`. Record actual
extraction, mapping, review and narrative model-visible phases. Local helper
execution cannot measure host model exposure: `local_processing_receipt.json`
explicitly leaves it unknown. Build and show the readable `model_data_report.md`
and its JSON using the shared report helper; declare both and each revision as
Studio Archive run artifacts. Do not close the managed run without them.
Current user restrictions govern any optional external attestation or publishing.

## Codex-Native Run UX

Default output policy: the Markdown and Excel workpapers, PDF summary, anomaly dossier,
unsent colleague draft, VP table, findings and readable model-data
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
Catalog classes, confidence, scope identifiers, quotations and attributed review
history may also enter context. An explicitly requested catalog history can
include other authorized studio entries; do not load it indiscriminately for a
single client. The selected catalog retains original evidence bytes locally.
Local helpers hash and read the selected sources, check quotations and arithmetic,
and write case artifacts; they make no model or network call. Public source
research uses non-identifying queries. No automatic anonymization, local-only
model processing, remote central code sharing or legal compliance certification is
provided. Keep the actual session disclosure distinct from these design limits.
Supplied receipts and transmitted files can expose filenames, identifiers,
timestamps, notes, errors, front-page fields and VP amounts. Record their actual
inspection in the same session disclosure. A local receipt parser makes no
network or model requests and cannot measure what the host has read.
