---
name: fatture-xml-check
description: "Use when formally checking Italian FatturaPA XML files in a customer folder: parse invoice metadata, create CSV summaries, identify malformed XML, date issues, and duplicate candidates."
---

## Client workflow gate

Resolve the exact Studio Archive client and engagement, import the XML source
into its managed input folder, and resume or prepare a
`client-file-preparation` run. Write only inside its `output_dir` and pass its
absolute context path as `--client-engagement`. Do not invent a sibling output
folder.

# Fatture XML Check

Use this workflow for formal checks on e-fattura XML files.

When `model_handoff.json` exists, Codex and Cowork use only `xml_anomaly` and
`xml_duplicate_group` items from every declared page for XML synthesis. These
items contain document refs, anomaly text, and opaque group refs; they omit
supplier/customer names, customer tax identifiers, and raw duplicate keys.
Read exact local XML or summaries only when the professional check needs a
party field or the source evidence itself.

## Codex-Native Run UX

Before running helper scripts or write-heavy work, identify material choices that would change execution: problem framing, decision angle, risk appetite, scope boundaries, audience, evidence posture, mappings, cut-off, OCR, notification, or review assumptions. Reuse choices already established in the conversation or bound case records. Ask only for unresolved material choices and wait before their dependent work; continue independent authorized preparation. Generate choices from the actual inputs; do not offer named frameworks, regulators, document types, output packages, or issue categories unless the facts cue them or the user must supply a missing custom value. Do not infer missing required evidence, approval, or a material business decision. State routine provisional assumptions when the workflow permits them.

Default output policy: produce the richest normal package for the workflow. DOCX/Word, Excel/CSV, JSON audit, diagnostics, charts, packaged reports, review notes, and Codex-written review files are not choices to propose when they are natural outputs of that plugin; generate them whenever dependencies and source data permit. Ask only when an output is technically impossible, unsafe, or the user explicitly requests a reduced/debug run.

Default currency policy: use Euro (`EUR`) unless the user or source file explicitly states another currency. Do not ask for currency when it is otherwise unresolved; record `EUR` as the assumption.

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

- Only report formal facts: parsed fields, malformed files, missing fields, date fuori periodo, and duplicate candidates.

## Run

From this skill directory, use the plugin script:

```bash
python ../../scripts/parse_fatturapa_xml.py <managed-input-folder> --year <anno> --out <client-run-output>/fatture --client-engagement <client_engagement_path>
```

## Outputs

- `fatture_summary.csv`: one row per XML with supplier, customer, date, number, amount, currency, document type, IVA summary, natura codes, withholding, stamp duty, payment methods and anomalies.
- `fatture_summary.jsonl`: same records in JSONL form when the full intake workflow is used.
- `duplicate_candidates.csv`: likely duplicates based on supplier, number, date and amount.
- `formal_anomalies.md`: readable anomaly memo for the studio.
