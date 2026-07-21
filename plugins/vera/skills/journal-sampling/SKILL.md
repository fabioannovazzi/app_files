---
name: journal-sampling
description: Use when a user wants Codex to extract accounting journal entries from variable Excel, CSV, print-friendly Excel, or text PDF formats, map columns, normalize deterministic rows, and generate reproducible audit samples with diagnostics and an audit trail.
---

# Journal Sampling

## Privacy Boundary

Before reading customer source or module-generated evidence, read
`../../privacy/workstreams/journal-sampling.json`. Show its notice in the
conversation language in the Run Intake. Continue without a redundant consent
question unless the manifest explicitly requires confirmation.

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.

Resolve `../../modules/journal-sampling` from this skill directory when it
exists; otherwise resolve `../../../journal-sampling` in the repository. Read
that module's `skills/journal-sampling/SKILL.md` completely and follow it. Treat
the resolved module root as the plugin working directory for all commands.
