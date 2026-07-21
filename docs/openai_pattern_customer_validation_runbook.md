# OpenAI Pattern Customer Validation Runbook

Use this runbook before claiming that the OpenAI-derived plugin interaction
patterns work well on real customer material. Fixture demos, generated payloads,
and screenshots prove structure; they do not prove real workflow usability.

## Scope

The default release-grade validation set is every generated non-plotting
review-workbench plugin:

- `audit-reconciliation`
- `check-entries`
- `new-client`
- `client-file-preparation` (New Client's document-preparation phase)
- `concordato-plan-review`
- `deep-research-validator`
- `journal-bank-reconciliation`
- `journal-sampling`
- `prompt-optimizer`
- `report-builder`

Use `--expected-customer-plugin` only when deliberately reporting a narrower
validation wave. Do not narrow scope by deleting expected plugins from the live
manifest.

## Evidence Required Per Case

Each passing case needs real local workflow output, not synthetic demo output:

- `run_intake.json`
- `review_payload.json`
- `ui_decisions.json`
- `applied_decisions.json`
- `final_artifacts.json`
- at least one screenshot showing queue, detail, and decision state
- `native_output_readback`, or `not_applicable` when the workflow has no native
  DOCX/XLSX/PDF/report output to inspect
- non-empty reviewer notes
- `ux_verdict: usable`
- every required UX check marked true:
  `queue_clear`, `evidence_comparison_clear`, `decision_controls_complete`,
  `edit_flow_usable`, `artifact_handoff_clear`, `no_blocking_issues`

`usable_with_issues`, missing screenshots, pending final artifacts, empty JSON
artifacts, or incomplete UX checks remain partial evidence.

The recorder also rejects run artifacts whose `run_intake.json`,
`review_payload.json`, or `final_artifacts.json` contain explicit synthetic,
sample, demo, or browser-audit markers. Browser write-back fixture runs are
valid mechanism evidence, but they cannot be promoted into the real customer
validation manifest.

The recorder can infer only low-risk metadata from the run output folder. Add
`--infer-case-metadata-from-run` when `run_intake.json` and
`review_payload.json` already contain workflow metadata; then `--plugin`,
`--scenario-name`, and `--language` may be omitted. Do not infer evidence
fields: `--case-id`, `--input-path-or-case-id`, `--reviewer`, screenshots, UX
checks, and `--reviewer-notes` remain explicit reviewer inputs.

## Procedure

1. Select an anonymized representative customer folder or file set for the
   plugin being validated. Record the scenario name, language, and local input
   path or case identifier.

2. Run the plugin workflow from those local inputs. Keep the output folder
   intact. It must contain `run_intake.json`, `review_payload.json`,
   `ui_decisions.json`, `applied_decisions.json`, and `final_artifacts.json`
   after review and apply.

3. Open the MCP review widget or local browser review surface. Complete
   representative actions: at least one accept or reject, one edit when the
   workflow supports edits, and one unclear/more-documents action when the
   workflow supports evidence gaps.

4. Capture screenshots after decisions are visible. The screenshot must show
   enough UI state for a reviewer to confirm queue clarity, evidence comparison,
   decision controls, and artifact handoff.

5. Read back any native output that was supposed to change. For example, inspect
   generated DOCX/XLSX/PDF/report output and save a short readback note such as
   `native_readback.md`. If no native output exists, pass
   `--native-output-readback` only when there is a real readback file, or leave
   it unset so the manifest records `not_applicable`.

6. Preflight the case. This validates the same run artifacts, screenshots, UX
   checks, synthetic/demo markers, and target manifest schema as recording, but
   does not write the manifest:

```bash
.venv/bin/python scripts/audit_openai_pattern_adoption_readiness.py \
  --preflight-customer-validation-case \
  --case-id case-check-entries-001 \
  --plugin check-entries \
  --scenario-name "Representative customer support check" \
  --input-path-or-case-id "anonymized/check-entries/001" \
  --language it \
  --reviewer "Reviewer Name" \
  --run-output-dir /path/to/workflow/output \
  --screenshot-path /path/to/review-desktop.png \
  --native-output-readback /path/to/native_readback.md \
  --validation-status pass \
  --ux-verdict usable \
  --ux-check queue_clear \
  --ux-check evidence_comparison_clear \
  --ux-check decision_controls_complete \
  --ux-check edit_flow_usable \
  --ux-check artifact_handoff_clear \
  --ux-check no_blocking_issues \
  --reviewer-notes "Queue, evidence, decision controls, edit flow, and artifact handoff were usable without blocking issues." \
  --validation-command "ran workflow from local customer input" \
  --validation-command "opened review UI and applied decisions"
```

7. Record the case after preflight passes:

```bash
.venv/bin/python scripts/audit_openai_pattern_adoption_readiness.py \
  --record-customer-validation-case \
  --case-id case-check-entries-001 \
  --plugin check-entries \
  --scenario-name "Representative customer support check" \
  --input-path-or-case-id "anonymized/check-entries/001" \
  --language it \
  --reviewer "Reviewer Name" \
  --run-output-dir /path/to/workflow/output \
  --screenshot-path /path/to/review-desktop.png \
  --native-output-readback /path/to/native_readback.md \
  --validation-status pass \
  --ux-verdict usable \
  --ux-check queue_clear \
  --ux-check evidence_comparison_clear \
  --ux-check decision_controls_complete \
  --ux-check edit_flow_usable \
  --ux-check artifact_handoff_clear \
  --ux-check no_blocking_issues \
  --reviewer-notes "Queue, evidence, decision controls, edit flow, and artifact handoff were usable without blocking issues." \
  --validation-command "ran workflow from local customer input" \
  --validation-command "opened review UI and applied decisions"
```

8. Run the strict gate only after the live manifest contains real cases:

```bash
.venv/bin/python scripts/audit_openai_pattern_adoption_readiness.py \
  --format markdown \
  --require-customer-validation \
  --verify-customer-validation-artifacts \
  --fail-on medium
```

The strict gate must remain non-passing until every expected plugin has a
passing complete case with existing artifacts, valid JSON, non-empty screenshots
and readbacks, non-pending final artifacts, and a usable UX verdict.

9. Build the reviewer evidence bundle after mechanism evidence or real cases
   change. Open `adoption_review_dashboard.html` first for the overall status
   and per-plugin adoption matrix, then open
   `customer_validation_checklist.html` to review covered versus missing
   plugins, required evidence, metadata inference limits, and per-plugin
   preflight/record commands in HTML:

```bash
.venv/bin/python scripts/build_openai_pattern_adoption_evidence.py \
  --output-dir /private/tmp/openai-pattern-adoption-evidence \
  --customer-validation-manifest docs/openai_pattern_customer_validation_manifest.json \
  --require-customer-validation \
  --verify-customer-validation-artifacts \
  --fail-on medium
```

## Interpretation

- `ok` without `--require-customer-validation` means the repo-level interaction,
  demo, and workflow-fixture contracts are covered.
- `customer_validation_required_not_covered` means the repository is still
  missing real customer-folder evidence.
- A passing strict gate means the recorded cases are complete enough to claim
  real-customer validation for the expected plugin set. It is still not a claim
  that every edge case or every possible customer folder is perfect.
