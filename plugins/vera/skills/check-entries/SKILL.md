---
name: check-entries
description: Use when comparing qualified Journal Sampling entries with FatturaPA XML or supporting PDFs, running exact evidence checks, and producing lineage-bound review outputs.
---

# Check Entries

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.

In local Codex, create one separate prepared and started customer-folder run
per support evidence batch. Bind its exact immutable support receipts and the
exact normalized-population, diagnostics, and sample artifacts from one
Journal Sampling run. Also bind the normalization companions that assurance
replay reads: `normalization_recipe.json`, `suggested_recipe.json`,
`reviewed_decisions.json`, `assurance_gates.json`, `assurance_envelope.json`,
and `qualification_review_payload.json`. Execute only those run-local bindings,
check only sampled rows, and finalize every output with purpose and audience
before review/completion. Use the explicit new-run option for an intentionally
separate batch whose exact input selection matches an earlier run.

Resolve `../../modules/check-entries` from this skill directory when it exists;
otherwise resolve `../../../check-entries` in the repository. Read that
module's `skills/check-entries/SKILL.md` completely and follow it. Treat the
resolved module root as the plugin working directory for all commands.
