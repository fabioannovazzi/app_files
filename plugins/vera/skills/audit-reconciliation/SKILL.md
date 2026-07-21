---
name: audit-reconciliation
description: Use when a user wants Codex to reconcile accounting evidence across open-item lists, ledgers, journals, bank statements, payment orders, factoring or advance evidence, and compensation evidence, then produce audit-ready Excel and Word workpapers with deterministic classifications and a documented Codex review layer.
---

# Riconciliazione partite

## Privacy Boundary

Before reading customer source or module-generated evidence, read
`../../privacy/workstreams/audit-reconciliation.json`. Show its notice in the
conversation language in the Run Intake. Continue without a redundant consent
question unless the manifest explicitly requires confirmation.

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.

Resolve `../../modules/audit-reconciliation` from this skill directory when it
exists; otherwise resolve `../../../audit-reconciliation` in the repository.
Read that module's `skills/audit-reconciliation/SKILL.md` completely and follow
it. Treat the resolved module root as the plugin working directory for scripts,
requirements, assets, review servers, and outputs.
