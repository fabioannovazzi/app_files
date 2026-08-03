# Journal Sampling

[Source code](https://github.com/fabioannovazzi/app_files/tree/main/plugins/journal-sampling) · [GNU AGPLv3 License](https://github.com/fabioannovazzi/app_files/blob/main/LICENSE)

Journal Sampling is a Codex workflow plugin for qualifying reviewed Excel, CSV,
and bounded print-style Excel journal layouts, preserving exact monetary text,
and creating reproducible audit samples from a complete qualified population.

The user experience is a guided Codex run. Codex inspects the files, asks only for unresolved mapping or sampling assumptions, runs deterministic helper scripts, reviews diagnostics, and reports the outputs. Users should not operate the helper CLI scripts directly.

## Source Of Truth

Editable plugin source lives in:

```text
plugins/journal-sampling
```

Do not edit downloaded plugin folders, ZIP contents, or Codex cache copies as source.

## Runtime Dependencies

Check dependencies from the plugin root before a workflow run:

```bash
python scripts/check_dependencies.py
```

Install only from the declared requirements file when the environment allows it:

```bash
python -m pip install -r requirements.txt
```

## First Run Shape

1. In Studio Archive, list clients, resolve existing versus new without using
   the filename as identity, register/create only after the user's choice, and
   create or select one durable engagement. Obtain authorization to import the
   journal as an immutable receipt and retain its exact `input_id`. Import does
   not create a run.
2. Prepare an idempotent `journal-sampling` run from that `input_id`, then start
   it. Load its portable client-engagement context and execute only the bound
   run-local journal path; write only to its `outputs/` directory.
3. Confirm sample size, sampling method, working language,
   source-document language, and filters.
4. Run `scripts/inspect_journal.py` with `--client-engagement` and the exact
   context `normalization` output to create `inspection.json`,
   `suggested_recipe.json`, and `qualification_review_payload.json`.
5. Resolve only essential mapping ambiguities, then bind the exact
   source-family mapping contract to its generated digest and a complete
   reviewed-decision receipt in the work-folder recipe. The contract includes
   posting identity, carry-forward, currency, unit, and the disposition of
   every monetary-labelled or numeric column.
6. Run `scripts/normalize_journal.py` with the same context.
7. Run `scripts/run_sample.py` with the same context and its exact `sample`
   output; it verifies the adjacent normalization
   diagnostics, replayable assurance envelope, independent gates, qualified row
   closure, implementation receipts, original source receipts, retained
   reviewed-recipe bytes, and normalized CSV receipt. It then freshly reruns
   normalization from the raw journal and that exact recipe and requires a
   byte-identical canonical CSV and material preparation contract. The sample
   output folder must be absent or empty.
8. Review diagnostics and the normalized rows, reviewed decisions,
   sample-stage assurance gates and envelope, sample files, the all-row material
   value ledger, output receipts, audit trail, and MCP review handoff files.
   Complete every write-producing MCP review transaction.
9. After the last output write, finalize the customer-folder run by declaring
   every physical output with a unique artifact ID, concrete purpose, audience,
   and media type. The exact downstream contract includes
   `prepared.normalized_journal`, `internal.normalization_diagnostics`, and
   `prepared.journal_sample_csv`. Review the final declaration and complete the
   run; record a failure or cancellation instead of treating partial output as
   available.

The customer folder, not a machine-local pointer, is the durable source of
truth. It contains the client and engagement manifests, immutable input
receipt, exact run input manifest, lifecycle, outputs, and artifact manifest.
Current absolute paths can therefore be recovered after a folder rename or in
a fresh local Studio Archive state.

## Journal Sampling to Check Entries

The normalized population, diagnostics, and sample are all intentional, but
they serve different purposes. The normalized population makes preparation
reproducible; diagnostics records whether that population qualified; the sample
selects the exact entries to check.

For each support delivery, Studio Archive imports or reuses one
content-addressed immutable `support` receipt and prepares a separate Check
Entries run. That run binds the exact
Journal Sampling artifacts and that evidence batch. Check Entries validates the
full prepared lineage but checks only the rows in the bound sample. A materially
different second ZIP or PDF batch creates another run; an intentionally
separate identical selection uses the explicit new-run option. It never expands
the first run's input manifest.

Normalization parses captured bytes and preserves exact Decimal text, currency,
unit, source-reported increment (including consistent native XLSX display
scale), worksheet, and physical row. It fails closed if captured bytes do not
match the source receipt, an additional numeric field is unresolved, a reviewed
carry-forward policy is contradicted, or a workbook has multiple worksheets
without a bounded adapter. Passed source and preparation gates do not claim
professional review of sample sufficiency or conclusions.

Every complete normalization retains the exact reviewed recipe as
`normalization_recipe.json`, binds both its captured receipt and its original
source receipt, and exposes `scripts/replay_normalization.py` for isolated
`-I -B` re-performance. The replay also reproduces reviewed decisions, gates,
the assurance envelope, and the qualification-review payload. The exact
execution boundary is 24 files: 16 plugin entry/core/MCP/widget/configuration
files and 8 shared Vera assurance files. Unexpected caches, links, special
files, directories, or executable/configuration files fail before local
imports. These hashes prove local execution consistency, not package publisher
or reviewer authority.

Codex runs the isolated replay inside the same still-running customer run:

```bash
python -I -B scripts/replay_normalization.py \
  <client-run-output>/normalization/normalized_journal.csv \
  --diagnostics <client-run-output>/normalization/normalization_diagnostics.json \
  --receipt-out <client-run-output>/normalization/replay_receipt.json \
  --client-engagement <customer-run>/context.json
```

Sampling is finalized transactionally. It first writes into a private sibling
staging directory, freshly replays upstream normalization and original-source
receipts, then promotes the complete output only after all checks pass. CSV and
XLSX are both required. Every canonical field of every sampled row is addressed
from its normalized prepared row to its CSV row and XLSX cell in
`sample_material_value_ledger.json`. `sample_output_receipts.json` declares the
exact physical file and directory set, file and directory modes, and current
byte hash and size of every payload file; missing, unexpected, linked, special,
or changed entries fail closure. The initial stage uses the
`sample_stage_finalization_pre_review` boundary. Each real save or apply creates
an exact `assurance_history/<index>_<kind>` predecessor archive and reseals a
new `save` or `apply` successor only after fresh replay. Archived stages are
single-link, immutable inputs to the successor chain and arbitrary files are
never archived. `sample_reproducibility.json` is deliberately run-independent, while
timestamps, output paths, and review run IDs remain in run-scoped artifacts.
These fixed checks are deterministic because byte identity, cell addresses,
canonical Decimal syntax, and output membership are mechanically verifiable.
They do not decide sample sufficiency or an audit conclusion.

## Local MCP Review UI

Sample runs emit `run_intake.json`, `review_payload.json`, `ui_decisions.json`,
`final_artifacts.json`, `sample_assurance_gates.json`,
`sample_assurance_envelope.json`, `sample_material_value_ledger.json`,
`sample_reproducibility.json`, and `sample_output_receipts.json` in the sample
output folder.

- `validate_journal_sampling_review` validates the review payload.
- `render_journal_sampling_review` renders the local widget
  `ui://widget/journal-sampling-review.html`.
- `save_journal_sampling_decisions` persists decisions, archives the replayed
  predecessor, refreshes run/audit/final state, receipts, gates, and the exact
  output manifest, then replays the whole successor before commit.
- `apply_journal_sampling_decisions` additionally rederives effects, counts,
  blockers, revisions, and application status from the persisted review items
  and decisions before committing an apply successor.
- The widget focuses on sampling parameters, filters, population counts,
  sampled entries, and generated CSV/XLSX/JSON artifacts.

Review persistence never establishes professional sample sufficiency. Even a
complete accepted decision set is
`review_applied_with_assurance_limits`, not `final_ready`; semantic review
remains `not_assessed`, reporting remains `blocked`, publication remains
`withheld`, and `report_ready` remains false.

If MCP rendering is unavailable, Codex should use the JSON payloads plus
`sampling_audit.json`, `journal_sample.csv`, and `journal_sample.xlsx` as the
fallback review surface.

## Supported Languages

Working/output language supports `it`, `en`, `fr`, `de`, and `es`. Source-document language can be `auto`, `it`, `en`, `fr`, `de`, or `es`.

## Release

After changing plugin source, rebuild and verify the package from repo source:

```bash
.venv/bin/python scripts/build_codex_plugin_zip.py journal-sampling
.venv/bin/python scripts/build_codex_plugin_zip.py journal-sampling --check
```
