# Native workspace pilot

Private MCP Apps review surface over the existing Python case service. The
resource `ui://vera/bilancio-workspace-v5.html` is registered by the Bilancio
MCP server and its `xbrl_workspace_open` tool has both global and thread
entrypoints. No public listing or discovery metadata is changed.

The first writable slice is: existing case → finding → recorded or explicitly
selected source cell → explanation request → explicit reviewer decision →
authoritative revision. The remaining nine existing review contracts can be
browsed. Their editors, native preview, final approval and export controls are
not implemented in this pilot. Do not advertise them as a completed native UI.

## Local installation and identity

Use `scripts/build_vera_workspace_pilot.py <new-private-directory>` from the
repository's existing Python environment. It creates a private local
marketplace, a plugin containing the actual component sources, and a separate
fictional Studio Archive run. It never reads the user's configured archive.
Its `demo_reviewer` identity is only a test identity, not professional approval.
Use `--reuse-demo <original-pilot-directory>` when rebuilding to keep the same
fictional case and its saved decisions. `--version 0.0.<number>` selects a
private development build version; this does not change a product release.

Register with `codex plugin marketplace add <private-directory>` and install
`vera-workspace-pilot@vera-ui-private`. In a fresh supported desktop host,
open **Fascicoli Vera** from the plugin sidebar or conversation panel. Local
marketplace refresh/restart requirements are host-dependent. Installation is
not proof of rendering. Do not restart a host running other work without the
user’s agreement.

The existing service requires trusted local environment configuration:
`VERA_XBRL_STORAGE_ROOT`, `VERA_XBRL_TENANT_ID`, `VERA_XBRL_ACTOR_ID`,
`VERA_XBRL_ROLES`, and `VERA_XBRL_PYTHON`. Add
`VERA_XBRL_WORKSPACE_BINDINGS` pointing to an owner-configured JSON file:

```json
{
  "tenant_id": "the_existing_tenant",
  "actor_id": "the_authenticated_local_actor",
  "bindings": [{
    "case_id": "the_existing_case",
    "client_id": "client_000000000000000000000000",
    "client_root": "/owner-selected/client-folder",
    "engagement_id": "eng_000000000000000000000000",
    "run_id": "run_000000000000000000000000"
  }]
}
```

This is an explicit allowlist of links to existing objects, not another client
database. No names, balances or decisions are stored here. The owner must bind
the existing case to its actual client run; the model must not invent paths,
identity, roles or associations. The service storage root remains authoritative
for both existing conversation tools and the UI. The UI is disabled by default:
`VERA_XBRL_NATIVE_UI=1` adds it to existing tools; `VERA_XBRL_UI_ONLY=1` enables
only the four workspace tools in the private pilot. Never expose this local static
identity configuration as an authenticated multi-user HTTP endpoint.

## Review and context boundaries

- Catalogue and view payloads are in result `_meta`; only compact status is
  model-visible. Metadata is not an authorization or secret-storage boundary.
- Source documents have no semantic auto-linking. Missing direct source links
  are shown; a reviewer can deliberately choose a parsed source cell to discuss.
- Explanation uses the existing bounded issue packet. It neither applies model
  suggestions nor records a model answer as an accepted decision.
- A decision requires an app-only tool, a signed short-lived ticket, the host's
  reviewer role, a running Archive run, an explicit checkbox, the exact revision
  and a persistent idempotency key. This depends on host-enforced app-only tool
  visibility; it is not remote human-identity attestation.
- The domain service invalidates dependent review material on edits. The UI
  shows validation freshness and saved decisions; it does not silently validate,
  approve accounts, export or file anything.
- Unsaved notes block navigation until saved or discarded. Saved work lives in
  the case, not browser storage. Closing the frame discards an unsaved note.
- This pilot sends a readable request with exact case, finding, revision and
  optional source references as an explicit `ui/message`. It sends no JSON,
  evidence packet, hashes or background attachment in that message. The new
  chat must retrieve the selection through `xbrl_workspace_explain`; that read
  checks authorization and rejects a changed revision before returning the
  existing bounded context and hash. Every explanation requests a new
  chat because the panel cannot verify the current conversation's client history.
  Without the new-chat capability it is blocked. Native acceptance must still
  test both actual new-chat behavior and the model's exact selection read before
  real-client use. No raw-case fallback is permitted if that read is unavailable.
- The observed desktop host displayed assistant-audience text in the send
  confirmation. The message therefore does not depend on audience annotations
  or content titles to hide structured data.
  Sending waits up to five minutes for the host confirmation rather than failing
  after the ordinary service-call timeout while a person reads the dialog.

## Verification and delivery route

The focused suite is `tests/plugins/test_bilancio_native_workspace.py`.
`scripts/serve_vera_workspace_pilot.cjs <private-directory>` supplies a loopback
protocol test host over the real MCP process. It advertises no chat capability,
disables the conversation button and rejects message requests rather than
simulating delivery. Opening, reading and saving use the fictional case service.
A successful browser test cannot satisfy native-host acceptance.

Required native acceptance: fresh installation, visible global/thread entry,
rendered case, exact evidence explanation in a real conversation, human save,
reload, two-client separation (including remount), authorization failure and
missing configuration/runtime behavior. Until those pass, keep this private.

Official references (inspected 2026-10-01):

- https://developers.openai.com/plugins/build/extensions
- https://developers.openai.com/plugins/build/chatgpt-ui
- https://developers.openai.com/plugins/build/mcp-server
- https://developers.openai.com/plugins/deploy/connect-chatgpt
- https://developers.openai.com/plugins/deploy/submission
- https://github.com/openai/mcp-extensions/blob/main/docs/spec.md

The submission documentation requires a stable public HTTPS endpoint and says
an existing skills-only listing cannot currently add MCP. The private desktop
pilot does not resolve either public-distribution requirement. No second public
listing, hosted client archive or tunnel is created.

## Quali dati arrivano al modello

Aprendo il pannello, il modello riceve soltanto conteggi o identificativi e
stato della revisione; il catalogo e le pagine di revisione servono alla UI.
Con «Discuti in una nuova chat» vengono inviati il titolo del rilievo, la data
del bilancio e i riferimenti esatti di fascicolo, rilievo, revisione ed eventuale
cella scelta. La chat legge poi quel solo rilievo mediante il servizio Vera,
che verifica accesso e revisione, e riceve le fonti collegate: valore originale,
coordinate, nome e hash del documento quando presenti. Non viene allegato
automaticamente il fascicolo completo. Il messaggio usa il modello e l'account
OpenAI dell'host: l'elaborazione del modello non è locale e i dati non sono
anonimizzati automaticamente. Le decisioni sono salvate nel servizio Python
locale; il test browser separato usa soltanto dati fittizi e non chiama modelli.
