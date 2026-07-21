---
name: journal-bank-reconciliation
description: Use when a user wants Codex to reconcile bank statements with journal or ledger exports, map variable customer formats, run deterministic amount/date/reference/beneficiary matching, and produce reviewable CSV/XLSX/JSON outputs.
---

# Journal-Bank Reconciliation

## Privacy Boundary

Before reading customer source or module-generated evidence, read
`../../privacy/workstreams/journal-bank-reconciliation.json`. Show its notice in
the conversation language in the Run Intake. Continue without a redundant
consent question unless the manifest explicitly requires confirmation.

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.

Resolve `../../modules/journal-bank-reconciliation` from this skill directory
when it exists; otherwise resolve `../../../journal-bank-reconciliation` in the
repository. Read that module's `skills/journal-bank-reconciliation/SKILL.md`
completely and follow it. Treat the resolved module root as the plugin working
directory for all commands.
