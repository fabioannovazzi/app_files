---
name: new-client
description: "Use when a studio starts work on a new client: prepare files, identify missing evidence, and build a source-bound setup covering identity, engagement, privacy, AML, and monitoring."
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

# New Client



This is Vera's sole new-client workflow. Do not route users to separate
document-preparation or professional-setup workflows.

Resolve the workflow root as `../../modules/new-client` when installed or
`../../../new-client` in repository source. Resolve its subordinate file
preparation engine as `../../modules/client-file-preparation` when installed or
`../../../client-file-preparation` in repository source.

Read that module's `skills/new-client/SKILL.md` completely. When incoming
documents need preparation, also read the engine's
`skills/client-file-preparation/SKILL.md` completely and execute that as phase
one. When callable, these MCP toolsets are optional persistence enhancements:

- `validate_client_file_preparation_review`,
  `render_client_file_preparation_review`,
  `save_client_file_preparation_decisions`, and
  `apply_client_file_preparation_decisions` review phase one;
- `validate_new_client_review`, `render_new_client_review`,
  `save_new_client_decisions`, and `apply_new_client_decisions` review the
  professional-setup phases.

Treat the relevant resolved module root as the plugin working directory for each
command. Present every phase and artifact to the user under **New Client**.

Phase one accepts `italy`, `geneva`, `zurich`, `uk`, or `mixed`; its review,
memo, client request, inventory, extraction report, and fiscal summary follow
`it`, `en`, `fr`, `de`, or `es`. Low-level machine records retain stable field and
status codes. The current professional setup country pack is Italy only.
Promote a reviewed phase-one run with the
resolved `new-client` module's
`scripts/promote_client_file_preparation.py`; the command verifies the sealed
manifest and every listed output, inherits the phase-one language, and must
reject non-Italian or mixed runs rather than implying another country pack.

Real client data may enter the current model context when useful for the professional
work. Do not add a per-case model-use authority or minimisation declaration
that Vera cannot verify. Keep credentials, cookies, tokens, session URLs, and
raw local paths outside the review payload.

For phase one, when `model_handoff.json` exists, both Claude and Cowork use it
and every declared page as their default context. Use only the item kinds
listed for the current phase. Keep `review_payload.json` as the local MCP/UI
contract; do not use its broader draft previews as ordinary synthesis context.
Exact local identifiers remain available in professional artifacts and may be
loaded when the work requires them. The generic `CLIENT-001` reference applies
only to phase-one email drafting; it is not blanket anonymization.

The normal Cowork handoff is the reviewable draft, artifact card, and source/review files in the connected folder. Review them directly. When a validated MCP or local workbench is callable, it may optionally persist save/apply actions. If it is unavailable, deliver the useful file-based package and keep professional review pending. Never claim that decisions were applied or that the package reached `final_ready` unless corresponding persisted artifacts prove it.
