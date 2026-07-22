---
name: concordato-plan-review
description: Use when a user wants Codex to tie out the numerical section of an Italian concordato plan against bilancio, mastrini, adjusted DB schedules, tax/social-security debt details, or other accounting support, then produce auditor-oriented differences and going-concern criticalities.
---

## Output Location Rule

Never write run outputs inside this Git workspace, `static/shared`, `protected_downloads`, or any GitHub Pages/static-site folder unless the task is explicitly plugin packaging/release. For user-data runs, choose an output directory outside the repo, preferably a sibling `output/<plugin-name-or-run-id>` folder next to the user-provided input folder, and pass that path to every `--output-dir` or `--out` argument. If a script has a safe default next to the input folder, use that default instead of inventing `out/...` under the repo.

# Revisione Piano Concordato

Use this skill for a vertical review of an Italian concordato plan, especially when the user asks to compare a `piano CP` or `piano di concordato` with bilancio, mastrini, DB rettificato, dettagli debiti tributari/previdenziali, or other accounting evidence.

This is not a general report builder. Deterministic scripts support extraction, arithmetic, inventory, and candidate matching. Codex owns semantic review: deciding whether a number is historical, a rettifica, a riclassifica, a forward-looking assumption, unsupported, omitted, or critical for the auditor.

## Codex-Native Run UX

Before running helper scripts or write-heavy work, identify material choices that would change execution: problem framing, decision angle, risk appetite, scope boundaries, audience, evidence posture, mappings, cut-off, OCR, notification, or review assumptions. Ask only those unresolved choices in chat and wait for the answer. Generate choices from the actual inputs; do not offer named frameworks, regulators, document types, output packages, or issue categories unless the facts cue them or the user must supply a missing custom value. Do not run long or write-heavy execution under unconfirmed assumptions.

Default output policy: produce the richest normal package for the workflow. DOCX/Word, Excel/CSV, JSON audit, diagnostics, charts, packaged reports, review notes, and Codex-written review files are not choices to propose when they are natural outputs of that plugin; generate them whenever dependencies and source data permit. Ask only when an output is technically impossible, unsafe, or the user explicitly requests a reduced/debug run.

Default currency policy: use Euro (`EUR`) unless the user or source file explicitly states another currency. Do not ask for currency when it is otherwise unresolved; record `EUR` as the assumption.

Use Codex-native UI artifacts as part of the workflow, not as optional narration. At minimum:

1. Start with a visible markdown run checklist. Track intake, dependency check, inspection, user decisions, deterministic run, Codex review, and delivery.
2. Before helper scripts, show a Run Intake table with input paths, output folder, working language, document language, assumptions, and notification choice when the skill supports user run notifications.
3. After inspection, show a compact Decision Table for missing mappings, filters, review choices, unsupported files, or evidence assumptions. Ask only unresolved decisions and update the working recipe or assumptions yourself.
4. Before a long-running or write-heavy step, show an execution checkpoint or approval checkpoint with command intent, inputs, output folder, and expected artifacts. Ask for approval only when the step is external, destructive, approval-sensitive, or still depends on an unresolved material choice.
5. During execution, update checklist statuses as steps complete.
6. End with an Artifact Card listing output path, purpose, review status, unresolved items, and next action. When useful, create `codex_run_review.md` in the output folder from generated JSON/CSV/Markdown outputs; never edit plugin source or generated ZIPs during a run.

## Core Principle

The deterministic code is justified only for mechanically verifiable tasks: file inventory, PDF text extraction, workbook sheet inspection, number parsing, exact arithmetic, and candidate amount matching. It must not decide legal/tax framing, auditor conclusions, going-concern status, or whether a source semantically supports a plan claim. If deterministic matches and Codex judgment disagree on semantic support, prefer Codex/reviewer judgment unless a documented benchmark proves the rule is better.

The user should not operate helper CLIs directly. Codex inspects the folder, confirms assumptions, runs scripts, reviews outputs, and explains limitations.

## Inputs

Required:

- input folder containing the plan and accounting support files.

Typical files:

- `ExampleCo piano CP_2026.05.25.pdf` or other concordato plan PDF;
- `BILANCIO 31-03-26 PROVVISORIO.pdf`;
- `mastrini al 31-03-26.pdf`;
- `DB_31.03.2026_21052026.xlsx`;
- `Dettaglio ... Debiti tributari e previdenziali ... .xlsx`;
- optional business-plan workbook or creditor schedules.

Ask only when missing or unclear:

- reference date or cut-off;
- working language and document language;
- which file is the authoritative plan if several plan-like files exist;
- materiality/tolerance for differences.

The default review scope includes the tie-out workpaper, Word summary, Codex reviewer memo, open items, missing evidence, and criticalities. Do not ask whether to stop at a thinner tie-out-only output unless the user explicitly requests a reduced run.

## First Run Workflow

1. Inventory the input folder and identify likely source roles from file names. Treat role detection as a suggestion for intake, not an authoritative mapping.
2. Run dependency checks from the plugin directory before helper scripts:

```bash
python scripts/check_dependencies.py
```

If requirements are missing, install from `requirements.txt` only when the environment allows it. If installation is unavailable or requires approval, explain which declared capability is missing and stop before producing unreliable output.

3. Run the deterministic review package:

```bash
python scripts/run_concordato_review.py /path/to/input \
  --output-dir /path/to/output \
  --reference-date 2026-03-31 \
  --language it \
  --document-language it \
  --tolerance 1.00
```

4. Review generated files:

- `inventory.json`;
- `source_pages.json`;
- `amount_candidates.csv`;
- `exact_amount_matches.csv`;
- `concordato_tie_out_workpaper.xlsx`;
- `concordato_review_summary.docx`;
- `review_packet.md`;
- `run_audit.json`;
- `run_intake.json`;
- `review_payload.json`;
- `ui_decisions.json`;
- `applied_decisions.json` after reviewer decisions are applied;
- `final_artifacts.json`.

5. Read `run_intake.json` and `review_payload.json`. Treat the review payload
as the structured contract for reviewer-facing UI: source roles, extraction
issues, candidate amount matches, unmatched plan amounts, generated artifacts,
and the Codex memo placeholder.
6. When the `concordatoPlanReviewWidgets` MCP server is available, call
`validate_concordato_plan_review` with the complete `review_payload.json`
object. If validation passes, call `render_concordato_plan_review` with the
same payload and optional `run_intake`, `ui_decisions`, and `final_artifacts`
objects. Do not hand-build another HTML page for the same review.
7. When the reviewer records actions in the widget or Codex collects decisions
through fallback review, call `save_concordato_plan_decisions` so
`ui_decisions.json` is validated and persisted. When the reviewer is done, call
`apply_concordato_plan_decisions` so `applied_decisions.json` and
`final_artifacts.json` reflect accepted, edited, unclear, skipped, or
document-requested items.
8. If MCP rendering is unavailable, continue by reading `review_payload.json`
and reviewing through Markdown/chat. Keep review decisions pending unless they
are recorded in `ui_decisions.json` and consumed into
`applied_decisions.json`.
9. Codex must then build the actual auditor review: inspect
`concordato_review_summary.docx`, candidate matches, unmatched material plan
amounts, distinguish historical data from rettifiche/riclassifiche/assumptions,
and write `codex_run_review.md` with open items, missing evidence, and
criticalities. If numbers match mechanically, say they match by amount and
still require context review. If they do not match, say clearly which amount
was not found and where it appears in the plan.

## MCP Review Handoff

The UI handoff follows the OpenAI-style local MCP/widget pattern:

1. Python writes bounded review-session JSON files in the output folder.
2. The local MCP server validates the `review_payload.json` schema and item
types.
3. The MCP render tool returns `openai/outputTemplate` metadata for
`ui://widget/concordato-plan-review.html`.
4. The reusable HTML widget renders the payload with summary metrics, type
filters, search, rows, and evidence detail.
5. Codex saves reviewer actions with `save_concordato_plan_decisions`, applies
them with `apply_concordato_plan_decisions`, and uses the reviewed payload plus
applied decisions when writing the final `codex_run_review.md`.

## Review Method

Load `references/review-methodology.md` when classifying numbers or writing the auditor-oriented memo.

Expected final review dimensions:

- source traceability: where each relevant number was gathered;
- plan-to-source difference: amount, source, delta, tolerance status;
- plain-language status: `batte per importo`, `non batte`, or `da spiegare`;
- evidence category: historical accounting data, rectification, reclassification, prospective assumption, unsupported or unclear;
- financial statement effect: balance sheet, P&L, net equity, debt maturity, tax/social-security debt, cash flow;
- going-concern implication: liquidity, debt sustainability, operational continuity, covenant/tax/social-security pressure, creditor treatment;
- omissions or unsupported assertions;
- reviewer follow-up questions and missing evidence requests.

## Deterministic Output Limits

Do not present `exact_amount_matches.csv` or the Word summary as final support. They are candidate outputs. Equal amounts can appear in unrelated places, and PDF extraction can fragment tables. Codex must review context and source role before marking a number as supported.

Do not use deterministic keyword rules to choose legal topics, tax conclusions, or going-concern conclusions. Use the deterministic data as evidence collection only.

## Plugin Improvement Feedback

At the end of every completed or blocked plugin run, after reporting the deliverables, briefly identify concrete improvements that would have made this plugin run better. Base suggestions on the actual session, such as missing source formats, brittle PDF extraction, weak plan table detection, unclear source-role assumptions, missing creditor-class logic, output gaps, installation friction, or repeated manual steps.

Keep the improvement note local to chat or run artifacts. Do not submit it to
Mparanza automatically. When this workflow runs through Vera, use Vera's
consent-based Plugin Improvement Feedback process for any transmission.
