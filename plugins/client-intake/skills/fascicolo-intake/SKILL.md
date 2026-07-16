---
name: fascicolo-intake
description: "Use when preparing the first intake of a customer folder for Italy, Geneva, Zurich, or the UK: scan files, classify documents, identify missing or uncertain material, run formal checks, and produce structured outputs."
---

## Output Location Rule

Never write run outputs inside this Git workspace, `static/shared`, `protected_downloads`, or any GitHub Pages/static-site folder unless the task is explicitly plugin packaging/release. For user-data runs, choose an output directory outside the repo, preferably a sibling `output/<plugin-name-or-run-id>` folder next to the user-provided input folder, and pass that path to every `--output-dir` or `--out` argument. If a script has a safe default next to the input folder, use that default instead of inventing `out/...` under the repo.

# Fascicolo Intake

Use this workflow when the user asks to prepare a first istruttoria for a customer folder, fascicolo cliente, 730/Redditi package, CU/F24/document package, Geneva or Zurich tax folder, UK Self Assessment folder, or mixed folder for an accounting studio.

This skill is not just a wrapper around a script. The script creates the raw evidence; Codex must then read that evidence and produce an internal synthesis for the studio.

## Codex-Native Run UX

Before running helper scripts or write-heavy work, identify material choices that would change execution: problem framing, decision angle, risk appetite, scope boundaries, audience, evidence posture, mappings, cut-off, OCR, notification, or review assumptions. Ask only those unresolved choices in chat and wait for the answer. Generate choices from the actual inputs; do not offer named frameworks, regulators, document types, output packages, or issue categories unless the facts cue them or the user must supply a missing custom value. Do not run long or write-heavy execution under unconfirmed assumptions.

Default output policy: produce the richest normal package for the workflow. DOCX/Word, Excel/CSV, JSON audit, diagnostics, charts, packaged reports, review notes, and Codex-written review files are not choices to propose when they are natural outputs of that plugin; generate them whenever dependencies and source data permit. Ask only when an output is technically impossible, unsafe, or the user explicitly requests a reduced/debug run.

Default currency policy: use Euro (`EUR`) unless the user or source file explicitly states another currency. Do not ask for currency when it is otherwise unresolved; record `EUR` as the assumption.

Use Codex-native UI artifacts as part of the workflow, scaled to this
sub-workflow. Start with a visible checklist, show a Run Intake table for the
folder/year/output assumptions, ask unresolved decisions through a compact
Decision Table, use execution checkpoints before write-heavy steps, ask for
approval only for external, destructive, or materially unresolved steps, update
the checklist while working, and end with an Artifact Card listing output paths,
review status, unresolved items, and next action. When useful, create
`codex_run_review.md` in the output folder from generated outputs; never edit
plugin source or generated ZIPs during a run.

## Scope

- Produce operational findings: inventory, missing or uncertain documents, formal anomalies, questions for the client, and internal studio questions.
- Distinguish what was read from a file name, what was extracted from text/XML, and what remained unreadable.
- Phrase uncertain items as "da verificare", "da confermare", or "classificazione basata sul nome file/testo estratto".

## Run

From the plugin root, first check dependencies:

```bash
python scripts/check_dependencies.py --folder <cartella-cliente>
```

If core PDF dependencies are missing, ask the user to install them:

```bash
python -m pip install -r requirements.txt
```

If OCR dependencies are missing and the folder contains scans or images, recommend:

```bash
python -m pip install -r requirements-ocr.txt
```

Use OCR automatically when dependencies are available and relevant. If OCR is
not available, continue with the text-readable pass and record unreadable scans
as a limitation unless the user explicitly asks to pause for OCR setup.

Then run the local script from the plugin root:

```bash
python scripts/build_intake_outputs.py <cartella-cliente> --year <anno> --out <cartella-output>
```

If the user does not provide `--out`, use a sibling `output/fascicolo-intake`
folder next to `<cartella-cliente>`.

## Codex Review Step

After the script finishes:

1. Read the generated markdown and CSV evidence files.
2. Check whether the findings are only filename-based or supported by parsed XML/text.
3. Read `run_intake.json` and `review_payload.json`. The review payload is the
   shared UI contract for document inventory, uncertain files, missing-document
   requests, extracted fiscal fields, draft memo, and draft client email.
4. When `clientIntakeWidgets` MCP tools are available, use the OpenAI-style UI
   path: call `validate_client_intake_review` with the complete payload, then
   call `render_client_intake_review` once validation succeeds. The MCP server
   validates and renders the HTML widget; Python scripts only produce the
   structured payload.
5. If a local UI or fallback review is used, persist user decisions in
   `ui_decisions.json` before revising final outputs.
6. Write `07_scheda_codex_per_studio.md` in the output folder.
7. Keep the synthesis short and operational.

The synthesis should answer:

- What did the folder contain?
- What is probably missing or uncertain?
- Which anomalies are formal and should be reviewed?
- What should be asked to the client?
- What should the studio inspect directly?
- What did Codex not actually read or verify?

## Expected Outputs

- `00_fascicolo_index.md`
- `01_document_inventory.csv`
- `02_documenti_mancanti_o_incerti.md`
- `03_domande_interne_studio.md`
- `04_bozza_email_cliente.md`
- `05_anomalie_formali.md`
- `06_memo_istruttoria.md`
- `07_scheda_codex_per_studio.md`
- `08_dati_fiscali_strutturati.md`
- `run_intake.json`
- `review_payload.json`
- `ui_decisions.json`
- `final_artifacts.json`
- `duplicate_candidates.csv`
- `extracted/documents.jsonl`
- `extracted/document_extraction.csv`
- `extracted/extraction_report.md`
- `extracted/structured_fiscal_fields.csv`
- `extracted/structured_fiscal_fields.jsonl`
- `extracted/fatture_xml.jsonl`
- `fatture/fatture_summary.csv`
- `fatture/duplicate_candidates.csv`
- `fatture/formal_anomalies.md`
- `avviso/avviso_intake_memo.md`
- `avviso/deadlines_and_amounts.csv`

## Final Response

Summarize:

- output folder;
- number of files analyzed;
- categories found;
- missing/uncertain items;
- XML anomalies or duplicate candidates;
- concise note on unreadable files, unresolved assumptions, and the output folder.
