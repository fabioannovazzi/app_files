---
name: fatture-xml-check
description: "Use when formally checking Italian FatturaPA XML files in a customer folder: parse invoice metadata, create CSV summaries, identify malformed XML, date issues, and duplicate candidates."
---

# Fatture XML Check

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.

Resolve `../../modules/client-file-preparation` from this skill directory when it exists;
otherwise resolve `../../../client-file-preparation` in the repository. Read that
module's `skills/fatture-xml-check/SKILL.md` completely and follow it. Treat the
resolved module root as the plugin working directory for all commands.
