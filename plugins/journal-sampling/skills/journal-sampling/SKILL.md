---
name: journal-sampling
description: Use when a user wants Codex to qualify and extract accounting journal entries from reviewed CSV, Excel, or bounded print-friendly Excel layouts, normalize exact monetary rows, and generate reproducible audit samples with diagnostics and an audit trail. This is a Codex workflow plugin; users should not operate the helper CLIs directly.
---

## Output Location Rule

Never write run outputs inside this Git workspace, `static/shared`, `protected_downloads`, or any GitHub Pages/static-site folder unless the task is explicitly plugin packaging/release. A user-data run must use the exact output root in the Studio Archive `client_engagement` context. Inspection and normalization use its `normalization` child; sampling uses its `sample` child. Do not invent a sibling output folder or run an unbound product CLI.

# Journal Sampling

Use this skill for audit sample-entry workflows where each customer's journal format may differ. The plugin is a guided Codex workflow: Codex inspects the files, asks only for unresolved mapping or sampling assumptions, runs deterministic helper scripts, reviews diagnostics, and delivers outputs.

The workflow is not Italian-only. Support the same five working locales used by the reconciliation plugin: `it`, `en`, `fr`, `de`, and `es`. Keep canonical data column names in English for stability, but speak to the user and write summaries in the chosen working language.

Detailed parser, mapping, sampling, and review-status notes live in `references/workflow-reference.md`. Load that reference only when the run needs extra detail beyond the workflow below.

## Codex-Native Run UX

Before running helper scripts or write-heavy work, identify material choices that would change execution: problem framing, decision angle, risk appetite, scope boundaries, audience, evidence posture, mappings, cut-off, OCR, notification, or review assumptions. Ask only those unresolved choices in chat and wait for the answer. Generate choices from the actual inputs; do not offer named frameworks, regulators, document types, output packages, or issue categories unless the facts cue them or the user must supply a missing custom value. Do not run long or write-heavy execution under unconfirmed assumptions.

Default output policy: produce the richest normal package for the workflow. DOCX/Word, Excel/CSV, JSON audit, diagnostics, charts, packaged reports, review notes, and Codex-written review files are not choices to propose when they are natural outputs of that plugin; generate them whenever dependencies and source data permit. Ask only when an output is technically impossible, unsafe, or the user explicitly requests a reduced/debug run.

Default currency policy: use Euro (`EUR`) unless the user or source file explicitly states another currency. Do not ask for currency when it is otherwise unresolved; record `EUR` as the assumption.

Use Codex-native UI artifacts as part of the workflow, not as optional
narration. At minimum:

1. Start with a visible markdown run checklist. Track intake, dependency check,
   inspection, user decisions, deterministic run, Codex review, and delivery.
2. Before helper scripts, show a Run Intake table with input paths, output
   folder, working language, document language, assumptions, and notification
   choice when the skill supports user run notifications.
3. After inspection, show a compact Decision Table for missing mappings,
   filters, review choices, unsupported files, or evidence assumptions. Ask
   only unresolved decisions and update the working recipe or assumptions
   yourself.
4. Before a long-running or write-heavy step, show an execution checkpoint or
   approval checkpoint with command intent, inputs, output folder, and expected
   artifacts. Ask for approval only when the step is external, destructive,
   approval-sensitive, or still depends on an unresolved material choice.
5. During execution, update checklist statuses as steps complete.
6. End with an Artifact Card listing output path, purpose, review status,
   unresolved items, and next action. When useful, create `codex_run_review.md`
   in the output folder from generated JSON/CSV/Markdown outputs; never edit
   plugin source or generated ZIPs during a run.

## Core Principle

Deterministic Python code owns extraction, normalization, filtering, sampling, and exports. Codex may inspect files, propose recipes, explain assumptions, and review diagnostics, but it must not silently override extracted rows or sampled rows with model reasoning.

The user should not interact directly with CLI scripts. Treat scripts as internal tools Codex runs on behalf of the user.

## First Run Workflow

1. Start with Studio Archive client intake. Call `list_studio_archive_clients`; do not infer the client from the journal filename. Resolve an existing registered client, explicitly register a confirmed existing scope, or create a client only after the user chooses New client. Explain that the original journal is preserved, obtain authorization for the controlled copy, and call `import_studio_client_document` with role `journal`. Use the returned imported path, `engagement_id`, `client_engagement`, and context path. If New Client onboarding is pending, preserve that status while preparing the journal; do not claim the relationship is active.
2. Ask for working language, source-document language, and any known filters only if they are not already provided or inferable. Do not ask for output richness. If the audit plan does not specify sample size or method, default to the deterministic script baseline: `random`, size `25`, seed `42`, and record those assumptions in the audit trail.
3. Run dependency checks from the plugin directory:

```bash
python scripts/check_dependencies.py
```

If requirements are missing, install from `requirements.txt` only when the environment allows it or explain what dependency capability is missing.

4. Run inspection to produce `inspection.json`, `suggested_recipe.json`, and
   `qualification_review_payload.json`:

```bash
python scripts/inspect_journal.py <imported-journal> --output-dir <client-run-output>/normalization --client-engagement <client-engagement.json> --language <it|en|fr|de|es> --document-language <auto|it|en|fr|de|es>
```

5. Read the inspection artifacts. Inspection never promotes a suggested mapping
   into the population. Review each source-family adapter, header/layout mapping,
   debit/credit or signed-amount convention, and localized number separators.
   Ask the user only for the smallest unresolved semantic decision.
6. Record the reviewed recipe in the work folder, not plugin source. The
   reviewed contract must explicitly bind the source artifact, adapter and
   version, field mapping, posting identity, carry-forward policy, currency,
   unit, and the disposition of every additional monetary-labelled or numeric
   column. Preserve the generated `mapping_sha256` and attach a complete
   `vera.reviewed_decision_receipt.v1` whose `decision_type` is
   `source_mapping` and whose content is the exact mapping contract. A free-text
   decision reference is not sufficient. If any bound field changes, rerun
   inspection with that recipe so a new digest is generated and review the new
   contract.
7. Normalize rows:

```bash
python scripts/normalize_journal.py <imported-journal> --output-dir <client-run-output>/normalization --recipe <client-run-output>/normalization/suggested_recipe.json --client-engagement <client-engagement.json> --language <it|en|fr|de|es> --document-language <auto|it|en|fr|de|es>
```

Require the complete normalization to retain the exact reviewed bytes as
`normalization_recipe.json`, with matching captured and original-source
receipts. Do not delete or replace the original reviewed recipe after the run.

8. Run deterministic sampling:

```bash
python scripts/run_sample.py <client-run-output>/normalization/normalized_journal.csv --output-dir <client-run-output>/sample --client-engagement <client-engagement.json> --method random --size 25 --language <it|en|fr|de|es>
```

The sample output folder must be absent or empty. Sampling stages every artifact
privately and publishes nothing to that folder unless upstream source and
normalization receipts freshly replay, raw input plus the exact retained recipe
freshly reproduces `normalized_journal.csv` and the material preparation
contract, CSV and XLSX both close, every sampled
material field closes from its normalized row to its CSV row and XLSX cell, and
the exact physical output allowlist closes. Do not treat a partial staging
failure as a deliverable.

9. Review `normalization_diagnostics.json`,
   `qualification_review_payload.json`, `reviewed_decisions.json`,
   `assurance_gates.json`, `assurance_envelope.json`, `sampling_audit.json`,
   `sample_reproducibility.json`, `sample_material_value_ledger.json`,
   `sample_assurance_gates.json`, `sample_assurance_envelope.json`, and
   `sample_output_receipts.json` before final delivery. Sampling is blocked unless
   every requested source is qualified, every monetary candidate emits exactly
   one canonical row, every additional monetary-labelled or numeric column is
   explicitly mapped or excluded, and the original sources, captured parse
   bytes, implementation, and normalized CSV still match their receipts.
   Report qualification status, separately
   excluded non-monetary rows, excluded and withheld monetary fields, source
   and preparation gates, population size after filters, sample size, and
   output paths. A passed deterministic preparation gate does not imply that
   sample sufficiency or an audit conclusion has been professionally reviewed.
   Treat the stage-zero manifest as pre-review only. A later save or apply is
   deliverable only after the MCP transaction archives the exact predecessor,
   freshly rederives all review counts/effects/statuses and gates, reseals the
   exact file/directory/mode contract, and replays the full successor chain.
   Semantic review must remain `not_assessed`, reporting `blocked`, publication
   `withheld`, and `report_ready=false`; do not translate accepted item
   decisions into `final_ready`.

## Supported V2 Inputs

- reviewed native Excel/CSV journals with explicit mappings;
- reviewed print-friendly Excel exports using the bounded
  `print_friendly.debit_credit_columns.v1` layout adapter.

Multi-worksheet workbooks currently abstain as a whole. No worksheet may be
silently ignored. Add a bounded multi-sheet adapter and representative fixtures
before such a workbook can qualify.

Unreadable containers emit no rows and record `failure_class=parser_failure`,
separately from readable sources whose structure is unsupported.

Generic text PDFs and OCR-only scanned PDFs are not qualified inputs. Text
position does not establish whether a trailing number is debit, credit, balance,
or a line total. Inspection returns `unsupported_source_layout` and emits no
rows unless a source-family-specific PDF adapter is implemented and tested.

## Language Policy

Ask for or infer two language assumptions:

- `language`: working/output language for Codex's questions and final summary; one of `it`, `en`, `fr`, `de`, `es`.
- `document_language`: source-document language used to interpret labels; one of `auto`, `it`, `en`, `fr`, `de`, `es`.

Store both assumptions in the generated recipe and preserve them in diagnostics/audit JSON. If the user writes in English, default `language=en` and `document_language=auto`. If the source files are clearly Italian, French, German, or Spanish, set `document_language` accordingly without asking unless ambiguity matters.

Starter prompts:

```text
IT: Usa Journal Sampling sulla cartella /percorso/input. Lingua: it. Lingua documenti: auto. Ispeziona i file, chiedimi solo le ambiguita essenziali e genera campione, diagnostiche e audit trail.
EN: Use Journal Sampling on /path/input. Language: en. Document language: auto. Inspect the files, ask only for essential ambiguities, then generate the sample, diagnostics, and audit trail.
FR: Utilise Journal Sampling sur /chemin/input. Langue: fr. Langue des documents: auto. Inspecte les fichiers, demande uniquement les ambiguïtés essentielles, puis génère l'échantillon, les diagnostics et l'audit trail.
DE: Verwende Journal Sampling für /pfad/input. Sprache: de. Dokumentsprache: auto. Prüfe die Dateien, frage nur wesentliche Unklarheiten ab und erstelle Stichprobe, Diagnostik und Audit-Trail.
ES: Usa Journal Sampling en /ruta/input. Idioma: es. Idioma de los documentos: auto. Inspecciona los archivos, pregunta solo por las ambigüedades esenciales y genera la muestra, los diagnósticos y el registro de auditoría.
```

## Mapping Recipe Rules

Codex can adjust the recipe JSON generated in the work folder. Use:

- `header_rows`: 1-indexed header rows for tabular files;
- `mapping`: source columns for `date`, `movement_number`, `line_number`,
  `account`, `account_desc`, `line_desc`, `debit`, `credit`, or `amount`;
- `posting_identity`: source-owned fields that define posting grain, with
  `source_row` permitted as a locator component rather than a fabricated
  movement number;
- `carry_forward_fields`: the exact fields for which reviewed carry-forward is
  allowed, including `line_desc` for print layouts when description ownership
  spans physical rows;
- `excluded_monetary_columns`: additional monetary-labelled or numeric fields
  that the reviewer has established are outside the posting amount;
- `currency`, `unit`, and `reported_increment`: explicit monetary context,
  preserving the source-reported increment per emitted row;
- per-file overrides under `files`.

Do not ask the user to edit JSON. Ask the user in business terms, then Codex updates the recipe and reruns the deterministic scripts.

## Sampling Rules

Available methods are `random`, `systematic`, `stratified`, and `mus`. Random sampling uses seed `42`; MUS uses deterministic cumulative amount thresholds. Always preserve `sampling_audit.json` with filters, method, requested size, population size, and output paths.

## Expected Outputs

- `inspection.json`;
- `suggested_recipe.json`;
- `qualification_review_payload.json`;
- `normalized_journal.csv`;
- `normalization_diagnostics.json`;
- `normalization_recipe.json`;
- `reviewed_decisions.json`;
- `assurance_gates.json`;
- `assurance_envelope.json`;
- `sample/journal_sample.csv`;
- `sample/journal_sample.xlsx` when XLSX dependencies are available;
- `sample/sampling_audit.json`;
- `sample/sample_reproducibility.json`;
- `sample/sample_material_value_ledger.json`;
- `sample/sample_assurance_gates.json`;
- `sample/sample_assurance_envelope.json`;
- `sample/sample_output_receipts.json`;
- `sample/assurance_history/<index>_<kind>/...` after each committed review
  successor;
- `sample/run_intake.json`;
- `sample/review_payload.json`;
- `sample/ui_decisions.json`;
- `sample/applied_decisions.json` after reviewer decisions are applied;
- `sample/final_artifacts.json`.

## MCP Review UI

When the local MCP server is available, prefer the OpenAI-style review handoff:

1. Read `run_intake.json`, `review_payload.json`, `ui_decisions.json`, and
   `final_artifacts.json` from the sample output folder.
2. Call `validate_journal_sampling_review` with `review_payload` before
   rendering.
3. If validation succeeds, call `render_journal_sampling_review` with the same
   payload objects so Codex can show the local HTML widget
   `ui://widget/journal-sampling-review.html`.
4. Use the widget to inspect sampling parameters, filters, population counts,
   sampled entries, and generated CSV/XLSX/JSON artifacts.
5. When the reviewer records actions in the widget or Codex collects decisions
   through fallback review, call `save_journal_sampling_decisions` so
   `ui_decisions.json` is validated and persisted in a replayed `save`
   successor. Reload the current `run_intake.json`, `ui_decisions.json`, and
   `final_artifacts.json` before the next action. When the reviewer is done,
   call `apply_journal_sampling_decisions` so `applied_decisions.json`,
   `sampling_audit.json`, `run_intake.json`, assurance gates/envelope,
   `final_artifacts.json`, and the output-set manifest are freshly closed in an
   `apply` successor. Accepted, edited, unclear, skipped, or
   document-requested items remain within the explicit assurance limits.

If MCP rendering is unavailable, fall back to a markdown review summary from
`review_payload.json`, `sampling_audit.json`, `journal_sample.csv`, and
`journal_sample.xlsx` when available. Do not change sampled rows by judgment
alone; change method, size, filters, mappings, or parser logic and rerun when
the sample basis is wrong. Keep review decisions pending unless they are
recorded in `ui_decisions.json` and consumed into `applied_decisions.json`.
Small setup choices should stay in chat or, when this conversation is in Plan
mode and the tool is available, native Plan-mode choices.

## Plugin Improvement Feedback

At the end of every completed or blocked plugin run, after reporting the deliverables, briefly identify concrete improvements that would have made this plugin run better. Base suggestions on the actual session, such as a new journal format, a brittle parser, a missing deterministic extraction script, a missing header-mapping rule, an unclear assumption, a needed fixture, output gaps, installation friction, or repeated manual steps.

When there is something useful to report, write a short improvement note with:

- observed gap;
- proposed improvement;
- why it matters;
- relevant input/output file names when available;
- suggested next engineering action.

Keep the improvement note local to chat or run artifacts. Do not submit it to
Mparanza automatically. When this workflow runs through Vera, use Vera's
consent-based Plugin Improvement Feedback process for any transmission.
