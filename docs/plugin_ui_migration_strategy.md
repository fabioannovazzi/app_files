# Plugin UI Migration Strategy

This document defines the target direction for improving local Codex plugin UX
without adding one-off interfaces to every plugin.

## Goal

Create one shared UI strategy for local Codex plugins:

- use Codex-native choices for small intake decisions;
- use local review UIs only when users must inspect, edit, or approve many
  rows, findings, documents, or evidence items;
- persist every user-facing decision to durable JSON;
- keep static Markdown/HTML fallbacks available;
- move every plugin family toward the same MCP-first handoff pattern, using
  row-review payloads for checking workflows and chart/report payloads for
  plotting workflows.

Use `docs/openai_plugin_lessons_playbook.md` as the adoption filter for
OpenAI plugin patterns. The UI can borrow review, validation, interaction, and
handoff mechanics from OpenAI plugins, but the Mparanza execution model remains
local-data-first and deterministic-script-first.

Review workflows and chart workflows should both be migrated one plugin at a
time using the shared local MCP plus reusable HTML/widget approach.

## Non-Goals

- Do not build a separate custom app for each plugin.
- Do not invest in legacy `/ui` work.
- Do not make HTML intake pages for simple 2-3 option questions.
- Do not make the front-door chooser own specialist workflows.

## UI Surfaces

Use the lightest surface that preserves workflow quality.

### Chat

Use chat when the user request is clear, the next decision is free-form, or a
wrong default is low risk.

### Plan-Mode Choices

Use native Plan-mode choices when a few discrete decisions must be fixed before
work starts, such as scope, language, source posture, output type, threshold, or
mapping mode.

When Plan-mode choices are unavailable, ask the same question in chat.

### Local Review UI

Use a local HTML review UI when the workflow materially benefits from tables,
search, filtering, side-by-side evidence, bulk decisions, editable cells, or
progress state.

The local UI must:

- run locally on `127.0.0.1` or as a local static fallback;
- avoid external CDNs and network assets;
- write durable decisions to a JSON handoff file;
- support submit, cancel, and recoverable partial-progress states when review
  volume is large;
- fall back to Markdown review files or chat confirmation when the UI cannot
  run.

### MCP Artifact Widgets

Use MCP widgets for reusable in-Codex review, report, and dashboard rendering.
The OpenAI Data Analytics pattern is the reference direction: Codex prepares a
bounded structured payload, a local MCP server validates it, and a reusable
widget renders it in the host.

## Shared Review Session Contract

Every UI-enabled plugin should be able to produce a review or render session
with these durable artifacts in the run output folder.

### `run_intake.json`

Records what Codex thinks the job is before write-heavy work.

Required fields:

- `schema_version`
- `plugin`
- `workflow`
- `created_at`
- `language`
- `input_paths`
- `output_dir`
- `inferred_task`
- `assumptions`
- `unresolved_questions`
- `dependency_check`

### `review_payload.json`

Records the rows, documents, findings, mappings, chart specs, datasets, or
evidence items that need human review or widget rendering.

Required fields:

- `schema_version`
- `plugin`
- `workflow`
- `run_id`
- `source_paths`
- `review_type`
- `items`
- `item_count`
- `columns`
- `evidence`
- `allowed_actions`
- `status`

Common `allowed_actions`:

- `accept`
- `reject`
- `edit`
- `mark_unclear`
- `request_more_documents`
- `skip`

### `ui_decisions.json`

Records user decisions from the review UI or fallback review flow.

Required fields:

- `schema_version`
- `plugin`
- `workflow`
- `run_id`
- `decided_at`
- `decision_source`
- `review_payload_path`
- `decisions`
- `decision_count`
- `status`

`decision_source` should be one of:

- `local_html_ui`
- `plan_mode_choice`
- `chat_confirmation`
- `markdown_fallback`

### `final_artifacts.json`

Records final outputs and caveats after Codex consumes the decisions.

Required fields:

- `schema_version`
- `plugin`
- `workflow`
- `run_id`
- `completed_at`
- `outputs`
- `caveats`
- `next_actions`
- `status`

## Migration Order

### Phase 1: Review Workflows

Start with plugins where UI value is review and confirmation, not chart
rendering. Include `report-builder` in this phase because its UI need is source
mapping, report-outline review, evidence selection, and draft section review,
not plotting.

Recommended order:

1. `new-client`
2. `check-entries`
3. `journal-bank-reconciliation`
4. `audit-reconciliation`
5. `journal-sampling`
6. `deep-research-validator`
7. `prompt-optimizer`
8. `report-builder`
9. `concordato-plan-review`

`new-client` is the best first plugin because it is one coherent workflow for a
commercialista: prepare the client file, establish the professional relationship,
and keep the dossier current. Its subordinate `client-file-preparation` engine
handles document inventory, detected document types, missing documents, extracted
fiscal fields, uncertain files, duplicate warnings, the draft memo, and the draft
client email.

### Phase 2: Chart And Plotting Workflows

Treat chart plugins like the other migrations: one plugin at a time, with
deterministic scripts still owning data prep and chart generation, and MCP/HTML
owning the review/rendering handoff.

Recommended order:

1. `variance-analysis`
2. `period-comparison`
3. `mix-contribution-analysis`
4. `scatter-bubble-analysis`
5. `distribution-analysis`

Target direction: structured report/chart manifest plus bounded snapshot,
validated and rendered by a local MCP widget when available. Static HTML,
Markdown, DOCX, PNG, and Plotly HTML remain fallbacks or export surfaces until
the MCP path is stable.

### Phase 3: Front-Door Chooser

Add a thin front-door plugin later, tentatively named `studio-assistant` or
`commercialista-assistant`.

Its responsibilities:

- infer user intent from the prompt and attached folders/files;
- inspect enough context to avoid asking unnecessary questions;
- ask one small clarifying question only when routing is ambiguous;
- hand off to the right specialist plugin with input paths, language, output
  folder, task type, and assumptions.

It should not own specialist workflows.

Example routes:

- prepare a new client file;
- analyze a tax notice or agency communication;
- check FatturaPA XML files;
- extract fiscal fields from CU, F24, 730, or Redditi PF;
- reconcile bank and accounting data;
- verify journal entries against supporting documents;
- draft a missing-documents email;
- sample accounting journal entries.

## Per-Plugin Target Surfaces

| Plugin | First UI Surface | Primary Review Object |
| --- | --- | --- |
| `new-client` | MCP review widget first; Markdown/static fallback | Client file, professional relationship, AML review, monitoring, and history; document preparation is handled by its `client-file-preparation` engine |
| `check-entries` | Local review UI | Entry-to-evidence comparisons and exceptions |
| `journal-bank-reconciliation` | Local review UI | Matches, unmatched rows, weak evidence, exceptions |
| `audit-reconciliation` | Local review UI | Open items, evidence categories, review samples |
| `journal-sampling` | Local review UI | Parsed journal rows, sample criteria, selected entries |
| `deep-research-validator` | Local review UI | Claims, citations, source snippets, validation findings |
| `prompt-optimizer` | Plan-mode choices first | Research angle, source posture, final prompt review |
| `report-builder` | Local review UI | Source mapping, report outline, evidence selection, draft sections |
| `concordato-plan-review` | Local review UI | Plan findings, evidence, unresolved checks |
| `variance-analysis` | MCP chart/report widget first; static exports fallback | Variance bridge, driver rows, chart evidence, narrative |
| `period-comparison` | MCP chart/report widget first; static exports fallback | Period movement charts, selected dimensions, chart evidence |
| `mix-contribution-analysis` | MCP chart/report widget first; static exports fallback | Mix/contribution charts, ranked drivers, source evidence |
| `scatter-bubble-analysis` | MCP chart/report widget first; static exports fallback | Scatter/bubble chart spec, point evidence, outliers |
| `distribution-analysis` | MCP chart/report widget first; static exports fallback | Distribution chart spec, bins/segments, source evidence |

## Definition Of Done For A Migrated Plugin Workflow

A plugin is migrated when:

- the skill explains the chosen UI surface and fallback;
- the plugin writes `run_intake.json` before write-heavy execution;
- the plugin can write `review_payload.json` for reviewable results or
  renderable chart/report payloads;
- user decisions or render-state decisions are persisted to `ui_decisions.json`
  when a review step runs;
- Codex consumes `ui_decisions.json` before final outputs when a review step ran;
- final outputs are listed in `final_artifacts.json`;
- the local UI is not required for simple intake choices;
- fallback review remains possible without blocking the workflow;
- tests cover the JSON contract and at least one happy-path review handoff.

## MCP Server Role Later

For future MCP widget work, the local MCP server should be a rendering and
validation layer, not the workflow owner.

Codex should:

- inspect inputs;
- reason through the workflow;
- prepare the structured payload;
- call validation/rendering tools exposed by the MCP server;
- read the resulting decisions or rendered artifact status.

The MCP server should:

- expose tools such as validate, render, and export;
- serve reusable local widget assets;
- validate payload schemas;
- return host metadata so Codex can display the widget;
- avoid doing specialist analysis that belongs in Codex or deterministic plugin
  scripts.
- keep source data bounded and local by default; it should receive reviewed
  payloads, not arbitrary raw client folders.

## Next Step

Continue one plugin at a time. For chart plugins, start with `variance-analysis`
unless a different chart workflow is more urgent. Its `review_payload.json`
should be a bounded chart/report payload: chart specs, driver data, source
evidence, narrative blocks, generated exports, and any reviewer choices needed
before final delivery.

Each implementation should follow the OpenAI plugin pattern: Python writes the
bounded payload, a local MCP server validates it, and a reusable HTML widget
renders it through `openai/outputTemplate`. Markdown/static review remains the
fallback when MCP tools are unavailable.
