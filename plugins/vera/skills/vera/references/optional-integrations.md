# Optional integrations

These connections are optional. Ordinary Vera work requires none of them.
For the shared product boundaries, see [Functions and limits of use](functions-and-limits.md).

## Local anonymization connectors

[Download the separate connector installer](https://mparanza.com/static/shared/vera-integrazioni/downloads/anonymization-connectors.zip).
[Setup and data handling](https://mparanza.com/static/shared/vera-integrazioni/index.html#connector-download).

The user chooses OpenAI Privacy Filter, GLiNER2-PII, Rizzo PII, Lethe or PII-Shield
(gregmos/PII-Shield). Mparanza does not currently recommend one engine. The
[engine comparison](https://mparanza.com/static/shared/vera-compliance/index.html#motori-anonimizzazione)
reports the authors' descriptions, not a Mparanza validation of professional
effectiveness. Do not rank,
choose, install or start an engine without the user's request. Vera's package
contains this guide, not their runtimes, model weights or automatic activation.
The separate download includes guided setup (`install.py --setup`) for Python
3.12 and generates Codex, Cowork and Antigravity connection files. Rizzo also
requires its own app installed and running on the same computer.

| Local desktop host | Setup result | User action |
| --- | --- | --- |
| Codex | `codex-mcp.toml` | Merge its one server section into the user's Codex configuration; preserve other settings and restart MCP. |
| Claude Cowork | `cowork-connector.zip` | Install this optional plugin in Customize → Plugins, enable it, and open a new local task. Run the installer on the host computer, not inside Cowork's Linux VM. |
| Google Antigravity | `antigravity-mcp.json` | Merge its entry into `mcpServers` in the app's raw configuration and reload MCP servers. |

The generated Cowork plugin contains the user's local installation paths.
Regenerate it on another computer. Local desktop setup does not establish
web/cloud availability, and an organization's settings may disable local MCP.

Check the selected engine's callable `*_status` tool and process a synthetic
file before claiming that host is connected. Pass a filename relative to the
configured input folder, not a Cowork `/sessions/...` VM path. Do not read or
attach originals in chat as part of the filtering workflow. The `*_file` and
`*_batch` tools save plain-text artifacts; `*_read` brings only the filtered
artifact into the conversation when requested. No layout or restoration
dictionary is returned to the conversation. Restoration depends on the engine:
Rizzo retains its own local map; Lethe reuses an approved identity set for a job;
PII-Shield supports a shared session across documents. Lethe and PII-Shield
provide the described cross-document placeholder paths. Their local maps are
not encrypted by Vera's adapters. See the setup guide for storage, cleanup and
host-specific limits. A timeout is not a completion receipt; check saved
outputs before retrying. Never substitute another engine or cloud processing.

Paths, counts and safe metadata enter the selected host's model context; filtered
text enters it when read. Detected values and original-text response fields are
excluded, but an engine can miss sensitive content. Review the local copy.
Do not represent a completed run as proof of anonymity. Rizzo's separately
running app retains control over its own model and network behavior.

## Second Brain and studio skills

No Second Brain installer is supplied or required by Vera. For an existing
repository, use its provider's connector and the
[integration guide](https://mparanza.com/static/shared/vera-integrazioni/index.html).
That guide covers Codex, Cowork and Antigravity configuration. The actual service
URL, authentication, account access and search/read tools must be verified in
the current app. Do not assume compatibility from a name or a successful test
in a different host. Follow `connected-studio-knowledge.md` before using retrieved
evidence. Studio skills stay independently installed and invoked.
