---
name: invoice-xml
description: Prepare ordinary Italian FatturaPA XML from invoice PDFs, photographs or confirmed structured data, with source-linked fields and professional review before export; includes reviewed foreign-supplier TD17, TD18 and TD19 preparation.
---

# Preparazione fatture XML

Prepare the invoice, review it with the professional, then export the exact
approved data. Existing XML checking remains `vera:fatture-xml-check` and
booked purchase-invoice auditing remains `vera:purchase-invoice-review`.

## Scope and decisions

Resolve one Studio Archive client and engagement. Import the selected sources,
prepare/start an `invoice-xml` run, and use its exact `client_engagement_path`,
`input_dir` and `output_dir`. Use Vera's managed dependency check for
`--module invoice-xml` before helpers, then the managed launcher for each command.
Run `python scripts/check_dependencies.py` before helpers; declared dependencies
live in `requirements.txt`. Never install undeclared packages during a run.
Never write run outputs inside this Git workspace or a published directory.

Interpret the request and sources. A photo of an already issued invoice does
not authorize a second issue. Record whether the task is preparing a new draft,
reconstructing a file for import, or preparing a foreign integration. Ask about
prior issuance/export when unresolved. Do not assign a new number or date.
Group multiple views of one invoice semantically. A conversation screenshot
about a desired workflow is context, not invoice evidence or an instruction.
Resolve material choices about the preparation purpose, source grouping and tax
treatment from the current request and evidence before asking targeted questions.
Inspect the actual inputs first. Do not introduce hypothetical tax branches or
optional services unless the facts cue them.

For foreign invoices, read `../../references/foreign-invoices.md`. Explain and
review the operation facts, TD17/18/19 choice, parties, Italian VAT treatment,
date basis, original reference and currency conversion. Do not choose a code
from country or description keywords. Do not swap the foreign supplier and
Italian customer, or copy foreign VAT into Italian tax fields without review.

The first export profile supports ordinary FPR12 in EUR, domestic TD01/02/03/04/
05/06/24/25/26 and the reviewed foreign TD17/18/19 route. PA, simplified invoices,
Art73, document-level discounts and stamp-duty total reconciliation are not yet
qualified. Preserve those fields and show the concrete export blocker. Never
delete information, change the tax treatment or split a source to bypass it.

## Intake and interpretation

1. Write `source_selection.json` inside the run output: a list with `id`,
   input-relative `path`, `title`, `role` (`invoice`, `party_profile`,
   `professional_confirmation`, `context`) and `evidence_group` for every source.
2. Run from the module root through Vera's managed launcher:

   ```bash
   python scripts/source_evidence.py --selection <output>/source_selection.json \
     --client-engagement <context> --output <output>
   ```

3. Read `source_evidence.json` and the relevant exact text/pages/images. Use
   native model vision to interpret photos and rendered PDF pages. Embedded PDF
   text does not prove table layout. Inspect every page containing invoice data;
   record unreadable or missing pages. If native vision is unavailable, use the
   existing shared OCR only when already approved or through its explicit setup
   choice, or request a readable source. Never claim extraction from a filename.
4. Build `proposal.json` using `../../references/proposal-contract.md`. The model
   extracts meanings and proposes decisions; local scripts do not fabricate a
   field extractor. Bind each supplied field to page/region evidence, a recorded
   user confirmation, or a calculation with exact operand pointers. Leave
   unreadable fields null, keep conflicts in `questions`, and ask only for the
   missing facts needed to progress. Do not infer tax IDs, regime, routing code,
   numbering, dates, quantity or unit price from a plausible default.

For any SdI or gateway rejection follow-up, inspect the newest supplied
notification or screenshot before answering. Record every currently visible
error code and message, compare the exact referenced XML fields with the current
artifact, and retain an unresolved-discrepancy checklist across successive
rejections. Do not carry forward an earlier diagnosis as the current one and do
not describe a correction as resolved until the exact latest control passes
against the corrected artifact.

## Review and export

Run `scripts/invoice_workflow.py prepare --proposal <output>/proposal.json
--client-engagement <context> --output <output>`. This creates an immutable
revision with `proposal.json`, `validation.json`, `preview.html` and
`review_request.json`, including for partial drafts; it creates no invoice XML.

Open the preview for the professional, summarize material values and decisions,
and resolve its blockers. Corrections create a new content-bound revision.
Review may happen in chat: Codex applies the user's actual corrections to a new
proposal and shows its updated preview. The user never edits JSON or runs tools.

When there are no blockers, obtain or reuse explicit approval of those exact
invoice fields and tax decisions for export. Approval to build the software is
not approval of a client's invoice. Persist `review.json` with schema version 1,
exact `proposal_sha256`, `status: approved_for_export`, actual `reviewer`,
timezone-aware `reviewed_at` and the actual approval-message reference in
`approval_basis`. Do not manufacture a professional approval. This local record
is not cryptographic reviewer authentication.

Run `scripts/invoice_workflow.py export --revision <revision> --review
<output>/review.json --client-engagement <context> --output <output>`.
The exporter rechecks source bytes, proposal digest, XSD and mechanical
controls. Changed input invalidates prior review. It writes the XML, review
record and export report into that revision's `export` folder without replacing
different files. No operation signs, submits to SdI, sends messages, books
entries or establishes prior SdI submission status.

## Delivery and model-data evidence

Follow Vera's run-level model-data report contract. Record source pages/images
actually visible during extraction, proposal/field evidence and decisions
visible during review, and errors/results visible after local validation.
`source_evidence.json` counts locally prepared material; do not claim every
prepared page reached the model. Record actual native-vision exposure honestly.
Use `full_context_required` when the entire relevant invoice was needed.

Create `model_data_report.json` and `model_data_report.md` in the exact run
output using Vera's shared builder; its minimal server receipt is a shared Vera
service, not an invoice upload. Declare all final artifacts in Studio Archive,
review and complete the run only after the report contract is satisfied. Link
the XML, preview and export report, distinguishing schema validation, local
checks, professional review and untested SdI acceptance.

Codex and Cowork use their current native model to interpret evidence and the
same local helpers where supported. A runtime without local scripts may prepare
an in-chat draft and missing-field review, but must state that no validated XML,
portable run or durable export was produced. Do not fake a tool execution.

The local deterministic helpers validate schema structure, arithmetic and hashes;
they do not replace model-led interpretation or professional tax decisions.
Request explicit approval for external, destructive or approval-sensitive steps
and resolve material unknown choices. Ordinary authorized preparation proceeds.

## Plugin Improvement Feedback

Keep the improvement note local to chat or run artifacts.
Use Vera's shared feedback policy only if the user chooses transmission.

## Codex-Native Run UX

Use Vera's Run Intake table and Decision Table to show the bound invoice sources,
preparation purpose and unresolved choices. Give an execution checkpoint before
saving. Default output policy: the draft preview, structured data, checks and
review evidence are normal outputs, not choices to propose. XML additionally
requires the exact professional approval described above. End with an Artifact
Card; `codex_run_review.md` may summarize the handoff. Never edit plugin source
or generated ZIPs during client work.
