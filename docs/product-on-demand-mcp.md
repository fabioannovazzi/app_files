# On-demand local MCP services

Vera, Clara and Lucia each expose one public server in `.mcp.json`. The host
starts one entry process per product connection. Host discovery reads a bundled
catalogue; it does not start the specialist services. A host may create more than
one connection, so this is not a machine-wide singleton.

The host sees the individual tools and can select them from an ordinary request.
The user does not have to mention the product first. The host model interprets
the request; the entry matches an exact tool name, resource URI or prompt name to
its owner in `mcp-services.json`. Only that owner starts. Later calls reuse it,
including its in-memory review state. Concurrent first calls share one worker.

The entry forwards JSON-RPC arguments, responses, progress, cancellation and
server requests. It adds no model call or network recipient and does not replay
failed operations. Used services remain until their host connection closes.
Already accepted native jobs keep their existing separate lifetime policy.

All three packages embed the same transport from `plugins/vera/scripts/`:
`on_demand_mcp.cjs`, `mcp_service_client.cjs` and `verify_mcp_package.cjs`.
Clara and Lucia's source entries delegate to it; released packages are standalone
and need no sibling installation. Exact package verification runs in the entry
process without an update-protection companion or retained product snapshot.

`scripts/build_product_mcp_catalog.py` queries discovery from the exact projected
package services at build time. The catalogue includes the product identity,
version, tool schemas and UI metadata. The final execution index binds it to the
package. The packaged MCP check compares it with fresh backend discovery.

Codex and Cowork receive the same mechanism. Cowork's private service registry
continues to exclude the OpenAI-only `courseChats` service. This changes process
startup, not each host's supported professional workflows. Older installations
and already-open host connections keep their previous code until updated and
reopened.
