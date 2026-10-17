# Model preference for Vera's legal and tax pipeline

Prefer the most capable model available in the user's current host/account for
preparation, research, drafting, validation, opposing opinion and revision.
This is guidance, never a prerequisite or a workflow gate. Continue the requested
work with the active model when it differs, is unknown, changes mid-work, or the
recommended model is unavailable. Never wait for a model switch or confirmation.
Do not hard-code a model name or treat an earlier preference as a version lock.
User instructions about model choice take precedence.

Keep the existing authenticated host, model account, tools and case boundaries.
Do not request model API keys, add a model API or transfer case material to
another account. The plugin does not switch the host's model.

## Record provenance without blocking

Use actual host metadata for model identity when exposed. Otherwise record it
as unknown; never invent host evidence or a user confirmation. Capability advice
may use an available catalogue, but missing catalogue access never requires a
question, a provider lookup or a delay. Do not infer capability from model names.

Prepare/start the normal managed or supported standalone run. Its existing
storage, input, review and professional approval requirements still apply.
Call `check_legal_tax_model` with `action: prepare`, the existing
`client_engagement`, `output_dir`, `run_id`, `workflow_id`, `host` and current
`session_ref`. `preferred_model` and `selection_basis` are optional advice.
Include `observed_model` and `observation_reference` only with actual host
evidence. Valid records always return `can_continue: true`; continue immediately.
The optional panel shows provenance and advice, with no required confirmation.

Cowork and hosts without UI use the same optional MCP record or the managed
Python launcher with `<prompt-optimizer>/scripts/model_policy.py --request
<request.json>`. Missing UI or model metadata never stops substantive work.
The legacy `confirm` action records an actual voluntary user statement only;
it is never necessary to proceed and never proves a host model switch.

## Resume and model changes

Read the existing record with `action: read`; old `requires_switch` and
`awaiting_confirmation` statuses are historical evidence and never block work.
The response always declares advisory enforcement and permits continuation.
Read leaves saved bytes intact, including finished runs. The next prepare or
phase write upgrades the record and preserves its previous version. Resume the existing run and substantive materials.
Refresh `prepare` when advice or host/session evidence changes; retain phase
history. Record actual stages with `action: phase`, `expected_sha256`, current
`session_ref`, phase and `execution_reference`. Include `model` only if known
and `observation_reference` when host-reported. A changed or unknown model or
session is accepted; evidence from a prior session is not claimed for the new one.
Stale writes still require reloading the latest digest to protect saved work.

Carry the advisory preference and truthful provenance into downstream reports.
If delegation is authorized, prefer the recommended model when available; a
different or unexposed worker model never blocks the workflow. Record available
evidence without claiming verification. Normal quality and professional review
requirements remain in force regardless of model identity.
