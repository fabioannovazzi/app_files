---
name: previdenza-inps
description: Use when a user wants Vera or Claude to prepare an evidence-backed Italian INPS social-security case review from connected documents or hash-bound official portal exports; validate facts and chronology, research the applicable framework with official sources, run only reviewer-approved contribution arithmetic, and package a draft for professional review.
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

# Previdenza INPS

Prepare a source-traceable social-security case file for a commercialista. Inventory local evidence, preserve document locators, validate model-authored facts, research the confirmed framework, verify material claims, run only explicitly approved arithmetic, and package a draft for professional review.

Do not claim autonomous INPS login or a general INPS API. Cowork uses documents already supplied in the connected folder and official portal exports registered from local storage. Do not open, attach to, or capture a live portal session; request an official readable export when material evidence is missing. Never request credentials, cookies, tokens, authentication codes, or delegation activation. Do not submit, sign, decide a legal or contribution classification, or infer labels such as “3°/4° gruppo” from keywords. Read `../../references/workflow-reference.md` and `../../references/inps-access-channels.md` completely before a case run. Here, the component root is the directory two levels above this skill file: `plugins/previdenza-inps`.

## Core boundary

Use deterministic Python only where correctness is mechanically verifiable: hashes, extraction, stable locators, quote presence, IDs, ISO dates, explicit timeline sorting, exact Decimal arithmetic, schema validation, and packaging. Claude may draft source-backed interpretations and alternatives; the professional reviewer owns the legal or contribution classification and the final conclusion.

The scripts must not contain contribution rates, regime mappings, thresholds, ceilings, limitation periods, deadlines, or legal-research source selectors. Exact source-origin checks used by the official-export registrar are required for provenance and do not select legal authority. If a deterministic result conflicts with semantic review, preserve the mechanical result as evidence and let Claude/reviewer judgment control the interpretation.

## Cowork-native Run UX

1. Start with a visible checklist covering intake, dependency check, inventory, material decisions, facts, research, claim validation, calculations, packaging, and professional review.
2. Show a Run Intake table with input folder, output folder, working language, period, cut-off date, Claude-context boundary, external acquisition posture, and assumptions.
3. Show a compact Decision Table for unresolved framework, period, ambiguous terms, evidence conflicts, OCR limits, or calculation recipes.
4. Before long or write-heavy work, show an execution checkpoint with command intent, inputs, output folder, and expected artifacts. Reserve explicit approval for a destructive, externally mutating, approval-sensitive, or materially unresolved step.
5. End with an Artifact Card listing each output, status, unresolved issues, and next professional action.

Default output policy: produce the normal package needed for review, without unnecessary copies of sensitive evidence. JSON, CSV, Markdown, DOCX, audit, and review artifacts are not choices to propose when tooling permits them. Ask only about material choices that change the framework, evidence, method, authority, destination, or write scope.

Generate choices from the actual inputs; do not offer named frameworks, regulators, document types, or issue categories unless the facts cue them. Ask only those unresolved choices in chat and wait when they materially change the work.

When useful, create `run_review.md` beside the package. Never edit plugin source or generated ZIPs during a case run.

## Required intake

Real case material may enter the Claude model context when it is useful for the professional analysis. Do not demand a per-case declaration that model processing was approved or that personal data was minimized; Vera cannot verify either assertion. For portal evidence, ask the user to supply an official readable export that they already downloaded. Never request credentials, cookies, tokens, authentication codes, or a live authenticated session.

Ask at most five material questions when the answers are not already in the evidence:

1. What exact professional question and decision will the output support?
2. Which document defines any ambiguous group or category label, and for which period?
3. Which subjects and relationships are in scope?
4. What period and legal/research cut-off date apply?
5. Are there deadlines, notices, disputes, or proceedings already underway?

Confirm the Italian/INPS framework separately from output language. Surface any apparent urgent deadline immediately and do not bury it behind the ordinary ambiguity-resolution loop. While a material framework, period, or label remains unresolved, exploratory research may identify candidate meanings or the documents needed to resolve them, but it must be marked non-conclusive and must not assign a regime, select a formula, or support a final claim.

## Workflow

### 0. Portal-derived evidence

Prefer an official PDF or other portal download made by the subject or appropriately profiled intermediary/delegate. No verified general-purpose API currently lets a commercialista retrieve a client's individual contribution position. Never route a private case through the public Open Data API or a PDND e-service merely because the words “INPS” or “Estratto Conto” match; verify the exact service contract and actor eligibility first.

Select the client and engagement first. Import each downloaded export as its
own Studio Archive input, prepare the exact receipt set, and start the run.
Register only the resulting run execution copies. The registrar copies and
hash-binds them under the same run's output tree; it does not operate the portal
or ask the professional to re-document access, profile, delegation, or
model-processing authority for a local file. The command shape is:

```bash
python scripts/register_portal_export.py register <run-execution-input>/export.pdf \
  --output-dir <client-run-output>/acquisition/inps-export-registration \
  --source-origin https://www.inps.it \
  --client-engagement <client_engagement_path>
python scripts/register_portal_export.py verify \
  <client-run-output>/acquisition/inps-export-registration
python scripts/inventory_case.py <client-run-output>/acquisition/inps-export-registration \
  --portal-export-manifest <client-run-output>/acquisition/inps-export-registration/manifest.json \
  --client-engagement <client_engagement_path> \
  --output-dir <client-run-output> \
  --language it \
  --reference-date YYYY-MM-DD
```

`--source-origin` records the declared official origin and enforces an exact INPS HTTPS host shape; the local registrar cannot prove where a file was downloaded. Registration performs no network request or portal action and rejects browser profiles, cookies, storage exports, HTML, HAR, symlinks, unsafe formats, or altered artifacts.

### 1. Dependencies and inventory

From the component root (`plugins/previdenza-inps`), run:

```bash
python scripts/check_dependencies.py
python scripts/check_dependencies.py --requirements requirements-ocr.txt
python scripts/inventory_case.py <run-execution-input-folder> \
  --client-engagement <client_engagement_path> \
  --output-dir <client-run-output> \
  --language it \
  --reference-date YYYY-MM-DD
```

The second dependency check covers Vera's existing local PaddleOCR capability and is needed for scanned PDFs or images. Do not install missing requirements at runtime. Report which declared requirement is missing and let the user decide how to update the environment. OCR is attempted only for PDF pages with absent or mechanically insufficient embedded text and for supported images; use `--no-ocr` only when the user wants it disabled.


Model packages and model weights are different. By default the OCR adapter uses only explicit local model directories or already cached weights and makes no download. If weights are absent, report `ocr_models_unavailable`; do not download them silently. If the user explicitly chooses the optional download route, add `--allow-ocr-model-download`. The run intake records whether that route was selected and whether network access actually occurred; an arbitrary approval ID is not evidence of authority. The route downloads pinned model weights, never case documents; recognition remains local.

Read `file_inventory.json`, `extraction_report.json`, and `extracted_evidence.md`. Filename cues are not legal classifications. Each successful OCR fragment records `extraction_method: paddle_ocr`, its original page locator, engine metadata, and `ocr_text_requires_visual_confirmation`; the extraction report therefore remains `partial_evidence`. If OCR cannot replace a sparse embedded layer, the retained fragment carries `embedded_text_below_ocr_quality_threshold` and has the same visual-check requirement. A fact citing either kind of fragment cannot be marked `confirmed` until its evidence anchor records a visual check by an authorized user or professional reviewer. Multi-frame TIFF scans produce one `page-N` locator per frame. If OCR is unavailable or finds no text, request a readable export when material. Preserve original email files and use their headers, thread context, and attachment inventory when a communication is material.

### 2. Structure and validate facts

Claude writes `case_records_draft.json` using `schemas/case_records.schema.json`. Every material fact needs a document locator and quote. Preserve pending, disputed, and conflicting facts. Record a stable actor reference for who made each material decision, their role, when it was recorded, and the document or instruction forming its basis; the model itself is never the approving authority.

Keep these evidentiary propositions separate: an F24 was prepared, an amount was debited, INPS allocated a payment, and an extract credits a contribution period. For a negative or absence claim, document the completeness and scope of the records reviewed; one silent page is not proof of absence.

After the material decisions are confirmed, run:

```bash
python scripts/validate_case_records.py \
  <client-run-output>/case_records_draft.json \
  <client-run-output>/file_inventory.json \
  --client-engagement <client_engagement_path> \
  --output-dir <client-run-output>
```

Repair schema or provenance failures. Do not waive missing anchors by inference. The output includes `case_records_validated.json`, `case_records_audit.json`, `timeline.csv`, and `evidence_matrix.csv`.

### 3. Research and validate claims

Use model-led reasoning to frame the actual issue and curate current official sources for the confirmed period. When available, route broad or disputed research through the sibling `prompt-optimizer` module, then validate the completed output with `deep-research-validator`.

Write or adapt the validated result as `claims_review.json` using `schemas/claims_review.schema.json`. Type each claim as `rule`, `case_application`, or `calculation_basis`. Every material claim needs a structured temporal scope, a research cut-off date, a support verdict, and separate reasoning review; case-application and calculation-basis claims also require one or more validated fact IDs. A pure rule claim may have no case-fact dependency but cannot itself classify the subject. Every cited source separately records its reference, temporal role, retrieval time, version note, support note, and optional immutable snapshot hash. Distinguish rules applicable during the contribution period from law known at the research cut-off and any later interpretive authority. Represent an unknown or open boundary as `unresolved` or `open_ended`; it cannot support a `supported` verdict until confirmed. Do not fabricate or silently substitute unavailable authorities. If sibling validation is unavailable, describe the fallback as a model self-check, not independent validation.

### 4. Optional approved arithmetic

Only after the rate/formula basis is fully supported and a professional reviewer confirms the recipe, create `arithmetic_recipes.json` using `schemas/arithmetic_recipes.schema.json`. Record the approving actor ID, professional role, timestamp, and specific basis, then run:

```bash
python scripts/reconcile_contributions.py \
  <client-run-output>/arithmetic_recipes.json \
  <client-run-output>/case_records_validated.json \
  <client-run-output>/claims_review.json \
  --client-engagement <client_engagement_path> \
  --output-dir <client-run-output>
```

If a formula, rate, operand, provenance, or rounding choice is missing, leave status `calculation_not_run`. Never guess.

The reconciler binds results to the exact recipe, validated case records, and claims file with hashes in `calculation_audit.json`. Packaging must reject missing, stale, edited, or handwritten calculation results.

### 5. Package the review draft

Run:

```bash
python scripts/package_case.py \
  <client-run-output>/case_records_validated.json \
  <client-run-output>/claims_review.json \
  --client-engagement <client_engagement_path> \
  --calculations <client-run-output>/calculation_results.json \
  --output-dir <client-run-output>
```

Omit `--calculations` when no reviewed calculation is needed. A validation failure remains visible even when draft artifacts are written.

## Expected outputs

- `file_inventory.json` and `file_inventory.csv`;
- `extraction_report.json` and `extracted_evidence.md`;
- `case_records_validated.json` and `case_records_audit.json`;
- `timeline.csv` and `evidence_matrix.csv`;
- optional `calculation_results.json`, `calculation_results.csv`, and `calculation_audit.json`;
- `claims_review_normalized.json` and `validation_audit.json`;
- `studio_memo.md`, `studio_memo.docx`, and `document_requests.md`;
- `run_intake.json`, `review_payload.json`, `ui_decisions.json`, `applied_decisions.json` after review, and `final_artifacts.json`.
- `review_handoff.md` with the visible validate/render/save/apply sequence.

For a blocked run, the minimum deliverables are `run_intake.json`, `file_inventory.json`, `extraction_report.json`, `extracted_evidence.md`, `document_requests.md`, and an Artifact Card naming the blocker and the exact next professional decision. Do not create a conclusive memo or calculation merely to fill the normal package.

The strongest machine status is `ready_for_professional_review`. The memo must remain visibly marked `BOZZA PER REVISIONE PROFESSIONALE`.

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

## Failure rules

- No readable material evidence: `blocked_input`.
- Unresolved framework, period, or ambiguous label: `blocked_decision`.
- Scans, protected files, or missing pages: `partial_evidence`.
- OCR-derived text without a recorded human page check: `partial_evidence` and never a confirmed calculation input.
- A missing, unreadable, or unverifiable official portal export: request a new official export and keep the run `partial_evidence` or blocked as appropriate.
- Invalid record or missing provenance: `schema_error`.
- Missing or changed inventory intake, acquisition posture, portal receipt, or stored review binding: stop and regenerate validation from the verified acquisition; never recreate a local-only posture.
- Missing approved arithmetic input: `calculation_not_run`.
- Unsupported material claim or malformed package: `validation_fail`.

Never replace missing required evidence with model inference. Never write credentials, SPID/CIE secrets, cookies, tokens, private or tokenized session URLs, or raw local paths into artifacts or review payloads. Persist only run-root-relative file references so a renamed customer folder can be resumed from its current `context.json`. Use the access-restricted Studio Archive run output, avoid duplicate evidence copies, and keep external research queries free of personal identifiers. The firm or user chooses the Claude account and its data controls outside the per-case workflow.
