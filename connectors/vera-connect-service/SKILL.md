---
name: vera-connect-service
description: Use when a studio wants to connect, check or disconnect an external service for Vera in Codex Desktop. Includes the A-Cube invoice connector and user-specified authenticated remote MCP services.
---

# Collega un servizio

Confirm the named service and environment, its official endpoint or documented connector, and the operations the studio wants. Describe who receives data and any provider charge. Reuse an existing matching registration. A local package, MCP discovery, authentication, authorization for a client and a saved result are distinct observations.

## A-Cube

The packaged adapter supports sandbox and production separately. Its operations request one download, list scoped references, and save an individual XML to the matching local Studio Archive engagement. It never exposes upstream filing or subscription tools. Studio authorization and provider terms are separate from possessing an A-Cube login. The provider sandbox creates synthetic invoices; production requires the configured taxpayer and qualified access. Do not submit a paid job merely to test credentials.

Use the included setup_acube.py. Resolve the currently enabled Vera root from its exposed skill path (the root above skills/) and its prepared Python runtime; the operator should not have to find them. Check for Node 20+, pnpm and Codex CLI. Use the provider vault/item selected by the studio, or the supported secret environment separately. Never type a secret into a setup argument. Use python setup_acube.py --help for the exact arguments. Run setup only when requested. Register sandbox first unless production was specifically selected. If an existing registration differs, explain the difference before replacing it. The packaged acquisition guide is `connectors/vera-acube/README.md`. When the installed Vera root moves after an update, repeat setup with the current root.

In a fresh chat discover the connector and call connection_status. For an authenticated check use list_invoice_references for the chosen configured fiscal ID, date window and direction. Empty results can prove authentication, not availability of invoices. To test a full download, request it once, keep the job identity, and follow the included A-Cube README for list, pagination, Archive selection and receipts. Return counts, file references and exceptions. A-Cube sees the request and invoices; credentials and raw XML stay in the local processes. A later explicit inspection of a saved file is separate.

## Other services

For a known remote MCP, verify the official HTTPS endpoint, its authentication method and tool scope from provider documentation. Use the host’s supported registration and OAuth login where available. Verify with a read for the intended account. A remote MCP may send its tool results directly to the model. Describe its actual behavior before requesting sensitive data. If the provider has only an API, explain what adapter is missing; this skill does not synthesize a working integration by registering an API URL. For attended website login, use the independent 1Password skill when available.

To disconnect a named registration, verify its name and use codex mcp remove NAME. Provider consent, subscriptions, vault items and archived documents have separate lifecycles; explain relevant provider revocation steps.
