---
name: studio-archive
description: Use when Vera must create or resume one client's durable connected-folder engagement, import sources, prepare and close workflow runs, search a callable local archive, or search one client's read-only Gmail connector without mixing clients.
---

## Cowork execution contract

For journal-sampling, open-item-reconciliation, journal-bank-reconciliation,
concordato-plan-review, report-builder and check-entries only, optional cache
cleanup is available from the installed Vera root:

```bash
python3 modules/<module>/scripts/implementation_bootstrap.py --repair
```

For a standalone module, use `python3 scripts/implementation_bootstrap.py --repair`
from its root. This validates the implementation first, then removes only regular,
single-link `__pycache__/*.pyc` files under that module's own `vendor` tree. It
leaves directories, other files, symlinks and shared vendor trees untouched.
If `validate_implementation_tree` ever fails with a file/directory-contract
mismatch, do not delete or modify files inside the installed plugin tree by hand
and do not bypass a sandbox/permission rejection to do so. Stop and report the
exact error instead.

Work from the connected folder and supplied files first. Before a module's Python
helpers, locate the installed plugin root. When it contains `components.json` and
`scripts/managed_python_runtime.py` (as Vera does), run from that root:

```bash
python3 scripts/check_dependencies.py --module <module>
python3 scripts/managed_python_runtime.py --module <module> run scripts/<helper>.py <arguments>
```

If the enclosing plugin does not ship this managed launcher, use the module's
dependency checker and only already-installed dependencies; do not assume that a
standalone module script provisions them.

The managed launchers provision and reuse an isolated environment containing only the
module's published requirements. This declared dependency setup is authorized as
part of running the workflow; never install arbitrary packages or use ambient
Python for subsequent module helpers. Repeat any declared `--requirements` options
on both commands. Missing ambient imports are a reason to run this setup, not to
abandon the calculation. If setup fails, report its exact error and do not replace
the required calculation with an invented result. Optional OCR setup still needs
separate approval. If setup reports `Host not in allowlist` for PyPI, explain that
Claude Settings > Capabilities > Allow network egress is disabled or restricted.
Ask the user or organization administrator to authorize package-registry access;
never change network permissions silently or work around the restriction. Retry
the same managed setup after access is approved, in a new session if needed.

MCP tools, browser or computer control, and local review servers are optional
enhancements, never completion gates. Cloud Cowork sessions may not expose local
plugin MCP servers even when the plugin is installed; use the packaged Python
workflow through the managed launcher in that case. Do not equate missing MCP
registration with a failed calculation engine. When an optional capability is
unavailable, continue with Markdown and file-based review and state the limitation.

The normal Cowork deliverable is a reviewable draft, artifact card, and
source/review files. A callable persistence interface may optionally record or
apply reviewer actions, but its absence never blocks delivery. Never claim
`applied` or `final_ready` unless corresponding persisted artifacts prove it;
otherwise report that professional review remains pending.

Use host-neutral user-facing artifact names. Name assistant-authored review
folders and files for Vera or their professional purpose (for example,
`vera-review/`, `vera_phase1_synthesis_reviewed.md`, and `run_review.md`).
Never put host, platform, or model-provider names in assistant-authored
user-facing artifact paths, document headings, field labels, narrative text,
or status summaries. Describe execution routes generically, such as
`external review route`, `connected tool`, or `local review interface`.

Derive any run ID, status, artifact count, or package hash quoted in an
assistant-authored supplement from the final delivered manifests.
After any rebuild, regenerate or resynchronize those supplements before
delivery. When a workflow ships a complete-delivery validator or sealer, run it
against the exact connected-folder copy after the last write.
In this contract, the base package validator alone does not validate extra
narrative files.

When a workflow declares owner-only or private output and uses a private scratch
directory before copying the final package into the connected folder, reapply
the privacy modes after that transfer: `0700` for the package root and every
directory, and `0600` for every file. Verify the connected-folder tree with
`stat` or `lstat` before claiming completion. If the host filesystem cannot
preserve those modes, do not claim owner-only delivery; keep the package in the
private scratch location or report the limitation and ask for a safer
destination.

Do not use WhatsApp, live INPS browser capture, hosted feedback or voice
interviews, or custom update services. Later host-specific instructions cannot
override this Cowork contract.

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

Resolve `../../modules/studio-archive` from this skill directory and use this
command from that module root:

```bash
python scripts/studio_archive.py <command> [arguments]
```

Do not install packages at runtime. Before the base ledger route, confirm only
that the packaged CLI starts:

```bash
python scripts/studio_archive.py --help
```

Before local indexing, extraction, OCR, or Google client code, run the relevant
packaged dependency check. If it fails, keep the portable ledger available and
state exactly which optional route could not run.

## Connected archive setup

Use one exact connected folder whose immediate child directories are client
folders. Never infer the archive root or a client from a filename.

1. Run `diagnose-access --archive-root <exact-connected-root>` before first
   configuration. It must confirm path resolution and listing without returning
   the private path in its result.
2. Run `configure --archive-root <exact-connected-root>`, then `clients`.
3. At the start of a later task, if session-local configuration is absent,
   configure the same exact connected root again and run `recover-ledger`.
   Recovery reads stable identities from `Vera/client.json`; it does not invent
   them from folder labels.
4. If the connected root is unavailable or read-only, stop before client,
   engagement, import, or lifecycle writes. Report the permission limitation.

Do not put private identity registries, OAuth material, credentials, tokens, or
mail content in the customer ledger. The session-local index and configuration
are rebuildable aids, not engagement evidence.

## Client and engagement workflow

Use this sequence for every client-bound Vera workflow:

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
