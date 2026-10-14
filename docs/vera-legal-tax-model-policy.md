# Vera legal/tax model selection

Vera's legal/tax entrypoint and each directly invoked stage require the most
capable model available in the current host/account. The requirement covers
preparation, research, drafting, validation, any required opposing examination
and revision. Other Vera workflows are unchanged.

The assistant resolves the preferred model from current host capability and
availability evidence. Local code compares exact identities; it does not rank
model names, call a model API or switch the host's model.

The optional panel shows the required and active model. Matching host metadata
allows work to continue immediately. Otherwise the user selects the model in
the host and confirms in the panel or chat. Host-reported, user-confirmed and
unknown identity remain distinct.

Cowork requires no panel. It uses the same MCP tools when callable, or
`modules/prompt-optimizer/scripts/model_policy.py --request <request.json>`
through its managed Python launcher. The JSON request contains the existing
run context, output directory and run identity. The helper validates these
before writing `legal_tax_model.json`. The complete field contract and
conversation-only fallback are in
`plugins/vera/skills/vera/references/legal-tax-model-policy.md`.

Confirmation and phase writes require the current record digest and session.
Different model assignments, stale screens and foreign run/output references
are rejected. Prior record revisions remain local. An unchanged session reuses
its confirmation; a new session or changed model requires a fresh check.
Delegation requires an explicit matching model or evidenced inheritance.

This is a selection and continuity check, not provider attestation. User
confirmation cannot prove the model that executed a token. Missing host
controls cannot be supplied by a plugin. The policy therefore waits for a real
selection where necessary, rather than silently using a weaker model.

Validation includes real managed and standalone contexts, the no-UI command
line path, persistent MCP confirmation, stale/downgrade/session rejection,
desktop/mobile browser rendering and package/source parity. Installed Codex
and Cowork acceptance must be established separately after updating each host.
