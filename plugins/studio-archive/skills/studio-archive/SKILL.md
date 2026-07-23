---
name: studio-archive
description: Use when Vera must configure, refresh, or search a shared studio document archive or a client-scoped connected Gmail mailbox, using one private local index and client identity registry per professional, then answer from reviewed evidence without mixing clients.
---

## Output Location Rule

Never write run outputs inside this Git workspace, `static/shared`,
`protected_downloads`, or any GitHub Pages/static-site folder unless the task is
explicitly plugin packaging/release. Studio Archive keeps its persistent,
derived index in the private state directory, normally
`~/.mparanza/vera-studio-archive`. Never place that state inside the source
archive or a synced/shared folder.

# Vera · Archivio dello Studio

Use one shared or synced source folder and duplicate only the derived index.
Each professional configures the folder on their own computer and receives a
separate SQLite FTS5 index, client identity registry, configuration, Codex
context, and ChatGPT history.
Do not create a shared database, shared account, vector service, or permissions
layer in this first version.

This workflow requires local Codex filesystem and process access. ChatGPT web
alone cannot index a local folder or start the local MCP server.

The source folder is read-only to this workflow. Immediate child directories
become exact search scopes; supported root-level files receive their own root
scope. Refresh detects and adopts top-level scope-folder changes; explicit
configuration also repairs them. The index never follows symbolic links.

Gmail remains in the user-selected Gmail account and is accessed only through
the connected Codex Gmail connector during an active task. Studio Archive does
not request or store Gmail credentials, tokens, cookies, message bodies,
attachments, or a mailbox copy. The private client identity registry stores
only confirmed full email or PEC addresses, legal names, tax identifiers, and
their exact archive `scope_id`.

## Evidence boundary

Deterministic code owns file discovery, scope enforcement, bounded extraction,
hashing, incremental refresh, lexical retrieval, and locators. This is
mechanically verifiable and benefits from reproducibility and fail-closed
behavior. It may route Gmail only when one unique confirmed full address
matches one client. Codex owns semantic query expansion, relevance judgement,
third-party-message attribution, synthesis, and explanation. A legal name,
subject, snippet, body passage, or attachment mention is only a candidate:
never turn it into automatic client routing. Do not present lexical score or a
Gmail search match as professional relevance.

Search results are candidates, not evidence. Before relying on any result, call
`open_studio_archive_source`; it re-hashes the live file and fails if the source
changed. Cite the returned `citation` and distinguish direct source facts from
your own inference. If opened sources do not support the answer, say so.

Real source passages returned by MCP may enter the user's selected Codex/OpenAI
account context. The local index itself stays outside Codex and outside the
shared archive. Do not send archive content to other services or use public web
search with client identifiers. The user-selected Gmail connector is the only
mailbox boundary in this workflow.

When the user chooses Gmail search, Gmail queries, message and thread
identifiers, headers, snippets, selected bodies, and selected attachment
content may enter the same Codex context through the Gmail connector. Gmail
evidence is not a local file and is not covered by Studio Archive's SHA-256
verification. Cite its sender, subject, timestamp, and connector message
identifier, and state the searched account scope and coverage.

## Material choices

Ask only those unresolved choices in chat that materially change the actual inputs or scope:

- the absolute shared archive folder on first configuration;
- which returned scope matches the user's intended client, practice, or
  internal area when that is not clear;
- whether the user truly wants a studio-wide search before using `scope_id:
  "all"`;
- whether already-installed local OCR should be used for scans when that could
  materially improve evidence.
- whether the user wants connected Gmail searched for the selected client;
- the confirmed full email or PEC addresses, legal names, or tax identifiers
  for that client when its profile is not yet configured.

Do not ask the user to choose RAG, embeddings, a database, chunk sizes, or
normal output formats.
Do not offer named client scopes, document classes, or search topics unless the facts cue them.

Request explicit approval only for external, destructive, approval-sensitive,
or materially unresolved steps. Local configuration, incremental refresh, and
read-only retrieval inside the user-selected archive do not need an extra
approval prompt. The user's explicit request to search Gmail is the connector
route confirmation; do not ask again. Never search Gmail merely because an
archive question was asked.

## First setup for Fabio and Paolo

On each professional's computer:

1. Install Vera in local Codex and point `configure_studio_archive` at that computer's
   absolute path to the same shared folder.
2. Read the returned scopes and run `refresh_studio_archive`.
3. Leave `VERA_STUDIO_ARCHIVE_STATE_DIR` unset unless a different private local
   state directory is needed.
4. For Gmail search, each professional connects their own Gmail connector.
   Configure confirmed client identities against that user's exact local
   `scope_id`; do not copy either user's `client-identities.json`.

The absolute source paths may differ between computers. That is fine. Do not
copy either user's `archive.sqlite3` or `config.json` to the other. If Fabio
and Paolo use the same operating-system account, each must set a different
absolute `VERA_STUDIO_ARCHIVE_STATE_DIR`; separate ChatGPT licences do not
separate files under one operating-system home directory. The derived index
contains extracted text and is not application-encrypted, so keep it under
private operating-system and disk/backup controls.

The local MCP cannot verify which Gmail account the connector selected. Before
each Gmail search, call the Gmail profile tool and show the selected account in
the Run Intake. If it is not the mailbox the user intended, stop and ask them
to reconnect or select the correct account.

## Search workflow

1. Call `studio_archive_status`. If not configured, configure it. If
   `index_requires_refresh` is true, refresh before searching.
2. At the start of a substantive archive session, run the incremental refresh
   unless the user explicitly wants the current snapshot only. Enable OCR only
   when scans matter and the local OCR requirements are already installed.
   Refresh verifies every supported file by hash, re-extracts only changed
   content, removes deleted content, and reports scan issues.
3. Select one exact `scope_id`. Use `all` only after explicit studio-wide
   intent.
4. Issue two or three short lexical searches when useful: exact names or
   identifiers, a compact topic phrase, and one plausible synonym. Do not spray
   broad queries across unrelated scopes.
5. Semantically review the candidates. Open every source used in the answer,
   with at most two adjacent chunks when necessary.
6. Answer with returned citations, evidence limits, conflicting passages, and
   the refresh date when recency matters. A verified hash proves unchanged
   bytes since indexing; it does not prove completeness, correctness, or legal
   authority.

## Gmail client workflow

1. Select one exact archive `scope_id`. Studio-wide Gmail search is not
   supported in this version.
2. Call the Gmail connector's `get_profile` action and show the selected account
   in the Run Intake. Stop if it is not the mailbox the user intended.
3. Call `plan_studio_archive_gmail_search` with that scope and, when useful, a
   compact topic or date bounds.
4. If the profile is `alias_only` or `candidate_only`, use only the bounded
   candidate query to find likely direct participants. Read a small shortlist,
   propose the full addresses, and obtain one user confirmation before calling
   `configure_studio_archive_client`. Candidate results must not enter the
   client answer before that confirmation.
5. Use `search_emails` with the returned Gmail-native queries and about 20
   results per page. Paginate only when coverage materially requires older
   messages.
6. Use `batch_read_email` only for the scoped shortlist. For every returned
   message, call `match_studio_archive_email` with every available From, To, Cc,
   and Bcc value. Set `headers_complete: true` only when the full message read
   exposed all four fields, including an explicit empty Bcc field, and every
   non-empty value was supplied. Missing or unparseable header coverage fails
   closed and cannot route automatically.
   Use `read_email_thread` only when conversation context changes the answer.
   Re-check every returned thread message separately; a thread is not itself a
   client scope.
   Use `read_attachment` only for a selected, supported attachment after the
   parent message is routed.
7. One unique confirmed-address match with complete headers may route
   automatically. Zero-client, multi-client, incomplete, or unparseable results
   remain unassigned, ambiguous, or incomplete.
8. For indirect correspondence from a lawyer, bank, adviser, authority, or
   other third party, Codex reviews the message meaning. Exclude it when client
   attribution remains ambiguous; never save a guessed address into the
   profile.
9. Combine Gmail and local archive evidence only after keeping their provenance
   separate. Local files receive hash-verified file citations; Gmail receives
   sender, subject, timestamp, and message-identifier citations.

This is on-demand connector retrieval, not background synchronization. Never
use Gmail send, draft, forward, archive, Trash, delete, label, or move actions
in this workflow. Never fall back to IMAP, browser scraping, or asking the user
to save `.eml` files when the Gmail connector is missing; report the missing
connector instead.

Supported citations are physical PDF/image pages, DOCX paragraphs or table
rows, XLSX sheets and rows, EML message lines, and text-file lines. EML
attachments, password-protected files, oversized files, unsupported formats,
and incomplete OCR remain explicit limitations. Treat OCR-derived passages as
transcription candidates and visually confirm the cited page before relying on
them for a material fact. Review both `scan_issues` and `document_issues`;
the latter names indexed documents whose extraction is partial, failed,
OCR-dependent, or produced no searchable passage.

## MCP and CLI fallback

Prefer these Vera MCP tools:

- `studio_archive_status`
- `configure_studio_archive`
- `refresh_studio_archive`
- `search_studio_archive`
- `open_studio_archive_source`
- `list_studio_archive_clients`
- `configure_studio_archive_client`
- `plan_studio_archive_gmail_search`
- `match_studio_archive_email`

If MCP is unavailable, work from the component root and use:

```bash
python scripts/check_dependencies.py
python scripts/studio_archive.py configure --archive-root /absolute/archive/path
python scripts/studio_archive.py refresh
python scripts/studio_archive.py status
python scripts/studio_archive.py search --scope-id scope_... --query "short query"
python scripts/studio_archive.py open --source-id src_... --context-chunks 1
python scripts/studio_archive.py configure-client --scope-id scope_... \
  --email-address amministrazione@example.com --legal-name "Esempio SRL"
python scripts/studio_archive.py clients
python scripts/studio_archive.py plan-gmail --scope-id scope_... \
  --topic "rateazione INPS"
python scripts/studio_archive.py match-email --expected-scope-id scope_... \
  --headers-complete \
  --header-address "Esempio SRL <amministrazione@example.com>"
```

The CLI only configures identities, plans queries, and matches headers. It does
not call Gmail. Gmail search and read actions require the Codex Gmail connector.

If the core dependency check fails, report the missing requirement and tell the
user that the declared requirements can be installed with:

```bash
python -m pip install -r requirements.txt
```

For scanned sources, check the optional local OCR requirements separately:

```bash
python scripts/check_dependencies.py --requirements requirements-ocr.txt
```

Do not install packages at runtime. OCR must keep model downloads disabled; if
local weights are unavailable, continue with readable files and report the
limitation.

## Codex-Native Run UX

Default output policy: return the richest normal, source-backed answer in chat;
the private derived index, citations, limitations, and a concise search trail
are not choices to propose.

1. Start substantive setup or search work with a short checklist.
2. Show a Run Intake table containing archive status, refresh posture, selected
   scope, OCR posture, Gmail posture and selected connector account when used,
   and the user's question.
3. Use a Decision Table only for unresolved scope, studio-wide search, OCR, or
   material evidence conflicts.
4. Before a long first refresh or rebuild, show an execution checkpoint with
   the source root, private state location, read-only source guarantee, and
   expected index work.
5. End with an Artifact Card naming the private index status, searched scope,
   opened sources, evidence limits, and next action.

Create `codex_run_review.md` only when the user requests a durable search memo,
and write it outside the Git workspace. Never edit plugin source or generated
ZIPs during an archive run.

## Failure rules

- Not configured or no index: configure and refresh.
- Unknown or ambiguous scope: stop before search and resolve it.
- Changed file at open: refresh, rerun the search, and use the new source ID.
- Missing/unsupported/unreadable material: report partial evidence.
- No opened source supports the answer: state that the archive search did not
  establish the answer.
- OCR unavailable: keep the text-readable pass and identify likely scan gaps.
- Gmail connector unavailable or disconnected: report that client-scoped email
  search cannot run; do not use IMAP or browser fallback.
- Client profile is alias-only or candidate-only: bootstrap a bounded candidate
  search, propose exact addresses, and wait for confirmation before
  client-scoped use.
- Client folder was renamed: after refresh, call
  `list_studio_archive_clients`, show the orphaned and target scopes, and use
  `configure_studio_archive_client` with `replace_orphaned_scope_id` only after
  the user confirms that exact rebind. Never infer or bulk-rebind profiles.
- Gmail message matches another client: exclude it from the selected client's
  answer.
- Gmail headers are incomplete or unparseable: do not route automatically.
- Gmail message matches zero or multiple clients: keep it unassigned or
  ambiguous and use it only after model review establishes the client without
  unresolved conflict.

## Plugin Improvement Feedback

At the end of a completed or blocked run, briefly identify a concrete
improvement supported by the actual session, such as a missing parser, weak
locator, OCR gap, slow refresh, or awkward scope.

Keep the improvement note local to chat or run artifacts. Do not submit it
automatically.
