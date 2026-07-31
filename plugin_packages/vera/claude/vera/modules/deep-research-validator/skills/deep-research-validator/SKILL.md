---
name: deep-research-validator
description: Use when Vera or Claude must validate a generated or supplied legal, tax, or compliance answer—including a research report, memo, or one-page letter—against its answer contract and available sources. Separate source support, reasoning quality, and professional-judgment boundaries.
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

Never write run outputs inside this Git workspace, `static/shared`, `protected_downloads`, or any GitHub Pages/static-site folder unless the task is explicitly plugin packaging/release. For user-data runs, choose an output directory outside the repo, preferably a sibling `output/<plugin-name-or-run-id>` folder next to the user-provided input folder, and pass that path to every `--output-dir` or `--out` argument. If a script has a safe default next to the input folder, use that default instead of inventing `out/...` under the repo.

# Validate Answer

Use this skill when a completed answer or professional document must be
reviewed against its answer contract and available sources. The document may
come from ChatGPT Deep Research, direct Claude drafting, or an external source.
Length does not determine whether validation is warranted: a one-page legal
letter can contain material factual, legal, and inferential claims.

Claude owns the semantic work: selecting material claims, evaluating source
support, reviewing reasoning, identifying professional-judgment boundaries,
deciding whether fixes are needed, and drafting a corrected document.

The workflow is not Italian-only. Support the same five working locales used by the Mparanza plugins: `it`, `en`, `fr`, `de`, and `es`. Keep artifact file names and JSON keys in English for stability, but speak to the user in the chosen working language.

Detailed validation criteria live in `references/workflow-reference.md`. Load that reference when a run needs source-support categories, claim-review JSON details, or output wording guidance.

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

Claude performs semantic validation and rewrite judgment.

Deterministic Python code only inspects document structure, extracts citations
and URLs, fetches or parses sources, records exact quote presence, validates
the answer-contract and review-record shape, packages outputs, and optionally
exports DOCX. Exact or fuzzy text matching must never decide whether a claim is
semantically supported. Plugin scripts must not make direct OpenAI API calls or
other model API calls.

The user should not interact directly with CLI scripts. Treat scripts as internal tools Claude runs on behalf of the user.

## Inputs

Required:

- a generated or supplied answer/document as Markdown, text, HTML, or readable
  PDF;
- `answer_contract.json` from the planning stage, or a contract written by
  Claude from user-confirmed context when the document arrived externally.

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
python scripts/inspect_document.py <document-file> --output-dir <output-dir>
```

5. Inspect cited sources and optional local source files:

```bash
python scripts/inspect_sources.py <output-dir>/document_inventory.json --output-dir <output-dir> [--source-file <path> ...]
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

8. Package and audit the review:

```bash
python scripts/package_validation.py <output-dir>/document_inventory.json <output-dir>/source_inventory.json <output-dir>/claims_review_draft.json --answer-contract-file <output-dir>/answer_contract.json --output-dir <output-dir>
```

Add `--docx` whenever DOCX tooling is available. Do not ask whether to export DOCX; it is a natural deliverable of the validation package.

9. Read `validation_audit.json`. `record_complete` means only that the required
   assessments and treatments were recorded. Use `delivery_readiness` to find
   whether answer revision, more evidence, or professional review remains.
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
