# Registro Imprese and SARI workflow reference

## Output contract

One run uses an owner-only directory outside the plugin Git workspace. The
normal package contains:

- `run_intake.json`
- `case_intake_draft.json` and `case_intake_validated.json`
- `local_evidence_inventory.json` when local exports/screenshots are present
- `official_sources.json`
- `practice_plan_draft.json` and `practice_plan_validated.json`
- `practice_validation_audit.json`
- `dire_practice_plan.json`
- `studio_checklist.md`
- `sari_question_draft.md`
- `review_payload.json`
- `ui_decisions.json`
- `applied_decisions.json` after review application
- `review_handoff.md`
- `final_artifacts.json`

No status may mean "ready to file". The strongest package status is
`ready_for_professional_review`; `ready_to_file` is always false.

## Semantic decision boundary

Codex and the professional, not Python rules, interpret the case and sources.
The plan author may propose:

- the competent chamber and territorial basis;
- legal form and activity description;
- ATECO classification;
- whether the intended operation affects RI, REA, Agenzia Entrate, INPS, INAIL,
  SUAP, IVASS/RUI, or another recipient;
- the DIRE category, practice type, panels, fields, dates, attachments, fees,
  signatory, and filing timing;
- whether a selected SARI card is applicable.

Each proposal must cite official-source IDs, identify its case-fact
dependencies, and carry `proposed`, `confirmed`, `not_applicable`, or `blocked`.
A `confirmed` item requires a human `professional_reviewer` confirmation object.

Python is appropriate for schema/type/date checks, exact identifier matching,
source allowlists, hash binding, file permissions, review completeness, and
packaging. These checks are mechanically verifiable and support auditability;
they do not replace professional judgment.

## Case facts

Private case JSON may contain names, fiscal identifiers, contact details,
addresses, case summaries, proposed values, and document passages when they are
useful to prepare or review the practice. Keep credentials, cookies, tokens,
signatures, and session material out of every artifact. The standard case-fact
IDs are:

- `CASE-CLIENT`
- `CASE-CHAMBER`
- `CASE-SUBJECT`
- `CASE-ACTIVITY`
- `CASE-OPERATION`
- `CASE-EFFECTIVE-DATE`
- `CASE-PROFESSIONAL-QUESTION`

The stable `client_reference` binds artifacts; it is not an anonymization
claim. The plan author selects the case facts needed for professional review.
Only an actual public SARI/search query must remain generic and exclude direct
client identifiers.

## OCR posture

`inventory_case.py` loads the shared `vera_ocr` adapter when it is available.
It does not duplicate the PaddleOCR engine. Model weights may use the network
only when the user explicitly selects `--allow-ocr-model-download`; the run
records the selected route and actual network use without manufacturing an
approval ID. Case-image
bytes remain local. Every OCR-derived fact carries
`ocr_text_requires_visual_confirmation`; a professional must check the source
image before confirmation.

## Review actions

- `accept`: accepts the review item only.
- `reject`, `mark_unclear`, `request_more_documents`: remain blockers.
- `edit`: stores a revision requirement; it never silently rewrites the plan.
- `skip`: does not approve the item.

The apply tool verifies the stored review payload and validation audit hashes
before writing. It updates only review manifests in the run directory and never
performs external or portal actions.
