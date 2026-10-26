# Directory reviewer notes: clara

## MCP servers
These servers run locally over stdio, exchanging data with local files and
helper processes on the user's machine.
The local reporting service sends ordinary HTTPS to Mparanza for technical
incidents, task events, receipt signatures and user-authored feedback.
Independent browser recovery uses https://mparanza.com/clara/incident-recovery.
It is operated by the agent when the host permits browser control. Reporting
credentials authenticate requests; they are never diagnostic content.
Reporting uses HTTPS; the former remote MCP and OAuth endpoints are retired.
Original local credentials can restore the browser reporting owner.
Client documents, professional output and unreviewed logs are not reporting inputs.
Privacy policy: https://mparanza.com/privacy.

- `clara`: Expose the packaged Clara tool catalogue and start only the service owning a requested tool, resource or prompt. Close used services with the host connection.
- `claraIncidentHost`: Preserve local installation/host identity and deliver incidents, task events and signed receipt requests through ordinary HTTPS.

## Lesson downloads
Lesson data is fetched when the user starts or resumes a lesson, not installation.
Only data attachments, not helper code, are downloaded from
https://mparanza.com/static/shared/courses/clara/.
Each attachment must match the SHA-256 in assets/courses/remote.json and its
course manifest. Downloads are written to a temporary file; only verified bytes
are moved to the lesson destination. The cap is 25 MiB per file. HTTPS, the exact
mparanza.com host and the course path are checked, including every redirect.

## Local review tokens (flagged as "Uses a credential")
This Cowork package has no `review_server.py` or `X-Mparanza-Review-Token` bridge. Its packaged analysis widgets do not use that header or `persistence_token`.
The applicable local preview files are `modules/reporting-engine/scripts/budget_report_preview.py` and `modules/management-control-pack/scripts/preview_report.py`. Each creates a random URL path with `secrets.token_urlsafe(24)` at startup, serves it only on `127.0.0.1`, and loses the in-memory route when the server session ends. These are not user credentials, are not read from the user's environment or files, and are not sent to remote hosts by the preview servers.
`.claude-plugin/plugin.json` contains plugin metadata, not these tokens or user credential values.
The Python installer (`scripts/_python_bootstrap.py`) gives `uv` only an allowlisted environment: host paths, locale, proxy and CA settings, with private `UV_PYTHON_*` / `UV_CACHE_DIR` overrides; no inherited token or API-key variables.

## Font references (UNREAD_ASSET_REFERENCED)
- `execution-files.json`: Records font SHA-256 hashes for package integrity, not execution.

Fonts are typography data; none of these references executes a font as code.

## Package size
The package contains 13 top-level workflow/router skills and their
supporting methods, helpers and document/widget assets. This accounts for its
size; a scanner timeout does not establish that validation completed.

Contact: [fabio@mparanza.com](mailto:fabio@mparanza.com).
