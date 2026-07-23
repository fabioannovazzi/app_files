# Vera · Archivio dello Studio

This Vera component makes one shared studio folder searchable without requiring
a shared ChatGPT account or a central database. It can also search one selected
client's Gmail correspondence on demand through the user's connected Codex
Gmail connector.

Fabio and Paolo each configure the same shared or synced source folder from
their own Vera installation in local Codex. Each computer builds its own
derived SQLite FTS5 index under `~/.mparanza/vera-studio-archive`; the database,
configuration, and ChatGPT history are not shared. Source documents remain in
the studio folder and are never modified. ChatGPT web alone cannot index a
local folder or run this local MCP server.

Gmail messages remain in Gmail. Vera stores no Gmail credentials, tokens,
message bodies, attachments, or local mailbox copy. A private
`client-identities.json` maps exact archive scopes to confirmed full email or
PEC addresses, legal names, and tax identifiers. Each professional keeps their
own registry and connects their own Gmail account.

For a Gmail question, Vera first selects one exact client scope, builds bounded
Gmail-native queries, searches with the Codex Gmail connector, and checks every
shortlisted message against confirmed full addresses. One unique address match
with complete From, To, Cc, and Bcc coverage may route automatically.
Legal-name matches, incomplete headers, third-party correspondence, and
messages involving multiple clients remain candidates for model review or are
left unassigned. Vera never labels, moves, sends, deletes, or bulk-copies mail.

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

Supported local sources are PDF, DOCX, XLSX, EML, TXT, Markdown, CSV, JSON,
XML, PNG, JPEG, and TIFF. PDF, DOCX, XLSX, and plain-text extraction require:

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
python scripts/studio_archive.py configure-client --scope-id scope_... \
  --email-address amministrazione@example.com --legal-name "Esempio SRL"
python scripts/studio_archive.py plan-gmail --scope-id scope_... \
  --topic "rateazione INPS"
python scripts/studio_archive.py match-email --expected-scope-id scope_... \
  --headers-complete \
  --header-address "Esempio SRL <amministrazione@example.com>"
```

The CLI does not call Gmail. Codex executes the returned query plan with the
connected Gmail search/read tools. This is active-task retrieval, not
background mail synchronization. It covers Gmail only; Outlook or PEC mailboxes
require a separate compatible connector unless their messages are available in
the selected Gmail account.

After a client folder rename, refresh the archive, run `clients`, and explicitly
rebind the listed orphaned profile to the new scope. Vera never guesses this
mapping.

Set `VERA_STUDIO_ARCHIVE_STATE_DIR` to an absolute private directory only when
the default state location is unsuitable. Never put that directory inside the
shared archive, a Git repository, or a cloud-synced folder. The derived index
contains extracted document text and is not application-encrypted; protect it
with a private operating-system account, full-disk encryption, and an
appropriate backup policy.
