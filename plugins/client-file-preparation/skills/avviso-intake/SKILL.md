---
name: avviso-intake
description: Use when creating a first intake memo for notices, agency communications, avvisi, cartelle, HMRC letters, or Swiss cantonal tax letters found in a customer folder, extracting practical references.
---

## Client workflow gate

Resolve the exact Studio Archive client and engagement before reading or writing
case material. Resume or prepare a `client-file-preparation` run, use only its
managed input folder and `output_dir`, and pass its absolute context path as
`--client-engagement`. Do not invent a sibling output folder.

# Avviso Intake

Use this workflow when a customer folder contains an avviso, comunicazione, cartella, Agenzia file, HMRC letter, Swiss cantonal tax letter, or similar document.

## Codex-Native Run UX

Before running helper scripts or write-heavy work, identify material choices that would change execution: problem framing, decision angle, risk appetite, scope boundaries, audience, evidence posture, mappings, cut-off, OCR, notification, or review assumptions. Reuse choices already established in the conversation or bound case records. Ask only for unresolved material choices and wait before their dependent work; continue independent authorized preparation. Generate choices from the actual inputs; do not offer named frameworks, regulators, document types, output packages, or issue categories unless the facts cue them or the user must supply a missing custom value. Do not infer missing required evidence, approval, or a material business decision. State routine provisional assumptions when the workflow permits them.

Default output policy: produce the richest normal package for the workflow. DOCX/Word, Excel/CSV, JSON audit, diagnostics, charts, packaged reports, review notes, and Codex-written review files are not choices to propose when they are natural outputs of that plugin; generate them whenever dependencies and source data permit. Ask only when an output is technically impossible, unsafe, or the user explicitly requests a reduced/debug run.

Default currency policy follows the document and jurisdiction: Italy uses
`EUR`, Swiss cantonal matters normally use `CHF`, and UK matters normally use
`GBP`. Preserve an explicit source currency. Ask only when an unresolved
currency would materially change the intake; otherwise record the applicable
jurisdiction default as an assumption.

Keep progress and handoff concise. Use a checklist, Run Intake table, Decision
Table, or Artifact Card when it helps the user review complex work; their chat
format is optional. Preserve all required saved mappings, review decisions,
validation records, and artifacts. Resolve material choices before dependent
execution and continue independent authorized work while awaiting an answer.
Obtain authorization for external, destructive, or approval-sensitive actions
when not already given, and preserve workflow-specific approval gates.
At delivery, link outputs and state their purpose, review status, unresolved
items, and next action. Create `codex_run_review.md` when a durable review index
is useful; never edit plugin source or generated ZIPs during a user-data run.

## Scope

- Extract practical elements only: file name, possible dates, possible amounts, protocol references, and documents to recover.
- State clearly when an element is "da verificare".

## Run

The avviso intake is included in the full workflow:

```bash
python ../../scripts/build_file_preparation_outputs.py <managed-input-folder> --client-engagement <client_engagement_path> --year <anno>
```

If the command is interrupted, rerun it with the same arguments and output
folder. The workflow resumes integrity-checked extraction checkpoints for
unchanged source files and rejects stale or incompatible partial runs.

Review:

- `avviso/avviso_intake_memo.md`
- `avviso/deadlines_and_amounts.csv`

For persisted Model review, validate once and reuse the returned opaque review
reference for render, save, and apply. Do not resend `review_payload.json`
merely to carry state. Routine high-confidence inventory rows omit extracted
text previews after deterministic mapping; exception rows retain a bounded
preview, and every row keeps its exact local source reference.
