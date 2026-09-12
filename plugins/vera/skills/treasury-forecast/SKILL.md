---
name: treasury-forecast
description: Prepare and maintain a reviewed EUR treasury forecast from supported accounting and bank tables, retaining assumptions and explaining changes between updates.
---

<!-- VERA_OPENAI_ONBOARDING_BEGIN -->
Before substantive work in desktop Codex or local ChatGPT Work, follow the
mandatory one-off local onboarding gate in `../vera/references/local-onboarding.md`.
Load the same local professional profile on every session. A verified paired
lesson worker follows only its active lesson handoff; never recursively onboard
it. Tutorial runs and their feedback stay local. Current user requests take
precedence over saved preferences. This gate does not apply to Claude Cowork.
<!-- VERA_OPENAI_ONBOARDING_END -->

# Budget di tesoreria

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.

Resolve `../../modules/treasury-forecast` from this skill directory in installed
Vera, or `../../../treasury-forecast` in repository source. Read that module's
`skills/treasury-forecast/SKILL.md` completely and follow its input contract.
Use the module root as the plugin working directory for helper commands. Required missing inputs stop the
workflow. Supplied FatturaPA XML is supported evidence; Agenzia downloading is
not a prerequisite and is not implemented by this workflow.
