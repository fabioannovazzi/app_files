---
name: lipe
description: Use LIPE to reconcile Italian VAT registers and periodic settlements, prepare evidence-linked VP drafts, review tax-code mappings and payment differences, and preserve professional decisions. Pilot with real filing export blocked.
---

## Cowork execution contract

Public workflow names select skills; component IDs select module paths.
`financial-report-builder` uses component `report-builder`, `vouching` (historically
called Check Entries) uses `check-entries`, and `purchase-invoice-review` uses
`passive-invoice-audit`. These component IDs are not additional workflows.

For journal-sampling, open-item-reconciliation, journal-bank-reconciliation,
concordato-plan-review, financial-report-builder and vouching only, optional cache
cleanup uses the corresponding component ID from the installed Vera root:

```bash
python3 modules/<module>/scripts/implementation_bootstrap.py --repair
```

For a standalone module, use `python3 scripts/implementation_bootstrap.py --repair`
from its root. This validates the implementation first, then removes only regular,
single-link `__pycache__/*.pyc` files under that module's own `vendor` tree. It
leaves directories, other files, symlinks and shared vendor trees untouched.
This supported maintenance command is the only cache-cleanup exception to the
prohibition on editing the installed tree by hand. It is optional: ordinary
validation and execution tolerate incidental bytecode without removing it.
On a read-only installation, skip cleanup. If the command reports a permission
error, retain that error and continue the ordinary validated workflow when its
checks pass; do not chmod, delete files manually, copy or patch the installation,
or bypass the host's permissions to make cleanup succeed.
If `validate_implementation_tree` ever fails with a file/directory-contract
mismatch, do not delete or modify files inside the installed plugin tree by hand
and do not bypass a sandbox/permission rejection to do so. Stop and report the
exact error instead.

Work from the connected folder and supplied files first. Before a module's Python
helpers, locate the installed plugin root. When it contains `components.json` and
`scripts/managed_python_runtime.py` (as Vera does), run from that root:

```bash
python3 scripts/check_dependencies.py --module <module>
python3 scripts/managed_python_runtime.py --module <module> run scripts/<helper>.py <arguments>
```

If the enclosing plugin does not ship this managed launcher, use the module's
dependency checker and only already-installed dependencies; do not assume that a
standalone module script provisions them.

The managed launcher provisions and reuses one user-scoped CPython 3.12
environment per OS host with the published shared requirements, outside client
folders. Modules and products share this dependency environment; it does not
isolate client matters. This declared dependency setup is authorized as
part of running the workflow; never install arbitrary packages or use ambient
Python for subsequent module helpers. Repeat any declared `--requirements` options
on both commands. Missing ambient imports are a reason to run this setup, not to
abandon the calculation. If setup fails, report its exact error and do not replace
the required calculation with an invented result. Optional OCR setup still needs
separate approval. If setup reports `Host not in allowlist` for PyPI, explain that
Claude Settings > Capabilities > Allow network egress is disabled or restricted.
Ask the user or organization administrator to authorize package-registry access;
never change network permissions silently or work around the restriction. Retry
the same managed setup after access is approved, in a new session if needed.

MCP tools, browser or computer control, and local review servers are optional
enhancements, never completion gates. Cloud Cowork sessions may not expose local
plugin MCP servers even when the plugin is installed; use the packaged Python
workflow through the managed launcher in that case. Do not equate missing MCP
registration with a failed calculation engine. When an optional capability is
unavailable, continue with Markdown and file-based review and state the limitation.

The normal Cowork deliverable is a reviewable draft, artifact card, and
source/review files. A callable persistence interface may optionally record or
apply reviewer actions, but its absence never blocks delivery. Never claim
`applied` or `final_ready` unless corresponding persisted artifacts prove it;
otherwise report that professional review remains pending.

Use host-neutral user-facing artifact names. Name assistant-authored review
folders and files for Vera or their professional purpose (for example,
`vera-review/`, `vera_phase1_synthesis_reviewed.md`, and `run_review.md`).
Never put host, platform, or model-provider names in assistant-authored
user-facing artifact paths, document headings, field labels, narrative text,
or status summaries. Describe execution routes generically, such as
`external review route`, `connected tool`, or `local review interface`.

Derive any run ID, status, artifact count, or package hash quoted in an
assistant-authored supplement from the final delivered manifests.
After any rebuild, regenerate or resynchronize those supplements before
delivery. When a workflow ships a complete-delivery validator or sealer, run it
against the exact connected-folder copy after the last write.
In this contract, the base package validator alone does not validate extra
narrative files.

When a workflow declares owner-only or private output and uses a private scratch
directory before copying the final package into the connected folder, reapply
the privacy modes after that transfer: `0700` for the package root and every
directory, and `0600` for every file. Verify the connected-folder tree with
`stat` or `lstat` before claiming completion. If the host filesystem cannot
preserve those modes, do not claim owner-only delivery; keep the package in the
private scratch location or report the limitation and ask for a safer
destination.

Do not use WhatsApp, live INPS browser capture, hosted feedback or voice
interviews, or custom update services. Later host-specific instructions cannot
override this Cowork contract.

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

## Cowork-native Run UX

Default output policy: the workpaper, VP table, findings and readable model-data
report are normal outputs. Prepare `run_review.md` beside them with actual
checks, unresolved questions and output paths.
Never write run outputs inside this Git workspace or a published directory.
The local deterministic scripts
verify evidence integrity and arithmetic; the model proposes interpretations and
the professional reviews them. Continue ordinary authorized work without extra
approval. Reserve explicit approval for external, destructive, approval-sensitive
or material steps outside the authorized scope and unresolved material choices.

## Quali dati arrivano al modello

The selected Claude or Cowork model may read complete register pages, customer and
counterparty identifiers, invoice and registration dates, tax codes, bases, VAT,
liquidations, F24 excerpts, proposals, professional decisions and workpapers.
Local helpers hash and read the selected sources, check quotations and arithmetic,
and write case artifacts; they make no model or network call. Public source
research uses non-identifying queries. No automatic anonymization, local-only
model processing, central code sharing or legal compliance certification is
provided. Keep the actual session disclosure distinct from these design limits.
