---
name: archive-organization
description: Use when Vera must screen one registered client folder, find duplicate or misplaced files, propose studio-policy destinations, collect collaborator decisions, and only then safely apply or roll back the approved organization plan.
---

## Cowork execution contract

Work from the connected folder and supplied files first. Use a local script only
when it is callable and every declared dependency it needs is already available;
never install packages at runtime. MCP tools, browser or computer control, and
local review servers are optional enhancements, never completion gates. When an
optional capability is unavailable, continue with Markdown and file-based review
and state the limitation.

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

# Riordino archivio



Local-folder mode runs in Claude Desktop and Cowork against the exact user-bound
folder. Native Google Drive mode uses the current guarded desktop OAuth adapter
and is not an enabled Cowork route. In a text-only chat, review
supplied plans or explain the method; never claim to scan or change a folder.

Resolve `../../modules/archive-organization` from this skill directory when it
exists; otherwise resolve `../../../archive-organization` in the repository.
Read that module's `skills/archive-organization/SKILL.md` completely and follow
it. Treat the resolved module root as the plugin working directory for all
commands, requirements, policy references, review assets, and MCP tools.

Use `studio-archive` first for the exact registered client, engagement, local
or Google Drive folder-snapshot receipt, workflow preparation, lifecycle, and artifact
closure. The shared archive's search and source-opening operations remain
read-only; only the separately reviewed and explicitly approved Riordino
archivio execution may change client-file paths.
