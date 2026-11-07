---
name: journal-bank-reconciliation
description: Use when a user wants Codex to reconcile qualified bank statements with journal or ledger exports, map variable tabular formats, run exact amount/date and explicit-reference matching, and produce reviewable CSV/XLSX/JSON outputs. This is a Codex workflow plugin; users should not operate the helper CLIs directly.
---

## Review in Vera

Deliver the result and usable documents in the current chat. If comparing or
editing saved items requires a panel, open the exact work with `vera_open_review`.
**Lavori dello studio → Apri lavoro** opens the same editor. Instructions below
for standalone widgets, browser servers and editable HTML files apply only to
the independent component. In Vera, keep outstanding decisions pending if the
panel is unavailable. Source checks and the workflow's save/apply rules still apply.

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
`finalize_studio_client_workflow` with just the three run identity fields to list the actual output paths. Use the returned paths for the declarations; a review route in the installed package is not a run output. Call the same tool again and declare every listed file with a stable
artifact ID, relative path, concrete purpose, audience, and media type. Review
the closed declaration, then call `complete_studio_client_workflow`; record
`failed` or explicitly cancel an abandoned run instead of treating a partial
directory as a result.

# Journal-Bank Reconciliation

## Jurisdiction and Geneva

For a CH-GE mandate, read `references/geneva.md` before the steps below. It specifies the Geneva input, source and output adaptations within this existing function. Choose governing jurisdiction independently of output language; the ordinary Italian path remains available for IT.


Use this skill when bank statement movements must be reconciled to accounting journal or ledger rows. The plugin is a guided Codex workflow: Codex inspects the files, asks only for unresolved mapping or review assumptions, runs deterministic helper scripts, reviews diagnostics, and delivers outputs.

The workflow is not Italian-only. Support the same five working locales used by the other accounting plugins: `it`, `en`, `fr`, `de`, and `es`. Keep canonical output column names in English for stability, but speak to the user and write summaries in the chosen working language.

Detailed parser, mapping, reconciliation-stage, and review-status notes live in `../../references/workflow-reference.md`. Load that reference only when the run needs extra detail beyond the workflow below.

## Codex-Native Run UX

Before running helper scripts or write-heavy work, identify material choices that would change execution: problem framing, decision angle, risk appetite, scope boundaries, audience, evidence posture, mappings, cut-off, OCR, notification, or review assumptions. Reuse choices already established in the conversation or bound case records. Ask only for unresolved material choices and wait before their dependent work; continue independent authorized preparation. Generate choices from the actual inputs; do not offer named frameworks, regulators, document types, output packages, or issue categories unless the facts cue them or the user must supply a missing custom value. Do not infer missing required evidence, approval, or a material business decision. State routine provisional assumptions when the workflow permits them.

Default output policy: produce the richest normal package for the workflow. DOCX/Word, Excel/CSV, JSON audit, diagnostics, charts, packaged reports, review notes, and Codex-written review files are not choices to propose when they are natural outputs of that plugin; generate them whenever dependencies and source data permit. Ask only when an output is technically impossible, unsafe, or the user explicitly requests a reduced/debug run.

Currency: carry the currency evidenced by the source or confirmed for the engagement (including CHF). Never infer currency from output language or silently default to EUR. If unresolved, obtain the currency before computing or matching amounts. Keep different currencies separate; conversion requires an explicit reviewed rate, date and basis.

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

## Core Principle

Deterministic Python code owns mechanically verifiable source qualification,
exact-decimal normalization, optional sample filtering, explicit-reference,
reference-group, and amount/date matching, content-addressed receipts, physical
source lineage, non-reusing relationship ledgers, independent assurance gates,
and exports.
Codex may inspect source metadata and the bounded inspection preview, propose
recipes, explain assumptions, and review the bounded residual packet. It must
not open the complete raw tables or load complete normalized, matched, or
unmatched row tables into model context. The inspection preview contains at
most the first 20 normalized rows per qualified source; the helper scripts read
and reconcile the complete population locally. Descriptions and beneficiary
names are review context, not automatic match identifiers. The reconciliation
helpers must not make direct OpenAI API calls; only the qualified
residual-worker launcher may transmit the admitted packet.

The user should not interact directly with CLI scripts. Treat scripts as internal tools Codex runs on behalf of the user.

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
`vera:journal-bank-reconciliation` as the workflow provenance and show this
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

1. Ask for the bank file/folder, journal or ledger file/folder, sample file when the user wants to restrict the population, working language, source-document language, and any known mapping hints only if they are not already provided or inferable. Do not ask for output richness. Review the proposed recipe amount tolerance and date window, using the user’s thresholds or the evidence where supplied. Execution inherits the sealed policy.
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
5. Prepare explicit decisions for every bank and journal file following the JSON
   contract in `../../references/workflow-reference.md`. Pass the complete JSON
   as one `--decisions-json` argument to the packaged sealer through `vera_execute`.
   The service persists a content-addressed `review_decisions.<sha256>.json` in
   the same run before sealing. Do not first write it through the chat shell.
   A failed write prevents sealing; retain the run and inspect the terminal job
   result before retrying. Use the packaged
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
python3 scripts/managed_python_runtime.py --module journal-bank-reconciliation run scripts/seal_review_receipts.py --client-engagement <client_engagement_path> --output-dir <client-run-output> --recipe <client-run-output>/suggested_recipe.json --decisions-json '<complete reviewed JSON>'
```

   This path works without MCP on Codex and Cowork. Re-run inspection with the
   sealed recipe before reconciliation. Changed sources require a fresh review;
   never copy or hand-author receipts or run an external helper script.
7. Run deterministic reconciliation:

```bash
python scripts/run_reconciliation.py <managed-bank-input> <managed-journal-input> --client-engagement <client_engagement_path> --output-dir <client-run-output>/reconciliation --recipe <client-run-output>/suggested_recipe.json --language <it|en|fr|de|es> --document-language <auto|it|en|fr|de|es>
```

Omit `--tolerance` and `--date-window-days` to use the sealed recipe policy. If explicitly supplied, these options must match that policy. Incorporate user-provided thresholds into the reviewed policy before sealing it.

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

## Complete grouped review and final workbook

Always use the same production sequence: source qualification, strict matching,
complete grouped review, exact arithmetic/coverage/non-reuse checks, and the
final client workbook. The initial `reconciliation/journal_bank_reconciliation.xlsx`
is an intermediate technical export. Never deliver it as the completed review.

After a qualified strict run, continue automatically:

```bash
python scripts/semantic_review.py run-all <output-dir>/reconciliation \
  --output-dir <output-dir>/semantic-review \
  --client-engagement <client_engagement_path>
```

`run-all` and `run_semantic_resolution_pipeline` call the same maintained grouped
review and exporter. No client-specific helper, manual alternative or case-name
branch may replace that route. Semantic review uses the established host account
and authorized reconciliation scope. Do not ask for a second consent receipt.
An actual host denial stops execution; do not bypass it.

The model sees the remaining bank rows and **all remaining journal counterparts**,
not just exact amount/same-day graph neighbors. Targeted original PDF posting and
continuation text supplies source context absent from normalized descriptions.
Names, dates, signed amounts, descriptions, references and selected posting text
are real case data; they are not automatically anonymized. Unmapped unrelated
columns, whole raw tables, credentials and other-client evidence remain excluded.
Only the qualified native launcher sends the bounded packet. The main chat keeps
its model and reviews the result; it must not manufacture worker output.

Each call focuses on at most 25 bank rows (or remaining journal rows), while
retaining the counterpart context needed to join whole financial groups. A group
can include additional bank rows, so salary totals are not split at a packet
boundary. Subsequent packets exclude accepted bank/journal evidence. The model
may propose one-to-many, many-to-one and many-to-many relationships, timing
explanations and monetary differences. Exact arithmetic never silently absorbs
a fee or a cent. Equal totals alone do not establish a semantic relationship.

The validator requires every focus movement, no reused rows, exact signed sums
for concordant/proposed groups and literal non-monetary source evidence on both
sides of a supported relationship. Unconfirmed groups, differences, missing
counterparts and unresolved questions stay distinct. A named beneficiary alone
is not a matched ledger row. The strict match files are never rewritten.

The normal route is identical for every client and every invocation: qualify
sources, run strict matching, complete grouped review, validate evidence and exact
sums with full coverage and no reused rows, then export the four-sheet workbook.
The main chat must not replace an incomplete worker review with manual decisions.
Every returned Codex process retains its raw events, stderr, observed usage and
duration before response interpretation. A complete, otherwise verified tool-free
turn with multiple assistant messages is rejected and can be retried through the
same stage, never adopted by choosing one message. Invalid domain output can
also be corrected within the same maximum of three calls per packet. Source,
executable, isolation and forbidden-tool failures stop; they are not format retries.
Missing terminal usage remains unknown, never zero. Reopening unchanged validated work replays
source/response bindings and the retained groups without another model call.

After complete coverage, the same producer writes:

- `grouped_reconciliation_result.json`: checked relationships, source binding,
  row counts, differences and measurements for all attempts;
- `Riconciliazione_banca_partitario.xlsx`: **Sintesi, Relazioni, Banca, Partitario**,
  with concordant groups, proposals, differences and required documents;
- `grouped_review_status.json`: complete/incomplete outcome and actual final path.

Deliver the returned final workbook and its result, not the intermediate export.
Completion means every supplied movement has an explicit disposition; it does
not mean all differences disappeared, an invoice allocation was verified, a
professional adopted the work or entries were posted. If the worker, source
replay, coverage, evidence or financial validation cannot complete, retain the
intermediates and diagnose that block. Never call the technical workbook final.
Report full elapsed time, all measured model attempts and any missing token or
privacy observations honestly. Privacy reporting failures do not suppress the
useful accounting result.

### Reviewed bank working copies

When a bank XLS has undated manual calculation cells, use the maintained
`inspect_inputs.py --prepare-bank-json '<reviewed JSON>'` action in the source
preparation run. Decisions identify the exact bound source path/hash, sheet,
zero-based date/description/amount columns, date convention, and every excluded
physical row. Include `reviewer_ref` and `reviewed_on`. The action retains all
excluded cells and original-to-working row links. It never silently discards an
undated amount. Seal these preparation outputs and bind the working copies as
same-engagement upstream inputs for the calculation stage. Do not write an ad hoc
customer parser or copy old review conclusions into a fresh worker response.

### Diagnostic row triage (not final completion)

`prepare`, `run-worker`, `validate` and `run_row_triage_pipeline` retain the narrow
historical exact-edge graph for diagnosis and historical receipt replay only.
They do not perform complete grouped reconciliation or produce the final client
workbook. Use `run-all` for every normal completion, including a resumed run.
The technical certainty funnel must not be presented as a count of completed
bank-to-ledger relationships. A counterparty name is not a matched posting.

Runtime capabilities, native host dispatch, isolation controls, source replay and
receipt validation still apply. See `../../references/workflow-reference.md`
and `../../references/native-host-workers.md` for the low-level diagnostic
protocol. Never reconstruct `codex exec`, change the current chat model,
hand-author worker responses or bypass an actual host denial. The grouped stage
uses the same maintained native launcher; it does not introduce a model API or
new provider. Final arithmetic and review status do not authorize posting.

## Mapping Recipe Rules

Codex can adjust the recipe JSON generated in the work folder. Use per-side recipe sections:

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

Do not ask the user to edit JSON. Ask the user in business terms, then Codex updates the recipe and reruns the deterministic scripts.

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
other than canonical `positive`, `negative`, or `zero`, Codex must confirm the
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

Codex may inspect individual rows and explain unresolved items, but should keep review judgment explicit in the final response rather than silently changing script outputs.

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
- `reconciliation/journal_bank_reconciliation.xlsx` (intermediate technical export);
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

Final delivery additionally requires `semantic-review/grouped_reconciliation_result.json` and the returned four-sheet `semantic-review/Riconciliazione_banca_partitario.xlsx`. No intermediate workbook substitutes for these outputs.

## MCP Review UI

For the reduced operational bank-exception view after semantic preparation,
pass only `review_payload_path` pointing to
`semantic-review/operational_review_payload.json` and, when available, the
current `client_engagement`. Do not combine this sibling payload with the
reconciliation folder's `run_intake_path`, `ui_decisions_path` or
`final_artifacts_path`. This operational handoff is read-only: its render has
`decision_policy.can_persist=false`. It does not record professional decisions
or alter strict reconciliation. Validate it, render using the returned opaque
reference, and request only selected cases as below.

The separate strict reconciliation review uses the four sibling files listed
below and supports its maintained decision-persistence route. Do not substitute
it for the reduced operational queue or move/copy payloads between folders to
bypass the path check.

When the local MCP server is available, prefer the OpenAI-style review handoff:

1. Locate `run_intake.json`, `review_payload.json`, `ui_decisions.json`, and
   `final_artifacts.json` in the reconciliation output folder without reading
   the complete private review payload into model context.
2. Call `validate_journal_bank_review` with `review_payload_path` and the
   sibling path fields. Validation returns a non-identifying case index and an
   opaque four-hour review reference.
3. Call `render_journal_bank_review` with only that reference. The server sends
   the complete payload to `ui://widget/journal-bank-review.html` through
   component-only metadata. The normal render requests the expanded Codex
   panel. If the host keeps the review inline, “Apri pannello” reopens the same
   review. From “Lavori dello studio”, select the same archived run and choose
   “Apri lavoro” to reach its saved review after leaving the conversation.
4. Start from the index and call `get_journal_bank_case_context` for no more
   than 25 specifically selected cases at a time. The deterministic
   post-mapping projection removes unmapped and empty fields, source locators,
   technical row IDs, the redundant absolute amount, write targets, and
   duplicate facts. Exact references, movement numbers, shared references,
   and account codes remain off by default; request them only when the selected
   accounting judgment requires exact identity.
5. Use the widget to inspect unmatched bank rows, unmatched journal rows,
   matched-pair evidence, diagnostics, and generated workbook/CSV/JSON outputs.
6. When the reviewer records actions in the widget or Codex collects decisions
   through fallback review, call `save_journal_bank_decisions` so
   `ui_decisions.json` is validated and persisted. When the reviewer is done,
   call `apply_journal_bank_decisions` so `applied_decisions.json` and
   `final_artifacts.json` reflect accepted, edited, unclear, skipped, or
   document-requested items. Then reread `assurance_gates.json`: review
   completion is not report readiness. Unmatched rows, exact residuals, failed
   source/preparation gates, or receipt mismatch keep the result blocked.

This is purpose-limited routing, not anonymization or pseudonymization of the
professional case data: selected case context can still contain real names,
descriptions, dates, amounts, and professional references. If MCP rendering is unavailable, fall
back to a locally prepared markdown projection of only the specifically
selected cases, using the same field exclusions and exact-identifier rule; do
not read the complete `review_payload.json` into model context. The human can
still use the complete local CSV/XLSX outputs. Do not promote ambiguous rows to matched by judgment alone;
change deterministic rules and rerun when a systematic correction is needed.
Keep review decisions pending unless they are recorded in `ui_decisions.json`
and consumed into `applied_decisions.json`. Small setup choices should stay in
chat or, when this conversation is in Plan mode and the tool is available,
native Plan-mode choices.

## Language Policy

Ask for or infer two language assumptions:

- `language`: working/output language for Codex's questions and final summary; one of `it`, `en`, `fr`, `de`, `es`.
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

## Plugin Improvement Feedback

At the end of every completed or blocked plugin run, after reporting the deliverables, briefly identify concrete improvements that would have made this plugin run better. Base suggestions on the actual session, such as a new bank export format, a brittle PDF text extractor, a missing deterministic extraction script, a missing column-mapping rule, an unclear assumption, a needed fixture, output gaps, installation friction, or repeated manual steps.

When there is something useful to report, write a short improvement note with:

- observed gap;
- proposed improvement;
- why it matters;
- relevant input/output file names when available;
- suggested next engineering action.

Keep the improvement note local to chat or run artifacts. Do not submit it to
Mparanza automatically. When this workflow runs through Vera, use Vera's
consent-based Plugin Improvement Feedback process for any transmission.

## Cowork execution contract

For journal-sampling, open-item-reconciliation, journal-bank-reconciliation,
concordato-plan-review, report-builder and check-entries only, optional cache
cleanup is available from the installed Vera root:

```bash
python3 modules/<module>/scripts/implementation_bootstrap.py --repair
```

For a standalone module, use `python3 scripts/implementation_bootstrap.py --repair`
from its root. This validates the implementation first, then removes only regular,
single-link `__pycache__/*.pyc` files under that module's own `vendor` tree. It
leaves directories, other files, symlinks and shared vendor trees untouched.
If `validate_implementation_tree` ever fails with a file/directory-contract
mismatch, do not delete or modify files inside the installed plugin tree by hand
and do not bypass a sandbox/permission rejection to do so. Stop and report the
exact error instead.


### Choosing and changing the matching tolerance

The professional can state a tolerance in ordinary chat, including zero or a
nonzero value (for example “use EUR 0.12”). Interpret an unambiguous localized
amount into exact canonical Decimal text without rounding it. Carry that value
into the relationship policy and seal it with the ordinary review helper.
Do not substitute EUR 0 or EUR 1 for a user-selected or established studio value.
If neither exists, disclose the selected value as a draft assumption, not as
user approval; no obligatory technical questionnaire is needed to prepare a draft.

When the professional changes the tolerance, retain the earlier recipe, receipt
and outputs, prepare a revised recipe with the new value, and use
`seal_review_receipts.py` again before recalculating into a fresh output directory
(or a new managed run when the earlier run is closed). Do not edit old receipts
or change execution flags alone. Read the resulting audit and review notes, and
use that exact recorded value in downstream review and the delivered explanation.
State whether it came from the professional, an established studio instruction,
or a disclosed draft assumption. Matching within tolerance does not authorize a
write-off or a new accounting entry: keep actual differences visible for review.
