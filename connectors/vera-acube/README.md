# A-Cube invoice downloads for Vera

A separate, optional Codex MCP connection for a studio using A-Cube. It starts the published [Cipay MCP server](https://github.com/nick-preda/mcp-server-acube) locally over stdio. Vera exposes four tools for invoice retrieval. The connector starts in sandbox mode by default. The ordinary Agenzia browser worker remains available independently.

## Connect on a development workstation

From a checkout with Vera's configured Python environment (`.venv`), Node 20+ and pnpm:

```sh
cd connectors/vera-acube
pnpm install --frozen-lockfile --ignore-scripts
codex mcp add vera_acube -- "$(command -v node)" "$PWD/server.mjs" --sandbox
codex mcp get vera_acube --json
```

In a fresh Codex chat, ask **“Controlla la connessione MCP A-Cube di Vera.”** `connection_status` verifies upstream tool discovery locally. It works before creating an A-Cube account and deliberately reports `provider_login: not_tested`.

## Connect an A-Cube account

Create an A-Cube sandbox account and configure a test company (Business Registry Configuration). In the `Vera` 1Password vault, save a Login item named `A-Cube sandbox`, with the provider email in **username** and its password in **password**. Enable desktop integration for the [1Password CLI](https://developer.1password.com/docs/cli/app-integration/) and make `op` available in the MCP host's PATH. The first provider tool call reads only those fields locally. The browser extension alone cannot supply a background process with these values. A secret manager may instead inject `ACUBE_EMAIL` and `ACUBE_PASSWORD` into the connector process. Keep both out of chat, command arguments and repository files.

For an authorized production account, register a separate connection with `--production` and a separate `A-Cube production` vault item. The production one-time request can incur provider charges. The server mode is fixed at startup.

## Retrieve invoices

1. `request_invoice_download` takes the configured fiscal ID and ISO dates. Production submits a one-time request through `download_invoices_once`. Acceptance means the job was submitted. Check its completion in the A-Cube dashboard before reporting the population as complete. An interrupted submission can have an unknown outcome. Check the dashboard before submitting it again.
2. In sandbox the published MCP lacks the simulator tool. For that call only, Vera uses the package's own authenticated API client to call the provider's documented simulation endpoint. A-Cube documents five synthetic outgoing and five incoming invoices. [Sandbox documentation](https://docs.acubeapi.com/documentation/italy/gov-it/sandbox/sim-invoice-download)
3. `list_invoice_references` takes the same client and dates, plus `incoming` or `outgoing`. It checks the selected party and invoice date before returning UUIDs. Continue with `next_page` until it is null. The list is a snapshot of available matching invoices, not a receipt for a particular job.
4. `archive_invoice_xml` takes a listed UUID, fiscal ID, direction and exact open Archive engagement ID. The worker retrieves the XML through `get_invoice`, verifies the selected party in the FatturaPA header, resolves the registered Archive client by tax ID, then uses Vera's ordinary document importer. Identical content reuses its receipt. The result contains a local path, input ID and SHA-256. The artifact is the UTF-8 XML representation supplied by A-Cube. This route does not retrieve the signed P7M envelope.

Production uses the local Studio Archive configuration. Sandbox uses a **separate** Archive configuration at `~/.vera-acube/sandbox` (`VERA_ACUBE_SANDBOX_HOME` overrides the location). Before the first sandbox import, configure a dedicated synthetic Archive root, client and engagement. For example, from the repository root:

```sh
source .venv/bin/activate
(
  export VERA_STUDIO_ARCHIVE_STATE_DIR="$HOME/.vera-acube/sandbox/state"
  export VERA_STUDIO_ARCHIVE_PROFILE_DIR="$HOME/.vera-acube/sandbox/profile"
  archive=plugins/studio-archive/scripts/studio_archive.py
  mkdir -p "$HOME/.vera-acube/sandbox/Studio"
  python "$archive" configure --archive-root "$HOME/.vera-acube/sandbox/Studio"
  python "$archive" create-client --legal-name 'A-Cube Sandbox' --tax-identifier TEST_COMPANY_FISCAL_ID
  python "$archive" create-engagement --client-id RETURNED_CLIENT_ID --engagement-label 'A-Cube Sandbox'
)
```

Use the fiscal ID actually configured on the provider's sandbox and the ID returned by `create-client`. Set `VERA_ACUBE_PYTHON` in the connector process to use a different prepared Vera Python runtime.

## Data visible to the model

Tool arguments contain the fiscal ID, dates, direction and selected document/engagement references. Results contain counts, status, UUIDs and the local Archive receipt (the path may include a client name). Login details, provider error bodies and invoice XML stay inside local processes. A-Cube itself receives the API requests and processes the documents.

## Verification

Run `node --test connectors/vera-acube/test/connection.test.mjs` from the repository root after installing dependencies. The test starts the actual upstream package, checks its tools, and exercises request, listing and Archive import with synthetic provider responses. It does not log into A-Cube.
