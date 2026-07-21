---
name: avviso-intake
description: Use when creating a first intake memo for notices, agency communications, avvisi, cartelle, HMRC letters, or Swiss cantonal tax letters found in a customer folder, extracting practical references.
---

## Output Location Rule

Never write run outputs inside this Git workspace, `static/shared`, `protected_downloads`, or any GitHub Pages/static-site folder unless the task is explicitly plugin packaging/release. For user-data runs, choose an output directory outside the repo, preferably a sibling `output/<plugin-name-or-run-id>` folder next to the user-provided input folder, and pass that path to every `--output-dir` or `--out` argument. If a script has a safe default next to the input folder, use that default instead of inventing `out/...` under the repo.

# Avviso Intake

Use this workflow when a customer folder contains an avviso, comunicazione, cartella, Agenzia file, HMRC letter, Swiss cantonal tax letter, or similar document.

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

- Extract practical elements only: file name, possible dates, possible amounts, protocol references, and documents to recover.
- State clearly when an element is "da verificare".

## Run

The avviso intake is included in the full workflow:

```bash
python ../../scripts/build_file_preparation_outputs.py <cartella-cliente> --year <anno>
```

Review:

- `avviso/avviso_intake_memo.md`
- `avviso/deadlines_and_amounts.csv`
