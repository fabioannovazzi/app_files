---
name: deep-research-validator
description: Use when Vera or Codex must validate a generated or supplied legal, tax, or compliance answer—including a research report, memo, or one-page letter—against its answer contract and available sources. Separate source support, reasoning quality, and professional-judgment boundaries.
---

## Output Location Rule

Never write run outputs inside this Git workspace or a published folder. Use
only the Studio Archive run path described below.

## Client engagement gate

Select one Studio Archive client and engagement, import the answer and supplied
sources or use artifacts from the same engagement, then call
`prepare_studio_client_workflow` with workflow ID
`deep-research-validator`. Pass the returned `client_engagement_path` as
`--client-engagement` to document inspection, source inspection, and packaging.
Cross-engagement inputs and arbitrary outputs are rejected.

Start the prepared run before inspection. After the last output write, call
`finalize_studio_client_workflow` and declare every physical file with a stable
artifact ID, relative path, concrete purpose, audience, and media type. Review
the closed declaration, then call `complete_studio_client_workflow`; record
`failed` or explicitly cancel an abandoned run instead of treating a partial
directory as a result.

# Validate Answer

Use this skill when a completed answer or professional document must be
reviewed against its answer contract and available sources. The document may
come from ChatGPT Deep Research, direct Codex drafting, or an external source.
Length does not determine whether validation is warranted: a one-page legal
letter can contain material factual, legal, and inferential claims.

Codex owns the semantic work: selecting material claims, evaluating source
support, reviewing reasoning, identifying professional-judgment boundaries,
deciding whether fixes are needed, and drafting a corrected document.

The workflow is not Italian-only. Support the same five working locales used by the Mparanza plugins: `it`, `en`, `fr`, `de`, and `es`. Keep artifact file names and JSON keys in English for stability, but speak to the user in the chosen working language.

Detailed validation criteria live in `references/workflow-reference.md`. Load that reference when a run needs source-support categories, claim-review JSON details, or output wording guidance.

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

Codex performs semantic validation and rewrite judgment.

Deterministic Python code only inspects document structure, extracts citations
and URLs, fetches or parses sources, records exact quote presence, validates
the answer-contract and review-record shape, packages outputs, and optionally
exports DOCX. Exact or fuzzy text matching must never decide whether a claim is
semantically supported. Plugin scripts must not make direct OpenAI API calls or
other model API calls.

The user should not interact directly with CLI scripts. Treat scripts as internal tools Codex runs on behalf of the user.

## Inputs

Required:

- a generated or supplied answer/document as Markdown, text, HTML, or readable
  PDF;
- `answer_contract.json` from the planning stage, or a contract written by
  Codex from user-confirmed context when the document arrived externally.

Optional:

- working language: `it`, `en`, `fr`, `de`, or `es`;
- validation objective, such as source support only, reasoning review, or corrected-document generation;
- local source files when cited URLs are unavailable or gated.

## First Run Workflow

1. Ask only for essential missing context: working language and validation objective when they cannot be inferred. The default objective is the full package: source-support review, reasoning review, correction proposal, validation package, and DOCX export when tooling is available.
2. Save the document in the work folder as `answer.md`, `answer.txt`,
   `answer.html`, or `answer.pdf`. Preserve its `answer_contract.json`.
3. Run dependency checks from the plugin directory:

```bash
python scripts/check_dependencies.py
```

If requirements are missing, install from `requirements.txt` only when the environment allows it or explain what dependency capability is missing.

4. Inspect the document:

```bash
python scripts/inspect_document.py <managed-document-or-same-engagement-artifact> --client-engagement <client_engagement_path> --output-dir <client-run-output>
```

5. Inspect cited sources and optional local source files:

```bash
python scripts/inspect_sources.py <client-run-output>/document_inventory.json --client-engagement <client_engagement_path> --output-dir <client-run-output> [--source-file <managed-source-path> ...]
```

Use `--no-fetch` if the environment cannot fetch URLs; then rely on listed references and local files.

6. Read `document_inventory.json`, `source_inventory.json`, and
   `extracted_document.md`. Select the material claims to review semantically. Prefer claims
   that affect conclusions, recommendations, numbers, dates, eligibility,
   legal/tax/compliance positions, or risk statements. Read the full extracted
   document. `mechanical_claim_candidates` is only a navigation aid and must
   not gate claim coverage or decide which statements are claims.
   Record whether the review covers all material claims, selected material
   claims, or is limited. Also review whether the answer conforms to the
   contracted question, document type, audience, and evidence display.
7. Write `claims_review_draft.json` using schema version `2.0`. Each material
   claim must keep source identity, semantic support, reasoning, professional
   judgment, issue treatment, disposition, and reviewer action separate:

```json
{
  "schema_version": "2.0",
  "language": "en",
  "validation_objective": "question_to_validated_answer",
  "coverage_review": {
    "selection_method": "model_led_materiality_review",
    "scope": "all_material_claims",
    "reviewed_sections": ["Full answer"],
    "omitted_sections": [],
    "limitations": [],
    "analysis": "All sections were read and all material claims were selected.",
    "reviewer_action": "accept"
  },
  "contract_review": {
    "question_answered": {"status": "conforms", "analysis": "The answer addresses the contracted question."},
    "document_type": {"status": "conforms", "analysis": "The answer uses the contracted document type."},
    "audience": {"status": "conforms", "analysis": "The answer is suitable for the contracted audience."},
    "evidence_display": {"status": "conforms", "analysis": "The evidence display follows the contract."},
    "issues": [{"type": "none", "explanation": "No contract defect identified.", "treatment_action": "none", "treatment_status": "not_needed", "treatment_explanation": "No treatment required."}],
    "reviewer_action": "accept"
  },
  "claims": [
    {
      "claim_index": 1,
      "claim_text": "Material claim text.",
      "claim_location": "Section 2, paragraph 1",
      "materiality": "material",
      "source_checks": [{"source_ref": "source-001", "identity_status": "matches_cited_source", "identity_analysis": "Why this is the authority actually cited.", "cited_passage": "Exact passage when available."}],
      "support": {"status": "supported", "analysis": "Why the source semantically supports the claim."},
      "reasoning": {"status": "sound", "analysis": "Why the conclusion follows.", "supported_premises": ["Supported premise"], "missing_premises": []},
      "professional_judgment": {"status": "not_judgment_dependent", "analysis": "Why no additional professional choice is needed.", "factors": [], "alternative_interpretations": []},
      "issues": [{"type": "none", "explanation": "No defect identified.", "treatment_action": "none", "treatment_status": "not_needed", "treatment_explanation": "No treatment required."}],
      "disposition": {"status": "retain", "analysis": "Retain as written.", "revised_claim": ""},
      "reviewer_action": "accept",
      "proposed_fix": ""
    }
  ],
  "overall_assessment": {"outcome": "no_material_defect_identified", "analysis": "Short validation summary.", "residual_uncertainties": [], "professional_review_items": []},
  "document_revision": {"status": "not_required", "summary": "No answer revision is required.", "unresolved_changes": []},
  "validated_document": "Corrected Markdown document if requested."
}
```

Valid support statuses are `supported`, `partially_supported`, `not_supported`, `contradicted`, and `uncertain`.

Valid reasoning statuses are `sound`, `partially_sound`, `unsound`,
`uncertain`, and `not_applicable`.

Valid judgment statuses are `not_judgment_dependent`,
`professional_judgment_required`, `contested`, and `uncertain`.

Issue types are `none`, `source_unavailable`, `source_not_identified`,
`wrong_source`, `wrong_source_version`, `wrong_jurisdiction_or_period`,
`missing_source_support`, `partial_or_overbroad_support`,
`source_contradiction`, `qualification_or_scope_distortion`,
`temporal_or_modality_distortion`, `reasoning_gap`, `judgment_dependent`, and
`answer_contract_failure`. Each non-`none` issue requires an explicit treatment
action and status. Use `none` alone.

Keep the coded review state internally consistent. Any non-supported support
status, reasoning concern, source-identity concern, or judgment-dependent
status requires a non-`none` issue and treatment. A `supported`,
`partially_supported`, or `contradicted` assessment requires at least one
identified source check. A `not_supported` or `contradicted` claim, or a claim
with `unsound` reasoning, cannot be retained unchanged. Contract-conformance
attention requires an `answer_contract_failure` treatment, and that treatment
must not appear when every contract dimension conforms. Reviewer rejection,
proposed treatment, blocked treatment, and professional-review requirements
must remain unresolved in `delivery_readiness` until addressed.

8. Package and audit the review:

```bash
python scripts/package_validation.py <client-run-output>/document_inventory.json <client-run-output>/source_inventory.json <client-run-output>/claims_review_draft.json --client-engagement <client_engagement_path> --answer-contract-file <client-run-output>/answer_contract.json --output-dir <client-run-output>
```

Add `--docx` whenever DOCX tooling is available. Do not ask whether to export DOCX; it is a natural deliverable of the validation package.

9. Read `validation_audit.json`. `record_complete` means only that the required
   assessments, treatments, and mechanically provable cross-field
   relationships were recorded consistently. Use `delivery_readiness` to find
   whether answer revision, more evidence, reviewer rejection, or professional
   review remains. A completed revision must pair with the `corrected` overall
   outcome; unresolved attention cannot pair with
   `no_material_defect_identified`.
10. If a reviewer edits `proposed_fix`, do not mark the answer final. Regenerate
    the reviewed or corrected answer semantically, update the disposition and
    document-revision record, then rerun packaging.
11. Deliver `claims_review.json`, `validation_audit.json`, the reviewed or
    corrected document when one is actually available, and
    `validation_package.md`. Report assumptions, unavailable/gated sources,
    answer-contract defects, coverage limits, and professional-review items.

## Validation Requirements

The review must:

- separate source availability issues from substantive support issues;
- separate mechanical observations, semantic support, reasoning assessment,
  and professional judgment;
- distinguish supported, partially supported, unsupported, contradicted, and uncertain claims;
- preserve source URLs, citations, and quoted passages where available;
- flag unavailable, gated, too-short, or unparseable sources as evidence limits;
- review reasoning separately from source existence;
- never treat literal, fuzzy, or exact quote matching as semantic entailment;
- mark legal applicability, materiality, competing interpretations, strategy,
  and uncertain outcomes as judgment-dependent when appropriate;
- make residual uncertainty explicit.

## Expected Outputs

- `document_inventory.json`;
- `source_inventory.json`;
- `answer_contract.json`;
- `claims_review.json`;
- `validation_audit.json`;
- `validated_document.md` only when a reviewed or corrected answer has actually
  been produced;
- `validated_document.docx` when that answer exists and DOCX tooling is
  available;
- `validation_package.md`;
- `run_intake.json`;
- `review_payload.json`;
- `ui_decisions.json`;
- `applied_decisions.json` after reviewer decisions are applied;
- `final_artifacts.json`.

## MCP Review UI

When the local MCP server is available, prefer the OpenAI-style review handoff:

1. Read `run_intake.json`, `review_payload.json`, `ui_decisions.json`, and
   `final_artifacts.json` from the validation output folder. Pass the current
   absolute `client_engagement_path` as `client_engagement` with every MCP call
   that includes `run_intake`. If the customer folder moved, use the
   `context.json` path under its current location; never reuse a previously
   recorded absolute path.
2. Call `validate_deep_research_review` with `review_payload` before rendering.
3. If validation succeeds, call `render_deep_research_review` with the same
   payload objects so Codex can show the local HTML widget
   `ui://widget/deep-research-review.html`.
4. Use the widget to inspect answer-contract conformance, claim-selection
   coverage, source identity/access, semantic support, reasoning, issue
   treatments, professional-judgment limits, failed record checks, and generated
   validation artifacts.
5. When the reviewer records actions in the widget or Codex collects decisions
   through fallback review, call `save_deep_research_decisions` so
   `ui_decisions.json` is validated and persisted. When the reviewer is done,
   call `apply_deep_research_decisions` so `applied_decisions.json` and
   `final_artifacts.json` reflect accepted, edited, unclear, skipped, or
   document-requested items before treating the validation package as reviewed.

If MCP rendering is unavailable, fall back to a markdown review summary from
`review_payload.json`, `claims_review.json`, `validation_audit.json`,
`validated_document.md`, and `validation_package.md`. If validation audit fails,
repair `claims_review_draft.json` and rerun packaging rather than ignoring the
failed checks. Keep review decisions pending unless they are recorded in
`ui_decisions.json` and consumed into `applied_decisions.json`. Small setup
choices should stay in chat or, when this conversation is in Plan mode and the
tool is available, native Plan-mode choices.

## Language Policy

Ask for or infer the working/output language:

- `it`: Italian;
- `en`: English;
- `fr`: French;
- `de`: German;
- `es`: Spanish.

Starter prompts:

```text
IT: Valida questa risposta rispetto al contratto di risposta e alle fonti disponibili. Lingua: it. Seleziona semanticamente i claim materiali, valuta separatamente supporto delle fonti, ragionamento e limiti del giudizio professionale, correggi ciò che le evidenze consentono e prepara il pacchetto di validazione.
EN: Validate this answer against its answer contract and available sources. Language: en. Select material claims semantically, assess source support, reasoning, and professional-judgment boundaries separately, correct what the evidence permits, and prepare the validation package.
FR: Valide cette réponse par rapport à son contrat de réponse et aux sources disponibles. Langue: fr. Sélectionne sémantiquement les assertions importantes, évalue séparément le support des sources, le raisonnement et les limites du jugement professionnel, corrige ce que les éléments permettent et prépare le paquet de validation.
DE: Validiere diese Antwort anhand ihres Antwortvertrags und der verfügbaren Quellen. Sprache: de. Wähle wesentliche Aussagen semantisch aus, bewerte Quellenstützung, Begründung und professionelle Ermessensgrenzen getrennt, korrigiere belegbare Mängel und erstelle das Validierungspaket.
```

## Failure Modes

- If the source document is empty or unreadable, ask for a Markdown/text export before validating.
- If URLs are unreachable or gated, report the evidence limit and ask for local source files only when that materially affects validation.
- If the document contains no citations, perform a reasoning and citation-gap review rather than inventing sources.
- If the user supplies only the underlying question, return to Vera's
  question-to-validated-answer journey rather than asking the user to request
  prompt optimization.
- If deterministic audit flags missing review fields, repair the review JSON before delivery.

## Plugin Improvement Feedback

At the end of every completed or blocked plugin run, after reporting the deliverables, briefly identify concrete improvements that would have made this plugin run better. Base suggestions on the actual session, such as a missing source parser, weak claim-selection rule, brittle citation extraction, missing deterministic validation check, unclear assumption, needed fixture, output gap, installation friction, or repeated manual step.

When there is something useful to report, write a short improvement note with:

- observed gap;
- proposed improvement;
- why it matters;
- relevant input/output file names when available;
- suggested next engineering action.

Keep the improvement note local to chat or run artifacts. Do not submit it to
Mparanza automatically. When this workflow runs through Vera, use Vera's
consent-based Plugin Improvement Feedback process for any transmission.
