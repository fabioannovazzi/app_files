# Vera · Archivio dello Studio

This Vera component has three independent routes. It searches one selected
client's Gmail correspondence in ChatGPT or Codex through the separately
connected OpenAI Gmail connector. Codex Desktop additionally inspects one
verified one-to-one chat in the local WhatsApp application through Computer Use
or makes one shared studio folder searchable without a shared ChatGPT account
or central database.

Fabio and Paolo each configure the same shared or synced source folder from
their own Vera installation in Codex Desktop. Each computer builds its own
derived SQLite FTS5 index under `~/.mparanza/vera-studio-archive`; the database,
configuration, and ChatGPT history are not shared. Source documents remain in
the studio folder and are never modified.

Gmail messages remain in Gmail. Vera stores no Gmail credentials, tokens,
message bodies, attachments, or local mailbox copy. Confirmed addresses remain
in the current task and may need confirmation again in a new task. Local Codex
can optionally persist a private
`client-identities.json` that maps exact archive scopes to confirmed full email
or PEC addresses, legal names, and tax identifiers.

WhatsApp remains in the user's already-authenticated local application and
WhatsApp account. Computer Use verifies one exact client phone and inspects only
the visible messages needed for the task. Vera never types in the composer,
sends, replies, forwards, downloads, exports, or changes settings. There is no
Mparanza WhatsApp webhook, connector, database, background synchronization, or
retention period. Opening a chat may mark messages as read.

For a Gmail question, Vera first verifies the connected account, selects one
client, and either uses an address supplied by the user or runs a bounded
candidate search and asks for one address confirmation. It then searches again
using only the confirmed address and checks the full shortlisted messages. One
unique address match with a parseable sender and returned recipient fields may
route automatically. Vera inspects Cc and Bcc when Gmail exposes them; absence
of an optional Bcc field alone is not treated as an error, and Vera states that
it cannot detect an undisclosed Bcc recipient. Legal-name matches, malformed
headers, third-party correspondence, and messages involving multiple clients
remain candidates for model review or are left unassigned. Vera never labels,
moves, sends, deletes, or bulk-copies mail.

The Codex Desktop Gmail route uses only `get_profile`, `search_emails`,
`batch_read_email`, `read_email_thread`, and `read_attachment` from the Gmail
plugin. It never calls Studio Archive MCP tools or local scripts.

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
