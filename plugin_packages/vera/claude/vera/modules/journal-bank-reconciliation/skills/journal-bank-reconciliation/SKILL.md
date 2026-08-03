---
name: journal-bank-reconciliation
description: Use when a user wants Claude to reconcile qualified bank statements with journal or ledger exports, map variable tabular formats, run exact amount/date and explicit-reference matching, and produce reviewable CSV/XLSX/JSON outputs. This is a Claude workflow plugin; users should not operate the helper CLIs directly.
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

Never write run outputs inside this Git workspace or a published folder. Use
only the Studio Archive run path described below.

## Client boundary in Cowork

Cowork does not package Studio Archive, so it cannot select or register its
local clients, import controlled snapshots, prepare or start customer-folder
runs, or finalize their artifact manifests. Use a product CLI only when a
compatible local Vera installation supplied a digest-valid, running
`vera.client_workflow_context.v2` for this exact workflow and its complete
customer-folder ledger paths are available. Otherwise work from the exact
connected files, preserve a reviewable file-based handoff, and state that the
sealed customer-folder run remains pending. Never invent an ID, receipt,
lifecycle state, or completed artifact declaration.

# Journal-Bank Reconciliation

Use this skill when bank statement movements must be reconciled to accounting journal or ledger rows. The plugin is a guided Claude workflow: Claude inspects the files, asks only for unresolved mapping or review assumptions, runs deterministic helper scripts, reviews diagnostics, and delivers outputs.

The workflow is not Italian-only. Support the same five working locales used by the other accounting plugins: `it`, `en`, `fr`, `de`, and `es`. Keep canonical output column names in English for stability, but speak to the user and write summaries in the chosen working language.

Detailed parser, mapping, reconciliation-stage, and review-status notes live in `../../references/workflow-reference.md`. Load that reference only when the run needs extra detail beyond the workflow below.

## Cowork-native Run UX

Before running helper scripts or write-heavy work, identify material choices that would change execution: problem framing, decision angle, risk appetite, scope boundaries, audience, evidence posture, mappings, cut-off, OCR, notification, or review assumptions. Ask only those unresolved choices in chat and wait for the answer. Generate choices from the actual inputs; do not offer named frameworks, regulators, document types, output packages, or issue categories unless the facts cue them or the user must supply a missing custom value. Do not run long or write-heavy execution under unconfirmed assumptions.

Default output policy: produce the richest normal package for the workflow. DOCX/Word, Excel/CSV, JSON audit, diagnostics, charts, packaged reports, review notes, and Vera-written review files are not choices to propose when they are natural outputs of that plugin; generate them whenever dependencies and source data permit. Ask only when an output is technically impossible, unsafe, or the user explicitly requests a reduced/debug run.

Default currency policy: use Euro (`EUR`) unless the user or source file explicitly states another currency. Do not ask for currency when it is otherwise unresolved; record `EUR` as the assumption.

Use Cowork-native UI artifacts as part of the workflow, not as optional
narration. At minimum:

1. Start with a visible markdown run checklist. Track intake, dependency check,
   inspection, user decisions, deterministic run, professional review, and delivery.
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
   unresolved items, and next action. When useful, create `run_review.md`
   in the output folder from generated JSON/CSV/Markdown outputs; never edit
   plugin source or generated ZIPs during a run.

## Core Principle

Deterministic Python code owns mechanically verifiable source qualification,
exact-decimal normalization, optional sample filtering, explicit-reference and
amount/date matching, content-addressed receipts, physical source lineage,
one-to-one relationship ledgers, independent assurance gates, and exports.
Claude may inspect files, propose recipes, explain assumptions, and review
unresolved items, but the plugin scripts must not make direct OpenAI API calls.
Descriptions and beneficiary names are review context, not automatic match
identifiers.

The user should not interact directly with CLI scripts. Treat scripts as internal tools Claude runs on behalf of the user.

## Inputs

Required:

- a bank statement file or folder in `.xlsx`, `.xls`, or `.csv` format; text
  `.pdf` files may be inspected but cannot emit movements without a supported,
  source-family-specific reviewed adapter;
- a journal or ledger file or folder in `.xlsx`, `.xls`, or `.csv` format;
  text `.pdf` files have the same fail-closed adapter requirement.

Optional:

- a sample movement file to restrict the journal/ledger side;
- mapping hints for date, signed amount or debit/credit, description,
  beneficiary, reference, movement number, account, currency, unit, entity,
  party, and direction; for CSVs, a field delimiter chosen only from comma,
  semicolon, tab, or pipe; and decimal/thousands separators when needed;
- amount tolerance;
- date window in days;
- working language and source-document language.

Generic and OCR-only PDFs are not movement sources. Inspection must expose
`unsupported_source_layout`, emit zero movements, and retain only the narrow
bank non-movement classifications supported by the script.

## First Run Workflow

1. Ask for the bank file/folder, journal or ledger file/folder, sample file when the user wants to restrict the population, working language, source-document language, and any known mapping hints only if they are not already provided or inferable. Do not ask for output richness. Use the script defaults for amount tolerance and date window unless the user provides stricter thresholds or the data requires a different assumption.
2. Run dependency checks from the plugin directory:

```bash
python scripts/check_dependencies.py
```

If requirements are missing, install from `requirements.txt` only when the environment allows it or explain what dependency capability is missing.

3. Run inspection to produce `inspection.json` and `suggested_recipe.json`:

```bash
python scripts/inspect_inputs.py <managed-bank-input> <managed-journal-input> --client-engagement <client_engagement_path> --output-dir <client-run-output> --language <it|en|fr|de|es> --document-language <auto|it|en|fr|de|es>
```

Add `--sample <sample-file>` when a sample movement list is provided.

4. Read `inspection.json`, `input_receipts.json`,
   `source_qualifications.json`, and `suggested_recipe.json`. Do not run
   reconciliation while any source reports `unsupported_source_layout`. A
   source with `needs_review` has emitted zero rows. Ask the smallest needed
   question about the physical header, monetary role, CSV field delimiter,
   decimal/thousands separators, ambiguous day/month date convention, or
   perimeter field. Treat the three separators as separate inputs. A generic
   PDF cannot be approved merely by changing a mapping.
5. If a mapping decision is needed, edit `suggested_recipe.json` in the work
   folder, then use `journal_bank_core.build_mapping_review_receipt` to seal the
   reviewed header rows, mapping, CSV field delimiter, numeric separators,
   `date_convention`, `date_locale` when Italian textual-month dates are
   present, exact `non_movement_summary_labels` when a reviewed tabular total
   row must be excluded,
   current `potential_monetary_columns`, and explicit
   `excluded_monetary_columns` against the current content-addressed source
   artifact reference. Supply the exclusions even when empty, and ensure every
   potential monetary column is mapped to amount/debit/credit or excluded. Do
   not hand-author or copy a receipt. Only exact supported headers in a
   uniquely profiled comma CSV need no mapping receipt; non-default delimiters
   and explicit/profile mismatches require the current
   `journal_bank.tabular.v6` receipt for the base contract. Use only
   `day_first` or `month_first`; leave the field null when every populated date
   is mechanical or unambiguous. Italian textual-month dates require
   `date_locale: it`, and reviewed tabular total rows require a sorted exact
   `non_movement_summary_labels` list; either authority uses the additive
   `journal_bank.tabular.v7` receipt.
6. Review the proposed `relationship.policy` in business terms. Confirm the
   one-to-one shape, no evidence reuse, currency/unit/entity/party perimeter,
   direction treatment, defaults, amount tolerance, and date window. Use
   `journal_bank_core.build_relationship_review_receipt` to seal the reviewed
   policy against the current bank and journal source references. Every run
   requires the current `journal_bank.relationship.v2` relationship receipt;
   v1 receipts predate batch-safe matching and are stale. Do not treat the
   generated proposal as reviewed.
7. Run deterministic reconciliation:

```bash
python scripts/run_reconciliation.py <managed-bank-input> <managed-journal-input> --client-engagement <client_engagement_path> --output-dir <client-run-output>/reconciliation --recipe <client-run-output>/suggested_recipe.json --language <it|en|fr|de|es> --document-language <auto|it|en|fr|de|es>
```

Use `--tolerance <amount>` and `--date-window-days <days>` when the user provides explicit thresholds.

8. Review `reconciliation_audit.json`, `relationship_ledger.json`,
   `relationship_residuals.csv`, `material_value_ledger.json`,
   `assurance_gates.json`, `reconciliation_matches.csv`, `unmatched_bank.csv`,
   `unmatched_journal.csv`, and `review_notes.md` before final delivery. Run
   `journal_bank_core.validate_material_value_ledger` against the output
   directory before relying on native values. Report matched count, unmatched
   bank count, unmatched journal count, residual or withheld gates, stage
   counts, unresolved/manual-review issues, and output paths.
   `material_value_ledger.json` is intentionally absent when source
   qualification or relationship authority blocks; review the persisted empty
   matches/residuals, unmatched partitions, blocked relationship ledger, gates,
   and audit instead.

## Mapping Recipe Rules

Claude can adjust the recipe JSON generated in the work folder. Use per-side recipe sections:

- `bank.files.<filename>.header_rows`: 1-indexed header rows for tabular bank files;
- `journal.files.<filename>.header_rows`: 1-indexed header rows for tabular journal/ledger files;
- `mapping.date`: transaction date;
- `mapping.amount`: signed amount column, when one exists;
- `mapping.debit` and `mapping.credit`: debit/credit columns, when signed amount is not present;
- `mapping.description`: movement or line description;
- `mapping.beneficiary`: counterparty/payee/beneficiary;
- `mapping.reference`: reference, document number, CRO, TRN, IBAN, or invoice reference;
- `mapping.movement_number`: journal movement/registration number;
- `mapping.account`: account identifier;
- `mapping.currency`: transaction currency;
- `mapping.unit`: measurement unit;
- `mapping.entity_ref`: legal entity or reconciliation perimeter;
- `mapping.party_ref`: counterparty identifier when party equality is required;
- `mapping.direction`: explicit flow/sign direction when supplied.
- `direction_value_mapping`: reviewed per-source translation from every
  observed non-canonical direction label to `positive`, `negative`, or `zero`.
- `date_convention`: source-bound `day_first` or `month_first` authority for
  genuinely ambiguous day/month text; it is not a parser-order preference.
- `date_locale`: source-bound `it` authority for full Italian textual-month
  dates under adapter v7; it is never inferred from the conversation language.
- `non_movement_summary_labels`: sorted exact normalized descriptions that may
  exclude only blank-date rows with no stable explicit reference under adapter
  v7.
- `csv_field_delimiter`: CSV transport delimiter, limited to comma, semicolon,
  tab, or pipe; this is not a decimal or thousands separator.
- `decimal_separator` and `thousands_separator`: numeric-text conventions,
  reviewed separately from the CSV field delimiter.
- `potential_monetary_columns`: exact current source-derived monetary
  candidates on reviewed paths.
- `excluded_monetary_columns`: explicit reviewed exclusions, present even when
  empty; together with amount/debit/credit mappings it must completely dispose
  of every potential monetary column.

Do not ask the user to edit JSON. Ask the user in business terms, then Claude updates the recipe and reruns the deterministic scripts.

Profiled dates, fuzzy headers, and positional numeric guesses are proposals,
not automatic facts. Never promote them by copying a prior receipt. Source
artifact references include the source digest, so changed bytes require a new
review.

CSV delimiter profiling is transport evidence, not semantic mapping authority.
It considers only the four supported one-byte delimiters over a bounded sample.
Ambiguous or unsupported delimiter profiles emit zero rows. LF, CRLF, and CR
record terminators are handled mechanically and never require review. The
full-file parse remains strict; malformed or ragged records anywhere in the
source block the population as `parser_failure`.

`debit` and `credit` are not universal sign conventions across banks, ledgers,
and account perspectives. If an explicit direction column contains anything
other than canonical `positive`, `negative`, or `zero`, Claude must confirm the
source-specific meaning and seal an exact, complete `direction_value_mapping`
with the mapping receipt. Unknown labels, extra unobserved labels, incomplete
coverage, or disagreement with the exact signed amount withhold the source.

Calendar-native dates and unambiguous displayed dates, including compact ISO
`YYYYMMDD`, are supported. Invalid eight-digit calendar values remain
unparsed; they never fall through to amount/date matching.

Full Italian month names are supported only through an exact current
`date_locale: it` v7 mapping receipt. Case and horizontal spacing normalize
mechanically; abbreviations, unknown or mixed-language months, two-digit years,
embedded text, line breaks, and invalid calendar dates fail closed. A reviewed
summary label is not a keyword classifier: it applies only by exact normalized
equality on a truly blank-date row with no stable reference.

## Deterministic Matching Rules

- Candidate rows use exact `Decimal` absolute amounts and an inclusive,
  exact-decimal tolerance.
- `reference` uses only explicit `reference` and `movement_number` fields;
  reference-like words in descriptions and generic explicit words such as
  `invoice` or `payment` are never reference evidence.
- Candidates must stay inside the reviewed currency, unit, entity, party, and
  direction perimeter.
- Amount/date stages require actual dates on both rows and the configured date
  window.
- Matching stages run in this order:
  1. `reference` accepts conflict-free singleton reference candidates in
     batches. If multiple singleton bank rows target the same journal row,
     none wins by row order.
  2. `amount_date_unique` is the first conflict-free singleton amount/date
     batch after reference matching is exhausted.
  3. `amount_date_single` is reserved for later conflict-free singleton waves:
     candidates that become singleton only because an earlier amount/date
     batch consumed other journal candidates.
- Every singleton wave is evaluated against one unchanged candidate snapshot
  before any row in that wave is accepted. Later waves repeat until no safe
  singleton remains.
- Rows are not reused after a match is accepted.
- Missing dates without a stable explicit reference block the source. Missing
  dates with a stable reference are marked `emitted_reference_only` and cannot
  enter amount/date stages.
- Sample movement files restrict only the journal/ledger side. If a supplied
  sample is empty, invalid, or selects no journal movement, the run blocks and
  never reconciles the full journal.
- Ambiguous candidates, including competing singleton bank rows targeting the
  same journal row, remain unmatched rather than being forced by row order or
  model judgment.

Claude may inspect individual rows and explain unresolved items, but should keep review judgment explicit in the final response rather than silently changing script outputs.

## Expected Outputs

- `inspection.json`;
- `suggested_recipe.json`;
- `reconciliation/normalized_bank.csv`;
- `reconciliation/normalized_journal.csv`;
- `reconciliation/reconciliation_matches.csv`;
- `reconciliation/relationship_residuals.csv`;
- `reconciliation/unmatched_bank.csv`;
- `reconciliation/unmatched_journal.csv`;
- `reconciliation/bank_pdf_non_movement_rows.csv`;
- `reconciliation/journal_bank_reconciliation.xlsx`;
- `reconciliation/reconciliation_audit.json`;
- `reconciliation/input_receipts.json`;
- `reconciliation/source_qualifications.json`;
- `reconciliation/reviewed_decisions.json`;
- `reconciliation/lineage.json`;
- `reconciliation/relationship_ledger.json`;
- `reconciliation/material_value_ledger.json`;
- `reconciliation/assurance_gates.json`;
- `reconciliation/artifact_receipts.json`;
- `reconciliation/review_notes.md`;
- `reconciliation/run_intake.json`;
- `reconciliation/review_payload.json`;
- `reconciliation/ui_decisions.json`;
- `reconciliation/applied_decisions.json` after reviewer decisions are applied;
- `reconciliation/final_artifacts.json`.

## Cowork review handoff

The normal Cowork completion point is delivery
of the reviewable draft, artifact card, and source/review files in the connected
folder. Review those artifacts directly. Report the package as
`ready_for_professional_review` where that status exists, otherwise as
`pending_review`.

When a validated MCP tool, browser interface, or local workbench is callable, it
may optionally persist or apply reviewer actions. Its absence never blocks
delivery. Never claim `applied` or `final_ready` unless corresponding persisted
artifacts prove it. A file or chat review without those artifacts remains
pending professional review.

Review actions cannot waive a failed deterministic check. Keep failed checks,
missing evidence, unresolved decisions, and applicable blockers visible in the
artifact card and final response.

## Language Policy

Ask for or infer two language assumptions:

- `language`: working/output language for Claude's questions and final summary; one of `it`, `en`, `fr`, `de`, `es`.
- `document_language`: source-document language used to interpret labels; one of `auto`, `it`, `en`, `fr`, `de`, `es`.

Store both assumptions in the generated recipe and preserve them in diagnostics/audit JSON. If the user writes in English, default `language=en` and `document_language=auto`. If the source files are clearly Italian, French, German, or Spanish, set `document_language` accordingly without asking unless ambiguity matters.

Starter prompts:

```text
IT: Usa Journal-Bank Reconciliation sugli estratti banca in /percorso/banca e sul giornale in /percorso/giornale.xlsx. Lingua: it. Lingua documenti: auto. Ispeziona colonne e file, chiedimi solo le ambiguità essenziali e genera riconciliazione, diagnostiche e audit trail.
EN: Use Journal-Bank Reconciliation on bank statements in /path/bank and journal file /path/journal.xlsx. Language: en. Document language: auto. Inspect columns and files, ask only for essential ambiguities, then generate reconciliation, diagnostics, and audit trail.
FR: Utilise Journal-Bank Reconciliation sur les relevés bancaires dans /chemin/banque et le journal /chemin/journal.xlsx. Langue: fr. Langue des documents: auto. Inspecte les colonnes et les fichiers, demande uniquement les ambiguïtés essentielles, puis génère le rapprochement, les diagnostics et l'audit trail.
DE: Verwende Journal-Bank Reconciliation für Kontoauszüge in /pfad/bank und Journaldatei /pfad/journal.xlsx. Sprache: de. Dokumentsprache: auto. Prüfe Spalten und Dateien, frage nur wesentliche Unklarheiten ab und erstelle Abstimmung, Diagnostik und Audit-Trail.
```

## Failure Modes

- For every generic or scanned PDF, report `unsupported_source_layout`; do not
  emit movements or complete reconciliation.
- If amount mapping is missing or a mapped amount has invalid/ambiguous
  separator syntax, keep the source unqualified and the run blocked.
- If a CSV delimiter is ambiguous or unsupported, or a non-default delimiter
  lacks a current v6 mapping receipt, emit zero movements. Do not substitute a
  decimal/thousands separator for `csv_field_delimiter`.
- If a populated day/month date is ambiguous, require a current source-bound
  `date_convention` receipt and emit zero rows until it exists. If a populated
  date is invalid, fail the complete source even when the row has a stable
  reference. Only a truly blank date with a stable explicit identifier may be
  emitted as reference-only.
- If a populated textual-month date lacks the exact `date_locale: it` v7
  receipt, emit zero rows and require review. Never ask a model to repair it.
  Exclude a tabular total row only when its exact normalized description is in
  the receipt-bound `non_movement_summary_labels` list and both date and stable
  reference are absent.
- If any potential monetary column is neither mapped nor explicitly excluded,
  or the declared list no longer equals the current source evidence, require a
  new mapping review and emit zero movements.
- If the strict full CSV parse finds a malformed or ragged record, including
  beyond the bounded delimiter profile, report `parser_failure`; never accept a
  partial population.
- If actual dates are missing, only an unambiguous explicit-reference match may
  proceed; amount/date, beneficiary, and description inference cannot replace
  date evidence.
- If a supplied sample is empty, invalid, or absent from the journal, report
  the block and do not fall back to the full journal.
- If a parser fails, distinguish `parser_failure` from
  `unsupported_source_layout` and deliver the available blocked assurance
  artifacts.
- Never describe a run as final-ready unless `assurance_gates.json` has
  `report_ready: true`. Reviewer acceptance cannot convert unmatched rows or
  residuals into reconciliation closure.
- Never classify, allocate, or force a residual to zero. Treat
  `relationship_residuals.csv` as the exact native projection of the reviewed
  allocation ledger and require `material_value_ledger.json` fresh replay for
  every match/residual CSV and XLSX value address.
- If deterministic rules create too many unmatched or ambiguous rows, write the gap as a plugin improvement suggestion rather than overriding the output silently.
