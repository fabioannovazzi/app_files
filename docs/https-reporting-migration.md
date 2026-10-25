# Product reporting without remote MCP

Vera 0.1.492, Clara 0.1.347 and Lucia 0.1.175 remove their product-specific
remote Incidents MCP registration. The existing local MCP tools remain. These
versions continue to use Mparanza for technical incidents, task usage and
signed receipt delivery through ordinary HTTPS.

Author-supplied public uploads omit the empty root app-binding file and app
declarations in compatibility manifests. Native distributions retain their
existing bindings. Both distributions retain the same local MCP servers.

## Operation mapping

| Former remote operation | Normal desktop route | Independent browser route |
| --- | --- | --- |
| incident register | local `<product>_incident_register` | `register` |
| incident report | local `<product>_incident_report` | `report` |
| incident status | local `<product>_incident_status` | `status` |
| incident progress | local `<product>_incident_progress` | `progress` |
| incident outcome | local `<product>_incident_outcome` | `outcome` |
| workflow record | existing local `<product>_workflow_usage` | `workflow-record` |
| workflow status | existing local `<product>_workflow_usage` | `workflow-status` |
| workflow stamp | local `<product>_workflow_stamp` | `workflow-stamp` |

The local tools use the retained private installation identity and ordinary
HTTP API envelopes. They do not forward MCP JSON-RPC to the service. Tool
arguments cannot override the reporter's credentials. Native requests retain
their exact payload before sending and validate the owner and request IDs in
acknowledgements. A definitive first schema rejection can be corrected; a lost
or ambiguous acknowledgement keeps the original payload immutable.

## Recovery and ownership

`https://mparanza.com/<product>/incident-recovery` is served independently of
the installed plugin. When local execution is unavailable, the agent uses
permitted host browser controls to operate it. The page exposes the eight
operations above and their product-specific JSON schemas. Browser access does
not override a host denial or grant missing computer-use capabilities.

The browser retains a Secure, HttpOnly, SameSite Strict capability. It can link
an original local capability and submit retained requests under their original
owner. A legacy OAuth-only owner can issue a five-minute, single-use transfer
code before retiring the connection. This preserves history without changing
record owners. Expired known sessions require explicit restoration; lost or
revoked credentials cannot be reconstructed. A browser owner is not evidence
of physical-computer identity.

The server keeps its legacy MCP/OAuth endpoints for older installed versions
and identity migration. The new packages do not register those endpoints.
Their presence on the server is not a dependency of the new HTTPS transport.

## Verification boundaries

The reporting regression gate covers the operation mapping, durable retries,
lost acknowledgements, product/owner binding, legacy transfer, recovery
progress/outcomes and signed receipts. The package regression inspects all
12 archives across Codex, ChatGPT upload, Cowork and Antigravity for remote
registrations and verifies the retained local reporter and operation schemas.
Cowork projects Vera's incident continuity instructions from the source skill
so a separate builder template cannot restore obsolete connector guidance.

A synthetic Codex browser exercise delivered a technical report after a
damaged local reporting helper was rejected and recovered the same report
after a server restart. This proves that exercised browser route only.
Fresh installed-conversation acceptance, other supported hosts' independent
browser capabilities, and deployment of the new public routes are separate
acceptance gates. Package tests do not establish those results. Marketplace
publication is outside this change.
