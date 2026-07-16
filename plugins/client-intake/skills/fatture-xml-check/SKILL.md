---
name: fatture-xml-check
description: "Use when formally checking Italian FatturaPA XML files in a customer folder: parse invoice metadata, create CSV summaries, identify malformed XML, date issues, and duplicate candidates."
---

## Output Location Rule

Never write run outputs inside this Git workspace, `static/shared`, `protected_downloads`, or any GitHub Pages/static-site folder unless the task is explicitly plugin packaging/release. For user-data runs, choose an output directory outside the repo, preferably a sibling `output/<plugin-name-or-run-id>` folder next to the user-provided input folder, and pass that path to every `--output-dir` or `--out` argument. If a script has a safe default next to the input folder, use that default instead of inventing `out/...` under the repo.

# Fatture XML Check

Use this workflow for formal checks on e-fattura XML files.

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

- Only report formal facts: parsed fields, malformed files, missing fields, date fuori periodo, and duplicate candidates.

## Run

From this skill directory, use the plugin script:

```bash
python ../../scripts/parse_fatturapa_xml.py <cartella> --year <anno> --out <cartella-output>/fatture
```

## Outputs

- `fatture_summary.csv`: one row per XML with supplier, customer, date, number, amount, currency, document type, IVA summary, natura codes, withholding, stamp duty, payment methods and anomalies.
- `fatture_summary.jsonl`: same records in JSONL form when the full intake workflow is used.
- `duplicate_candidates.csv`: likely duplicates based on supplier, number, date and amount.
- `formal_anomalies.md`: readable anomaly memo for the studio.
