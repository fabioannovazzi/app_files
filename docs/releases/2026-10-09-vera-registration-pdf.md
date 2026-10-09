# Vera 0.1.358: reviewed registration journals in text PDFs

The reported files contained selectable text. The old sampling route rejected every PDF; reconciliation attempted generic table extraction and reread the entire failed source as text without closing per-page caches. The new supported source family uses reviewed physical column coordinates, registration headers and cross-page continuations. Source bytes and layout semantics are bound into mapping receipts. The full source must close every registration before it emits a population. Amount sides, account identities and registration boundaries are never inferred from numeric clusters.

The reviewed layout contains finite body bounds and nonoverlapping account-debit, account-credit, description, debit and credit bands. Printed header/footer exclusions are explicit review decisions; they must not hide postings. Date and registration number carry over page boundaries, descriptions can span rows, and totals are checked at registration closure rather than page end. Wrong continuation dates, missing accounts, unmapped monetary values, negative monetary sides, empty-text pages and unbalanced registrations withhold all postings. Two simultaneous posting sides on one physical line remain unsupported pending a reviewed identity contract.

Both sampling and reconciliation use the same packaged shared reader. Sampling emits the usual normalized population and reproducible sample for the existing Vouching handoff. Reconciliation uses the usual reviewed account perimeter and sign relationship contract. Page caches are released in finally blocks; failed table inspection stops at its first unmapped monetary page and no longer rereads the entire PDF. Verbose mode suppresses low-level decoder debug dumps. Recoverable memory errors and forced worker termination have explicit persisted diagnostics. A termination code alone is not proof of memory exhaustion.

Model layout review can receive at most 300 words (100 characters each) from each of the first two and final pages, with coordinates, page dimensions and source SHA-256. The complete reconstruction runs locally and makes no direct model API calls. Sampling previews are capped at 10 postings and reconciliation previews at 20. The public five-language model-data sections and governed privacy manifests describe this boundary.

Synthetic acceptance covers continued registrations, multiline descriptions, exact source/layout review, stale-source and coordinate refusal, complete-population withholding, normalized lineage, real Excel sampling and bank reconciliation. The extra shared code root participates in preimport and replay integrity checks. Existing localized teaching content and input bytes remain unchanged; source bindings were regenerated and prior editorial/output judgments retained as historical evidence.

Reproduce the large-reader benchmark from the activated repository environment:

```sh
python tests/plugins/journal_pdf_memory_benchmark.py --output-dir /tmp/vera-pdf-benchmark
```

The original run on macOS processed a synthetic 951-page, 19,020-posting, 826,017-byte PDF in 8.29 seconds with 71.14 MiB peak RSS. This measures the shared reader, not the complete host process or an arbitrary PDF. The PDF page cache is bounded; accepted canonical posting storage still grows with the population size.

Nicola's actual journal files and installed-host case have not been tested: only the emailed report was available. The maintained adapter has a defined supported structure; exact coordinates and printed labels must be reviewed against those files. No claim is made that every text PDF is supported, that a plugin update reaches an already-open conversation, or that this release has been published to the OpenAI Marketplace.
