---
name: deep-research-validator
description: Use when Vera or Claude must validate a generated or supplied legal, tax, or compliance answer—including a research report, memo, or one-page letter—against its answer contract and available sources. Separate source support, reasoning quality, and professional-judgment boundaries.
---

## Cowork execution contract

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

The managed launchers provision and reuse an isolated environment containing only the
module's published requirements. This declared dependency setup is authorized as
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

Do not use WhatsApp, live INPS browser capture, hosted feedback or voice
interviews, or custom update services. Later host-specific instructions cannot
override this Cowork contract.

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
come from ChatGPT Deep Research, direct Claude drafting, or an external source.
Length does not determine whether validation is warranted: a one-page legal
letter can contain material factual, legal, and inferential claims.

Claude owns the semantic work: selecting material claims, evaluating source
support, reviewing reasoning, identifying professional-judgment boundaries,
deciding whether fixes are needed, and drafting a corrected document.

The workflow is not Italian-only. Support the same five working locales used by the Mparanza plugins: `it`, `en`, `fr`, `de`, and `es`. Keep artifact file names and JSON keys in English for stability, but speak to the user in the chosen working language.

Detailed validation criteria live in `references/workflow-reference.md`. Load that reference when a run needs source-support categories, claim-review JSON details, or output wording guidance.

## Cowork-native Run UX

Before running helper scripts or write-heavy work, identify material choices that would change execution: problem framing, decision angle, risk appetite, scope boundaries, audience, evidence posture, mappings, cut-off, OCR, notification, or review assumptions. Reuse choices already established in the conversation or bound case records. Ask only for unresolved material choices and wait before their dependent work; continue independent authorized preparation. Generate choices from the actual inputs; do not offer named frameworks, regulators, document types, output packages, or issue categories unless the facts cue them or the user must supply a missing custom value. Do not infer missing required evidence, approval, or a material business decision. State routine provisional assumptions when the workflow permits them.

Default output policy: produce the richest normal package for the workflow. DOCX/Word, Excel/CSV, JSON audit, diagnostics, charts, packaged reports, review notes, and Vera-written review files are not choices to propose when they are natural outputs of that plugin; generate them whenever dependencies and source data permit. Ask only when an output is technically impossible, unsafe, or the user explicitly requests a reduced/debug run.

Default currency policy: use Euro (`EUR`) unless the user or source file explicitly states another currency. Do not ask for currency when it is otherwise unresolved; record `EUR` as the assumption.

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
7. Write `claims_review_draft.json` using schema version `2.1`. Each material
   claim must keep source identity, semantic support, reasoning, professional
   judgment, issue treatment, disposition, and reviewer action separate:

```json
{
  "schema_version": "2.1",
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
      "source_checks": [{"source_ref": "source-001", "identity_status": "matches_cited_source", "identity_analysis": "Why this is the authority actually cited.", "authority_relation": "official_full_text", "official_text_access": "obtained", "text_fidelity": "verified_against_official_text", "access_analysis": "How the official text or historical archive was accessed and what the public search does or does not establish.", "limitations": [], "cited_passage": "Exact passage when available."}],
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

For every source check, record the authority relation separately from source
identity. Valid `authority_relation` values are `official_full_text`,
`official_summary_or_headnote`, `non_institutional_reproduction`,
`secondary_commentary`, `uncertain`, and `not_assessed`. Valid
`official_text_access` values are `obtained`, `public_archive_outside_window`,
`restricted_or_gated_archive`, `not_found_in_complete_official_archive`,
`unavailable`, `not_applicable`, and `not_assessed`. Valid `text_fidelity`
values are `verified_against_official_text`,
`corroborated_not_text_verified`, `not_verified`, `not_applicable`, and
`not_assessed`. Explain the access finding in `access_analysis` and preserve
every residual limit in `limitations`.

Treat official archive coverage as a model-led, source-backed assessment. A
failed lookup, the oldest year shown in a facet, or the absence of a result
from a rolling or access-restricted public portal does not establish that a
decision or authority is nonexistent. Distinguish: existence and identity of
the decision; access to its official full text; provenance of the copy actually
reviewed; semantic support for the claim; and fidelity of that copy to the
official text. A non-institutional reproduction may support a claim when its
identity and substance are corroborated, but if the official full text was not
obtained, state that text fidelity remains unverified. Do not automatically
downgrade otherwise sound reasoning solely because the official historical
archive is gated or outside the public portal's documented window.

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
- distinguish an official archive's documented public-access window from the
  completeness of the authority's underlying historical collection;
- never translate a no-result in a rolling, partial, or gated official portal
  into a finding that the cited decision does not exist;
- distinguish the provenance and text fidelity of a reproduction from whether
  the reproduced authority substantively supports the claim;
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
