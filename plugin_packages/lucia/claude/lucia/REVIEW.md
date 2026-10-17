# Directory reviewer notes: lucia

## MCP servers
These servers run locally over stdio, exchanging data with local files and
helper processes on the user's machine.

- `luciaAssuranceRuntime`: Expose the limited local archive tools used by Lucia assurance.
- `luciaDeepResearchValidator`: Review sourced legal answers and research evidence.
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
