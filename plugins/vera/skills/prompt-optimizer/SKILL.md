---
name: prompt-optimizer
description: Use when a user wants Codex to turn a legal, tax, or compliance question into a source-backed Deep Research prompt, with fact preservation, research posture, source hierarchy, citation rules, and deterministic validation. Do not use for general copywriting unrelated to Deep Research.
---

# Optimize Prompt

## Privacy Boundary

At workstream start, read `../../privacy/workstreams/prompt-optimizer.json` and
show its notice in the conversation language. The notice must state that text
already entered in Codex is already in model context. Do not claim that Vera can
remove or anonymize it retroactively.

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.

Resolve `../../modules/prompt-optimizer` from this skill directory when it
exists; otherwise resolve `../../../prompt-optimizer` in the repository. Read
that module's `skills/prompt-optimizer/SKILL.md` completely and follow it. Treat
the resolved module root as the plugin working directory for all commands.
