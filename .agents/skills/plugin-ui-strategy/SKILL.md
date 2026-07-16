---
name: plugin-ui-strategy
description: Use when designing, editing, or reviewing Codex plugin UX, especially plugin intake, material choices, Plan-mode request_user_input widgets, chat fallback, local HTML review UIs, or script-to-browser-to-JSON handoff patterns.
---

# Plugin UI Strategy

Use this skill when a Codex plugin needs user choices or review. Choose the
lightest UI that preserves workflow quality.

## Selective OpenAI Pattern Adoption

Use `docs/openai_plugin_lessons_playbook.md` as the local reference when
adapting OpenAI plugin patterns. Adopt interaction, review, validation, and
handoff practices only when they preserve the Mparanza model:

- source data stays local by default;
- deterministic scripts own parsing, matching, reconciliation, chart-ready
  evidence, and other mechanically verifiable calculations;
- Codex owns orchestration, review, narrative, and handoff;
- local HTML/MCP surfaces render bounded payloads and capture decisions;
- no remote SQL, hosted notebook, or external data execution path is assumed
  unless the user explicitly chooses it.

Do not copy OpenAI patterns that only make sense for remote warehouses,
hosted artifact apps, or general-purpose model-generated calculations.

## Decision Rule

Use chat when the choice is simple, the answer is free-form, or the cost of a
wrong default is low.

Use Plan-mode native choices when there are a few discrete setup decisions that
must be fixed before work starts:

- research angle, framework, risk posture, output format, source posture;
- input/output scope, mapping mode, sampling strategy, review threshold;
- "before doing anything else, choose among these three things" moments.

Use a local HTML UI when chat or a single native widget would make the process
materially worse:

- many rows or findings need review;
- users must compare evidence side by side;
- decisions are stateful, editable, filterable, or bulk-applied;
- the workflow needs tables, search, sorting, grouping, or progress state;
- the script can receive browser decisions and write a durable JSON result.

Do not build an HTML UI for one-shot 2-3 option intake unless the user
explicitly asks for it.

Do not ask the user to type `continue` merely to create ceremony. Ask for
explicit continuation only when the next step is irreversible, external,
approval-sensitive, destructive, or when the current host mode genuinely
requires approval before execution. Otherwise state material assumptions,
proceed with conservative defaults, and record unresolved issues in the run
intake or final caveats.

## Plan-Mode Intake Pattern

In Default mode:

1. Run the normal inspection first.
2. State the inferred assumptions, defaults, and unresolved material choices.
3. If native choices would help, say the user can switch this chat to Plan mode
   for structured choices, or answer in chat.
4. Do not claim the plugin can switch modes itself.

In Plan mode, when `request_user_input` is available:

1. Ask only the unresolved material choice.
2. Show 2-3 high-signal options, with the recommended/default option first.
3. Let the host's free-form path cover custom answers.
4. After choices are fixed, state the execution plan and proceed unless the
   next step is irreversible, external, approval-sensitive, destructive, or
   still depends on an unresolved material choice.

If `request_user_input` is unavailable, ask in chat and wait.

## Local HTML UI Pattern

Use this pattern for richer review workflows:

1. Codex runs a plugin script.
2. The script starts a local server on `127.0.0.1` using an available port.
3. The server serves a small HTML UI from the plugin or work folder.
4. The browser posts decisions back to the script.
5. The script writes a durable handoff file such as `ui_decisions.json`,
   `review_result.json`, or `mapping_review.json`.
6. Codex reads that JSON, validates it, and continues the workflow.

Implementation requirements:

- Persist every final decision in a JSON file in the run output folder.
- Include a schema version, source file paths, timestamps, and decision status.
- Include the local data posture: which files were read locally, which bounded
  excerpts or summaries were sent to the model if any, and whether any external
  connector or upload path was used.
- Keep the UI local-only by default; do not depend on external CDNs or network
  assets.
- Provide submit and cancel states, and make partial progress recoverable when
  review volume is large.
- If the server cannot start, fall back to a markdown review file or chat
  confirmation rather than blocking indefinitely.

## Practical Examples

Good Plan-mode native-choice uses:

- Optimize Prompt asks for the research angle before drafting.
- A reconciliation plugin asks which matching threshold to apply.
- A report builder asks whether the report is board memo, audit memo, or client
  letter.

Good local HTML UI uses:

- Review 80 extracted invoice fields and correct selected cells.
- Accept, reject, or edit journal-to-bank matches with evidence side by side.
- Triage Deep Research validation findings with source snippets and claim rows.
- Map ambiguous spreadsheet columns with preview rows and bulk apply.

## Guardrails

- Native widgets are host-controlled. Use `request_user_input` only when the
  tool is available in the current mode.
- A plugin should not use Plan mode only for theater. Use it when a structured
  pre-work choice genuinely improves the run.
- HTML is a small local app, not just a static artifact, when decisions must
  flow back into the script.
- Do not hide unresolved assumptions inside generated prompts or reports. Show
  them before execution when they materially change the outcome.
- Treat `partial` and `blocked` as first-class workflow states, not as buried
  caveats. Missing required evidence, source files, or deterministic outputs
  should block or partially block the relevant path rather than trigger model
  inference.
- Validate review payloads before rendering and validate `ui_decisions.json`
  before applying decisions. Do not claim completion from file existence alone;
  the final handoff should prove that decisions were consumed and final
  artifacts were written.
