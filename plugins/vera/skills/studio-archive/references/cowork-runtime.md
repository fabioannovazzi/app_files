---
name: studio-archive
description: Use when Vera must create or resume one client's durable connected-folder engagement, import sources, prepare and close workflow runs, search a callable local archive, or search one client's read-only Gmail connector without mixing clients.
---

# Archivio dello Studio

Studio Archive is available in Cowork. Its base workflow uses the portable
customer-folder ledger in the exact connected studio folder. It can list or
register clients, create client folders and engagements, import immutable source
receipts, prepare and start client-bound Vera runs, finalize their complete
artifact declarations, resume them in a later task, and report retention.

The customer folder is the durable source of truth. Cowork's session-local
configuration is only a rebuildable path pointer; it may be recreated from the
same connected archive root without changing the client, engagement, input,
run, lifecycle, or artifact records under `Vera/`.

## Routes

- **Portable client ledger:** the normal route. It needs code execution plus
  read/write permission to the exact connected studio folder. Its lifecycle,
  path, receipt, hash, and artifact checks use the Python standard library and
  the packaged Vera assurance module.
- **Local document search:** available when the connected folder is callable
  and the packaged dependency check succeeds with dependencies already present.
  Missing optional extraction dependencies do not block the portable ledger.
- **Local archive organization:** available through the packaged
  `archive-organization` workflow for the exact connected client folder. It
  keeps the complete snapshot, dry run, persistent professional decisions,
  separate explicit apply approval, verification journal, and rollback checks.
- **Gmail:** available when a read-only Anthropic Gmail connector exposes
  mailbox confirmation, search, and bounded message reading.
- **Guarded WhatsApp Desktop review and native Google Drive OAuth:** not enabled
  as Cowork routes. Do
  not substitute an unguarded screen-control flow, browser login, copied token,
  or generic Drive access. Continue with the portable ledger and connected
  files.

Do not redirect the user to another product. Do not claim a route ran when its
capability was unavailable.

## Packaged command

Resolve the installed Vera root from this skill directory, not from a guessed
AppData path. Generate one UUID for this task and retain that exact value in
all commands, including separate shell calls. Use a new UUID for a new task;
never share configuration across concurrent tasks. The session helper passes
that identity to the managed runtime and the archive subprocess.

On native Windows, use PowerShell and the packaged launcher (replace the UUID
placeholder with the one generated for this task):

```powershell
& "<installed-vera-root>\scripts\studio_archive_windows.ps1" -SessionId "<task-uuid>" diagnose
& "<installed-vera-root>\scripts\studio_archive_windows.ps1" -SessionId "<task-uuid>" check
& "<installed-vera-root>\scripts\studio_archive_windows.ps1" -SessionId "<task-uuid>" clients
```

The launcher probes `py -3`, `python`, and `python3`, then uses the verified
interpreter's absolute path. `-PythonExecutable` may select an explicit existing
interpreter. Do not copy or rename python.exe, uninstall another Python, create
junctions, change execution policy, or change Windows security settings. If host
policy blocks PowerShell, report the denial; do not bypass it. If bootstrap is
unavailable, distinguish a missing/unusable interpreter from package access;
request the exact attempted command and error, not client documents.

On a Linux or macOS execution surface (including a Cowork VM), run from the
installed Vera root using a callable Python:

```bash
python3 scripts/studio_archive_session.py --session-id <task-uuid> diagnose
python3 scripts/studio_archive_session.py --session-id <task-uuid> check
python3 scripts/studio_archive_session.py --session-id <task-uuid> <command> [arguments]
```

`diagnose` checks package readability without provisioning or archive writes.
`check` prepares and checks the managed runtime. Every archive command must use
this session helper; invoking the archive CLI without its task identity can
select a different configuration on every process. The actual workflow remains
`scripts/managed_python_runtime.py --module studio-archive run scripts/studio_archive.py`.

The bootstrap may start under ambient Python; the workflow runs under managed
CPython 3.12. Setup uses only published shared requirements and respects host
network permissions. Optional OCR remains an explicitly approved feature. A
setup failure must be resolved before execution; do not bypass it with an
ambient interpreter. Run relevant optional dependency checks before indexing,
extraction, OCR or Google client code.

## Check supplied files before starting client work

Select the exact files needed for this request. Folder access does not select
all its contents: if the task needs two files in a folder containing four, use
only those two. Resolve genuinely ambiguous choices with the user; reuse clear
choices without another confirmation.

Before parsing documents or creating a client, engagement or run, call
`check_studio_import_sources` with all selected paths on the actual importer
host. It needs no configured Archive and creates no records. If the MCP tool is
unavailable, use the packaged `check-import-sources --source-path <path>` CLI
through the maintained managed launcher on that same host (repeat the flag per
file). A cloud-shell `ls` is not proof of access by a computer-side importer.
Readable attachments, including `/mnt/user-data/uploads/` paths when the importer
can read them, continue directly without requiring a connected computer folder.

If files are unavailable, explain the cause immediately before creating anything:
"The file is in the chat, but the import tool looks for it on your computer."
Do not keep trying that same inaccessible path. Use this recovery sequence:

1. Inspect the host's actual callable file-transfer capabilities and the already
   connected folders. Reuse an authorized ordinary working folder outside the
   managed `Vera/engagements/.../inputs` tree. Offer **Add folder** from the **+**
   menu only when the current host offers it; otherwise explain the available
   connection method. Ask for a folder only if an accessible destination is needed.
2. With a supported bridge, copy only the selected original attachments to that
   folder as files. Compute each original SHA-256 through the host file tools.
   Do not recreate CSV text, convert encodings or line endings, relay document
   contents through model-authored tool arguments, guess a mount translation,
   overwrite a different file with the same name, or scan unrelated folders.
   A verified byte-for-byte copy may reuse its destination on retry.
3. Check the actual destination paths with `check_studio_import_sources`, passing
   `expected_sha256` as the original hashes in the same order as `source_paths`.
   The CLI takes one `--expected-sha256` per source. Archive hashes the destination
   locally and returns `ready=true` only when all supplied original hashes match.
   If no byte-preserving host transfer is available, say so and ask the user to
   save the original selected files to the accessible working folder; then verify
   them. Do not promise a bridge operation that is not callable.
4. Only after all selected sources are ready, select/create the client and
   engagement and import each through `import_studio_client_document` (CLI
   `import-document`). Pass that file's `expected_sha256` / `--expected-sha256`
   when a transfer was required. The importer checks it again during copying and
   creates the input ID and SHA receipt itself. Never manually populate `inputs`.

The path importer does not itself fetch chat attachments. Direct attachment use
requires actual importer access or a demonstrated host transfer. If neither an
importer-side check nor transfer is callable, explain the missing capability
before creating records; do not create a cloud-only replacement for a local Archive.

On any later import failure, disclose the existing `client_id` and `engagement_id`
and resume those same records. A folder-name collision calls for inspecting the
returned existing scope and reusing it when its identity matches; never clear old
folders or change the client's name just to get past the error. A deliberately
separate synthetic test may have a distinct name; retries retain their identities.
Documentless client work needs no file check. Standalone workflows check access
on their own execution host and do not require Archive or a computer folder when
that engine can read the inputs.

## Connected archive setup

Use one exact connected folder whose immediate child directories are client
folders. Never infer the archive root or a client from a filename.

1. Run `diagnose-access --archive-root <exact-connected-root>` before first
   configuration. It must confirm path resolution and listing without returning
   the private path in its result.
2. If the user has an existing archive, select that exact connected root.
   "Not configured" means this session has no pointer; it does not mean the
   archive was deleted. Ask for the original folder if it is not connected.
   Do not create a replacement, move folders, or scan unrelated directories.
   Run `configure --archive-root <exact-connected-root>`, then `recover-ledger`
   and `clients`, all through the same session helper.
3. At the start of a later task, run `clients` first. With the same retained
   owner-private profile, the helper revalidates the approved connected root,
   creates fresh session configuration and recovers confirmed aliases and stable
   client IDs without another folder selection. Existing sessions remain pinned.
   If the host provides a new/ephemeral home or the selected folder is no longer
   accessible, reconnect the exact original folder; do not claim host persistence
   that was not observed. Run `recover-ledger` when ledger verification is needed.
   Recovery reads stable identities from `Vera/client.json`, not folder labels.
4. If the connected root is unavailable or read-only, stop before client,
   engagement, import, or lifecycle writes. Report the permission limitation.

Do not put private identity registries, OAuth material, credentials, tokens, or
mail content in the customer ledger. The session-local index and configuration
are rebuildable aids, not engagement evidence.

## Client and engagement workflow

Use this sequence for archived client work. Explicit standalone invoice/answer
work follows Vera's `references/standalone-work.md` and retains task artifacts
without this archive configuration or client-registration gate.

Complete the supplied-file checks above before these record-creation steps.

1. Run `clients`. Select one returned stable client semantically from the
   user's instruction. If ambiguous, ask; never choose by recency or filename.
2. For an existing unregistered folder, run `configure-client` with its exact
   returned scope ID and at least one user-confirmed legal name, full email/PEC,
   or tax identifier. For a new client, run `create-client` only after the user
   chooses New client; the resulting relationship remains
   `new_client_workflow_pending`.
3. Run `create-engagement` or `engagements` and select one exact engagement.
4. Explain that import preserves the original and creates an immutable copy and
   SHA-256 receipt. After authorization, run `import-document` separately for
   each selected file with role `source`, `journal`, or `support`.
5. Run `prepare-workflow` with the exact workflow ID, input IDs, and any exact
   finalized same-engagement upstream artifacts. Repeating the same request is
   idempotent; use `--new-run` only for an explicitly separate run.
6. Run `start-workflow`. Pass the returned `client_engagement_path` unchanged to
   the specialist module. Execute only its hydrated input bindings and write
   only below its exact output directory.
7. After the final write, run `finalize-workflow` with every physical output,
   including a unique artifact ID, relative path, concrete purpose, audience,
   and media type. An empty, changed, partial, or undeclared tree is not ready.
8. Review the declaration, then run `complete-workflow`. Record `fail-workflow`
   or `cancel-workflow` instead of presenting a partial folder as a result.

Journal Sampling and Check Entries keep their exact handoff: finalize the
normalized population, diagnostics, and sample first; import each later support
batch separately; then use `start-check-entries-from-sample`. Check Entries
checks only the bound sample and never discovers later files implicitly.

## Saved-input verification and document continuations

Before claiming an import or earlier working note is preserved, use the callable
`verify_studio_client_inputs` MCP tool, or run the maintained `verify-inputs`
command through the same session helper. Select the exact client, engagement
and input IDs from native import or `engagements` results. Never improvise a
verifier that reads raw `engagement.json` or `receipt.json` for hydrated paths.

The command takes `--client-id`, `--engagement-id` and repeated `--input-id`.
Supply `--expected-receipts-json` with the prior `input_id` and `content_sha256`
pair for every selected input when checking preservation. Use
`--require-exact-input-set` only when the selection is the complete expected
engagement population. Inspect `verified`, each input and `failures`; a blocked
check exits nonzero and never repairs the archive. Do not invent a baseline.

The result supplies verified controlled paths for any separately authorized
content read. Complete file hashing is local; IDs, names, roles, paths, sizes,
file and receipt hashes and check results may enter the host model context,
but this operation returns no document text. Verification does not establish
document meaning, payment, authored lineage or professional approval.

For a document-only continuation, import the new derived note as `support`,
retain the earlier receipt and verify both versions against their prior import
receipts. For an exact retry, retain the actual import result `already_imported`
and the same input ID; verification cannot invent a historical retry outcome.
The full contract is in the component's `references/input-verification.md`.

## Local document search

When the dependency check succeeds, `refresh`, `search`, and `open` may index
and verify one exact connected scope. Refresh hashes the supported files and
re-extracts changed content. Search results are candidates, not evidence; open
every source used, require its current hash to match, and cite the returned
locator. Do not claim complete coverage when extraction issues, OCR gaps, file
bounds, or unsupported formats remain.

## Connected Gmail

Use Gmail only when the user asks for it. Confirm the mailbox, process exactly
one client, and construct the address set only from complete email or PEC
addresses supplied or explicitly confirmed in the current task. When no full
address is confirmed, run one discovery-only query using the supplied client
name or identifier and return at most 20 candidates. Read only the smallest
useful candidate shortlist, propose complete participant addresses from the
returned metadata, and obtain one explicit confirmation before using any
candidate message as client evidence.

After confirmation, search only the confirmed addresses, in batches of at most
ten, with the user's topic or date bounds when useful. Request at most 20
results per page and paginate only when the requested coverage materially
requires older messages. Read only the scoped shortlist. For every message,
compare all available From, To, Cc, and Bcc values case-insensitively against
the confirmed address set. Automatic routing requires a parseable From value,
parseable returned recipient values, exactly one selected client, and no visible
other-client or ambiguous external participant. Inspect Cc and Bcc whenever
exposed; an absent optional field alone is not incomplete, and returned fields
cannot prove the absence of an undisclosed Bcc recipient.

Use read actions only. Never send, draft, forward, archive, trash, delete,
label, move, download, or otherwise mutate mail. Do not use IMAP or browser
scraping as a fallback. Gmail evidence remains connector evidence rather than a
hash-verified ledger input unless the user separately supplies and imports an
authorized export.

## Model and privacy boundary

The model may receive the selected client directory rows with stable IDs,
labels, status, and counts; the task instructions; exact workflow context and
artifact declarations; bounded search candidates and opened source passages;
and the selected Gmail evidence described above. Stored private identity values,
absolute archive paths, raw file hashes, the SQLite index, and unselected files
remain outside model context unless a specific professional operation requires
an exact value or opened source.

This is purpose-based minimization, not anonymization or pseudonymization. Do
not remove names, account labels, amounts, relationships, or evidence locators
when they are necessary to select the right client, interpret the accounting
evidence, or support the professional result.
