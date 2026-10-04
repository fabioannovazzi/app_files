> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Selected ledger intake and normalization

The host model proposes accounting meanings and dispositions. Code retains
selected source cells, checks exact references and arithmetic, and writes an
immutable proposal. This is neither professional approval nor proof that the
selected range covers the complete business population.

## Host-operated steps

1. Start the bound Studio Archive run and initialize the Patent Box session.
   Read only its selected receipts. Explain the proposed source, sheet/range,
   header and control-total scope. Never ask the user to edit JSON.
2. Write `ledger_options.json` in that run's output directory using
   `schemas/ledger-selection.schema.json`, then call:

   ```text
   patent_box_workflow.py --client-engagement <context> inspect-ledger --evidence-id <id> --options <output/ledger_options.json>
   ```

   CSV requires an explicit delimiter, encoding and closed row range. XLSX
   requires the exact sheet, header and closed row range. Formula cells are
   retained as formulas and cannot supply mapped amounts: ask for a reviewed
   values-only export. The parser never evaluates formulas or external links.
   Numeric OOXML strings are parsed directly as Decimal, avoiding binary-float
   conversion. Other worksheets are not included in the returned table.

   For a text PDF the host proposes columns and rows with exact page passages.
   Each supplied cell must occur literally in its page passage. This verifies
   the citation, not the table's meaning or completeness. Scanned PDFs require
   an explicitly approved OCR path or another selected source; do not install
   OCR or silently invent cells.
3. Retain returned table and row references. Write a normalization plan using
   `schemas/ledger-normalization.schema.json`. Include explicit numeric and
   currency mappings, original totals, fiscal bases, dated rate evidence,
   row-level groupings and reasons for every exclusion/non-data row. Net credit
   notes or aggregate payroll only when the source documents support that
   proposed grouping. Rates are EUR per source-currency unit. No rate, negative
   adjustment, accounting classification or fiscal treatment is inferred.
4. Call:

   ```text
   patent_box_workflow.py --client-engagement <context> normalize-ledger --plan <output/normalization_plan.json>
   ```

   Source totals include all data rows, including explicitly excluded entries.
   The normalized ledger total includes only retained cost groups. Every row
   must be consumed once, excluded with selected proof, or identified as
   non-data. Conversion uses Decimal; rounding to cents occurs once per final
   normalized cost, with the rounding delta retained.
5. Open the returned `normalization_<digest>.md`. Show mappings, original
   totals, rate evidence, component rows, candidate income/IRAP bases and
   duplicate decisions. Exact selected economic keys, repeated ledger IDs and
   repeated physical rows produce candidate duplicates. These do not prove
   economic duplication. The host must also examine semantic duplicates that
   exact keys miss and can add located groups to the plan. Never claim the
   mechanical comparison guarantees an absence of duplicates.
6. A DISTINCT disposition needs a reason and the contributing evidence. A
   DUPLICATE disposition requires one retained row and explicit exclusions for
   the others. Unresolved groups retain every row and identify only affected
   cost IDs. Their allocation `PB.COST` controls must remain BLOCKED or
   NOT_TESTED. Missing evidence does not justify FAIL. Other costs stay available
   for their independent controls.
7. Put `normalization_digest` into the main proposal and copy the exact returned
   costs and `ledger_control_total`. Proposing replays tables from selected
   originals, recalculates the normalization and embeds the complete plan,
   tables and result in the proposal's review digest. A rehashed intermediate
   table cannot change the original cells. Revised mappings need a new proposal
   and a new explicit review. Original bytes and previous versions are retained.

## Current verification and limits

The importer and archive-bound proposal actions have 31 passing technical
checks, including actual CSV, XLSX and text-PDF fixtures, FX rounding, credit-note
netting, grouped payroll, duplicate decisions, stale inputs and cross-run
isolation. They do not establish extraction quality on representative client
PDFs, accounting or legal validity, authenticated review, or professional UAT.
The current broader workflow has a separately documented aggregation regression.
No client source is sent by these parsing helpers to a network service. The
host model can receive selected cells and passages while preparing mappings.
