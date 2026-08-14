---
name: email-cliente
description: Use when drafting a client email from first-intake missing documents and clarifications for an accounting studio, keeping the message operational.
---

## Client workflow gate

Resume the exact Studio Archive `client-file-preparation` run whose reviewed
missing-items output supports the draft. Read only from that engagement and
write drafts only inside its `output_dir`. Do not invent a sibling output folder.

# Email Cliente

Use this workflow after `client-file-preparation` has produced missing or uncertain items.

When `model_handoff.json` exists, Codex and Cowork draft only from
`email_request` items in all declared pages. Those items are created only from
reviewed missing-request decisions and use `CLIENT-001`; do not turn
`missing_request_candidate` items, the inferred folder name, or the existing
local draft preview into email content before Apply. If no `email_request` item
exists, keep the draft pending review. Exact identifiers may remain in the
local professional artifact when the reviewed request itself requires them.

## Codex-Native Run UX

Before running helper scripts or write-heavy work, identify material choices that would change execution: problem framing, decision angle, risk appetite, scope boundaries, audience, evidence posture, mappings, cut-off, OCR, notification, or review assumptions. Ask only those unresolved choices in chat and wait for the answer. Generate choices from the actual inputs; do not offer named frameworks, regulators, document types, output packages, or issue categories unless the facts cue them or the user must supply a missing custom value. Do not run long or write-heavy execution under unconfirmed assumptions.

Default output policy: produce the richest normal package for the workflow. DOCX/Word, Excel/CSV, JSON audit, diagnostics, charts, packaged reports, review notes, and Codex-written review files are not choices to propose when they are natural outputs of that plugin; generate them whenever dependencies and source data permit. Ask only when an output is technically impossible, unsafe, or the user explicitly requests a reduced/debug run.

Preserve the currency shown in the reviewed evidence. If a currency is needed
but absent, follow the selected jurisdiction (`EUR` for Italy, `CHF` for Geneva
or Zurich, `GBP` for the United Kingdom) and state that assumption; do not
silently impose EUR on a Swiss, UK, or mixed case.

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

Use, in order:

- `model_handoff.json` and its `email_request` page items after Apply
- `templates/email_documenti_mancanti.md`

Use `02_documenti_mancanti_o_incerti.md` only as local reviewer evidence, not
as the default drafting input.

The full workflow writes the draft to:

- `04_bozza_email_cliente.md`

Before presenting the draft, read the missing/uncertain items and remove
questions that are not supported by the findings. The email is a client-facing
draft for review, not an automatic send action.
