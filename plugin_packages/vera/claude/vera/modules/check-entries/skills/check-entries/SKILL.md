---
name: check-entries
description: Use when a user wants Claude to compare qualified Journal Sampling entries with FatturaPA XML or supporting PDFs, run exact deterministic evidence checks, and produce reviewable lineage-bound outputs. This is a Claude workflow plugin; users should not operate the helper CLIs directly.
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

Never write run outputs inside this Git workspace, `static/shared`, `protected_downloads`, or any GitHub Pages/static-site folder unless the task is explicitly plugin packaging/release. A user-data run must use the exact output root in the Studio Archive Check Entries `client_engagement` context. Inspection uses its `inspection` child and checks use its `checks` child. Do not invent a sibling output folder or run an unbound product CLI.

The context is a portable customer-folder run record, not a machine-local
workspace pointer. Load it through the workflow gate so current absolute paths
are hydrated after a folder rename. Use only its exact upstream and support
bindings; never scan all files imported into the engagement.

# Check Entries

Use this skill when sampled, qualified journal entries must be checked against
supporting documents. Three artifacts define the semantic boundary from one
finalized Journal Sampling run: `normalized_journal.csv`, its sealed
`normalization_diagnostics.json`, and `journal_sample.csv`. Bind those three
artifacts plus every normalization companion that Check Entries reads to replay
assurance: `normalization_recipe.json`, `suggested_recipe.json`,
`reviewed_decisions.json`, `assurance_gates.json`, `assurance_envelope.json`,
and `qualification_review_payload.json`. The normalized population and
diagnostics validate preparation; the sample is the exact row selection. Check
Entries does not check the unsampled population and does not infer headers,
mappings, amounts, or movement identifiers from a raw journal. professional reviews
evidence ambiguities and professional conclusions after the mechanical checks.

The workflow is not Italian-only. Support the same five working locales used by the reconciliation plugin: `it`, `en`, `fr`, `de`, and `es`. Keep canonical output column names in English for stability, but speak to the user and write summaries in the chosen working language.

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

Journal Sampling owns source parsing, reviewed mappings, source qualification,
and canonical monetary preparation. Check Entries deterministically validates
that sealed boundary, extracts support facts, performs exact comparisons, binds
receipts and lineage, and exports review artifacts. Claude owns evidence
sufficiency and professional conclusions. Helper scripts must not make direct OpenAI API calls.

The user should not interact directly with CLI scripts. Treat scripts as internal tools Claude runs on behalf of the user.

## Inputs

Required:

- an exact, closed artifact handoff from one review-ready or completed Journal
  Sampling run in the same client and engagement. Its three semantic IDs are
  `prepared.normalized_journal`, `internal.normalization_diagnostics`, and
  `prepared.journal_sample_csv`; it must also bind the six normalization
  companions named above so assurance replay uses only this run's input view;
- one explicit evidence batch: a FatturaPA ZIP/XML, a local export produced by
  an authorized accounting-system connector, or one or more supporting PDFs,
  each imported into that engagement as an immutable `support` receipt;
- a Check Entries run prepared from only those upstream artifact references and
  support `input_ids`, then moved to `running` before execution.

Optional:

- exact amount tolerance expressed as decimal text;
- date window in days;
- working language and source-document language.

Raw XLS/XLSX/CSV/PDF journals never enter Check Entries execution. Run Journal
Sampling first. Ambiguous or inferred mappings must be reviewed and hash-bound
there before Check Entries can run. A support import does not create a Check
Entries context or automatically add itself to an existing run.

## First Run Workflow

1. Resume the exact client engagement before acquiring support. Call
   `list_studio_archive_clients`, select the stable client without inferring it
   from a filename, then call `list_studio_client_engagements`. The latter
   reads the customer-folder ledger, so the initiating chat is not required.
   Select one review-ready or completed Journal Sampling run whose artifact
   manifest contains the exact normalized population, diagnostics, sample, and
   six normalization companions required for assurance replay.
   If more than one engagement or sampling run could apply, show the choices
   and ask; never pick by recency or filename alone.
2. Apply this acquisition ladder: ask first for the ZIP containing all relevant
   FatturaPA XMLs; if unavailable, offer an authorized accounting-system
   connection that materializes a local ZIP/folder export; otherwise request
   PDFs only for unresolved sampled entries. Never request credentials, tokens,
   cookies, or one-time codes. Ask for working language, source-document
   language, and evidence assumptions only when unresolved.
   When the user chooses connection, use a callable provider-specific connector
   only after confirming the studio/client has authorized access. Restrict the
   connector action to read/export for the selected client and period, record
   the connector name, and pass its local ZIP/folder result to Check Entries.
   If no connector for the named accounting system is callable, say so rather
   than simulating a connection; ask which provider must be integrated or move
   to the targeted-PDF fallback at the user's direction.
   Explain that each external original is preserved. After the user authorizes
   a controlled copy, call `import_studio_client_document` with role `support`
   and the selected `engagement_id` for each file. Retain the returned immutable
   `input_ids`; import does not prepare or start Check Entries. Do not accept
   support from another customer folder or engagement directly.
3. Call `start_check_entries_from_sample` with the selected `client_id`,
   `engagement_id`, completed Journal Sampling `sample_run_id`, and only the
   current evidence-batch `support_input_ids`. This operation resolves and
   validates the complete internal handoff, prepares an idempotent Check
   Entries run, and starts it. Do not ask the user to identify internal files
   or assemble artifact references. Load the returned `client_engagement_path`
   and use only its hydrated bound paths. A later ZIP or PDF delivery must be
   imported and started as another run; it cannot mutate this run's input
   manifest. If its exact byte selection repeats an earlier run, set
   `new_run=true` only after the user confirms that it is intentionally a
   separate evidence batch.
4. Run dependency checks from the plugin directory:

```bash
python scripts/check_dependencies.py
```

If requirements are missing, install from `requirements.txt` only when the environment allows it or explain what dependency capability is missing.

5. Confirm that Journal Sampling produced a qualified complete population and
   exact sample, then run inspection to validate their closure and inventory
   only the bound support batch:

```bash
python scripts/inspect_entries.py <bound-normalized-journal> <bound-support-path-or-closed-folder> --output-dir <client-run-output>/inspection --client-engagement <check-client-engagement.json> --language <it|en|fr|de|es> --document-language <auto|it|en|fr|de|es>
```

6. Read `inspection.json` and `suggested_recipe.json`. If source qualification,
   diagnostics hash, receipt, row closure, or exact monetary closure fails, stop
   and return to Journal Sampling. Do not repair or infer preparation inside
   Check Entries.
7. Record only Check Entries settings such as exact amount tolerance and date
   window in the work-folder recipe.
8. Run deterministic checks:

```bash
python scripts/run_checks.py <bound-normalized-journal> <bound-support-path-or-closed-folder> --output-dir <client-run-output>/checks --recipe <client-run-output>/inspection/suggested_recipe.json --client-engagement <check-client-engagement.json> --language <it|en|fr|de|es> --document-language <auto|it|en|fr|de|es>
```

9. Review `check_audit.json`, `pdf_inventory.json`, `check_results.csv`, and
   `review_notes.md` before final delivery. Report the stable client and
   engagement binding, exact Journal Sampling run and sample, evidence-batch
   input IDs, support matching coverage, status counts, unresolved/manual-review
   rows, mismatches, and output paths. Complete every write-producing MCP save
   or apply transaction before sealing the outer customer-folder run.
10. After the last output write, call `finalize_studio_client_workflow` and
   declare every physical output with a unique artifact ID, relative path,
   concrete purpose, audience, and media type. Finalization moves the run to
   `ready_for_review`; an undeclared, changed, partial, or empty output tree is
   not available. Review the final declaration, then call
   `complete_studio_client_workflow`. If execution fails, record `failed`;
   explicitly cancel an abandoned run rather than deleting it.

## Prepared-Evidence Contract

- Treat the bound `prepared.journal_sample_csv` as an input, not a display-only
  output. Join it to the qualified normalized population by the preserved
  physical source locators and reject missing, duplicate, or extra matches.
  Check only the resulting sampled rows.
- Preserve `source_file`, `source_sheet`, `source_page`, `source_row`,
  `movement_number`, `currency`, `unit`, `reported_increment`, and the Journal
  Sampling qualification ID.
- Never synthesize a movement number from a row index.
- Derive `prepared_entry_id` from the qualified source identity, exact source
  locator, and row-owned posting fields so unrelated population changes do not
  rename an entry.
- Reject stale diagnostics, modified CSV bytes, incomplete qualifications,
  non-canonical amounts, failed debit/credit closure, zero rows, and wrong
  schema/order.
- Replay the complete Journal Sampling assurance envelope, gate register,
  reviewed decisions, original-source and exact retained-recipe receipts,
  normalized receipt, and exact 24-file Journal Sampling/shared implementation
  receipt set. Before Polars parses the captured normalized bytes, invoke
  Journal Sampling's isolated `-I -B` replay CLI and require raw source plus the
  retained recipe to reproduce the CSV and material preparation contract.
  Recheck every current receipt after support extraction so mid-run mutations
  block output.
- Monetary values and tolerances remain canonical decimal strings in every
  CSV/JSON artifact.

## Deterministic Check Rules

- A PDF can match only when exactly one candidate has a distinctive movement
  identifier beside an accounting movement label in text extracted from its
  immutable captured bytes, or a reviewed relationship receipt binds the exact
  prepared entry, support artifact, support locator, and recording exception.
  Filenames never establish identity. Generic numeric/year/single-letter
  tokens, page numbers, row numbers, and one-entry/one-PDF coincidence are
  never identity evidence.
- FatturaPA matching precedes PDF matching and requires exactly one candidate
  with a distinctive invoice number in labelled invoice syntax plus at least
  one corroborating amount or date signal, unless the same exact reviewed
  relationship receipt exists. Generic numeric/year/single-letter tokens do
  not establish identity. Amount/date/currency coincidence can confirm
  identity but can never establish it.
- Capture each support artifact once. Its receipt, PDF extraction or bounded
  FatturaPA parsing, qualification, comparison, numeric ledger, and final replay
  must all use those same captured bytes. A permanent live-source change
  blocks the run; a temporary swap can never change the parsed facts.
- When support is a directory, seal its complete nested file
  membership in `support_manifest.json` using canonical Unicode/casefold-unique
  relative paths and receipts. Re-enumerate that membership at final
  validation. Added, deleted, replaced, aliased, or duplicate paths block the
  run, temporary-prefixed names are never omitted, unsupported file types fail
  source qualification, and symlinks, hardlink aliases, or special entries are
  rejected. ZIP member
  locators always include the captured archive path
  (`archive.zip!/member.xml`) and bind to that archive's receipt.
- Source-qualify every PDF, XML, ZIP, and P7M artifact. Readable PDF extraction
  is separate from identity. P7M is unsupported until a bounded decoder and
  signature-validation policy exists. Parse errors, failed qualifications, and
  missing support prevent a passed source gate.
- Mechanical `ok` additionally requires an exact reviewed party perimeter.
  Prefer tax IDs. Exact names are allowed only for structured XML under the
  reviewed `casefold_alnum_v1` normalization contract. Free-text party or
  beneficiary containment is diagnostic only. A reviewed relationship receipt
  and recording exception can close a genuinely missing party field.
  In PDF text, an exact tax ID must be coupled to the reviewed
  supplier/customer role label; a generic role is unresolved and an opposite
  role is a mismatch.
- An authorized connector is an acquisition mechanism, not a matching rule.
  Record the connector name with `--connector-name` after it has produced a
  local export; the helper scripts do not authenticate or call provider APIs.
- Amount magnitude checks use exact Decimal values with the configured
  canonical tolerance; binary floats and ambiguous numeric strings are
  rejected. Magnitude cannot pass alone: the sealed journal `amount_signed`
  direction must close independently.
- Date checks compare extracted dates within the configured day window.
- FatturaPA preserves `TipoDocumento` and bounded document polarity only as
  diagnostic source facts. Neither determines which journal line/account side
  is being checked. Automatic XML identity still requires a distinctive
  invoice number plus amount or date corroboration.
- PDF currency requires the exact expected ISO code or an exact reviewed
  currency receipt. `$` alone is ambiguous among USD/CAD/AUD, and an explicit
  conflicting ISO 4217 label cannot be overridden.
- The numeric ledger carries exact `amount_signed`, signed support amount,
  signed difference, absolute difference, and passing support amount values
  through prepared CSV plus CSV/XLSX outputs. Decimal arithmetic is replayed
  even for mismatches.
- PDF invoice/credit-note labels are diagnostic document-polarity facts only.
  Signed support values, differences, and `ok` require an exact reviewed
  direction receipt bound to the normalized journal, prepared entry, captured
  support artifact, and exact locator. Without one they remain withheld/manual
  review; stale or opposite-side decisions are rejected.
- Beneficiary containment is diagnostic only and cannot establish the reviewed
  party perimeter or promote a result.
- Rows with missing support are `missing_support`.
- `ok` requires unique explicit/reviewed support, a closed party perimeter, and
  amount, date, currency, and direction checks present and passing. Missing
  checks can never emit `ok`.
- Rows with deterministic mismatches are `mismatch`.
- Rows with no amount/date/beneficiary fields are `manual_review`.

Every row separately records extracted evidence facts and
`professional_conclusion=pending_review`. An ambiguous XML/PDF match, support
reuse, mismatch, or missing evidence remains review. Reviewer acceptance does
not by itself pass reconciliation, semantic-review, reporting, or publication
gates.

## Reviewed Party And Relationship Decisions

After inspection, Claude may add only decisions actually made by the reviewer to
the work-folder recipe:

- `reviewed_party_perimeters`: shared reviewed-decision receipts with type
  `check_entries_party_perimeter`, adapter
  `check_entries.party_perimeter@1`, exact
  `source.normalized_journal` binding, one prepared-entry ID, expected party
  role, and reviewed tax IDs or names. Names require the explicit
  `casefold_alnum_v1` contract.
- `reviewed_support_relationships`: shared reviewed-decision receipts with type
  `check_entries_support_relationship`, adapter
  `check_entries.relationship@1`, exact normalized-journal and support-artifact
  bindings, one prepared-entry ID, one exact support locator, confirmed status,
  and a non-empty recording exception.
- `reviewed_currency_decisions`: type `check_entries_currency`, adapter
  `check_entries.currency@1`, exact normalized-journal plus PDF-artifact
  bindings, one prepared-entry ID, exact PDF locator, expected ISO currency,
  confirmed status, and a non-empty recording exception.
- `reviewed_direction_decisions`: type `check_entries_direction`, adapter
  `check_entries.direction@1`, exact normalized-journal plus support-artifact
  bindings, one prepared-entry ID, exact locator, direction equal to sealed
  `amount_signed`, confirmed status, and a non-empty recording exception.

Do not infer or fabricate reviewer identity, review date, party perimeter,
relationship, or recording exception. If the reviewer has not made the
judgment, leave the arrays empty and keep the row in manual review.

## Expected Outputs

- `inspection.json`;
- `suggested_recipe.json`;
- `checks/normalized_entries.csv`;
- `checks/prepared_support_facts.csv`;
- `checks/pdf_inventory.json`;
- `checks/invoice_inventory.json`;
- `checks/support_manifest.json`;
- `checks/check_results.csv`;
- `checks/check_results.xlsx` when XLSX dependencies are available;
- `checks/check_audit.json`;
- `checks/numeric_evidence_ledger.json`;
- `checks/assurance_envelope.json`;
- `checks/review_notes.md`;
- `checks/run_intake.json`;
- `checks/review_payload.json`;
- `checks/ui_decisions.json`;
- `checks/applied_decisions.json` after reviewer decisions are applied;
- `checks/final_artifacts.json`.

## Cowork review handoff

The normal Cowork completion point is delivery
of the reviewable draft, artifact card, and source/review files in the connected
folder. When the Check Entries review MCP is callable, pass the local
`review_payload.json` path to validation so the server loads the private file
without placing it in model context. Begin from the returned non-identifying
case index and opaque review reference, then request no more than 25
specifically selected cases at a time. Physical paths, filenames, write targets,
technical row and artifact IDs, empty fields, and duplicate facts stay out.
Exact invoice, movement, account, tax, and reference identifiers stay off by
default and are requested only when a selected evidence judgment requires exact
identity comparison. If the MCP is unavailable, prepare the same bounded
projection only for specifically selected cases; do not read the complete
`review_payload.json` into model context. Report the package as
`ready_for_professional_review` where that status exists, otherwise as
`pending_review`.

When a validated MCP tool, browser interface, or local workbench is callable,
it may optionally persist or apply reviewer actions from its private review
reference. Its absence never blocks delivery. Never claim `applied` or
`final_ready` unless corresponding persisted artifacts prove it. A file or
chat review without those artifacts remains pending professional review.
Opaque case handles are routing controls, not anonymization or
pseudonymization of selected professional facts.

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
IT: Usa Check Entries per il cliente <cliente>. Riprendi il campione Journal Sampling <campione> e controllalo contro questo lotto di supporti <percorso>. Lingua: it. Lingua documenti: auto.
EN: Use Check Entries for <client>. Resume Journal Sampling sample <sample> and check it against this support batch <path>. Language: en. Document language: auto.
FR: Utilise Check Entries pour <client>. Reprends l'échantillon Journal Sampling <échantillon> et contrôle-le avec ce lot de justificatifs <chemin>. Langue: fr. Langue des documents: auto.
DE: Verwende Check Entries für <Mandant>. Öffne die Journal-Sampling-Stichprobe <Stichprobe> und prüfe sie gegen diesen Belegsatz <Pfad>. Sprache: de. Dokumentsprache: auto.
ES: Usa Check Entries para <cliente>. Reanuda la muestra de Journal Sampling <muestra> y compruébala con este lote de soportes <ruta>. Idioma: es. Idioma de los documentos: auto.
```

## Failure Modes

- If support PDFs are scanned/OCR-only and no text is extracted, report that deterministic PDF text extraction is insufficient and list the affected files.
- If preparation or mapping evidence is missing, stop and return the source to
  Journal Sampling; do not run partial checks.
- If an explicit invoice-number relationship or a distinctive/labeled movement
  identifier is absent, amount/date coincidences remain unresolved evidence;
  they do not auto-match XML or PDF support.
- If a deterministic rule flags many false positives, write the gap as a plugin improvement suggestion rather than overriding the output silently.
