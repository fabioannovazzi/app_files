# Codex Plugin Guide Checklist

Use this checklist when creating, reviewing, or releasing first-party Codex plugins in this repo. It translates the OpenAI plugin/skills guide into repo checks that can be applied consistently.

## Workflow First

- The plugin describes a repeatable, bounded, testable workflow with a named user, expected inputs, outputs, review points, and definition of done.
- The skill makes clear what deterministic scripts own and what Codex owns.
- The user experience is a guided Codex workflow, not direct CLI use.
- Platform claims are separated from operating patterns; do not imply undocumented marketplace, RBAC, release-channel, or publishing capabilities.
- OpenAI plugin patterns are adopted only through
  `docs/openai_plugin_lessons_playbook.md`: preserve local data, deterministic
  calculation ownership, bounded payloads, review-state persistence, and
  source/evidence gates.
- The skill does not ask the user to type `continue` for theater. It asks only
  when a material choice, approval-sensitive action, external write, or
  irreversible step requires explicit confirmation.

## Skill Anatomy

- `.codex-plugin/plugin.json` exists and points `skills` to `./skills/`.
- Each `SKILL.md` has concise frontmatter with trigger phrases and boundaries.
- Long standards, prompts, artifact lists, and operational rubrics live in `references/` and are loaded only when needed.
- Scripts are used for deterministic parsing, checks, transforms, rendering, or validation.
- Critical checks, uncertainty handling, and failure modes appear near the top of the workflow instead of being buried in examples.

## Packaging

- Runtime dependencies are declared in `requirements.txt`.
- `scripts/check_dependencies.py` exists and the skill tells Codex to run it before helper scripts.
- The repo-local marketplace points only to plugin source directories that exist.
- Download ZIPs are generated from source with `scripts/build_codex_plugin_zip.py`; do not patch ZIPs manually.
- Manifest paths stay relative to the plugin root and start with `./` where required.
- API Skills, local Codex skills, and installable plugins are described as separate rollout surfaces.

## Testing And Evaluation

- `tests/plugins` verifies source/ZIP drift, metadata, dependency checks, marketplace entries, feedback policy, and local-junk exclusion.
- `docs/openai_plugin_interaction_patterns.json` is the structured source of
  truth for selectively adopted and explicitly rejected OpenAI interaction
  lessons. Edit this catalog when adding, retiring, or rejecting a pattern,
  then run
  `scripts/audit_plugin_interaction_patterns.py --format markdown` for the
  repo-level scorecard: per-pattern coverage, playbook traceability, rejected
  patterns with guardrail signals, no `continue` theater, material approval
  boundaries, local/deterministic posture language, stateful review
  persistence, visible handoff cards, and acceptable custom UI exceptions.
- `scripts/audit_non_plotting_review_workbench_demos.py --format markdown
  --fail-on medium` verifies generated non-plotting workbench demos exercise a
  real review queue, multiple item types/actions, evidence, edit targets,
  detail panels, localized workflow labels, and item/action values accepted by
  each plugin MCP validator. It also reports each adapter's workflow
  `detailMode` and fails duplicate modes or shallow panel definitions, so the
  shared renderer cannot silently collapse into the same generic page for every
  plugin.
- `tests/plugins/test_non_plotting_review_workbench.py` verifies those adapter
  demo payloads are accepted by each plugin's MCP save/apply writer, not only
  by the HTML renderer.
- `scripts/serve_review_workbench.py` is the shared local-browser fallback for
  generated review workbench plugins. It injects a local `window.openai`
  bridge into the generated HTML, forwards Save/Apply to the plugin MCP server,
  and persists `ui_decisions.json`, `applied_decisions.json`, changed target
  artifacts, and `final_artifacts.json` in the run output folder. Package
  validation injects it as `scripts/review_server.py` for generated workbench
  plugins that do not already ship a custom local server.
- When a local browser is available,
  `scripts/audit_local_review_workbench_writeback.py --format markdown
  --fail-on high --screenshots-dir /private/tmp/local_review_writeback`
  opens the shared local review server for every generated non-plotting
  workbench, clicks each plugin's actual Save/Apply controls, verifies durable
  decision files and declared target-artifact updates, and captures screenshots.
  This is browser-level fixture evidence for the write-back path, not
  customer-folder validation. For machine-readable readiness evidence, run the
  same audit with `--format json --report-path <path>` and pass that file to
  `scripts/audit_openai_pattern_adoption_readiness.py --browser-writeback-report <path>`;
  add `--require-browser-writeback` when that mechanism proof is a release gate.
- `scripts/validate_plugin_review_contract.py` verifies real generated
  `review_payload.json` files against the plugin MCP item/action contract when
  the plugin declares static `ITEM_TYPES` and `ALLOWED_ACTIONS`.
- `scripts/audit_review_payload_contract_coverage.py --format markdown
  --fail-on high` verifies each generated non-plotting workbench plugin has a
  plugin-owned contract test and a workflow-scenario test validating generated
  review-session artifacts with `validate_contract(...)`. Use `--fail-on
  medium` when you want missing workflow-scenario evidence to fail locally.
- `scripts/audit_openai_pattern_adoption_readiness.py --format markdown
  --report-path <path> --fail-on medium` gives reviewers a single persisted
  OpenAI-pattern adoption scorecard across interaction lessons, workbench demo
  quality, and workflow-scenario contract coverage. The validation tiers
  deliberately keep real
  customer-folder validation separate from test-fixture workflow coverage and
  list the evidence needed to upgrade that tier: representative cases, local
  review screenshots, saved decisions, final artifact readback, and a recorded
  validation manifest. Generate a TODO-filled starter with
  `scripts/audit_openai_pattern_adoption_readiness.py --write-customer-validation-template <path>`,
  or pass `--expected-customer-plugin` for a deliberately narrower validation wave.
  The live evidence file remains
  `docs/openai_pattern_customer_validation_manifest.json`; only fill it with
  real runs. The recorder refuses run artifacts that still carry explicit
  synthetic/demo/browser-audit markers, so fixture proof stays separate from
  real-customer readiness evidence. Before writing the live manifest, run
  `scripts/audit_openai_pattern_adoption_readiness.py --preflight-customer-validation-case`
  against the workflow output folder; it performs the same case and manifest
  validation without creating or modifying the evidence file. Add
  `--infer-case-metadata-from-run` only to infer missing `--plugin`,
  `--scenario-name`, and `--language` from `run_intake.json` /
  `review_payload.json`; keep case id, input case, reviewer, screenshots, UX
  checks, and reviewer notes explicit. Prefer recording real cases with
  `scripts/audit_openai_pattern_adoption_readiness.py --record-customer-validation-case`
  only after preflight passes, so required artifacts and screenshots are
  captured consistently. Recorded passing cases must include
  `--ux-verdict usable`, every required `--ux-check`
  (`queue_clear`, `evidence_comparison_clear`, `decision_controls_complete`,
  `edit_flow_usable`, `artifact_handoff_clear`, `no_blocking_issues`), and
  non-empty `--reviewer-notes`; cases with `usable_with_issues` or `blocked`
  remain partial evidence. Use
  `docs/openai_pattern_customer_validation_runbook.md` as the operating
  procedure for selecting representative cases, capturing screenshots, reading
  back native outputs, and recording live evidence. The static example
  `docs/openai_pattern_customer_validation_manifest.example.json` documents the
  full expected shape with one TODO case for each generated non-plotting
  workbench plugin. Do not narrow that expected set by deleting cases from the
  live manifest; use `--expected-customer-plugin` only when a deliberately
  smaller validation wave is being reported. By default the readiness report
  expects coverage for generated non-plotting workbench plugins. For a
  release-grade gate after real evidence exists, add
  `--require-customer-validation --verify-customer-validation-artifacts --fail-on medium`.
  This strict mode checks that listed local files exist, required JSON artifacts
  are parseable and non-empty, screenshots/readbacks are non-empty, and
  `final_artifacts.json` is no longer pending review. Coverage also requires
  `ux_verdict: usable` plus all required UX checks.
- `scripts/build_openai_pattern_adoption_evidence.py --output-dir <dir>` is the
  normal persisted handoff for reviewers: it writes `readiness.json`,
  `readiness.md`, `browser_writeback_gallery.html`,
  `browser_writeback_gallery.json`, `customer_validation_template.json`,
  `customer_validation_plan.md`, `customer_validation_plan.json`,
  `customer_validation_checklist.html`, `completion_assessment.json`,
  `completion_assessment.md`, `adoption_review_dashboard.html`,
  `bundle_manifest.json`, and `README.md` into one folder. The completion
  assessment maps the original adoption objective to covered evidence and
  remaining gaps; it must stay incomplete until real customer-folder validation
  is covered. The manifest and README record rerunnable commands for the browser
  write-back report, bundle rebuild, and strict customer-validation gate. Pass
  `--browser-writeback-report <path>` after running the local browser audit
  when mechanism evidence should be included in the same bundle; the gallery
  copies available screenshots into the bundle so reviewers can scan the actual
  local review surfaces instead of reading only JSON. Open
  `adoption_review_dashboard.html` first for the reviewer front door across
  validation tiers, quick evidence links, objective requirements, and next
  actions. It includes a per-plugin adoption matrix for demo UI, workflow
  contracts, browser write-back, real customer validation, and scenario-test
  evidence. It also shows the adopted OpenAI lessons and the rejected OpenAI
  patterns with their local replacements, so reviewers can see what was learned
  and what was deliberately not copied. Open
  `customer_validation_checklist.html` to see the remaining real-case evidence
  requirements, preflight/record commands, metadata inference boundaries, and
  covered versus missing plugins without digging through JSON. After real cases
  are recorded, pass
  `--customer-validation-manifest <path> --require-customer-validation
  --verify-customer-validation-artifacts` so the bundle becomes the persisted
  strict-gate evidence. Add `--require-complete-objective` only when the bundle
  should fail unless every objective requirement, including real customer-folder
  validation, is covered.
- When a local browser is available,
  `scripts/audit_non_plotting_review_workbench_visuals.py --format markdown
  --fail-on high --languages en,it,fr,de --screenshots-dir
  /private/tmp/non_plotting_workbench_visuals_i18n`
  opens each generated workbench at desktop and mobile sizes, loads the sample
  review payload in each listed language, checks rows/details/decision
  controls/key sections/localized labels, detects runtime errors and horizontal
  overflow, and writes screenshots for review.
- `scripts/build_codex_plugin_zip.py --check` runs the same interaction audit
  plus the workbench-demo and generated-payload coverage audits during plugin
  source validation and fails on blocker/high/medium interaction, demo-quality,
  or generated-output coverage issues; informational custom-UI notes remain
  scorecard-only.
- Every plugin has trigger/eval fixtures with positive prompts, negative prompts, and required workflow signals.
- Functional tests cover deterministic helper behavior for new or changed business logic.
- Obvious, paraphrased, contextual, and negative-control prompts should be represented in fixtures as the workflow matures.
- UI-enabled plugins validate `run_intake.json`, `review_payload.json`,
  `ui_decisions.json`, `applied_decisions.json`, and `final_artifacts.json`
  when those files are part of the workflow.
- Use `scripts/validate_plugin_review_contract.py` for the shared
  review-session contract, then add plugin-specific checks for domain evidence.
- Tests cover `partial` and `blocked` states when required source files,
  evidence, deterministic outputs, or user decisions are missing.

## Public HTML Pages

- Public pages describe the actual workflow, inputs, outputs, install path, and first-use prompt without claiming unsupported distribution behavior.
- Pages link to generated ZIPs, not hand-edited packages.
- Pages support the same working locales as the plugin when the plugin is multilingual.
- Pages direct maintainers and contributors to the repository for feedback; creating a GitHub issue still requires explicit user confirmation.

## Governance

- Manifests expose homepage, website, privacy policy, terms, category, icons, default prompts, and useful descriptions.
- Skills document approval-sensitive actions such as email sending and never send automatically.
- End-of-run plugin improvement feedback is written by Codex, then submitted as a GitHub issue only if the user confirms.
- Skills state important professional limits, such as no tax advice or no silent model override of deterministic results.
- Skills are workflow instructions, not policy controls; access, sandboxing, and approvals must remain explicit product or platform controls.
