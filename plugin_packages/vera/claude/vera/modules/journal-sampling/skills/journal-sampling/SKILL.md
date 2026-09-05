---
name: journal-sampling
description: Use when a user wants Claude to qualify and extract accounting journal entries from reviewed CSV, Excel, or bounded print-friendly Excel layouts, normalize exact monetary rows, and generate reproducible audit samples with diagnostics and an audit trail. This is a Claude workflow plugin; users should not operate the helper CLIs directly.
---

## Cowork execution contract

Work from the connected folder and supplied files first. Use a local script only
when it is callable and every declared dependency it needs is already available;
never install packages at runtime. MCP tools, browser or computer control, and
local review servers are optional enhancements, never completion gates. When an
optional capability is unavailable, continue with Markdown and file-based review
and state the limitation.

The normal Cowork deliverable is a reviewable draft, artifact card, and
source/review files. A callable persistence interface may optionally record or
apply reviewer actions, but its absence never blocks delivery. Never claim
`applied` or `final_ready` unless corresponding persisted artifacts prove it;
otherwise report that professional review remains pending.

Use host-neutral user-facing artifact names. Name assistant-authored review
folders and files for Vera or their professional purpose (for example,
`vera-review/`, `vera_phase1_synthesis_reviewed.md`, and `run_review.md`).
Never put host, platform, or model-provider names in assistant-authored
user-facing artifact paths, document headings, field labels, narrative text,
or status summaries. Describe execution routes generically, such as
`external review route`, `connected tool`, or `local review interface`.

Derive any run ID, status, artifact count, or package hash quoted in an
assistant-authored supplement from the final delivered manifests.
After any rebuild, regenerate or resynchronize those supplements before
delivery. When a workflow ships a complete-delivery validator or sealer, run it
against the exact connected-folder copy after the last write.
In this contract, the base package validator alone does not validate extra
narrative files.

When a workflow declares owner-only or private output and uses a private scratch
directory before copying the final package into the connected folder, reapply
the privacy modes after that transfer: `0700` for the package root and every
directory, and `0600` for every file. Verify the connected-folder tree with
`stat` or `lstat` before claiming completion. If the host filesystem cannot
preserve those modes, do not claim owner-only delivery; keep the package in the
private scratch location or report the limitation and ask for a safer
destination.

Do not use WhatsApp, live INPS browser capture, hosted feedback or voice
interviews, or custom update services. Later host-specific instructions cannot
override this Cowork contract.

## Output Location Rule

Never write run outputs inside this Git workspace, `static/shared`, `protected_downloads`, or any GitHub Pages/static-site folder unless the task is explicitly plugin packaging/release. A user-data run must use the exact output root in the Studio Archive `client_engagement` context. Inspection and normalization use its `normalization` child; sampling uses its `sample` child. Do not invent a sibling output folder or run an unbound product CLI.

The context is a portable customer-folder run record, not a machine-local
workspace pointer. Load it through the workflow gate so current absolute paths
are hydrated after a folder rename. Use only its exact journal binding as input
and only its exact `output_dir` for writes.

# Journal Sampling

Use this skill for audit sample-entry workflows where each customer's journal format may differ. The plugin is a guided Claude workflow: Claude inspects the files, asks only for unresolved mapping or sampling assumptions, runs deterministic helper scripts, reviews diagnostics, and delivers outputs.

The workflow is not Italian-only. Support the same five working locales used by the reconciliation plugin: `it`, `en`, `fr`, `de`, and `es`. Keep canonical data column names in English for stability, but speak to the user and write summaries in the chosen working language.

Detailed parser, mapping, sampling, and review-status notes live in `references/workflow-reference.md`. Load that reference only when the run needs extra detail beyond the workflow below.

## Cowork-native Run UX

Before running helper scripts or write-heavy work, identify material choices that would change execution: problem framing, decision angle, risk appetite, scope boundaries, audience, evidence posture, mappings, cut-off, OCR, notification, or review assumptions. Reuse choices already established in the conversation or bound case records. Ask only for unresolved material choices and wait before their dependent work; continue independent authorized preparation. Generate choices from the actual inputs; do not offer named frameworks, regulators, document types, output packages, or issue categories unless the facts cue them or the user must supply a missing custom value. Do not infer missing required evidence, approval, or a material business decision. State routine provisional assumptions when the workflow permits them.

Default output policy: produce the richest normal package for the workflow. DOCX/Word, Excel/CSV, JSON audit, diagnostics, charts, packaged reports, review notes, and Vera-written review files are not choices to propose when they are natural outputs of that plugin; generate them whenever dependencies and source data permit. Ask only when an output is technically impossible, unsafe, or the user explicitly requests a reduced/debug run.

Default currency policy: use Euro (`EUR`) unless the user or source file explicitly states another currency. Do not ask for currency when it is otherwise unresolved; record `EUR` as the assumption.

Keep progress and handoff concise. Use a checklist, Run Intake table, Decision
Table, or Artifact Card when it helps the user review complex work; their chat
format is optional. Preserve all required saved mappings, review decisions,
validation records, and artifacts. Resolve material choices before dependent
execution and continue independent authorized work while awaiting an answer.
Obtain authorization for external, destructive, or approval-sensitive actions
when not already given, and preserve workflow-specific approval gates.
At delivery, link outputs and state their purpose, review status, unresolved
items, and next action. Create `run_review.md` when a durable review index
is useful; never edit plugin source or generated ZIPs during a user-data run.

## Core Principle

Deterministic Python code owns extraction, normalization, filtering, sampling, and exports. Claude may inspect files, propose recipes, explain assumptions, and review diagnostics, but it must not silently override extracted rows or sampled rows with model reasoning.

The user should not interact directly with CLI scripts. Treat scripts as internal tools Claude runs on behalf of the user.

## First Run Workflow

1. Start with Studio Archive client intake. Call `list_studio_archive_clients`;
   do not infer the client from the journal filename. Resolve an existing
   registered client, explicitly register a confirmed existing customer folder,
   or create a client only after the user chooses New client. Create or select
   one engagement. Explain that the external original is preserved, obtain
   authorization, and call `import_studio_client_document` with that
   `engagement_id` and role `journal`. Retain its immutable `input_id` and
   receipt. Import does not prepare or start Journal Sampling. If New Client
   onboarding is pending, preserve that status while preparing the journal; do
   not claim the relationship is active.
2. Call `prepare_studio_client_workflow` for `journal-sampling` with that exact
   journal `input_id`, a concrete label, and a purpose. Use the idempotent
   returned run unless the user explicitly requests `new_run=true`. Call
   `start_studio_client_workflow` before any helper script. Load the returned
   `client_engagement_path` through the workflow gate and use the one
   `input_bindings` item with role `journal`; do not use an unbound live file or
   scan the engagement's other imports.
3. Ask for working language, source-document language, and any known filters
   only if they are not already provided or inferable. Do not ask for output
   richness. If the audit plan does not specify sample size or method, default
   to the deterministic script baseline: `random`, size `25`, seed `42`, and
   record those assumptions in the audit trail.
4. Run dependency checks from the plugin directory:

```bash
python scripts/check_dependencies.py
```

If requirements are missing, install from `requirements.txt` only when the environment allows it or explain what dependency capability is missing.

5. Run inspection to produce `inspection.json`, `suggested_recipe.json`, and
   `qualification_review_payload.json`:

```bash
python scripts/inspect_journal.py <bound-journal-path> --output-dir <client-run-output>/normalization --client-engagement <client-engagement.json> --language <it|en|fr|de|es> --document-language <auto|it|en|fr|de|es>
```

6. Read the inspection artifacts. Inspection never promotes a suggested mapping
   into the population. Review each source-family adapter, header/layout mapping,
   debit/credit or signed-amount convention, and localized number separators.
   Ask the user only for the smallest unresolved semantic decision.
7. Record the reviewed recipe in the work folder, not plugin source. The
   reviewed contract must explicitly bind the source artifact, adapter and
   version, field mapping, posting identity, carry-forward policy, currency,
   unit, and the disposition of every additional monetary-labelled or numeric
   column. Preserve the generated `mapping_sha256` and attach a complete
   `vera.reviewed_decision_receipt.v1` whose `decision_type` is
   `source_mapping` and whose content is the exact mapping contract. A free-text
   decision reference is not sufficient. If any bound field changes, rerun
   inspection with that recipe so a new digest is generated and review the new
   contract.
8. Normalize rows:

```bash
python scripts/normalize_journal.py <bound-journal-path> --output-dir <client-run-output>/normalization --recipe <client-run-output>/normalization/suggested_recipe.json --client-engagement <client-engagement.json> --language <it|en|fr|de|es> --document-language <auto|it|en|fr|de|es>
```

Require the complete normalization to retain the exact reviewed bytes as
`normalization_recipe.json`, with matching captured and original-source
receipts. Do not delete or replace the original reviewed recipe after the run.

9. Run deterministic sampling:

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

10. Review `normalization_diagnostics.json`,
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
   Treat the stage-zero manifest as pre-review only. When an MCP save or apply is used, its successor is deliverable only after that transaction archives the exact predecessor,
   freshly rederives all review counts/effects/statuses and gates, reseals the
   exact file/directory/mode contract, and replays the full successor chain.
   Semantic review must remain `not_assessed`, reporting `blocked`, publication
   `withheld`, and `report_ready=false`; do not translate accepted item
   decisions into `final_ready`. Complete every write-producing MCP save or
   apply transaction before sealing the outer customer-folder run.

   Isolated normalization replay and the internal review-successor bridge must
   use the same still-running context. MCP supplies these arguments
   automatically before any review write:

```bash
python -I -B scripts/replay_normalization.py \
  <client-run-output>/normalization/normalized_journal.csv \
  --diagnostics <client-run-output>/normalization/normalization_diagnostics.json \
  --receipt-out <client-run-output>/normalization/replay_receipt.json \
  --client-engagement <customer-run>/context.json
python -I -B scripts/review_successor.py context <client-run-output> \
  --client-engagement <customer-run>/context.json
```

11. After the last output write, call `finalize_studio_client_workflow` and
   declare every physical output with a unique artifact ID, relative path,
   concrete purpose, audience, and media type. The downstream handoff must
   include `prepared.normalized_journal`,
   `internal.normalization_diagnostics`, and
   `prepared.journal_sample_csv`. Finalization moves the run to
   `ready_for_review`; an undeclared or empty output tree is not available.
   Review the final declaration, then call `complete_studio_client_workflow`.
   If execution fails, record the run as `failed`; explicitly cancel an
   abandoned run rather than deleting it.

## Check Entries handoff

The three files have different jobs. `normalized_journal.csv` is the qualified
population needed to reproduce and validate the preparation;
`normalization_diagnostics.json` proves how that population qualified; and
`sample/journal_sample.csv` is the exact row-selection boundary. Check Entries
must bind all required upstream artifacts from this one finalized Journal
Sampling run and then restrict its work to the rows in the bound sample.

Each support delivery is a separate evidence batch. Import it as an immutable,
content-addressed `support` receipt (reusing the same receipt when the bytes and
role are identical), then call `start_check_entries_from_sample` with this
Journal Sampling run ID and the support input IDs. Studio Archive resolves and
validates the internal artifacts; neither the user nor the chat should name or
assemble them. Use the explicit new-run option when a separately tracked batch
has the same exact byte selection. A later support import does not change an
earlier Check Entries input manifest or cause it to scan the engagement folder.

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

- `language`: working/output language for Claude's questions and final summary; one of `it`, `en`, `fr`, `de`, `es`.
- `document_language`: source-document language used to interpret labels; one of `auto`, `it`, `en`, `fr`, `de`, `es`.

Store both assumptions in the generated recipe and preserve them in diagnostics/audit JSON. If the user writes in English, default `language=en` and `document_language=auto`. If the source files are clearly Italian, French, German, or Spanish, set `document_language` accordingly without asking unless ambiguity matters.

Starter prompts:

```text
IT: Usa Journal Sampling per il cliente <cliente> sul giornale <percorso-file>. Lingua: it. Lingua documenti: auto. Riprendi o crea il fascicolo corretto, chiedimi solo le ambiguità essenziali e genera campione, diagnostiche e audit trail.
EN: Use Journal Sampling for <client> on journal <file-path>. Language: en. Document language: auto. Resume or create the correct engagement, ask only for essential ambiguities, then generate the sample, diagnostics, and audit trail.
FR: Utilise Journal Sampling pour <client> sur le journal <chemin-fichier>. Langue: fr. Langue des documents: auto. Reprends ou crée la mission correcte, demande uniquement les ambiguïtés essentielles, puis génère l'échantillon, les diagnostics et l'audit trail.
DE: Verwende Journal Sampling für <Mandant> mit dem Journal <Dateipfad>. Sprache: de. Dokumentsprache: auto. Öffne oder erstelle den richtigen Auftrag, frage nur wesentliche Unklarheiten ab und erstelle Stichprobe, Diagnostik und Audit-Trail.
ES: Usa Journal Sampling para <cliente> con el diario <ruta-archivo>. Idioma: es. Idioma de los documentos: auto. Reanuda o crea el encargo correcto, pregunta solo por las ambigüedades esenciales y genera la muestra, los diagnósticos y el registro de auditoría.
```

## Mapping Recipe Rules

Claude can adjust the recipe JSON generated in the work folder. Use:

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

Do not ask the user to edit JSON. Ask the user in business terms, then Claude updates the recipe and reruns the deterministic scripts.

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
- `sample/model_review_context.json`;
- `sample/ui_decisions.json`;
- `sample/applied_decisions.json` after reviewer decisions are applied;
- `sample/final_artifacts.json`.

## Cowork review handoff

The normal Cowork completion point is delivery
of the reviewable draft, artifact card, and source/review files in the connected
folder. For model-led sample review, begin with
`sample/model_review_context.json`. It preserves the semantic sample,
parameters, diagnostics, counts, and review actions while replacing exact known
technical file references with stable opaque aliases. Do not load
`run_intake.json`, `review_payload.json`, `ui_decisions.json`, or
`final_artifacts.json` into model context. Open `sampling_audit.json`,
`journal_sample.csv`, or `journal_sample.xlsx` only for a specific unresolved
review question. Report the package as `ready_for_professional_review` where
that status exists, otherwise as `pending_review`.

When a validated MCP tool, browser interface, or local workbench is callable,
it may optionally persist or apply reviewer actions using the minimized context;
a compatible local Vera context path may still be required so the local tool
can resolve complete control records. Its absence never blocks delivery. Never
claim `applied` or `final_ready` unless corresponding persisted artifacts prove
it. A file or chat review without those artifacts remains pending professional
review.

Review actions cannot waive a failed deterministic check. Keep failed checks,
missing evidence, unresolved decisions, and applicable blockers visible in the
artifact card and final response.
