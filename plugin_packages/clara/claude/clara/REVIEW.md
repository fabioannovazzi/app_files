# Directory reviewer notes: clara

## MCP servers
This package declares no MCP servers (.mcp.json is absent).

## Lesson downloads
Lesson data is fetched when the user starts or resumes a lesson, not installation.
Only data attachments, not helper code, are downloaded from
https://mparanza.com/static/shared/courses/clara/.
Each attachment must match the SHA-256 in assets/courses/remote.json and its
course manifest. Downloads are written to a temporary file; only verified bytes
are moved to the lesson destination. The cap is 25 MiB per file. HTTPS, the exact
mparanza.com host and the course path are checked, including every redirect.

## Font references (UNREAD_ASSET_REFERENCED)
None of the listed scanner font-reference paths is present in this package.

Fonts are typography data; none of these references executes a font as code.

## Package size
The package contains 12 top-level workflow/router skills and their
supporting methods, helpers and document/widget assets. This accounts for its
size; a scanner timeout does not establish that validation completed.

Contact: [fabio@mparanza.com](mailto:fabio@mparanza.com).
