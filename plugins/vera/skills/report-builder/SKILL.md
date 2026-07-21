---
name: report-builder
description: Use when a user wants Codex to inspect financial Excel/CSV/text-PDF inputs, map tables to report sections, write or refine the report narrative in Codex, and produce reviewable Markdown/DOCX/JSON outputs.
---

# Build Report

## Privacy Boundary

Before reading customer source or module-generated evidence, read
`../../privacy/workstreams/report-builder.json`. Show its notice in the
conversation language in the Run Intake. Continue without a redundant consent
question unless the manifest explicitly requires confirmation.

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.

Resolve `../../modules/report-builder` from this skill directory when it exists;
otherwise resolve `../../../report-builder` in the repository. Read that
module's `skills/report-builder/SKILL.md` completely and follow it. Treat the
resolved module root as the plugin working directory for all commands.
