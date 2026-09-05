---
name: dati-fiscali-strutturati
description: "Use when Codex needs to extract or review structured fiscal fields from readable Italy, Geneva, Zurich, or UK customer-folder documents."
---

## Client workflow gate

Resume the exact Studio Archive `client-file-preparation` run that produced the
extracted documents. Read only from that engagement and write only inside its
`output_dir`; pass its absolute context path as `--client-engagement`. Do not
invent a sibling output folder.

# Dati Fiscali Strutturati

Use this workflow after text extraction has produced `extracted/documents.jsonl` and `extracted/pdf_text/`.

When `model_handoff.json` exists, Codex and Cowork must read every declared
page and use all `fiscal_field` items as the default model input. Each mapped
field remains present with its exact value and citation of at most 600
characters. Use its `source_document_ref` to load the exact local source only
when layout or evidence verification requires it; do not sample fields.

## Codex-Native Run UX

Before running helper scripts or write-heavy work, identify material choices that would change execution: problem framing, decision angle, risk appetite, scope boundaries, audience, evidence posture, mappings, cut-off, OCR, notification, or review assumptions. Reuse choices already established in the conversation or bound case records. Ask only for unresolved material choices and wait before their dependent work; continue independent authorized preparation. Generate choices from the actual inputs; do not offer named frameworks, regulators, document types, output packages, or issue categories unless the facts cue them or the user must supply a missing custom value. Do not infer missing required evidence, approval, or a material business decision. State routine provisional assumptions when the workflow permits them.

Default output policy: produce the richest normal package for the workflow. DOCX/Word, Excel/CSV, JSON audit, diagnostics, charts, packaged reports, review notes, and Codex-written review files are not choices to propose when they are natural outputs of that plugin; generate them whenever dependencies and source data permit. Ask only when an output is technically impossible, unsafe, or the user explicitly requests a reduced/debug run.

Default currency policy follows the selected jurisdiction: Italy uses `EUR`,
Geneva and Zurich use `CHF`, and the United Kingdom uses `GBP`. Preserve any
explicit source currency. For mixed cases, retain the currency attached to each
source instead of imposing one default.

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

## Run

From the plugin root:

```bash
python scripts/parse_fiscal_forms.py <client-run-output>/extracted --client-engagement <client_engagement_path>
```

The full `client-file-preparation` workflow already runs this automatically.

## Outputs

- `extracted/structured_fiscal_fields.csv`: one row per extracted field.
- `extracted/structured_fiscal_fields.jsonl`: same data for programmatic review.
- `08_dati_fiscali_strutturati.md`: readable summary by document type and file.

## Field Scope

- `F24`: codice tributo, anno riferimento, importi a debito/credito, righe tabellari when readable.
- `CU`: codici fiscali, years, common income/withholding/addizionale labels, numeric CU points when present in text.
- `730`: liquidation labels and readable righi/quadri such as `RC1`, `E1`, `RN`, `RX`.
- `Redditi PF`: common riepilogo labels and readable righi/quadri such as `RN1`, `RX1`, `LM`, `RE`, `RF`, `RG`.
- `Geneva/Zurich/CH`: salary certificates/Lohnausweis, tax returns, assessments, bank tax certificates, withholding-tax certificates when readable.
- `UK`: P60, P45, P11D, payslips, Self Assessment, HMRC notices, bank interest certificates, dividend vouchers, consolidated tax vouchers when readable.

## Scope

- Do not infer missing values.
- Treat row/quadri extraction as layout-dependent when the warning says `campo da verificare su layout originale`.
- Always cite source file and evidence/confidence when summarizing extracted values.
