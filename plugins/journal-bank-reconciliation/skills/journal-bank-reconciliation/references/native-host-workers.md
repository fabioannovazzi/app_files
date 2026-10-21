# Cowork and Antigravity native reconciliation workers

The ordinary command prepares `native_host_request.json` when the packaged host
policy is Cowork or Antigravity. `NATIVE_WORKER_PENDING` is an internal handoff,
not a request for the user to copy JSON, select a model, or approve a draft.
Complete these steps automatically in the same parent conversation. Keep its
model unchanged. Do not open ordinary per-case chats or call a provider API.

1. Inspect the actual native tool schema and registered agent list in this
   session. Cowork uses `Agent`, `vera:reconciliation-reviewer`, model `haiku`,
   with the declared tool list `Read`. Antigravity uses `invoke_subagent`,
   `reconciliation-reviewer`, model tier `flash`, with an empty declared tool
   list. The request contains the exact tool parameters, including its entire
   bounded prompt and JSON schema. Confirm those capabilities are actually
   exposed before invoking it. A policy preference is not availability proof.
2. Spawn a new child with exactly `request.invocation.parameters`. Never use
   `fork`, `self`, a resumed child, another host, or the main chat as the worker.
   Do not add case files or conversation history. If the configured native
   type/model is unavailable, retain the prepared request and report the actual
   missing capability; continue delivering the unresolved draft.
3. Wait for completion. Cowork returns an agent ID, final text, tool-use count
   and usage. Antigravity returns a child conversation ID and completion
   notification; inspect that child's exact transcript from the returned log
   reference for tool activity. An invocation acknowledgement or idle state
   without the final response is insufficient. Do not count the parent's tools
   as child tools. Do not infer zero child tool calls from silence.
4. The parent writes `native_host_record.json` beside the request using this
   shape, replacing every placeholder from the actual invocation evidence:

```json
{
  "schema_version": "vera.native_host_worker_record.v1",
  "provenance": "parent_observed_native_tool",
  "request_sha256": "request.content_sha256",
  "invocation": {"tool": "actual tool", "parameters": {}},
  "capabilities": {
    "host": "cowork or antigravity",
    "tool": "actual tool",
    "agent": "actual registered agent type",
    "model_choices": ["actual tool schema model choices"],
    "declared_tools": [],
    "fresh_context": true,
    "runtime": "observed host/version or current session tool-schema identity"
  },
  "completion": {
    "invocation_id": "actual child ID",
    "status": "completed",
    "tool_uses": 0,
    "parent_history_inherited": false,
    "resumed": false,
    "response_text": "exact final JSON text returned by the child",
    "model_observed": null,
    "usage": {}
  }
}
```

Copy `invocation` exactly from the request after observing that actual call.
For Cowork, `declared_tools` is `["Read"]`; for Antigravity it is `[]`.
Keep `model_observed` null unless the host exposes it independently of model
prose. Record measured usage only; an unavailable metric is not zero. The child
must not write or certify its own invocation record.

5. Resume the identical original command and inputs. Open-item reconciliation
   consumes the records and regenerates its native results/workbooks. Journal–
   Bank `run-all` resumes the pending generation, validates its graph and native
   completion, applies the resolution funnel and archives the completed packet.
   Do not edit prepared assumptions to bypass a pending result. Invalid money,
   stale evidence, another request's response, tool use, or incomplete execution
   stays unresolved. Inspect the regenerated status before delivery.

These records are parent-observed host evidence. They do not attest provider
model identity, exclude host ambient instructions, or prove OS filesystem
isolation. `Read` is available to the Cowork agent, although a valid bounded run
must report zero tool calls. Antigravity's empty tool declaration is not a claim
that its CLI main-agent mode has no tools. Host-managed child transcripts may
persist. The parent necessarily reads the bounded request to dispatch it, so its
mapped business fields also enter the parent context on these two hosts. Keep
that exposure in the model-data report; do not describe it as anonymized or as
status-only. Codex retains its separate capability-probed capsule path.
