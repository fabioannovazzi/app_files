---
name: previdenza-inps
description: Use when a user wants Vera or Codex to prepare an evidence-backed Italian INPS social-security case review from local documents, hash-bound official portal exports, or a conditionally permitted read-only capture of one already-authenticated INPS tab; validate facts and chronology, research the applicable framework with official sources, run only reviewer-approved contribution arithmetic, and package a draft for professional review. Especially relevant to insurance agents or subagents, contribution positions, disputed classifications, missing periods, payments, notices, or labels such as 3rd/4th group.
---

## Output Location Rule

Never write run outputs inside this Git workspace, `static/shared`, `protected_downloads`, or any GitHub Pages/static-site folder unless the task is explicitly plugin packaging/release. For user-data runs, choose an output directory outside the repo, preferably a sibling `output/previdenza-inps-<run-id>` folder next to the user-provided input folder, and pass that path to every `--output-dir` argument.

# Previdenza INPS

Prepare a source-traceable social-security case file for a commercialista. Inventory local evidence, preserve document locators, validate model-authored facts, research the confirmed framework, verify material claims, run only explicitly approved arithmetic, and package a draft for professional review.

Do not claim autonomous INPS login or a general INPS API. The default bridge registers official exports. The conditional browser bridge is limited to a local read-only snapshot of one tab that an authorized human has already authenticated and selected, and it stays blocked unless permission for software-assisted capture under the particular service terms or another applicable basis has been verified separately. User or studio approval alone is insufficient. Do not submit, navigate the portal on the user's behalf, activate a delegation, inspect browser credentials/state, sign, or decide a legal or contribution classification. Do not infer the meaning of labels such as “3°/4° gruppo” from keywords. Read `../../references/workflow-reference.md` and `../../references/inps-access-channels.md` completely before an actual portal-assisted run. Here, the component root is the directory two levels above this skill file: `plugins/previdenza-inps`.

## Core boundary

Use deterministic Python only where correctness is mechanically verifiable: hashes, extraction, stable locators, quote presence, IDs, ISO dates, explicit timeline sorting, exact Decimal arithmetic, schema validation, and packaging. Codex may draft source-backed interpretations and alternatives; the professional reviewer owns the legal or contribution classification and the final conclusion.

The scripts must not contain contribution rates, regime mappings, thresholds, ceilings, limitation periods, deadlines, or legal-research source selectors. Exact transport-origin allowlists used only to enforce the portal connector's security boundary are required and do not select legal authority. If a deterministic result conflicts with semantic review, preserve the mechanical result as evidence and let Codex/reviewer judgment control the interpretation.

## Codex-Native Run UX

1. Start with a visible checklist covering intake, dependency check, inventory, material decisions, facts, research, claim validation, calculations, packaging, and professional review.
2. Show a Run Intake table with input folder, output folder, working language, period, cut-off date, Codex-context boundary, external acquisition posture, and assumptions.
3. Show a compact Decision Table for unresolved framework, period, ambiguous terms, evidence conflicts, OCR limits, or calculation recipes.
4. Before long or write-heavy work, show an execution checkpoint with command intent, inputs, output folder, and expected artifacts. Ask for approval only for external, destructive, approval-sensitive, or materially unresolved actions.
5. End with an Artifact Card listing each output, status, unresolved issues, and next professional action.

Default output policy: produce the normal package needed for review, without unnecessary copies of sensitive evidence. JSON, CSV, Markdown, DOCX, audit, and review artifacts are not choices to propose when tooling permits them. Ask only about material choices that change the framework, evidence, method, authority, destination, or write scope.

Generate choices from the actual inputs; do not offer named frameworks, regulators, document types, or issue categories unless the facts cue them. Ask only those unresolved choices in chat and wait when they materially change the work.

When useful, create `codex_run_review.md` beside the package. Never edit plugin source or generated ZIPs during a case run.

## Required intake

Real case material may enter the Codex model context when it is useful for the professional analysis. Do not demand a per-case declaration that model processing was approved or that personal data was minimized; Vera cannot verify either assertion. Before portal capture, separately verify the human actor's access/profile/delegation authority and own-credential use, plus the particular service's permission for software-assisted capture. Also record the exact approved origin, scope, purpose, approval time, and confirmation that the visible page contains no credentials or one-time codes.

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

Register files already present in local storage before inventory. Keep both the source and registered directory outside the Git workspace. The registrar copies and hash-binds the files; it does not operate the portal or ask the professional to re-document access, profile, delegation, or model-processing authority for a local file. The command shape is:

```bash
python scripts/register_portal_export.py register /path/to/downloaded/export.pdf \
  --output-dir /private/path/inps-export-registration \
  --source-origin https://www.inps.it
python scripts/register_portal_export.py verify \
  /private/path/inps-export-registration
python scripts/inventory_case.py /private/path/inps-export-registration \
  --portal-export-manifest /private/path/inps-export-registration/manifest.json \
  --output-dir /private/path/previdenza-inps-run \
  --language it \
  --reference-date YYYY-MM-DD
```

`--source-origin` records the declared official origin and enforces an exact INPS HTTPS host shape; the local registrar cannot prove where a file was downloaded. Registration performs no network request or portal action and rejects browser profiles, cookies, storage exports, HTML, HAR, symlinks, unsafe formats, or altered artifacts.

For an alternative current-view snapshot, first verify and record permission for software-assisted capture under the particular service terms or another applicable basis. One inventory run accepts one portal-derived acquisition mode; do not mix a capture receipt and an export-registration receipt. If capture permission is unresolved, do not attach to the browser; use an official export/import path. When permission is confirmed, the human must open a dedicated browser session, authenticate personally with their own SPID/CIE/CNS, confirm the relevant profile/delegation, navigate to the exact read-only view, and remove any credential or one-time-code display. Vera may then attach only to a loopback browser endpoint and capture that already-open tab. The capture implementation is forbidden from navigating, clicking, filling, submitting, downloading, reading cookies/storage, saving HTML, exporting browser state, or closing the user's browser. Do not ask the user to disclose credentials, cookies, tokens, or authentication codes.

Run `python scripts/capture_portal_snapshot.py --help` from the component root and use its `capture` command only after every authority and permission field is explicit. Run its `verify` command before inventory. Point `inventory_case.py` at the private capture directory and pass its verified manifest with `--portal-capture-manifest`. The manifest and all artifacts must remain outside the Git workspace in an owner-only folder.

### 1. Dependencies and inventory

From the component root (`plugins/previdenza-inps`), run:

```bash
python scripts/check_dependencies.py
python scripts/check_dependencies.py --requirements requirements-ocr.txt
python scripts/inventory_case.py /path/to/case \
  --output-dir /path/to/output/previdenza-inps-run \
  --language it \
  --reference-date YYYY-MM-DD
```

The second dependency check covers Vera's existing local PaddleOCR capability and is needed for scanned PDFs or images. Do not install missing requirements at runtime. Report which declared requirement is missing and let the user decide how to update the environment. OCR is attempted only for PDF pages with absent or mechanically insufficient embedded text and for supported images; use `--no-ocr` only when the user wants it disabled.

For a portal-assisted run, verify the capture receipt and add `--portal-capture-manifest /path/to/capture/portal_capture_manifest.json` to the inventory command. This records `inps_browser_read_only` in the data posture and preserves the external approval without exposing its actor or purpose in the MCP widget.

Model packages and model weights are different. By default the OCR adapter uses only explicit local model directories or already cached weights and makes no download. If weights are absent, report `ocr_models_unavailable`; do not download them silently. Only after explicit approval may Codex add both `--allow-ocr-model-download` and `--ocr-model-download-approval-id <stable-id>`. This downloads model weights, never case documents; recognition remains local.

Read `file_inventory.json`, `extraction_report.json`, and `extracted_evidence.md`. Filename cues are not legal classifications. Each successful OCR fragment records `extraction_method: paddle_ocr`, its original page locator, engine metadata, and `ocr_text_requires_visual_confirmation`; the extraction report therefore remains `partial_evidence`. If OCR cannot replace a sparse embedded layer, the retained fragment carries `embedded_text_below_ocr_quality_threshold` and has the same visual-check requirement. A fact citing either kind of fragment cannot be marked `confirmed` until its evidence anchor records a visual check by an authorized user or professional reviewer. Multi-frame TIFF scans produce one `page-N` locator per frame. If OCR is unavailable or finds no text, request a readable export when material. Preserve original email files and use their headers, thread context, and attachment inventory when a communication is material.

### 2. Structure and validate facts

Codex writes `case_records_draft.json` using `schemas/case_records.schema.json`. Every material fact needs a document locator and quote. Preserve pending, disputed, and conflicting facts. Record a stable actor reference for who made each material decision, their role, when it was recorded, and the document or instruction forming its basis; the model itself is never the approving authority.

Keep these evidentiary propositions separate: an F24 was prepared, an amount was debited, INPS allocated a payment, and an extract credits a contribution period. For a negative or absence claim, document the completeness and scope of the records reviewed; one silent page is not proof of absence.

After the material decisions are confirmed, run:

```bash
python scripts/validate_case_records.py \
  /path/to/output/case_records_draft.json \
  /path/to/output/file_inventory.json \
  --output-dir /path/to/output
```

Repair schema or provenance failures. Do not waive missing anchors by inference. The output includes `case_records_validated.json`, `case_records_audit.json`, `timeline.csv`, and `evidence_matrix.csv`.

### 3. Research and validate claims

Use model-led reasoning to frame the actual issue and curate current official sources for the confirmed period. When available, route broad or disputed research through the sibling `prompt-optimizer` module, then validate the completed output with `deep-research-validator`.

Write or adapt the validated result as `claims_review.json` using `schemas/claims_review.schema.json`. Type each claim as `rule`, `case_application`, or `calculation_basis`. Every material claim needs a structured temporal scope, a research cut-off date, a support verdict, and separate reasoning review; case-application and calculation-basis claims also require one or more validated fact IDs. A pure rule claim may have no case-fact dependency but cannot itself classify the subject. Every cited source separately records its reference, temporal role, retrieval time, version note, support note, and optional immutable snapshot hash. Distinguish rules applicable during the contribution period from law known at the research cut-off and any later interpretive authority. Represent an unknown or open boundary as `unresolved` or `open_ended`; it cannot support a `supported` verdict until confirmed. Do not fabricate or silently substitute unavailable authorities. If sibling validation is unavailable, describe the fallback as a model self-check, not independent validation.

### 4. Optional approved arithmetic

Only after the rate/formula basis is fully supported and a professional reviewer confirms the recipe, create `arithmetic_recipes.json` using `schemas/arithmetic_recipes.schema.json`. Record the approving actor ID, professional role, timestamp, and specific basis, then run:

```bash
python scripts/reconcile_contributions.py \
  /path/to/output/arithmetic_recipes.json \
  /path/to/output/case_records_validated.json \
  /path/to/output/claims_review.json \
  --output-dir /path/to/output
```

If a formula, rate, operand, provenance, or rounding choice is missing, leave status `calculation_not_run`. Never guess.

The reconciler binds results to the exact recipe, validated case records, and claims file with hashes in `calculation_audit.json`. Packaging must reject missing, stale, edited, or handwritten calculation results.

### 5. Package the review draft

Run:

```bash
python scripts/package_case.py \
  /path/to/output/case_records_validated.json \
  /path/to/output/claims_review.json \
  --calculations /path/to/output/calculation_results.json \
  --output-dir /path/to/output
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

## MCP review handoff

When the local review server is available:

1. Validate `review_payload.json` with `validate_previdenza_inps_review`.
2. Render it with `render_previdenza_inps_review` at `ui://widget/previdenza-inps-review.html`.
3. Persist reviewer actions with `save_previdenza_inps_decisions`.
4. Apply them with `apply_previdenza_inps_decisions` so `applied_decisions.json` and `final_artifacts.json` reflect the review.

For persisted runs, a review marked ready requires a regular, identity-matching `final_artifacts.json` that is itself ready and binds the exact stored review. Every render, save, and apply call must also revalidate the acquisition binding against the current acquisition posture, exact `file_inventory.json` bytes, and canonical portal receipts. Any mismatch stops before review artifacts are written; do not replace or recompute the expected binding merely to clear the error.

If MCP rendering is unavailable, review the local artifacts in Markdown. Keep decisions pending until they are recorded and applied.

## Failure rules

- No readable material evidence: `blocked_input`.
- Unresolved framework, period, or ambiguous label: `blocked_decision`.
- Scans, protected files, or missing pages: `partial_evidence`.
- OCR-derived text without a recorded human page check: `partial_evidence` and never a confirmed calculation input.
- Browser-visible text without a recorded human comparison to the captured page image: `partial_evidence` and never a confirmed calculation input.
- Unverified portal-service permission for software-assisted capture, missing access/profile/delegation authority, non-loopback browser endpoint, origin mismatch, multiple matching tabs, or changed/tampered capture artifacts: stop the capture; use an official export/import path and do not fall back to broader browser access.
- Invalid record or missing provenance: `schema_error`.
- Missing or changed inventory intake, acquisition posture, portal receipt, or stored review binding: stop and regenerate validation from the verified acquisition; never recreate a local-only posture.
- Missing approved arithmetic input: `calculation_not_run`.
- Unsupported material claim or malformed package: `validation_fail`.

Never replace missing required evidence with model inference. Never write credentials, SPID/CIE secrets, cookies, tokens, private or tokenized session URLs, or raw local paths into artifacts or review payloads. Use a dedicated access-restricted output directory, avoid duplicate evidence copies, and keep external research queries free of personal identifiers. The firm or user chooses the Codex account and its data controls outside the per-case workflow.

## Plugin Improvement Feedback

At the end of every completed or blocked plugin run, after reporting the deliverables, briefly identify concrete improvements that would have made this plugin run better. Base suggestions on the actual session, such as a missing file parser, OCR limitation, weak evidence locator, schema gap, ambiguous review gate, calculation recipe friction, unavailable official source, or repeated manual step.

Keep the improvement note local to chat or run artifacts. Do not transmit it automatically.
