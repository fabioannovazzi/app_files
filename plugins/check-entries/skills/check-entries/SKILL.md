---
name: check-entries
description: Use when a user wants Codex to compare qualified Journal Sampling entries with FatturaPA XML or supporting PDFs, run exact deterministic evidence checks, and produce reviewable lineage-bound outputs. This is a Codex workflow plugin; users should not operate the helper CLIs directly.
---

## Output Location Rule

Never write run outputs inside this Git workspace, `static/shared`, `protected_downloads`, or any GitHub Pages/static-site folder unless the task is explicitly plugin packaging/release. A user-data run must use the exact output root in the Studio Archive Check Entries `client_engagement` context. Inspection uses its `inspection` child and checks use its `checks` child. Do not invent a sibling output folder or run an unbound product CLI.

# Check Entries

Use this skill when qualified journal entries must be checked against supporting
documents. Check Entries consumes `normalized_journal.csv` and the adjacent
sealed `normalization_diagnostics.json` written by Journal Sampling. It does
not infer headers, mappings, amounts, or movement identifiers from a raw journal.
Codex reviews evidence ambiguities and professional conclusions after the
mechanical checks.

The workflow is not Italian-only. Support the same five working locales used by the reconciliation plugin: `it`, `en`, `fr`, `de`, and `es`. Keep canonical output column names in English for stability, but speak to the user and write summaries in the chosen working language.

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

Journal Sampling owns source parsing, reviewed mappings, source qualification,
and canonical monetary preparation. Check Entries deterministically validates
that sealed boundary, extracts support facts, performs exact comparisons, binds
receipts and lineage, and exports review artifacts. Codex owns evidence
sufficiency and professional conclusions. Helper scripts must not make direct OpenAI API calls.

The user should not interact directly with CLI scripts. Treat scripts as internal tools Codex runs on behalf of the user.

## Inputs

Required:

- Journal Sampling `normalized_journal.csv` with adjacent
  `normalization_diagnostics.json`, a complete population status, qualified
  source records, a valid CSV receipt, and a persisted Journal Sampling client
  context;
- one support source: a FatturaPA ZIP/XML, a local export produced by an
  authorized accounting-system connector, or a supporting PDF file/folder,
  imported into the same Studio Archive client and engagement;
- a persisted Check Entries `client_engagement` context returned by that
  support import.

Optional:

- exact amount tolerance expressed as decimal text;
- date window in days;
- working language and source-document language.

Raw XLS/XLSX/CSV/PDF journals never enter Check Entries execution. Run Journal
Sampling first. Ambiguous or inferred mappings must be reviewed and hash-bound
there before Check Entries can run.

## First Run Workflow

1. Resume the exact client engagement before acquiring support. Call
   `list_studio_archive_clients`, select the stable client without inferring it
   from a filename, then call `list_studio_client_engagements`. The latter
   exposes persisted Journal Sampling runs and exact normalized-journal paths,
   so an archived initiating chat is not required. If more than one engagement
   or normalized run could apply, show the choices and ask the user; never pick
   by recency or filename alone. The selected run must report
   `normalization_available=true`.
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
   Explain that the original support file is preserved. After the user
   authorizes a controlled copy, call `import_studio_client_document` with role
   `support` and the selected `engagement_id`. Use the returned imported path,
   Check Entries context, and context path. Do not accept support from another
   folder or engagement directly.
3. Run dependency checks from the plugin directory:

```bash
python scripts/check_dependencies.py
```

If requirements are missing, install from `requirements.txt` only when the environment allows it or explain what dependency capability is missing.

4. Confirm that Journal Sampling produced a qualified complete population, then
   run inspection to validate its closure and inventory support:

```bash
python scripts/inspect_entries.py <same-engagement-normalized-journal.csv> <imported-support-path-or-support-folder> --output-dir <client-run-output>/inspection --client-engagement <check-client-engagement.json> --language <it|en|fr|de|es> --document-language <auto|it|en|fr|de|es>
```

5. Read `inspection.json` and `suggested_recipe.json`. If source qualification,
   diagnostics hash, receipt, row closure, or exact monetary closure fails, stop
   and return to Journal Sampling. Do not repair or infer preparation inside
   Check Entries.
6. Record only Check Entries settings such as exact amount tolerance and date
   window in the work-folder recipe.
7. Run deterministic checks:

```bash
python scripts/run_checks.py <same-engagement-normalized-journal.csv> <imported-support-path-or-support-folder> --output-dir <client-run-output>/checks --recipe <client-run-output>/inspection/suggested_recipe.json --client-engagement <check-client-engagement.json> --language <it|en|fr|de|es> --document-language <auto|it|en|fr|de|es>
```

8. Review `check_audit.json`, `pdf_inventory.json`, `check_results.csv`, and `review_notes.md` before final delivery. Report the stable client and engagement binding, support matching coverage, status counts, unresolved/manual-review rows, mismatches, and output paths.

## Prepared-Evidence Contract

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

After inspection, Codex may add only decisions actually made by the reviewer to
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

## MCP Review Handoff

After `scripts/run_checks.py` completes, read `checks/run_intake.json` and
`checks/review_payload.json`. Treat the review payload as the structured
contract for reviewer-facing UI: supported rows, missing support, mismatches,
manual-review rows, PDF extraction diagnostics, mapping issues, and generated
artifacts.

When the `checkEntriesWidgets` MCP server is available, call
`validate_check_entries_review` with the complete `review_payload.json` object.
If validation passes, call `render_check_entries_review` with the same payload
and optional `run_intake`, `ui_decisions`, and `final_artifacts` objects. When
the reviewer records actions in the widget or Codex collects decisions through
fallback review, call `save_check_entries_decisions` with `run_intake`,
`review_payload`, current `ui_decisions`, and the decision list so
`ui_decisions.json` is validated and persisted. When the reviewer is done, call
`apply_check_entries_decisions` with the same review payload, current
`final_artifacts`, and decision list so `applied_decisions.json` and
`final_artifacts.json` reflect the accepted, edited, unclear, skipped, or
document-requested items. Do not hand-build another HTML page for the same
review.

Never remove or recompute the review payload digest outside the workflow.
`ui_decisions.json` and `applied_decisions.json` must retain the exact
`review_payload.content_sha256` binding. Reject stale review state. Before any
apply write, replay the locally persisted envelope; caller-provided gate
summaries never grant `final_ready`. Structured edits may change only the
authorized `review_notes` cell for the stable prepared entry, must close to the
receipted original CSV, regenerate native outputs, and reseal
`assurance_envelope.json`. Accept-only review also creates a reviewed-decision
receipt and reseals the envelope. Review completion alone cannot promote
withheld professional gates.

Every deterministic run starts from a fresh output tree. On success it cannot
inherit stale applied decisions or revisions; on any early or late failure it
restores the exact prior run. MCP save/apply likewise uses a private staged
tree, rejects internal symlinks, hardlinks, special entries, and post-preflight
path swaps, and rolls back every revision, structured edit, workbook
regeneration, reseal, manifest, and trace write on failure.

For every assured validate, render, save, or apply path, require a fresh
mechanical rederivation rather than accepting persisted hashes or gates as
authority. The run receipts exact `execution_recipe.json` bytes. Preflight
rebuilds from the still-available normalized journal, support source, and
original recipe in a private fresh directory, then compares support facts,
result CSV/XLSX, numeric evidence, material audit/review/intake projections,
gates, professional conclusion, and final status. A successor may differ only
through the exact reviewed-decision/effect lineage and authorized
`review_notes` cells. If an original input or recipe is absent or changed,
stop.

Invoke supported Python launchers with `python -I -B`. Before importing any
local implementation module, they snapshot the bootstrap without following
aliases and close the exact 26-file Check Entries/shared-assurance
implementation tree. Reject any unowned entry, bytecode cache, symlink,
hardlink, FIFO, or other special file. Load the validated assurance package
from its exact directory without exposing the broader vendor parent as an
import root. Close the owned Journal Sampling tree before replaying its
implementation receipts or executing its normalization replay CLI.

Do not describe these controls as package authentication or reviewer
authentication. Local receipts and self-hashes prove consistency only; the
mutable package has no external attestation here and reviewer identity is not
cryptographically established. Fresh re-performance rejects a stale
self-resealed normalized population, but it cannot authenticate a fully
regenerated internally consistent package or reviewer authority. Keep
publication withheld.

If MCP rendering is unavailable, continue by reading `review_payload.json` and
reviewing through Markdown/chat. Keep `ui_decisions.json` pending unless a
review step records decisions.

The UI handoff follows the OpenAI-style local MCP/widget pattern:

1. Python writes bounded review-session JSON files in the output folder.
2. The local MCP server validates the review payload schema and item types.
3. The MCP render tool returns `openai/outputTemplate` metadata for
   `ui://widget/check-entries-review.html`.
4. The reusable HTML widget renders summary metrics, type filters, search,
   rows, evidence detail, and reviewer action controls.
5. The MCP save tool validates actions against each item and writes durable
   `ui_decisions.json` when `run_intake.output_dir` is available.
6. The MCP apply tool writes `applied_decisions.json` and updates
   `final_artifacts.json` status when `run_intake.output_dir` is available.
7. Codex uses the reviewed payload and any durable decisions when writing the
   final response or `codex_run_review.md`.

## Language Policy

Ask for or infer two language assumptions:

- `language`: working/output language for Codex's questions and final summary; one of `it`, `en`, `fr`, `de`, `es`.
- `document_language`: source-document language used to interpret labels; one of `auto`, `it`, `en`, `fr`, `de`, `es`.

Store both assumptions in the generated recipe and preserve them in diagnostics/audit JSON. If the user writes in English, default `language=en` and `document_language=auto`. If the source files are clearly Italian, French, German, or Spanish, set `document_language` accordingly without asking unless ambiguity matters.

Starter prompts:

```text
IT: Usa Check Entries su /percorso/normalized_journal.csv qualificato da Journal Sampling e sui PDF in /percorso/pdf. Lingua: it. Lingua documenti: auto.
EN: Use Check Entries on /path/normalized_journal.csv qualified by Journal Sampling and support PDFs in /path/pdfs. Language: en. Document language: auto.
FR: Utilise Check Entries sur /chemin/normalized_journal.csv qualifié par Journal Sampling et les PDF dans /chemin/pdfs. Langue: fr. Langue des documents: auto.
DE: Verwende Check Entries für die von Journal Sampling qualifizierte Datei /pfad/normalized_journal.csv und die Beleg-PDFs in /pfad/pdfs. Sprache: de. Dokumentsprache: auto.
```

## Failure Modes

- If support PDFs are scanned/OCR-only and no text is extracted, report that deterministic PDF text extraction is insufficient and list the affected files.
- If preparation or mapping evidence is missing, stop and return the source to
  Journal Sampling; do not run partial checks.
- If an explicit invoice-number relationship or a distinctive/labeled movement
  identifier is absent, amount/date coincidences remain unresolved evidence;
  they do not auto-match XML or PDF support.
- If a deterministic rule flags many false positives, write the gap as a plugin improvement suggestion rather than overriding the output silently.

## Plugin Improvement Feedback

At the end of every completed or blocked plugin run, after reporting the deliverables, briefly identify concrete improvements that would have made this plugin run better. Base suggestions on the actual session, such as a new support-document format, a brittle PDF text extractor, a missing deterministic extraction script, a missing column-mapping rule, an unclear assumption, a needed fixture, output gaps, installation friction, or repeated manual steps.

When there is something useful to report, write a short improvement note with:

- observed gap;
- proposed improvement;
- why it matters;
- relevant input/output file names when available;
- suggested next engineering action.

Keep the improvement note local to chat or run artifacts. Do not submit it to
Mparanza automatically. When this workflow runs through Vera, use Vera's
consent-based Plugin Improvement Feedback process for any transmission.
