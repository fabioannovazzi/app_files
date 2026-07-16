---
name: deep-research-validator
description: Use when a user wants Codex to validate a Deep Research answer or report against cited sources, review material claims, identify unsupported or weak reasoning, propose corrections, and package a validated document. Do not use for creating Deep Research prompts or for answering the underlying legal, tax, or compliance question directly.
---

## Output Location Rule

Never write run outputs inside this Git workspace, `static/shared`, `protected_downloads`, or any GitHub Pages/static-site folder unless the task is explicitly plugin packaging/release. For user-data runs, choose an output directory outside the repo, preferably a sibling `output/<plugin-name-or-run-id>` folder next to the user-provided input folder, and pass that path to every `--output-dir` or `--out` argument. If a script has a safe default next to the input folder, use that default instead of inventing `out/...` under the repo.

# Validate Deep Research

Use this skill when a completed Deep Research output must be reviewed against its cited sources. Codex owns the judgment work: selecting material claims, evaluating source support, reviewing reasoning, deciding whether fixes are needed, and drafting a corrected document.

The workflow is not Italian-only. Support the same four working locales used by the Mparanza plugins: `it`, `en`, `fr`, and `de`. Keep artifact file names and JSON keys in English for stability, but speak to the user in the chosen working language.

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

Deterministic Python code only inspects document structure, extracts citations and URLs, fetches or parses sources, checks exact quote matches, validates review JSON, packages outputs, and optionally exports DOCX. The plugin scripts must not make direct OpenAI API calls or other model API calls.

The user should not interact directly with CLI scripts. Treat scripts as internal tools Codex runs on behalf of the user.

## Inputs

Required:

- a Deep Research answer/report as Markdown, text, HTML, or readable PDF.

Optional:

- working language: `it`, `en`, `fr`, or `de`;
- validation objective, such as source support only, reasoning review, or corrected-document generation;
- local source files when cited URLs are unavailable or gated.

## First Run Workflow

1. Ask only for essential missing context: working language and validation objective when they cannot be inferred. The default objective is the full package: source-support review, reasoning review, correction proposal, validation package, and DOCX export when tooling is available.
2. Save the Deep Research document in the work folder as `deep_research.md`, `deep_research.txt`, `deep_research.html`, or `deep_research.pdf`.
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

6. Read `document_inventory.json`, `source_inventory.json`, and `extracted_document.md`. Select the material claims to review. Prefer claims that affect conclusions, recommendations, numbers, dates, eligibility, legal/tax/compliance positions, or risk statements.
7. Write `claims_review_draft.json` in this shape:

```json
{
  "language": "en",
  "validation_objective": "source_support_and_reasoning",
  "claims": [
    {
      "claim_index": 1,
      "claim_text": "Material claim text.",
      "verdict": "supported",
      "source_refs": ["https://example.com/source"],
      "source_quote": "Exact source passage when available.",
      "source_support": "Why the cited source supports, partially supports, contradicts, or fails to support the claim.",
      "reasoning_review": "Whether the inferential step from sources to claim is sound.",
      "proposed_fix": "Correction or caveat if needed."
    }
  ],
  "overall_assessment": "Short validation summary.",
  "validated_document": "Corrected Markdown document if requested."
}
```

Valid verdicts are `supported`, `partially_supported`, `not_supported`, `contradicted`, and `uncertain`.

8. Package and audit the review:

```bash
python scripts/package_validation.py <output-dir>/document_inventory.json <output-dir>/source_inventory.json <output-dir>/claims_review_draft.json --output-dir <output-dir>
```

Add `--docx` whenever DOCX tooling is available. Do not ask whether to export DOCX; it is a natural deliverable of the validation package.

9. Read `validation_audit.json`. If required fields, verdicts, or review text are missing, repair `claims_review_draft.json` in Codex and rerun packaging.
10. Deliver `claims_review.json`, `validation_audit.json`, `validated_document.md`, `validated_document.docx` when tooling permits, and `validation_package.md`. Report assumptions, unavailable/gated sources, and any failed audit checks explicitly.

## Validation Requirements

The review must:

- separate source availability issues from substantive support issues;
- distinguish supported, partially supported, unsupported, contradicted, and uncertain claims;
- preserve source URLs, citations, and quoted passages where available;
- flag unavailable, gated, too-short, or unparseable sources as evidence limits;
- review reasoning separately from source existence;
- avoid answering the underlying legal, tax, or compliance question beyond validation/correction;
- make residual uncertainty explicit.

## Expected Outputs

- `document_inventory.json`;
- `source_inventory.json`;
- `claims_review.json`;
- `validation_audit.json`;
- `validated_document.md`;
- `validated_document.docx` when DOCX tooling is available;
- `validation_package.md`;
- `run_intake.json`;
- `review_payload.json`;
- `ui_decisions.json`;
- `applied_decisions.json` after reviewer decisions are applied;
- `final_artifacts.json`.

## MCP Review UI

When the local MCP server is available, prefer the OpenAI-style review handoff:

1. Read `run_intake.json`, `review_payload.json`, `ui_decisions.json`, and
   `final_artifacts.json` from the validation output folder.
2. Call `validate_deep_research_review` with `review_payload` before rendering.
3. If validation succeeds, call `render_deep_research_review` with the same
   payload objects so Codex can show the local HTML widget
   `ui://widget/deep-research-review.html`.
4. Use the widget to inspect claim verdicts, unsupported/contradicted/uncertain
   items, source availability limits, failed audit checks, and generated
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
- `de`: German.

Starter prompts:

```text
IT: Usa Validate Deep Research su questo output. Lingua: it. Ispeziona documento e fonti, scegli le affermazioni materiali, valuta supporto delle fonti e ragionamento, segnala limiti o correzioni, e prepara il pacchetto di validazione.
EN: Use Validate Deep Research on this output. Language: en. Inspect the document and sources, choose material claims, review source support and reasoning, flag limits or corrections, and prepare the validation package.
FR: Utilise Validate Deep Research sur cette sortie. Langue: fr. Inspecte le document et les sources, choisis les allegations materielles, examine le support des sources et le raisonnement, signale les limites ou corrections, puis prepare le paquet de validation.
DE: Verwende Validate Deep Research fuer diesen Output. Sprache: de. Pruefe Dokument und Quellen, waehle wesentliche Aussagen, pruefe Quellenstuetzung und Begruendung, markiere Grenzen oder Korrekturen und erstelle das Validierungspaket.
```

## Failure Modes

- If the source document is empty or unreadable, ask for a Markdown/text export before validating.
- If URLs are unreachable or gated, report the evidence limit and ask for local source files only when that materially affects validation.
- If the document contains no citations, perform a reasoning and citation-gap review rather than inventing sources.
- If the user asks for the substantive answer instead of validation, explain that this plugin validates a completed Deep Research output and route prompt creation to the prompt optimizer when relevant.
- If deterministic audit flags missing review fields, repair the review JSON before delivery.

## Plugin Improvement Feedback

At the end of every completed or blocked plugin run, after reporting the deliverables, briefly identify concrete improvements that would have made this plugin run better. Base suggestions on the actual session, such as a missing source parser, weak claim-selection rule, brittle citation extraction, missing deterministic validation check, unclear assumption, needed fixture, output gap, installation friction, or repeated manual step.

When there is something useful to report, write a short improvement note with:

- observed gap;
- proposed improvement;
- why it matters;
- relevant input/output file names when available;
- suggested next engineering action.

Keep the improvement note local to chat or run artifacts.
