---
name: email-cliente
description: Use when drafting a client email from first-intake missing documents and clarifications for an accounting studio, keeping the message operational.
---

## Output Location Rule

Never write run outputs inside this Git workspace, `static/shared`, `protected_downloads`, or any GitHub Pages/static-site folder unless the task is explicitly plugin packaging/release. For user-data runs, choose an output directory outside the repo, preferably a sibling `output/<plugin-name-or-run-id>` folder next to the user-provided input folder, and pass that path to every `--output-dir` or `--out` argument. If a script has a safe default next to the input folder, use that default instead of inventing `out/...` under the repo.

# Email Cliente

Use this workflow after `client-file-preparation` has produced missing or uncertain items.

## Codex-Native Run UX

Before running helper scripts or write-heavy work, identify material choices that would change execution: problem framing, decision angle, risk appetite, scope boundaries, audience, evidence posture, mappings, cut-off, OCR, notification, or review assumptions. Ask only those unresolved choices in chat and wait for the answer. Generate choices from the actual inputs; do not offer named frameworks, regulators, document types, output packages, or issue categories unless the facts cue them or the user must supply a missing custom value. Do not run long or write-heavy execution under unconfirmed assumptions.

Default output policy: produce the richest normal package for the workflow. DOCX/Word, Excel/CSV, JSON audit, diagnostics, charts, packaged reports, review notes, and Codex-written review files are not choices to propose when they are natural outputs of that plugin; generate them whenever dependencies and source data permit. Ask only when an output is technically impossible, unsafe, or the user explicitly requests a reduced/debug run.

Default currency policy: use Euro (`EUR`) unless the user or source file explicitly states another currency. Do not ask for currency when it is otherwise unresolved; record `EUR` as the assumption.

Use Codex-native UI artifacts as part of the workflow, scaled to this
sub-workflow. Start with a visible checklist, show a Run Intake table for the
source files, output path, tone assumptions, and reviewer expectations, ask
unresolved decisions through a compact Decision Table, use execution checkpoints
before write-heavy steps, ask for approval only for external, destructive, or
materially unresolved steps, update the checklist while working, and end with an
Artifact Card listing output paths, review status, unresolved items, and next
action. When useful, create `codex_run_review.md` in the output folder from
generated outputs; never edit plugin source or generated ZIPs during a run.

## Rules

- Keep the email concise and professional.
- Ask for documents and confirmations.
- Keep the output as a studio draft.

## Source File

Use:

- `02_documenti_mancanti_o_incerti.md`
- `templates/email_documenti_mancanti.md`

The full workflow writes the draft to:

- `04_bozza_email_cliente.md`

Before presenting the draft, read the missing/uncertain items and remove
questions that are not supported by the findings. The email is a client-facing
draft for review, not an automatic send action.
