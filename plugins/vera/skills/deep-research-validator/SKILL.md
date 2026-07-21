---
name: deep-research-validator
description: Use when a user wants Codex to validate a Deep Research answer or report against cited sources, review material claims, identify unsupported or weak reasoning, propose corrections, and package a validated document. Do not use for creating Deep Research prompts.
---

# Validate Deep Research

## Privacy Boundary

Before reading the report or module-generated evidence, read
`../../privacy/workstreams/deep-research-validator.json`. Show its notice in the
conversation language in the Run Intake. Continue without a redundant consent
question unless the manifest explicitly requires confirmation.

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.

Resolve `../../modules/deep-research-validator` from this skill directory when
it exists; otherwise resolve `../../../deep-research-validator` in the
repository. Read that module's `skills/deep-research-validator/SKILL.md`
completely and follow it. Treat the resolved module root as the plugin working
directory for all commands.
