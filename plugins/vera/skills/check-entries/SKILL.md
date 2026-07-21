---
name: check-entries
description: Use when a user wants Codex to compare selected journal entries with supporting PDF documents, map entry columns, run deterministic amount/date/beneficiary checks, and produce reviewable CSV/XLSX/JSON outputs.
---

# Check Entries

## Privacy Boundary

Before reading customer source or module-generated evidence, read
`../../privacy/workstreams/check-entries.json`. Show its notice in the
conversation language in the Run Intake. Continue without a redundant consent
question unless the manifest explicitly requires confirmation.

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.

Resolve `../../modules/check-entries` from this skill directory when it exists;
otherwise resolve `../../../check-entries` in the repository. Read that
module's `skills/check-entries/SKILL.md` completely and follow it. Treat the
resolved module root as the plugin working directory for all commands.
