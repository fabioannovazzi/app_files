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
- `luciaArchivePanel`: Local Studio Archive client and practice browser. Uses the same local runtime as Lucia chat; browsing labels stay in app-only metadata, and an explicit button sends selected stable IDs to a new host chat when supported.
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
The three shipped helpers below read no credentials or settings from the user's process environment. Internal session/task UUIDs, host and private storage locations are passed explicitly by the plugin's own server; they are not user secrets and require no `userConfig` entries.

1. **`scripts/_python_bootstrap.py`** downloads the pinned uv 0.12.10 wheel from `https://files.pythonhosted.org` and verifies SHA-256 before execution. It launches uv with normal inherited environment, so corporate proxies and CA configuration keep working, without enumerating or copying environment values. Private cache and Python installation locations are command-line arguments. This uv version has no `--bin-dir` option; `--no-bin` prevents global executable links and `--no-registry` prevents Windows registration. The helper locates the resulting private interpreter and checks CPython 3.12 capabilities. uv itself downloads CPython from Astral's `python-build-standalone` GitHub releases; inherited proxy configuration may include proxy authentication. Neither absence of inherited credentials nor a PyPI-only destination boundary is claimed for uv.
2. **`scripts/notarized_run_receipt.py`** reads the local report, plugin version and saved receipt request; it reads no installation key or signing secret from the environment. Production posts only schema/product/version, a random receipt UUID and report SHA-256 to the fixed `https://mparanza.com/api/lucia/run-receipts` endpoint. The report, client documents, case text and file names are not request fields. Explicit test parameters permit a validated loopback endpoint or local-only operation; there is no environment endpoint override. Redirects are rejected.
3. **`scripts/operational_incidents.py`** receives internal settings through `configure_settings` or an explicitly selected JSON settings file (`--settings`). The native server supplies the same settings to its Python bridge; fixed recovery helpers receive them as arguments. UUID and private-path validation remain in place. Recovery subprocesses inherit their environment normally without copying environment keys.
   Generated installation ID/key remain in `~/.mparanza/lucia/incidents/<host>/state.json`; native device ID/key remain in `~/.mparanza/vera/host-identity/identity.json`, shared across products. Explicit storage settings support isolated tests. Linux Cowork guests do not read a native device key.
   Production requests go only to operations beneath the fixed `https://mparanza.com/api/operational-incidents` endpoint; redirects are rejected. Installation/device proofs authenticate technical incident, workflow and recovery reporting. These are Mparanza-generated identities for its own service, not user or third-party credentials. Client documents, case text and unreviewed logs are not diagnostic inputs.
4. **`.claude-plugin/plugin.json`** contains plugin metadata and a skills path, with no credential values or executable command. Local server declarations are in `.mcp.json`. No user-supplied endpoint or secret is introduced; internal settings are not exposed as `userConfig`.

The Python helpers' direct network destinations are the fixed Mparanza endpoints and `files.pythonhosted.org` for pinned uv wheels. The separate uv-managed CPython download and normal proxy/CA inheritance are described above.


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
