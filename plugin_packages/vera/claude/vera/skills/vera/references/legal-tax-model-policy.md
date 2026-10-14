> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Model requirement for Vera's legal and tax pipeline

Use the most capable model available in the user's current host/account for
preparation, research, drafting, validation, the opposing opinion when required,
and final revision. This applies only to this pipeline, including directly
invoked stages. Do not choose cheaper/faster models or weaker delegated agents.
Keep the existing host, model account, tools and case boundaries. Do not add a
model API, request model-provider credentials or transfer work to another model
account. Authorized research-subscription access follows its separate policy.

## Before substantive preparation

1. Resolve the preferred exact model identifier from the current host's exposed
   model catalogue/capability descriptions and availability. If these are not
   exposed, use current official provider documentation together with the
   user's available model selector. Never guess your own identity, sort model
   names/versions, equate recency with capability, or silently treat the current
   model as the strongest. The capability choice is a reasoned judgment; the
   helper only compares exact identities. Record the actual basis. If neither
   source is available, ask the user to select the most capable model available
   in that host and provide its displayed name. Do not hard-code a stale model.
2. Read the active model from actual host metadata when available. Otherwise
   leave it unknown. A model naming itself is not host evidence. Use the current
   conversation identifier as `session_ref`; if unavailable, create a local
   session label and explicitly record that it is not a host identifier. Do
   not reuse that label across a new conversation or resumed unknown session.
3. Prepare/start the normal `prompt-optimizer` managed or standalone run using
   the existing mechanical intake. This creates storage, not a substantive
   answer. Keep that run open until the pipeline's model record is complete.
   For a direct review or research stage, the existing running
   `deep-research-validator` context can own the same record.
4. Call `check_legal_tax_model` with `action: prepare`, the exact
   `client_engagement`, `output_dir`, `run_id`, `workflow_id`, `host`,
   `preferred_model`, `selection_basis`, `session_ref` and output `language`.
   Include `observed_model` and `observation_reference` only with actual host
   evidence. The result persists `legal_tax_model.json`. Where the plugin UI is
   supported it shows the required/active model and an explicit confirmation.
5. If `can_continue` is true, proceed without asking for a ceremonial click.
   Otherwise ask the user to select the required model using the host's own
   selector. The plugin does not switch the chat model. Confirm in the panel
   or through the chat fallback below. Wait for the actual answer; an inferred
   preference, preselected checkbox, timeout or silence is not confirmation.
   A confirmed selection is labelled `user_confirmed`, never host-verified.
   If the preferred model is unavailable, explain the limitation and refresh
   the preference from the actual available choices. No silent substitution.

## Cowork and all hosts without a plugin UI

The UI is optional. In Cowork use chat immediately; do not attempt to enable
Claude UI, install an app or require a browser. State the required model and,
only when actual host evidence is absent or differs, ask one concise question:
"Select [model] in the model selector and confirm when it is selected."
Reuse an explicit confirmation already supplied for this same session/run.

If the MCP tools are available without rendering, use them. Otherwise resolve
the prompt-optimizer module and run its Python helper through the existing
managed Python launcher:

```text
python <prompt-optimizer>/scripts/model_policy.py --request <request.json>
```

Prepare requests use the same fields as the MCP tool. To persist the user's
actual reply, send `action: confirm` with the same context/output/run/workflow,
`session_ref`, the returned `expected_sha256`, `confirmed_model`,
`confirmation_source: chat` and `confirmation_reference` quoting or locating
the user's reply. With MCP, `confirm_legal_tax_model` takes the returned token,
SHA-256, confirmed model, confirmation source and reference. Never fabricate
a reply or save a UI confirmation from the agent merely to clear the check.

If local tools are entirely unavailable, retain the identical fields visibly
in the conversation and continue after the same host evidence or real user
confirmation. State that durable storage is unavailable. Missing UI alone
never blocks the workflow or weakens the model requirement.

## Across stages and delegated work

Read the same record (`action: read`) before every stage. Preserve its required
model throughout the existing research/validation loop. Check available host
metadata again after a model/session change, resumption or handoff; refresh the
check when identity is unknown in a new session. Do not repeat confirmation in
an unchanged session. An existing confirmation does not cover another worker.

If delegation is authorized, request the exact required model explicitly when
the host permits it; otherwise verify inheritance from that model. If neither
can be established, perform the stage in the already confirmed parent session.
Do not silently launch a weaker worker or claim a worker's identity from prose.

Record each actual stage with `action: phase`, the owning context/output/run,
`session_ref`, current `expected_sha256`, `phase`, exact `model` and an
`execution_reference` to the actual assignment or host invocation. Allowed
phases are `preparation`, `research`, `drafting`, `validation`,
`opposing_opinion`, `revision`. The helper rejects a different model, stale
revision or changed session. Identity labels describe the evidence available,
not provider attestation or proof that the model is universally best.

Carry the requirement and record location into the answer contract, research
record and any reviewer/worker instructions. Preserve the model record and its
history as run artifacts. At final delivery record only stages actually run,
then complete the owning run through its existing lifecycle. This policy adds
no research mode, new opinion requirement or benchmark matrix.
