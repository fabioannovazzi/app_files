# Directory reviewer notes: lucia

## MCP servers
These servers run locally over stdio with local files and helper processes.
The local reporting service sends HTTPS to Mparanza for technical incidents, task events, receipt signatures and user-authored feedback.
Independent browser recovery uses https://mparanza.com/lucia/incident-recovery.
It is operated by the agent when the host permits browser control. Reporting
credentials authenticate requests; they are never diagnostic content.
Reporting uses HTTPS; the former remote MCP and OAuth endpoints are retired.
Original local credentials can restore the browser reporting owner.
Client documents, professional output and unreviewed logs are not reporting inputs.
Privacy policy: https://mparanza.com/privacy.

- `lucia`: Expose the packaged Lucia tool catalogue and start only the service owning a requested tool, resource or prompt. Close used services with the host connection.
- `luciaDeepResearchValidator`: Review sourced legal answers and research evidence.
- `luciaFirmMethod`: Native firm-method form; validates and saves immutable versions only in the explicitly selected studio directory. Form data stays app-only until selected for a model workflow.
- `luciaIncidentHost`: Preserve local installation/host identity and deliver incidents, task events and signed receipt requests through ordinary HTTPS.
- `luciaMatterOpening`: Native selected-matter review; restores and saves pending lawyer decisions against exact intake/review versions. Saving does not apply them or accept an engagement.
- `luciaPromptOptimizer`: Review the legal answer plan.
- `luciaStudioArchive`: Manage registered local client folders and engagement records.

## Lesson downloads
Lesson data is fetched when the user starts or resumes a lesson, not installation.
Only data attachments, not helper code, are downloaded from
https://mparanza.com/static/shared/courses/lucia/.
Each attachment must match the SHA-256 in assets/courses/remote.json and its
course manifest. Downloads are written to a temporary file; only verified bytes
are moved to the lesson destination. The cap is 25 MiB per file. HTTPS, the exact
mparanza.com host and the course path are checked, including every redirect.

## Uses a credential from the user's machine: the 4 findings
1. **`scripts/_python_bootstrap.py`** reads an allowlist of host paths, locale, proxy, CA and cache settings for `uv`, with private `UV_PYTHON_*` / `UV_CACHE_DIR` overrides. It downloads pinned `uv` wheels from `https://files.pythonhosted.org`, checks SHA-256, and runs `uv` to install Python and declared dependencies. It does not pass inherited token or API-key variables or upload client documents. Proxy settings are passed through and may contain proxy authentication; the code does not guarantee that they contain no credentials.
2. **`scripts/notarized_run_receipt.py`** reads the local model-data report, plugin version and saved receipt request; it reads no installation key or signing secret. It posts only schema/product/version, a random receipt UUID and the report's SHA-256 to `https://mparanza.com/api/lucia/run-receipts`, Mparanza's own service, which signs the receipt server-side (Ed25519). The report, client documents, case text, file names and user secrets are not request fields. `LUCIA_RUN_RECEIPT_ENDPOINT` permits the same production URL or an explicit localhost/127.0.0.1 HTTP port with the same path for testing; redirects are rejected.
3. **`scripts/operational_incidents.py`** reads `MPARANZA_INCIDENT_HOST_SESSION`, `MPARANZA_INCIDENT_TASK_ID`, `MPARANZA_INCIDENT_HOST`, `MPARANZA_INCIDENT_DEVICE_DIR`, `MPARANZA_INCIDENT_STATE_DIR`, `MPARANZA_INCIDENT_DELIVERY`, and `CLAUDE_PLUGIN_ROOT`/`PLUGIN_ROOT` for session, task, host, storage and delivery configuration.
   Its generated installation ID/key are stored in `~/.mparanza/lucia/incidents/<host>/state.json` (or the state-directory override). Native device ID/key default to `~/.mparanza/vera/host-identity/identity.json`, shared across products; device-directory or state-directory overrides change this location. Linux Cowork guests do not read a native device key.
   Requests go only to operations beneath `https://mparanza.com/api/operational-incidents`, Mparanza's own service; redirects are rejected. Installation/device proofs authenticate technical incident, workflow and recovery reporting. Client documents, case text and user/third-party credentials are not diagnostic inputs; technical error text is redacted before reporting. The installation/device credentials themselves are sent to the vendor for authentication.
4. **`.claude-plugin/plugin.json`** contains plugin metadata and a skills path, with no credential values or executable command. The local MCP server declarations are in the separate `.mcp.json`; the manifest itself reads or sends no secret.

Reporting credentials are Mparanza's own generated installation/device identities for its own service; no user secret or third-party token is a reporting input, while installer proxy authentication remains the exception described above.


## Runtime download/execution findings (RUNTIME_FETCH_EXEC)
- `scripts/_python_bootstrap.py`: Separate setup downloads the pinned uv 0.12.10 wheel, verifies its SHA-256 before extraction/execution, then uses uv to provision CPython 3.12; retained as verified runtime setup.

## Font references (UNREAD_ASSET_REFERENCED)
- `modules/comunicazione-professionale/scripts/render_visuals.py`: Loads bundled Instrument Sans TTFs with Pillow/ReportLab for PNG/PDF text; fontTools checks glyph coverage.
- `modules/comunicazione-professionale/scripts/check_dependencies.py`: Checks that the three bundled TTF files exist.
- `modules/comunicazione-professionale/scripts/studio_document_format.py`: Reads/sets Word style font names and sizes; does not load TTF bytes.
- `modules/comunicazione-professionale/scripts/package_communications.py`: Names Instrument Sans in HTML CSS; does not load TTF bytes.

Fonts are typography data; none of these references executes a font as code.

## Package size
The package contains 25 top-level workflow/router skills and their
supporting methods, helpers and document/widget assets. This accounts for its
size; a scanner timeout does not establish that validation completed.

Contact: [fabio@mparanza.com](mailto:fabio@mparanza.com).
