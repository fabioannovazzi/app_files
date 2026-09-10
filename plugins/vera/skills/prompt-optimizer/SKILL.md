---
name: prompt-optimizer
description: Use automatically before Vera answers any accepted substantive legal, tax, or compliance question or prepares source-backed professional drafting that needs an answer contract and generation instructions for direct Codex work or a ChatGPT Deep Research handoff. The user never needs to request prompt optimization. Do not use this skill as a substitute for a missing operational return, declaration, filing, or form workflow.
---

# Plan The Answer

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.

Resolve `../../modules/prompt-optimizer` from this skill directory when it
exists; otherwise resolve `../../../prompt-optimizer` in the repository. Read
that module's `skills/prompt-optimizer/SKILL.md` completely and follow it. Treat
the resolved module root as the plugin working directory for all commands.

## Optional ChatGPT Deep Research handoff

Before providing this handoff, identify the exact optimized_prompt.md and the
separate ChatGPT account or workspace chosen by the user. The full prompt,
including material client names, case facts, dates and amounts, enters ChatGPT
model processing when the user pastes it there. It is not covered by the
originating Codex or Cowork account arrangement. Obtain the route choice if it
is not already explicit. The user checks the destination account's plan,
training controls and retention before professional use or when terms change;
Vera cannot inspect or enforce them. No helper uploads the prompt or
anonymizes it. Vera records this optional destination in the prompt-optimizer
external-boundary manifest; its runtime profiles describe only the originating
Codex and Cowork sessions. For direct drafting, continue in the selected runtime.
