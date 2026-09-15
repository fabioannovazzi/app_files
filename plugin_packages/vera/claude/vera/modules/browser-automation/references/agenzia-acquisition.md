> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Agenzia invoice acquisition: CR-49 prototype

`scripts/agenzia_acquisition.mjs` is the resumable acquisition layer for CR-49.
It archives each explicitly selected Agenzia category by year, reconciles the
independently observed population, preserves XML or P7M originals, extracts the
encapsulated FatturaPA XML from P7M, and can verify a PDF saved by the operator.
It does not establish current portal compatibility or replace the two clean
target-environment repetitions required by CR-49.

The model reviews the category plan from the authorized portal before execution.
Do not infer category meaning or format availability from source code or button
names. Each entry needs the observed accessible category name, an exact
single-year range, an independently observed non-negative count, and an explicit
format state. `original` may be `available` or `unavailable`; `pdf` may be
`native_gap` or `unavailable`. A category with no portal output for a format must
say `unavailable` rather than silently omitting the gap.

```js
const { acquireAgenziaInvoices } = await import(
  moduleRoot + "/scripts/agenzia_acquisition.mjs"
);
const result = await acquireAgenziaInvoices({
  tab: session.tab,
  categoryPlan: [{
    category: "fatture-emesse",
    accessibleName: observedAccessibleName,
    dateFrom: "2026-01-01",
    dateTo: "2026-12-31",
    expectedCount: observedCount,
    formats: { original: "available", pdf: "native_gap" }
  }],
  downloadDirectory: actualChromeDownloadsDirectory,
  nativePdfDirectory: operatorChosenPdfDirectory,
  runDirectory: freshPrivateRunDirectory,
  executionMode: "live_connected_chrome",
  onNativePdf: operatorSaveAsPdfHandoff
});
```

The browser download route requires both the browser download event and one new,
stable regular file in the selected directory. The archive uses
`<year>/<category>` and exclusive writes. Direct XML and P7M are preserved
byte-for-byte. For P7M, the runtime parses CMS SignedData and writes the exact
encapsulated FatturaPA XML with the source P7M SHA-256. It does **not** validate
the digital signature, certificate chain, signer identity, revocation, or legal
validity; report `signature_validation: not_performed` exactly.

Chrome cannot control the operating-system Print dialog. The runtime first uses
the observed `visualizza file fattura` control and verifies that the resulting
view exposes one Stampa control. `onNativePdf` is then the operator handoff: the
operator uses Print → Save as PDF, and the runtime accepts the result only after
the supplied Stampa control was invoked and a unique stable new file begins with
the PDF signature. Any run using this path records
`operator-save-as-pdf`, remains prototype, and is ineligible as a clean browser
validation replay.

The run directory is fresh, owner-only, outside the repository. State revisions
are append-only and hash-linked. On `resume: true`, use the exact same category
plan, execution mode, run directory, and download directories. The runtime
verifies the full revision chain and every retained archive hash before touching
the portal. It re-enumerates the interrupted category, skips documents already
complete, and never overwrites prior attempts or artifacts. Do not start a new
directory and call it a resume.

The returned summary exposes category/year counts, pages, declared format
availability, prototype status, and sanitized errors. The private attempt report
contains document hashes and owner-only paths; invoice bytes do not enter model
context or a portable capability. A page/count mismatch, duplicate detail
identity, changed retained file, ambiguous folder arrival, missing format, or
page/invoice safety limit fails without a completion claim.

Before CR-49 can close, run the exact released version twice on the target
Agenzia environment across the requested categories and at least one multi-page
population. Reconcile the portal counts, pages, archived originals, P7M/XML
bindings, PDF native gaps, unavailable formats, and attempt reports. One run must
be interrupted and resumed without redownloading or overwriting a verified
artifact. Any selector recovery, model repair, native PDF handoff, or unexplained
count difference excludes that run from clean browser replay evidence.
