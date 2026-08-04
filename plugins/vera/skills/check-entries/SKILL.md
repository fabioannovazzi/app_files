---
name: check-entries
description: Use when comparing qualified Journal Sampling entries with FatturaPA XML or supporting PDFs, running exact evidence checks, and producing lineage-bound review outputs.
---

# Check Entries

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.

In local Codex, call `start_check_entries_from_sample` once per support evidence
batch with the selected Journal Sampling run and immutable support receipts.
Studio Archive resolves and validates the complete internal artifact handoff;
do not ask the user to name files or assemble artifact references. Execute only
the returned run-local bindings, check only sampled rows, and finalize every
output with purpose and audience before review/completion. Use the explicit
new-run option for an intentionally separate batch whose exact input selection
matches an earlier run.

Resolve `../../modules/check-entries` from this skill directory when it exists;
otherwise resolve `../../../check-entries` in the repository. Read that
module's `skills/check-entries/SKILL.md` completely and follow it. Treat the
resolved module root as the plugin working directory for all commands.
