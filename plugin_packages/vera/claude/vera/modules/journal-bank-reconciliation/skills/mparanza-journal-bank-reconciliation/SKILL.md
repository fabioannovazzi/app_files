---
name: mparanza-journal-bank-reconciliation
description: Use when a user wants Claude to reconcile qualified bank statements with journal or ledger exports, map variable tabular formats, run exact amount/date and explicit-reference matching, and produce reviewable CSV/XLSX/JSON outputs. This is a Claude workflow plugin; users should not operate the helper CLIs directly.
---

## Output Location Rule

Never write run outputs inside this Git workspace or a published folder. Use
only the Studio Archive run path described below.

## Client engagement gate

Select one Studio Archive client and engagement, import the bank and
journal/ledger sources into its managed inputs, then call
`prepare_studio_client_workflow` with workflow ID
`journal-bank-reconciliation`. Pass the returned `client_engagement_path` as
`--client-engagement` to inspection and reconciliation. Use only the context's
run folder; cross-engagement inputs and arbitrary outputs are rejected.

Start the prepared run before inspection. After the last output write, call
`finalize_studio_client_workflow` and declare every physical file with a stable
artifact ID, relative path, concrete purpose, audience, and media type. Review
the closed declaration, then call `complete_studio_client_workflow`; record
`failed` or explicitly cancel an abandoned run instead of treating a partial
directory as a result.

# Journal-Bank Reconciliation

## Jurisdiction and Geneva

For a CH-GE mandate, read `references/geneva.md` before the steps below. It specifies the Geneva input, source and output adaptations within this existing function. Choose governing jurisdiction independently of output language; the ordinary Italian path remains available for IT.


Use this skill when bank statement movements must be reconciled to accounting journal or ledger rows. The plugin is a guided Claude workflow: Claude inspects the files, asks only for unresolved mapping or review assumptions, runs deterministic helper scripts, reviews diagnostics, and delivers outputs.

The workflow is not Italian-only. Support the same five working locales used by the other accounting plugins: `it`, `en`, `fr`, `de`, and `es`. Keep canonical output column names in English for stability, but speak to the user and write summaries in the chosen working language.

Detailed parser, mapping, reconciliation-stage, and review-status notes live in `../../references/workflow-reference.md`. Load that reference only when the run needs extra detail beyond the workflow below.

## Cowork-native Run UX

Before running helper scripts or write-heavy work, identify material choices that would change execution: problem framing, decision angle, risk appetite, scope boundaries, audience, evidence posture, mappings, cut-off, OCR, notification, or review assumptions. Reuse choices already established in the conversation or bound case records. Ask only for unresolved material choices and wait before their dependent work; continue independent authorized preparation. Generate choices from the actual inputs; do not offer named frameworks, regulators, document types, output packages, or issue categories unless the facts cue them or the user must supply a missing custom value. Do not infer missing required evidence, approval, or a material business decision. State routine provisional assumptions when the workflow permits them.

Default output policy: produce the richest normal package for the workflow. DOCX/Word, Excel/CSV, JSON audit, diagnostics, charts, packaged reports, review notes, and Vera-written review files are not choices to propose when they are natural outputs of that plugin; generate them whenever dependencies and source data permit. Ask only when an output is technically impossible, unsafe, or the user explicitly requests a reduced/debug run.

Currency: carry the currency evidenced by the source or confirmed for the engagement (including CHF). Never infer currency from output language or silently default to EUR. If unresolved, obtain the currency before computing or matching amounts. Keep different currencies separate; conversion requires an explicit reviewed rate, date and basis.

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

Deterministic Python code owns mechanically verifiable source qualification,
exact-decimal normalization, optional sample filtering, explicit-reference,
reference-group, and amount/date matching, content-addressed receipts, physical
source lineage, non-reusing relationship ledgers, independent assurance gates,
and exports.
Claude may inspect source metadata and the bounded inspection preview, propose
recipes, explain assumptions, and review the bounded residual packet. It must
not open the complete raw tables or load complete normalized, matched, or
unmatched row tables into model context. The inspection preview contains at
most the first 20 normalized rows per qualified source; the helper scripts read
and reconcile the complete population locally. Descriptions and beneficiary
names are review context, not automatic match identifiers. The reconciliation
helpers must not make direct OpenAI API calls; only the qualified
residual-worker launcher may transmit the admitted packet.

The user should not interact directly with CLI scripts. Treat scripts as internal tools Claude runs on behalf of the user.

## Inputs

Required:

- a bank statement file or folder in `.xlsx`, `.xls`, `.csv`, or text `.pdf`
  format. A PDF can emit movements only when inspection recovers a labelled
  physical column grid and a current source-bound receipt approves the header,
  amount/debit/credit roles, sign convention, and every excluded monetary
  column such as a running balance;
- a journal or ledger file or folder in `.xlsx`, `.xls`, `.csv`, or text `.pdf`
  format, subject to the reviewed PDF-table contract or the registration-PDF
  adapter described below.

Optional:

- a sample movement file to restrict the journal/ledger side;
- mapping hints for date, signed amount or debit/credit, description,
  beneficiary, reference, movement number, account, currency, unit, entity,
  party, and direction; for CSVs, a field delimiter chosen only from comma,
  semicolon, tab, or pipe; and decimal/thousands separators when needed;
- amount tolerance;
- date window in days;
- working language and source-document language.

PDF text without a labelled physical column grid, a reviewed registration
layout or a checked bank source-reference adapter, inconsistent page tables,
and OCR-only PDFs are not movement sources. Inspection must expose
`unsupported_source_layout`, emit zero qualified movements, and retain readable
partial entries separately from the supported bank non-movement classifications. The presence of a
date and one or more amounts on a line is never enough to infer a movement.

### Agent-led journal and bank PDF recovery

Before declaring an unfamiliar journal or bank statement layout unsupported, follow
`../../references/pdf-recovery.md`. Use the maintained inspection, trial and
freeze actions in the existing inspection command. The host agent diagnoses,
revises source-bound recipes or writes a run-local source-reference adapter
with distinct evidence-based attempts retained in the run. Keep ordinary host inspection and
reasoning available. Independent checks reconstruct source amounts, enforce
coverage and accounting controls, and replay frozen code. Retain readable partial
entries and explicit unresolved issues; block population-dependent operations.
Successful recovery still requires the ordinary reviewed mapping and complete
qualification. Do not alter installed code or bypass a failed gate. The managed
runtime reports issues and recovery evidence through the existing incident
pipeline; verify the original task before claiming it recovered.

Select `--pdf-side bank` on every recovery action for a bank statement; journal
is the default. Use `--pdf-source` to select one exact PDF inside a bound source
folder. Bank recipes use `bank.files[filename].pdf_bank_layout` and independent
per-source histories. Review date, description, signed amount or debit/credit
bands and printed opening/closing balances or movement totals. The bank checker
enforces source coverage and bank arithmetic; it does not require debit to equal
credit. Multiline and cross-page descriptions retain source references. Include
the frozen bank layout in the ordinary mapping decision. A single payment receipt
cannot establish a complete statement population.

### Registration-style journal PDF

A text journal with `N ---- dd/mm/yyyy ----` registration headers and
`seguito registrazione del dd/mm/yyyy` continuations can use the shared
registration reader. When ordinary table inspection cannot qualify a journal,
read its bounded `pdf_layout_evidence` with the host model. Review the physical
column semantics and prepare `journal.files[filename].pdf_registration_layout`
with `body: [top, bottom]`, five non-overlapping `[left, right]` bands under
`columns` (`account_debit`, `account_credit`, `description`, `debit`, `credit`),
and explicit `ignored_line_prefixes` limited to printed headers/footers.
Reinspect using this recipe. Review the resulting ordinary column mapping and
relationship perimeter, and include `pdf_registration_layout` in that file's
decision passed to `seal_review_receipts.py`. The mapping receipt binds the
layout, source digest and `journal_bank.registration_pdf.v1` adapter version
`1`; changing coordinates or source bytes invalidates it. This is a maintained
Vera adapter, not an ad hoc extraction alternative.

The reader carries date/registration state across pages, retains multiline
descriptions and page/row locators, and verifies each completed registration's
debit/credit totals. Printed page totals can differ during a continued
registration. Missing postings, empty-text pages, unassigned money, overlapping
bands and incomplete/unbalanced registrations withhold the source. Review the
bank-account scope and sign convention before matching a complete journal;
counterpart postings must not be mistaken for bank-account movements. The bank
PDF requires its own labelled table mapping or checked bank recovery adapter. An unsupported layout
cannot be promoted merely because its text is readable.

Each page cache is released after extraction; progress names the current page.
Unsupported table extraction stops early and does not reread the whole PDF.
A catchable `MemoryError` produces `memory_exhausted` parser diagnostics. If
an OS kills the worker, Vera's parent runtime reports forced termination and
writes `execution_failure.json` inside the declared client-run output. The exit
code alone does not prove memory exhaustion. Retain this file, mark the run
failed and do not report a completed reconciliation.

### Unsupported PDF hard stop

When either source reports `unsupported_source_layout`, preserve
`vera:mparanza-journal-bank-reconciliation` as the workflow provenance and show this
blocked result before ending the run:

- `status`: `blocked`;
- `source_qualification`: `unsupported_source_layout`;
- `emitted_movements`: `0`;
- `reconciliation_deliverable`: `not_created`;
- `next_supported_input`: a reviewed registration journal PDF, a labelled text-PDF table or a reviewed CSV/XLSX
  export from the source system.

A blocked population does not prevent diagnosis, targeted reading or run-local
adapter development under `references/pdf-recovery.md`. Show readable partial
entries with unresolved issues. Do not invoke population-dependent
`run_reconciliation.py` until qualification passes, invent movements, weaken
independent checks, or relabel a generic comparison as a Vera result. Keep the Vera run
blocked until supported inputs or a reviewed PDF-table or registration-layout mapping are available.

## First Run Workflow

The agent reviews routine source mappings and relationship settings from the
actual source evidence. Record the agent's identity and review date; do not wait
for a professional to confirm an unambiguous header, sign or delimiter. Ask only
for a material ambiguity the evidence cannot resolve. These technical decisions
authorize preparation of reviewable workpapers, not human approval, professional
adoption, signing, filing or external actions.

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
   `source_qualifications.json`, and `suggested_recipe.json`. In an Archive run,
   discover and use `read_studio_run_artifact` with this run's client,
   engagement and run IDs and the actual file path. Use that same recorded
   read for subsequent source and generated-artifact contents needed by the
   model, including the audit, review notes and worker receipts. Printing them
   with `cat` or an ad hoc Python read bypasses the report's observation
   boundary. Local calculations and writing agent decisions may still use
   local files without displaying their contents. Do not run
   reconciliation while any source reports `unsupported_source_layout`. A
   source with `needs_review` has emitted zero rows. Review the physical header,
   monetary role, CSV field delimiter,
   decimal/thousands separators, ambiguous day/month date convention, or
   perimeter field from available evidence; ask the smallest needed question
   only when a material ambiguity remains. Treat the three separators as separate inputs. For a PDF,
   explicitly review the recovered physical header, incoming/outgoing sign
   roles, and all running-balance or total columns. A PDF with no qualified
   physical column grid must use the dedicated reviewed registration adapter, if its supported structure is present; it cannot be approved merely by changing a table mapping.
5. Record explicit decisions for every bank and journal file in
   `review_decisions.json` inside the run output directory, following the JSON
   contract in `../../references/workflow-reference.md`. Use the packaged
   `scripts/seal_review_receipts.py` entrypoint, which calls
   `journal_bank_core.build_mapping_review_receipt` to seal the
   reviewed header rows, mapping, CSV field delimiter, numeric separators,
   `date_convention`, `date_locale` when Italian textual-month dates are
   present, exact `non_movement_summary_labels` when a reviewed tabular total
   row must be excluded, and explicit
   `excluded_monetary_columns` against the current content-addressed source
   artifact reference. The sealer derives `potential_monetary_columns` from
   the current source; it is not an agent decision to supply. If copied from
   inspection, that informational value is ignored and recomputed.
   Supply the exclusions even when empty, and ensure every
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
   required relationship shape (`one_to_one`, `one_to_many`, `many_to_one`, or
   `many_to_many`), no evidence reuse, currency/unit/entity/party perimeter,
   direction treatment, defaults, amount tolerance, and date window. Use
   the same packaged command (which calls
   `journal_bank_core.build_relationship_review_receipt`) to seal the reviewed
   policy against the current bank and journal source references. Every run
   requires the current `journal_bank.relationship.v3` relationship receipt;
   older receipts predate grouped reference allocation and are stale. Do not treat the
   generated proposal as reviewed. Supply the actual `reviewer_ref` and
   `reviewed_on` explicitly. For agent review use an identifier such as
   `agent.codex` and the actual review date; never claim a human reviewed it.
   From the installed Vera root:

```bash
python3 scripts/managed_python_runtime.py --module journal-bank-reconciliation run scripts/seal_review_receipts.py --client-engagement <client_engagement_path> --output-dir <client-run-output> --recipe <client-run-output>/suggested_recipe.json --decisions <client-run-output>/review_decisions.json
```

   This path works without MCP on Claude and Cowork. Re-run inspection with the
   sealed recipe before reconciliation. Changed sources require a fresh review;
   never copy or hand-author receipts or run an external helper script.
7. Run deterministic reconciliation:

```bash
python scripts/run_reconciliation.py <managed-bank-input> <managed-journal-input> --client-engagement <client_engagement_path> --output-dir <client-run-output>/reconciliation --recipe <client-run-output>/suggested_recipe.json --language <it|en|fr|de|es> --document-language <auto|it|en|fr|de|es>
```

Use `--tolerance <amount>` and `--date-window-days <days>` when the user provides explicit thresholds.

8. Review the counts, stages, controls, and limitations in
   `reconciliation_audit.json`, `assurance_gates.json`, and `review_notes.md`
   before final delivery. Validate `relationship_ledger.json`,
   `relationship_residuals.csv`, `material_value_ledger.json`,
   `reconciliation_matches.csv`, `unmatched_bank.csv`, and
   `unmatched_journal.csv` through the deterministic validators and expose
   their paths in the local workbench; do not load their complete row contents
   into model context. `run_reconciliation.py` already runs
   `journal_bank_core.validate_material_value_ledger` before completing.
   The published `semantic_review.py prepare` and `run-all` commands replay the
   current values and receipts again before preparing a worker. Use those
   commands through the installed managed execution service/runtime when a
   fresh replay is needed; do not import the core with an unrelated shell
   Python or install dependencies there. Report matched count, unmatched
   bank count, unmatched journal count, residual or withheld gates, stage
   counts, unresolved/manual-review issues, and output paths.
   `material_value_ledger.json` is intentionally absent when source
   qualification or relationship authority blocks; review the persisted empty
   matches/residuals, unmatched partitions, blocked relationship ledger, gates,
   and audit instead.

## Native semantic residual resolution

This distribution selects the Cowork host in the shared worker policy. A verified isolated invocation adapter is not implemented for this route. Keep residuals in the native review handoff and report that no automatic semantic worker ran. Do not silently use another harness, switch the main chat model, create visible per-case chats, or infer that a named model is callable from its name. Preparation and delivery of the reviewable workpapers continue without professional-approval ceremony.

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
  2. `reference_group` accepts reviewed one-to-many or many-to-one shapes
     defined by a shared identifier or a complete explicit reference list.
     Lists are read only from the mapped reference field, contain at most 100
     distinct alphanumeric identifiers, and must identify exactly one opposite
     row per identifier. Missing, duplicated, or competing membership remains
     unmatched. The same perimeter, date-window and amount checks apply.
  3. `amount_date_unique` is the first conflict-free singleton amount/date
     batch after reference matching is exhausted.
  4. `amount_date_single` is reserved for later conflict-free singleton waves:
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

- For every PDF without a consistent labelled physical table or a reviewed
  supported registration layout, and every
  scanned/OCR-only PDF, report `unsupported_source_layout`; do not emit
  qualified movements or complete reconciliation. Use host-led recovery before
  closing an unfamiliar layout as unsupported. Retain readable entries and show
  the blocked provenance result while population-dependent work remains blocked.
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

## Cowork execution contract

Select the exact files needed for this request. Folder access does not select
all its contents: if the task needs two files in a folder containing four, use
only those two. Resolve genuinely ambiguous choices with the user; reuse clear
choices without another confirmation.

Before parsing documents or creating a client, engagement or run, call
`check_studio_import_sources` with all selected paths on the actual importer
host. It needs no configured Archive and creates no records. If the MCP tool is
unavailable, use the packaged `check-import-sources --source-path <path>` CLI
through the maintained managed launcher on that same host (repeat the flag per
file). A cloud-shell `ls` is not proof of access by a computer-side importer.
Readable attachments, including `/mnt/user-data/uploads/` paths when the importer
can read them, continue directly without requiring a connected computer folder.

If files are unavailable, explain the cause immediately before creating anything:
"The file is in the chat, but the import tool looks for it on your computer."
Do not keep trying that same inaccessible path. Use this recovery sequence:

1. Inspect the host's actual callable file-transfer capabilities and the already
   connected folders. Reuse an authorized ordinary working folder outside the
   managed `Vera/engagements/.../inputs` tree. Offer **Add folder** from the **+**
   menu only when the current host offers it; otherwise explain the available
   connection method. Ask for a folder only if an accessible destination is needed.
2. With a supported bridge, copy only the selected original attachments to that
   folder as files. Compute each original SHA-256 through the host file tools.
   Do not recreate CSV text, convert encodings or line endings, relay document
   contents through model-authored tool arguments, guess a mount translation,
   overwrite a different file with the same name, or scan unrelated folders.
   A verified byte-for-byte copy may reuse its destination on retry.
3. Check the actual destination paths with `check_studio_import_sources`, passing
   `expected_sha256` as the original hashes in the same order as `source_paths`.
   The CLI takes one `--expected-sha256` per source. Archive hashes the destination
   locally and returns `ready=true` only when all supplied original hashes match.
   If no byte-preserving host transfer is available, say so and ask the user to
   save the original selected files to the accessible working folder; then verify
   them. Do not promise a bridge operation that is not callable.
4. Only after all selected sources are ready, select/create the client and
   engagement and import each through `import_studio_client_document` (CLI
   `import-document`). Pass that file's `expected_sha256` / `--expected-sha256`
   when a transfer was required. The importer checks it again during copying and
   creates the input ID and SHA receipt itself. Never manually populate `inputs`.

The path importer does not itself fetch chat attachments. Direct attachment use
requires actual importer access or a demonstrated host transfer. If neither an
importer-side check nor transfer is callable, explain the missing capability
before creating records; do not create a cloud-only replacement for a local Archive.

On any later import failure, disclose the existing `client_id` and `engagement_id`
and resume those same records. A folder-name collision calls for inspecting the
returned existing scope and reusing it when its identity matches; never clear old
folders or change the client's name just to get past the error. A deliberately
separate synthetic test may have a distinct name; retries retain their identities.
Documentless client work needs no file check. Standalone workflows check access
on their own execution host and do not require Archive or a computer folder when
that engine can read the inputs.

Public workflow names select skills; component IDs select module paths.
`financial-report-builder` uses component `report-builder`, `vouching` (historically
called Check Entries) uses `check-entries`, and `purchase-invoice-review` uses
`passive-invoice-audit`. These component IDs are not additional workflows.

For journal-sampling, open-item-reconciliation, journal-bank-reconciliation,
concordato-plan-review, financial-report-builder and vouching only, optional cache
cleanup uses the corresponding component ID from the installed Vera root:

```bash
python3 modules/<module>/scripts/implementation_bootstrap.py --repair
```

For a standalone module, use `python3 scripts/implementation_bootstrap.py --repair`
from its root. This validates the implementation first, then removes only regular,
single-link `__pycache__/*.pyc` files under that module's own `vendor` tree. It
leaves directories, other files, symlinks and shared vendor trees untouched.
This supported maintenance command is the only cache-cleanup exception to the
prohibition on editing the installed tree by hand. It is optional: ordinary
validation and execution tolerate incidental bytecode without removing it.
On a read-only installation, skip cleanup. If the command reports a permission
error, retain that error and continue the ordinary validated workflow when its
checks pass; do not chmod, delete files manually, copy or patch the installation,
or bypass the host's permissions to make cleanup succeed.
If `validate_implementation_tree` ever fails with a file/directory-contract
mismatch, do not delete or modify files inside the installed plugin tree by hand
and do not bypass a sandbox/permission rejection to do so. Stop and report the
exact error instead.

Work from the connected folder and supplied files first. Before a module's Python
helpers, locate the installed plugin root. When it contains `components.json` and
`scripts/managed_python_runtime.py` (as Vera does), run from that root:

```bash
python3 scripts/check_dependencies.py --module <module>
python3 scripts/managed_python_runtime.py --module <module> run scripts/<helper>.py <arguments>
```

If the enclosing plugin does not ship this managed launcher, use the module's
dependency checker and only already-installed dependencies; do not assume that a
standalone module script provisions them.

The managed launcher provisions and reuses one user-scoped CPython 3.12
environment per OS host with the published, hash-checked dependency locks, outside client
folders. Modules and products share this dependency environment; it does not
isolate client matters. This declared dependency setup is authorized as
part of running the workflow; never install arbitrary packages or use ambient
Python for subsequent module helpers. Repeat any declared `--requirements` options
on both commands. Missing ambient imports are a reason to run this setup, not to
abandon the calculation. If setup fails, report its exact error and do not replace
the required calculation with an invented result. Optional OCR setup still needs
separate approval. If setup reports `Host not in allowlist` for PyPI, explain that
Claude Settings > Capabilities > Allow network egress is disabled or restricted.
Ask the user or organization administrator to authorize package-registry access;
never change network permissions silently or work around the restriction. Retry
the same managed setup after access is approved, in a new session if needed.

MCP tools, browser or computer control, and local review servers are optional
enhancements, never completion gates. Cloud Cowork sessions may not expose local
plugin MCP servers even when the plugin is installed; use the packaged Python
workflow through the managed launcher in that case. Do not equate missing MCP
registration with a failed calculation engine. When an optional capability is
unavailable, continue with Markdown and file-based review and state the limitation.

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

Do not use WhatsApp, live INPS browser capture, hosted suggestion or voice
interviews, or custom update services. Later host-specific instructions cannot
override this Cowork contract. When invoked through Vera, Clara or Lucia, task
usage, signed receipts, technical recovery and 1–5-star feedback through the
invoking product's incident service and rating form remain available. Follow the
primary task's workflow-usage contract and product identity. Tutorials retain
their no-reporting boundary.
