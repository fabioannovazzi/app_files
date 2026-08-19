---
name: quesito-legale-fiscale
description: Use when Vera receives a substantive legal, tax, or compliance question, analysis request, or source-backed professional drafting request and must take it through one complete question-to-reviewed-answer journey. Do not use for returns, declarations, filings, or forms whose correctness requires a dedicated operational workflow.
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

# Risposta A Quesiti Legali E Fiscali

This is Vera's user-facing specialist workflow for an ordinary substantive
legal, tax, or compliance question. Select it automatically from the user's
question. Do not require the user to invoke, choose, or understand the internal
planning and validation skills.

Follow the `Question To Validated Answer Journey` in `../vera/SKILL.md`. Treat
this skill as the matching specialist workflow for that journey, then:

1. Read `../prompt-optimizer/SKILL.md` completely and follow it before drafting
   or research. It prepares the answer contract, source posture, generation
   route, and generation instructions.
2. Generate the contracted answer directly when the current runtime can meet
   the required standard, or prepare the explicit ChatGPT Deep Research handoff
   when native Deep Research is materially needed.
3. Read `../deep-research-validator/SKILL.md` completely and follow it before
   delivering a generated or supplied answer. Reuse the same answer contract,
   correct supported defects, and keep professional-judgment items explicit.
4. Deliver the reviewed or corrected answer, its sources and validation limits
   as one result. Do not stop after prompt preparation when direct generation is
   available, and do not describe a structurally complete record as proof of
   legal or tax correctness.

The two underlying skills remain separate stages with separate Studio Archive
runs in the same client engagement when local Vera run capabilities are
available. This orchestration skill does not create a third client workstream,
duplicate their artifacts, or introduce a new external data route. In ChatGPT
or another surface without local run tooling, continue with the useful in-chat
version required by the Vera runtime contract and state which durable artifacts
were not created.

Do not use this workflow to imitate an unsupported operational return,
declaration, filing, statutory form, signature, payment, or submission. Select
the dedicated Vera workflow when one exists; otherwise use Vera's no-matching-
specialist-workflow outcome.

Before substantive delivery, disclose:

```text
Vera workflow: vera:quesito-legale-fiscale -> vera:prompt-optimizer -> vera:deep-research-validator
```
