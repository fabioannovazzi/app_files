---
name: journal-sampling
description: Use when a user wants Codex to extract accounting journal entries from variable Excel, CSV, print-friendly Excel, or text PDF formats, map columns, normalize deterministic rows, and generate reproducible audit samples with diagnostics and an audit trail. This is a Codex workflow plugin; users should not operate the helper CLIs directly.
---

## Output Location Rule

Never write run outputs inside this Git workspace, `static/shared`, `protected_downloads`, or any GitHub Pages/static-site folder unless the task is explicitly plugin packaging/release. For user-data runs, choose an output directory outside the repo, preferably a sibling `output/<plugin-name-or-run-id>` folder next to the user-provided input folder, and pass that path to every `--output-dir` or `--out` argument. If a script has a safe default next to the input folder, use that default instead of inventing `out/...` under the repo.

# Journal Sampling

Use this skill for audit sample-entry workflows where each customer's journal format may differ. The plugin is a guided Codex workflow: Codex inspects the files, asks only for unresolved mapping or sampling assumptions, runs deterministic helper scripts, reviews diagnostics, and delivers outputs.

The workflow is not Italian-only. Support the same four working locales used by the reconciliation plugin: `it`, `en`, `fr`, and `de`. Keep canonical data column names in English for stability, but speak to the user and write summaries in the chosen working language.

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

1. Ask for the input file or folder, working language, source-document language, and any known filters only if they are not already provided or inferable. Do not ask for output richness. If the audit plan does not specify sample size or method, default to the deterministic script baseline: `random`, size `25`, seed `42`, and record those assumptions in the audit trail.
2. Run dependency checks from the plugin directory:

```bash
python scripts/check_dependencies.py
```

If requirements are missing, install from `requirements.txt` only when the environment allows it or explain what dependency capability is missing.

3. Run inspection to produce `inspection.json` and `suggested_recipe.json`:

```bash
python scripts/inspect_journal.py <input-file-or-folder> --output-dir <output-dir> --language <it|en|fr|de> --document-language <auto|it|en|fr|de>
```

4. Read the inspection artifacts. If confidence is low or required fields are missing, ask the user for the smallest needed decision, such as the header row or which column is account/date/debit/credit.
5. If a mapping decision is needed, edit `suggested_recipe.json` in the work folder, not plugin source.
6. Normalize rows:

```bash
python scripts/normalize_journal.py <input-file-or-folder> --output-dir <output-dir> --recipe <output-dir>/suggested_recipe.json --language <it|en|fr|de> --document-language <auto|it|en|fr|de>
```

7. Run deterministic sampling:

```bash
python scripts/run_sample.py <output-dir>/normalized_journal.csv --output-dir <output-dir>/sample --method random --size 25 --language <it|en|fr|de>
```

8. Review `normalization_diagnostics.json` and `sampling_audit.json` before final delivery. Report parser confidence, missing fields, population size after filters, sample size, and output paths.

## Supported V1 Inputs

- good Excel/CSV journals;
- print-friendly Excel exports generated from PDFs;
- text PDFs where journal lines are extractable as text.

OCR-only scanned PDFs are not a v1 target. If inspection returns no rows for a scanned file, explain that OCR support is outside this plugin milestone rather than pretending the sample is complete.

## Language Policy

Ask for or infer two language assumptions:

- `language`: working/output language for Codex's questions and final summary; one of `it`, `en`, `fr`, `de`.
- `document_language`: source-document language used to interpret labels; one of `auto`, `it`, `en`, `fr`, `de`.

Store both assumptions in the generated recipe and preserve them in diagnostics/audit JSON. If the user writes in English, default `language=en` and `document_language=auto`. If the source files are clearly Italian, French, or German, set `document_language` accordingly without asking unless ambiguity matters.

Starter prompts:

```text
IT: Usa Journal Sampling sulla cartella /percorso/input. Lingua: it. Lingua documenti: auto. Ispeziona i file, chiedimi solo le ambiguita essenziali e genera campione, diagnostiche e audit trail.
EN: Use Journal Sampling on /path/input. Language: en. Document language: auto. Inspect the files, ask only for essential ambiguities, then generate the sample, diagnostics, and audit trail.
FR: Utilise Journal Sampling sur /chemin/input. Langue: fr. Langue des documents: auto. Inspecte les fichiers, demande uniquement les ambiguïtés essentielles, puis génère l'échantillon, les diagnostics et l'audit trail.
DE: Verwende Journal Sampling für /pfad/input. Sprache: de. Dokumentsprache: auto. Prüfe die Dateien, frage nur wesentliche Unklarheiten ab und erstelle Stichprobe, Diagnostik und Audit-Trail.
```

## Mapping Recipe Rules

Codex can adjust the recipe JSON generated in the work folder. Use:

- `header_rows`: 1-indexed header rows for tabular files;
- `mapping`: source columns for `date`, `movement_number`, `account`, `account_desc`, `line_desc`, `debit`, `credit`, or `amount`;
- per-file overrides under `files`.

Do not ask the user to edit JSON. Ask the user in business terms, then Codex updates the recipe and reruns the deterministic scripts.

## Sampling Rules

Available methods are `random`, `systematic`, `stratified`, and `mus`. Random sampling uses seed `42`; MUS uses deterministic cumulative amount thresholds. Always preserve `sampling_audit.json` with filters, method, requested size, population size, and output paths.

## Expected Outputs

- `inspection.json`;
- `suggested_recipe.json`;
- `normalized_journal.csv`;
- `normalization_diagnostics.json`;
- `sample/journal_sample.csv`;
- `sample/journal_sample.xlsx` when XLSX dependencies are available;
- `sample/sampling_audit.json`;
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
   `ui_decisions.json` is validated and persisted. When the reviewer is done,
   call `apply_journal_sampling_decisions` so `applied_decisions.json` and
   `final_artifacts.json` reflect accepted, edited, unclear, skipped, or
   document-requested items before treating the sample as reviewed.

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

Keep the improvement note local to chat or run artifacts.
