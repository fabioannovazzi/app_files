> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Proposal and review contract

`proposal.json` is a model-authored record, not a form the user fills manually.

- `schema_version`: 1; `draft_id`: a short opaque identifier.
- `route`: `domestic` or `foreign_integration`, professionally reviewed.
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
