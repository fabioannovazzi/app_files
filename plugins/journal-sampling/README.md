# Journal Sampling

[Source code](https://github.com/fabioannovazzi/app_files/tree/main/plugins/journal-sampling) · [MIT License](https://github.com/fabioannovazzi/app_files/blob/main/LICENSE)

Journal Sampling is a Codex workflow plugin for extracting accounting journal entries from variable Excel, CSV, print-style Excel, and text PDF formats, then creating reproducible audit samples.

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

1. Confirm input file or folder, sample size, sampling method, working language, source-document language, and filters.
2. Run `scripts/inspect_journal.py` to create `inspection.json` and `suggested_recipe.json`.
3. Resolve only essential mapping ambiguities, then update the work-folder recipe.
4. Run `scripts/normalize_journal.py`.
5. Run `scripts/run_sample.py`.
6. Review diagnostics and deliver normalized rows, sample files, audit trail,
   and MCP review handoff files.

## Local MCP Review UI

Sample runs emit `run_intake.json`, `review_payload.json`, `ui_decisions.json`,
and `final_artifacts.json` in the sample output folder.

- `validate_journal_sampling_review` validates the review payload.
- `render_journal_sampling_review` renders the local widget
  `ui://widget/journal-sampling-review.html`.
- The widget focuses on sampling parameters, filters, population counts,
  sampled entries, and generated CSV/XLSX/JSON artifacts.

If MCP rendering is unavailable, Codex should use the JSON payloads plus
`sampling_audit.json`, `journal_sample.csv`, and `journal_sample.xlsx` as the
fallback review surface.

## Supported Languages

Working/output language supports `it`, `en`, `fr`, and `de`. Source-document language can be `auto`, `it`, `en`, `fr`, or `de`.

## Release

After changing plugin source, rebuild and verify the package from repo source:

```bash
.venv/bin/python scripts/build_codex_plugin_zip.py journal-sampling
.venv/bin/python scripts/build_codex_plugin_zip.py journal-sampling --check
```
