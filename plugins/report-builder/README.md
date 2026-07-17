# Build Report Codex Plugin

[Source code](https://github.com/fabioannovazzi/app_files/tree/main/plugins/report-builder) · [GNU AGPLv3 License](https://github.com/fabioannovazzi/app_files/blob/main/LICENSE)

Build Report is a Codex-guided reporting workflow for variable finance and audit inputs. It replaces the old web report-builder flow with deterministic local scripts plus Codex review.

## What It Does

- Inspects `.xlsx`, `.xlsm`, `.csv`, readable `.pdf`, and ZIP inputs.
- Produces `inspection.json` and `suggested_recipe.json`.
- Lets Codex map tables, ask only essential questions, and write narrative fields in the recipe.
- Builds `report_tables.json`, `report_analysis.json`, `report_draft.md`, a styled `report.docx`, `report_audit.json`, and `used_recipe.json`.
- Writes a local review handoff: `run_intake.json`, `review_payload.json`, `ui_decisions.json`, and `final_artifacts.json` in the report output folder.
- Supports working locales `it`, `en`, `fr`, and `de`.

## What It Does Not Do

- It does not expose a web application.
- It does not call OpenAI or other model APIs from helper scripts.
- It does not OCR scanned PDFs in v1.

## Dependency Check

From the plugin directory:

```bash
python scripts/check_dependencies.py
```

Install only from `requirements.txt` when the environment allows it.

## Local MCP Review UI

After `scripts/build_report.py` completes, Codex can use the local MCP server to
validate and render the generated review payload:

- `validate_report_builder_review` validates `review_payload.json`.
- `render_report_builder_review` renders `ui://widget/report-builder-review.html`.

Use the widget for report sections, table evidence, narrative gaps, and the
generated Markdown/DOCX/JSON/XLSX artifacts. Keep simple intake and mapping
choices in Codex chat or native Plan-mode choices.
