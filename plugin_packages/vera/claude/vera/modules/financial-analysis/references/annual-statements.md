> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Annual OIC statements analysis

Use this path for a historical comparison of two to ten annual Italian OIC
statements supplied in XLSX, with optional PDF/XBRL/other supporting sources.
It is a separate source-cell recipe, `annual_oic_source_cells.v1`, not one of
the eight accounting/FDD packs. Do not force annual statements into a monthly
P&L case or present an initial report-builder sheet suggestion as a diagnosis.
Native FDD case constructors are not this path; use the same file route in
Claude and Cowork. The current generated report labels are Italian.

## Intake and mapping

Reuse the established client, engagement, scope and authority. If the client
choice is genuinely missing, ask once for it. Do not repeat confirmation already
given for the same client and files. Preserve Studio Archive's immutable imports,
run lifecycle and output gate. Prepare/start a `financial-analysis` run containing
the workbook and every supporting original to be used. Copy the exact hydrated
inputs into a `case/sources/` folder below the run output, preserving hashes;
write `case/annual_case.json` beside `sources/`. Each declared source must name
its exact run `input_binding_id` and SHA256. The runner verifies both. User files
are never edited, and other clients' files cannot substitute for those imports.

Read source content needed to establish the mapping and record actual model
exposure. If using Report Builder inspection, use its bounded expansion contract
and a separately prepared report-builder run; never open its private control
inventory. Financial Analysis can read explicitly selected originals through
the host's maintained readers. Do not promise that all original data stays local.

Decide mapping semantically from source labels, units and notes. The recipe uses
explicit cell coordinates; it does not classify a worksheet as a single balance
sheet, guess row numbers, parse account labels or infer years from filenames.
Combined SP/CE sheets and separate sheets use the same contract. Use the years
actually supplied. Map expenses with the explicitly declared positive-expense
convention; stop to resolve contrary signs rather than silently invert them.
Map the original subtotal AND its components. Never replace an inconsistent
source subtotal with a reconstructed value. Distinguish true source zeros from
missing detail: `null` means unavailable, not zero. An export's zero-filled detail
does not establish the absence of that balance in the filing.

## Case contract

`annual_case.json` is an object with these fields:

```json
{
  "schema_version": "vera.annual_statements_case.v1",
  "entity": "Impresa dimostrativa",
  "accounting_basis": "italian_oic_positive_expenses",
  "currency": "EUR",
  "years": ["2021", "2022"],
  "tolerance": "0",
  "mapping_basis": "Mapping proposto dal modello dalle etichette originali; revisione professionale pendente.",
  "sources": {
    "statements": {
      "path": "sources/statements.xlsx",
      "sha256": "<SHA256 effettivo>",
      "input_binding_id": "<binding_id restituito dal run>"
    }
  },
  "fields": {
    "revenue": {
      "2021": {"source_id": "statements", "sheet": "Conti", "cell": "B2", "scale": "1"},
      "2022": {"source_id": "statements", "sheet": "Conti", "cell": "C2", "scale": "1"}
    },
    "financial_debt": {"2021": null, "2022": null}
  },
  "coverage": {
    "statements": {"status": "partial", "basis": "Lette le righe mappate; dettaglio debito finanziario non presente nel prospetto letto."}
  },
  "commentary": [
    {"kind": "question", "text": "Richiedere il dettaglio dei debiti finanziari.", "references": [{"source_id": "statements", "locator": "Conti, prospetto dei debiti"}]}
  ],
  "limitations": ["Bozza da sottoporre a revisione professionale; nota integrativa non fornita."]
}
```

This is a shape example, not a complete analytical case. The canonical mapped
fields and labels live in `scripts/annual_statements.py` (`FIELDS`). Map every
available field relevant to the supplied accounts. Each included field must
state every year, with explicit `null` for missing evidence. Unknown field names,
duplicate source-cell assignments, formulas/errors, ambiguous numeric text and
stale source hashes fail. Literal XLSX numbers or canonical decimal text are
supported; localized numeric strings need a reviewed values export. Blank cells
never become zero. Scaling must be positive and explicit.

The recipe calculates both A−B plus depreciation/amortisation and A−B plus all
B.10, and preserves their difference. Ratios disclose their denominator and do
not divide by zero. The liquidity ratio needs mapped current liabilities; the
total of all debts is not a substitute. Mapped financial debt less cash is not
labelled a complete PFN. No cash-flow classification or dividend amount is
manufactured as a balancing residual.

## Notes and model-written diagnosis

Inventory every supplied supporting file in `sources` and `coverage`, including
unread material. `read`, `partial`, `unread` describe the model/reviewer's actual
reading, not the helper's hashing. Before claiming a fact is absent, examine the
relevant supplied pages: an unread note means **not checked**, not **missing**.
For the industry code, examine company information; for debt, examine debt
composition/maturity notes. The model selects relevant note pages, interprets
exceptional income, group transactions and period changes, and writes the
diagnosis. Code only validates that each commentary item names declared sources
and nonempty locators; it does not verify a sentence's truth or page coverage.

Populate `commentary` with `observed`, `inferred`, and `question` items carrying
exact cell/page/tag references. Describe the business movements, plausible
explanations supported by notes, assumptions and questions for management.
Never fabricate a reviewer, professional approval, sector benchmark or coverage.
If a studio method is explicitly supplied/adopted, read it and preserve its
attribution; disclose definitions/thresholds as studio choices, not source facts.

## Execution and delivery

```bash
python scripts/check_dependencies.py --annual-statements
python scripts/run_annual_statements.py \
  --case <run-output>/case/annual_case.json \
  --client-engagement <client_engagement_path> \
  --output-dir <run-output>/annual-review-v1
```

The output directory must be new. The normal outputs are `annual_report.docx`,
`annual_analysis.xlsx`, `annual_report.md`, `annual_result.json`,
`reconciliation.json`, `used_case.json`, and `annual_execution_receipt.json`.
If first calculating before writing the diagnosis, read the result, complete
the model commentary in a new case version, and render a new output version.
Do not deliver calculation tables alone as a completed professional diagnosis.

An arithmetic/source exception is a **qualified draft**, not a crashed run and
not permission to repair a filing. Continue the unaffected analysis and put the
exception prominently in both Word and Excel. `report_ready=false` and
`professional_review=pending` remain explicit even when every available check
passes. Missing checks remain visible. The runner returns success when a
qualified package was produced; malformed/stale inputs return an execution error.

The Excel workbook contains original references, editable formulas, independent
Decimal results, definitions, notes and checks. Office formulas recalculate on
opening; their stored cache is not certified. Excel has a fifteen-significant-
digit precision limit; the helper rejects amounts it cannot faithfully export.
Edits in Excel do not automatically update Word or receipts. Regenerate after
review. Inspect the generated Word and workbook before claiming rendering or
spreadsheet-host acceptance. Create the actual run model-data report, declare all
physical files and finalize/review/complete through Studio Archive. Completion
records delivery, not professional approval.
