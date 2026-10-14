# Existing tax matters and studio formats

This optional Codex panel reads and revises existing public case/profile outputs. It does not create a matter, infer professional authority or discover private folders. Prepare the ordinary specialist workflow first.

The owned local MCP service must receive `VERA_PRACTICE_WORKSPACE_BINDINGS`, the absolute path to an operator-owned JSON configuration outside Git. Its `tenant_id` and `actor_id` must exactly match the service environment. A reviewer service also requires the existing `VERA_WORKSPACE_ROLES=REVIEWER` role. Logical declarations are not identity authentication. The user must authorize the exact case/workspace connection; do not guess folders or manufacture approval.

Configuration shape (replace placeholders with the authorized existing paths):

```json
{
  "tenant_id": "actual-service-tenant",
  "actor_id": "actual-service-actor",
  "bindings": [
    {"work_ref": "tax-case", "kind": "tax", "run_dir": "/absolute/private/tax-matter"},
    {"work_ref": "studio-format", "kind": "format", "workspace": "/absolute/private/communications-workspace", "review_id": "existing-preview-review"}
  ]
}
```

Use only the rows actually requested. Tax requires the public `matter.json` with kind `contenzioso-tributario` and its registered source pack. Format requires an existing public workspace and review with both generated Word previews. The service rechecks complete identities and hashes on every read/write. Set the environment through supported MCP configuration, reconnect the service and use a fresh conversation when its tool catalog changed. Never modify generated plugin caches.

`vera_workspace_practice_catalogue` opens the maintained panel. Select the connected practice in **Pratiche e formato documenti**. If no binding is available, the panel says so; use the ordinary specialist file workflow until the operator connects the exact case.

A saved tax calendar is versioned with the matter. Actual event and deadline meanings remain model/professional judgments supported by current research; shape/date/citation checks cannot establish legal correctness. Unsaved edits must be conserved or explicitly discarded before navigation or discussion.

Format preparation creates a new private review and both previews, while adoption is separate. The exact proposal, source samples/logo, previews and current profile are checked before adoption. Open both Word files and complete visual inspection; a path or chat-request receipt alone is insufficient.

Only an explicit saved-item discussion sends the chosen tax item with its cited source units, selected format settings or selected preview identity/path to the host model. Private navigation does not send the whole case or original sample documents. Changed revisions are refused. Interrupted writes retain intent and require inspection before repetition. No Marketplace publication, filing, notification, external calendar write or Archive completion occurs.
