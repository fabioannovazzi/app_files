# Proposal and review contract

`proposal.json` is a model-authored record, not a form the user fills manually.

- `schema_version`: 2; `draft_id`: a short opaque identifier.
- `route`: `domestic` or `foreign_integration`, professionally reviewed.
- `transmission_mode`: `supplier_direct` only when the supplier will be the
  transmitter, otherwise `intermediary`. Bind that choice to the reviewed
  `routing` decision. The exporter requires the transmitter and supplier fiscal
  identities to match for direct transmission, using the Italian supplier tax
  code when supplied and otherwise the VAT identity; it never infers the mode.
- `sources`: exact `sources` records from `source_evidence.json`. Each has an
  ID, input-relative path, SHA-256, title, role and evidence group.
- `invoice`: the ordinary invoice's XML structure represented as nested JSON
  objects. Top-level fields are `FatturaElettronicaHeader` and an array of
  `FatturaElettronicaBody`. Use official XML element names, arrays for repeated
  elements, exact strings for text and decimals, null for unresolved values.
  Never use floating-point JSON numbers. Omit absent optional elements. The
  exporter orders fields from the official XSD; unknown fields are errors.
- `field_evidence`: one entry for every leaf JSON pointer in `invoice`.
  Each has `kind` (`source`, `confirmed`, `calculated`), `basis`, `references`
  (source ID and exact page/region/confirmation locator), and optional boolean
  `uncertain`. Calculated fields also name their `operands` as other exact
  invoice-field JSON pointers. Mechanical presence of a citation does not prove
  support; the model and professional must inspect it.
- `decisions`: objects with `assessment` and source `references` for
  `source_grouping`, `source_completeness`, `parties`, `document_type`,
  `tax_treatment`, `numbering_and_date`, `routing`, `duplicate_and_issue_status`.
  The foreign route additionally requires `operation_facts`, `date_basis`,
  `original_invoice_reference`, `currency_conversion`.
- `questions`: remaining factual, extraction or professional questions. Any
  unresolved question blocks export but does not prevent saving the draft.

Example evidence pointer:

```json
{
  "/FatturaElettronicaBody/0/DatiGenerali/DatiGeneraliDocumento/Numero": {
    "kind": "source",
    "basis": "Invoice number visible in the document header",
    "references": [{"source_id": "invoice-1", "locator": "page 1, header"}],
    "uncertain": false
  }
}
```

The schema reference is
`xsd/Schema_VFPR12_v1.2.3.xsd`; inspect the relevant element/type declarations
when constructing optional blocks. Do not copy synthetic identities, routing
values, tax rates or dates from tests into a real proposal.

The content hash binds all fields, sources, decisions and questions. Each
`draft-<digest>` folder is immutable. `review_request.json` is an unapproved
request; copying it does not approve anything. Persist an approval only from
the actual user's review of that exact revision. An export report records its
scope and still reports `sdi_acceptance: not_tested`.

Local export deterministically checks Italian VAT-number and tax-code control
characters because these are fixed statutory transcription controls. VAT numbers and tax codes need not be equal; their association requires
reviewed registry evidence rather than a local equality rule. These checks do not query the Anagrafe Tributaria and do not establish
registry-level identity coherence, activity status or SdI acceptance.

The transmitter may have an 11-digit or 16-character Italian tax code. See the
[official transmitter field guidance](https://docs.italia.it/italia/18app/18app-esercenti-docs/it/bozza/linee-guida-fatturazione.html)
and the bundled FPR12 schema. Checksum validity does not establish ownership.
