---
name: dati-fiscali-strutturati
description: "Use when Codex needs to extract or review structured fiscal fields from readable Italy, Geneva, Zurich, or UK customer-folder documents."
---

## Output Location Rule

Never write run outputs inside this Git workspace, `static/shared`, `protected_downloads`, or any GitHub Pages/static-site folder unless the task is explicitly plugin packaging/release. For user-data runs, choose an output directory outside the repo, preferably a sibling `output/<plugin-name-or-run-id>` folder next to the user-provided input folder, and pass that path to every `--output-dir` or `--out` argument. If a script has a safe default next to the input folder, use that default instead of inventing `out/...` under the repo.

# Dati Fiscali Strutturati

Use this workflow after text extraction has produced `extracted/documents.jsonl` and `extracted/pdf_text/`.

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

## Run

From the plugin root:

```bash
python scripts/parse_fiscal_forms.py <cartella-output>/extracted
```

The full `client-intake` workflow already runs this automatically.

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
