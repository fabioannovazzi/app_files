---
name: studio-archive
description: Use when Vera must configure, refresh, or search a shared studio document archive through one private local index per professional, then answer from opened and hash-verified source passages with precise file, page, paragraph, sheet-row, or line citations.
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
separate SQLite FTS5 index, configuration, Codex context, and ChatGPT history.
Do not create a shared database, shared account, vector service, or permissions
layer in this first version.

This workflow requires local Codex filesystem and process access. ChatGPT web
alone cannot index a local folder or start the local MCP server.

The source folder is read-only to this workflow. Immediate child directories
become exact search scopes; supported root-level files receive their own root
scope. Refresh detects and adopts top-level scope-folder changes; explicit
configuration also repairs them. The index never follows symbolic links.

## Evidence boundary

Deterministic code owns file discovery, scope enforcement, bounded extraction,
hashing, incremental refresh, lexical retrieval, and locators. This is
mechanically verifiable and benefits from reproducibility and fail-closed
behavior. Codex owns semantic query expansion, relevance judgement, synthesis,
and explanation. Do not add a deterministic semantic classifier or present the
lexical score as professional relevance.

Search results are candidates, not evidence. Before relying on any result, call
`open_studio_archive_source`; it re-hashes the live file and fails if the source
changed. Cite the returned `citation` and distinguish direct source facts from
your own inference. If opened sources do not support the answer, say so.

Real source passages returned by MCP may enter the user's selected Codex/OpenAI
account context. The local index itself stays outside Codex and outside the
shared archive. Do not send archive content to other services or use web search
with client identifiers.

## Material choices

Ask only those unresolved choices in chat that materially change the actual inputs or scope:

- the absolute shared archive folder on first configuration;
- which returned scope matches the user's intended client, practice, or
  internal area when that is not clear;
- whether the user truly wants a studio-wide search before using `scope_id:
  "all"`;
- whether already-installed local OCR should be used for scans when that could
  materially improve evidence.

Do not ask the user to choose RAG, embeddings, a database, chunk sizes, or
normal output formats.
Do not offer named client scopes, document classes, or search topics unless the facts cue them.

Request explicit approval only for external, destructive, approval-sensitive,
or materially unresolved steps. Local configuration, incremental refresh, and
read-only retrieval inside the user-selected archive do not need an extra
approval prompt.

## First setup for Fabio and Paolo

On each professional's computer:

1. Install Vera in local Codex and point `configure_studio_archive` at that computer's
   absolute path to the same shared folder.
2. Read the returned scopes and run `refresh_studio_archive`.
3. Leave `VERA_STUDIO_ARCHIVE_STATE_DIR` unset unless a different private local
   state directory is needed.

The absolute source paths may differ between computers. That is fine. Do not
copy either user's `archive.sqlite3` or `config.json` to the other. If Fabio
and Paolo use the same operating-system account, each must set a different
absolute `VERA_STUDIO_ARCHIVE_STATE_DIR`; separate ChatGPT licences do not
separate files under one operating-system home directory. The derived index
contains extracted text and is not application-encrypted, so keep it under
private operating-system and disk/backup controls.

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

If MCP is unavailable, work from the component root and use:

```bash
python scripts/check_dependencies.py
python scripts/studio_archive.py configure --archive-root /absolute/archive/path
python scripts/studio_archive.py refresh
python scripts/studio_archive.py status
python scripts/studio_archive.py search --scope-id scope_... --query "short query"
python scripts/studio_archive.py open --source-id src_... --context-chunks 1
```

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
   scope, OCR posture, and the user's question.
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

## Plugin Improvement Feedback

At the end of a completed or blocked run, briefly identify a concrete
improvement supported by the actual session, such as a missing parser, weak
locator, OCR gap, slow refresh, or awkward scope.

Keep the improvement note local to chat or run artifacts. Do not submit it
automatically.
