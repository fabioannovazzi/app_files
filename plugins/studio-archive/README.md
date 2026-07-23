# Vera · Archivio dello Studio

This Vera component makes one shared studio folder searchable without requiring
a shared ChatGPT account or a central database.

Fabio and Paolo each configure the same shared or synced source folder from
their own Vera installation in local Codex. Each computer builds its own
derived SQLite FTS5 index under `~/.mparanza/vera-studio-archive`; the database,
configuration, and ChatGPT history are not shared. Source documents remain in
the studio folder and are never modified. ChatGPT web alone cannot index a
local folder or run this local MCP server.

If two professionals use the same operating-system account on one computer,
they must start Codex with different absolute
`VERA_STUDIO_ARCHIVE_STATE_DIR` values. Different ChatGPT licences do not by
themselves separate files stored under the same operating-system home
directory.

This first version deliberately uses local lexical full-text search rather than
embeddings or a vector database. Codex supplies semantic judgement by issuing a
few compact query variants, reviewing candidates, opening the useful passages,
and citing only sources whose current SHA-256 still matches the indexed file.
Every refresh hashes each supported source, re-extracts only changed content,
removes deleted content, adopts new top-level scopes, and reports skipped or
partially extracted material.

Supported sources are PDF, DOCX, XLSX, EML, TXT, Markdown, CSV, JSON, XML, PNG,
JPEG, and TIFF. PDF, DOCX, XLSX, and plain-text extraction require:

```bash
python -m pip install -r requirements.txt
python scripts/check_dependencies.py
```

Scans can use Vera's existing local OCR runtime. OCR is opt-in for refreshes and
never downloads model weights:

```bash
python -m pip install -r requirements-ocr.txt
python scripts/check_dependencies.py --requirements requirements-ocr.txt
```

The normal Codex path is the MCP server. A direct CLI fallback is also
available:

```bash
python scripts/studio_archive.py configure --archive-root /absolute/path/to/Studio
python scripts/studio_archive.py refresh
python scripts/studio_archive.py status
python scripts/studio_archive.py search --scope-id scope_... --query "cessione quote"
python scripts/studio_archive.py open --source-id src_...
```

Set `VERA_STUDIO_ARCHIVE_STATE_DIR` to an absolute private directory only when
the default state location is unsuitable. Never put that directory inside the
shared archive, a Git repository, or a cloud-synced folder. The derived index
contains extracted document text and is not application-encrypted; protect it
with a private operating-system account, full-disk encryption, and an
appropriate backup policy.
