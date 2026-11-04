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

## Local review tokens (flagged as "Uses a credential")
The native editors in `scripts/method_mcp.py` and `scripts/matter_mcp.py` create `secrets.token_urlsafe(32)` session references bound to the selected folder or matter and exact saved revision. They are kept in memory and passed through app-bound host tool calls; selected configuration and review evidence stay in app-only result metadata. These references are not user credentials and are not read from the user's environment or files. The editors do not start loopback HTTP review servers.
The validation engines retain opaque, exact-review references for explicit save/apply operations; those references may enter model context. The adapter in `scripts/review_engine_mcp.cjs` removes their retired inspector resources and render tools while preserving validation and professional confirmation requirements.
The flagged `.claude-plugin/plugin.json` contains plugin metadata, not session references or user credential values.
The Python installer (`scripts/_python_bootstrap.py`) gives `uv` only an allowlisted environment: host paths, locale, proxy and CA settings, with private `UV_PYTHON_*` / `UV_CACHE_DIR` overrides; no inherited token or API-key variables.

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
