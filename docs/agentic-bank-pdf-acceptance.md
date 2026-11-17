# Agent-led bank PDF recovery — Vera 0.1.652

The host model inspects representative text and rendered pages, chooses the
extraction strategy, writes a source-bound local adapter, and revises it from
targeted trial diagnostics. Python reconstructs values from the original PDF;
it does not accept model-authored accounting values. No new model API or
external service is introduced.

The optional `source_blocks` strategy supports descriptions above a vertically
centered amount and dates/balances on different physical rows. Source word
endpoints define each movement. The checker verifies field containment,
non-overlapping blocks, complete description/reference text inside each block,
amount ownership, monetary coverage and printed controls. Existing amount-row,
CSV, spreadsheet, labelled PDF-table and registration-journal routes remain.

Source-bound overview/information-page decisions record exact headings and
numeric references. The model owns their semantic classification. Dates plus
amounts on such a page produce review evidence, not an automatic transaction
classification: legitimate summary balances also have dates. Arithmetic and
reference checks cannot independently prove semantic completeness. Ordinary
mapping review and downstream reconciliation are still required.

## Observed development acceptance

- A real six-page text bank statement: 105 readable movements; zero coverage
  or arithmetic issues; full-source trial and fresh freeze replay succeeded.
- All 105 descriptions matched a separate comparison against the PDF's vector
  cell boundaries using glyph centers. The adapter used centered-text geometry,
  so this check did not repeat its grouping heuristic. Client PDFs and extracted
  accounting data are not included in the repository.
- Broad regression selection: 637 tests, initially 633 passed and four failed
  because the isolated checkout did not yet have package ZIPs. After building,
  all six parametrizations of that package-entrypoint test passed.
- Final focused source/package, update-notification and projected-receipt
  selection: 75 passed, two environment-dependent skips; bank-reader coverage
  87.82%. Black, Isort, Mypy and Bandit checks passed for the changed code.
- The build initially required source/privacy fingerprints and course source
  metadata to be regenerated. The course content was unchanged; 44 course
  records changed only their source bindings, plus the corresponding index.
- An initial development freeze invocation used an output child that did not
  contain the adapter. The existing ownership check rejected it; using the
  correct workflow output directory resolved it without changing the check.

This proves development extraction and packaged regressions. It does not prove
that an already-open host session updated, that the original archived case has
completed mapping/reconciliation, or that any Marketplace version was published.
