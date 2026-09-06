# Vera · Archivio dello Studio

This Vera component owns the portable customer-folder ledger used by local
Codex workflows. It has four independent routes. In ChatGPT or Codex,
the separately connected OpenAI Gmail connector searches one selected client's
correspondence. Codex Desktop can additionally inspect one verified one-to-one
chat in the local WhatsApp application through Computer Use, make one shared
studio folder searchable without a shared ChatGPT account or central database,
or bind one client to a My Drive or Shared Drive folder for native Drive
snapshots and transient evidence opening.

Fabio and Paolo each configure the same shared or synced source folder from
their own Vera installation in Codex Desktop. On first use, Vera opens the
operating system's folder chooser, diagnoses the selected root, and saves the
private local configuration; a typed absolute path is only a fallback when the
native chooser is unavailable. Each computer builds its own
derived SQLite FTS5 index under `~/.mparanza/vera-studio-archive`; the index,
configuration, private contact metadata, and ChatGPT history are not shared.
They are not the operational source of truth. Search and indexing never modify
existing source documents. After an explicit client choice, intake may create
one derived top-level customer folder, create durable engagements, and copy
selected source, journal, or support files into that folder's `Vera/` subtree;
originals are preserved and existing files are never overwritten.

## Portable customer-folder workflow

The complete run record travels with the customer folder:

```text
<customer-folder>/
  Vera/client.json
  Vera/engagements/<engagement-id>/
    engagement.json
    .vera-engagement.lock        # process/thread mutation mutex; no case data
    inputs/<input-id>/<original-file>
    inputs/<input-id>/receipt.json
    runs/<run-id>/
      run.json
      input_manifest.json
      context.json
      inputs/                 # closed execution view of selected inputs only
      outputs/                # workflow artifacts
      artifact_manifest.json
```

Every file has a specific role: customer and engagement manifests preserve
identity; the hidden engagement lock serializes imports, run transitions, and
closure across simultaneous local processes and contains no case data; input
receipts preserve the exact imported bytes; the run and input manifests
preserve lifecycle, purpose, and the exact selected inputs; the run-local input
view prevents a workflow from accidentally consuming later files; the artifact
manifest states why every output exists, who it is for, and which exact bytes
are presented for review. Absolute machine paths are hydrated at runtime, so
the folder can be renamed or opened from another configured computer.

The explicit flow is:

1. Identify an existing customer folder or create one only after the user
   chooses New client.
2. Create or select one engagement.
3. Import each authorized source as an immutable receipt. Import does not
   create or start a run.
4. Prepare a run from exact input IDs and, when needed, exact finalized
   same-engagement upstream artifacts. Repeating the same request is
   idempotent; a separate run must be explicit.
   For Journal Sampling to Check Entries, use the dedicated handoff operation:
   select the completed sample run and support receipts, and let Studio Archive
   validate and bind the internal artifacts.
5. Start the prepared run, execute only its bound input paths, and write only
   below its `outputs/` directory.
6. Finalize by declaring every physical output with an artifact ID, purpose,
   audience, and media type. Then review and complete it. Record failures or
   cancellations instead of treating partial folders as results.

A later chat reads this ledger instead of relying on chat history.
`recover-ledger` rebuilds machine-local pointers from `Vera/client.json` and
verifies the ledger.
A folder rename retains the same client identity. The retention report is
non-destructive; closing an engagement requires every active run to be
completed or cancelled.

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

Google Drive mode uses Drive API v3 with the restricted
`https://www.googleapis.com/auth/drive` scope. It stores the refresh token only
in the owner-only Studio Archive state directory, binds one stable Vera client
ID to one exact Drive folder ID, and supports Shared Drive listings. Snapshot
records stable file and parent IDs, version, MIME type, capabilities, and
available binary checksums; shortcuts are skipped. Opening evidence revalidates
the immutable snapshot, transiently downloads a supported binary or exports a
common Google-native document, extracts bounded text, and deletes the temporary
bytes. Riordino archivio performs any later parent/name changes only after its
persistent review and separate explicit apply approval. A public or
multi-tenant deployment must complete Google's applicable OAuth verification
and security assessment.

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
cd <vera-plugin-root>
python scripts/check_dependencies.py --module studio-archive
```

The check installs the published core requirements into Vera's fingerprinted,
user-scoped managed virtual environment only when needed and reuses it after restarts.

Scans can use Vera's existing local OCR runtime. OCR is opt-in for refreshes and
never downloads model weights:

```bash
python scripts/check_dependencies.py --requirements requirements-ocr.txt
```

The normal Codex path is the MCP server. A direct CLI fallback is also
available:

```bash
python scripts/studio_archive.py setup
python scripts/studio_archive.py configure --archive-root /absolute/path/to/Studio
python scripts/studio_archive.py refresh
python scripts/studio_archive.py status
python scripts/studio_archive.py clients
python scripts/studio_archive.py client-folder --client-id client_...
python scripts/studio_archive.py authorize-google-drive --client-secrets /private/path/oauth-client.json
python scripts/studio_archive.py google-drive-status
python scripts/studio_archive.py bind-google-drive --client-id client_... --folder-id DRIVE_FOLDER_ID
python scripts/studio_archive.py snapshot-google-drive --client-id client_... --engagement-id eng_...
python scripts/studio_archive.py open-google-drive --client-id client_... --engagement-id eng_... --snapshot-input-id input_... --file-id DRIVE_FILE_ID
python scripts/studio_archive.py create-client --legal-name "Zecca SPA"
python scripts/studio_archive.py create-engagement --client-id client_... --engagement-label "2026 analysis"
python scripts/studio_archive.py import-document --client-id client_... --engagement-id eng_... --source-path /absolute/path/source.xlsx --role source
python scripts/studio_archive.py import-document --client-id client_... --engagement-id eng_... --source-path /absolute/path/journal.xlsx --role journal
python scripts/studio_archive.py engagements --client-id client_...
python scripts/studio_archive.py prepare-workflow --engagement-id eng_... --workflow-id journal-sampling --input-id input_...
python scripts/studio_archive.py start-check-entries-from-sample --client-id client_... --engagement-id eng_... --sample-run-id run_... --support-input-id input_...
python scripts/studio_archive.py start-workflow --client-id client_... --engagement-id eng_... --run-id run_...
python scripts/studio_archive.py finalize-workflow --client-id client_... --engagement-id eng_... --run-id run_... --artifacts-json '[{"artifact_id":"deliverable.result","path":"result.pdf","purpose":"Reviewed client deliverable","audience":"deliverable","media_type":"application/pdf"}]'
python scripts/studio_archive.py complete-workflow --client-id client_... --engagement-id eng_... --run-id run_...
python scripts/studio_archive.py close-engagement --client-id client_... --engagement-id eng_...
python scripts/studio_archive.py recover-ledger
python scripts/studio_archive.py retention-report --client-id client_... --older-than-days 365
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

`client-folder` returns a digest-bound v2 identity object containing the stable
`client_id`, current folder `scope_id`, paths, and display name—not the private
email/legal-name/tax-ID values. An executable workflow uses the separate
prepared run context, not this folder object as a substitute. Engagement
listing reads the customer-folder ledger and returns immutable input receipts,
run lifecycle, exact bound inputs, declared artifacts, and current mechanically
available paths. Consuming workflows reject unbound inputs and outputs outside
the exact run.

After a customer-folder rename, refresh and run `recover-ledger` when a full
verification is useful. The stable `client_id` in `Vera/client.json` lets Vera
adopt the new path without guessing from the folder label.

Set `VERA_STUDIO_ARCHIVE_STATE_DIR` to an absolute private directory only when
the default state location is unsuitable. Never put that directory inside the
shared archive, a Git repository, or a cloud-synced folder. The derived index
contains extracted document text and is not application-encrypted; protect it
with a private operating-system account, full-disk encryption, and an
appropriate backup policy.

### Session state ownership

State now defaults to a private session subdirectory under
`~/.mparanza/vera-studio-archive/sessions/`. The session key is
`VERA_STUDIO_ARCHIVE_SESSION_ID`, then `CODEX_THREAD_ID`, with a unique
process identity as the fallback. The MCP server supplies a stable session ID
across its helper commands. For a multi-command terminal workflow, set one
unique `VERA_STUDIO_ARCHIVE_SESSION_ID` before configuring and keep it for the
whole run. Use a different ID for each concurrent workflow.

`VERA_STUDIO_ARCHIVE_STATE_DIR` still selects an explicit absolute directory.
An OS lock covers the full process lifetime after first configuration access;
competing processes fail clearly. Persisted session ownership also prevents
another session from adopting or overwriting that directory between commands.
Reuse a session ID only to resume that same session. To start a new session,
use fresh state, configure the approved root and run `recover-ledger`.
Never copy the old config into a new session or work around a configuration
change error by repeatedly reconfiguring the contested state.
