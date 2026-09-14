---
name: journal-bank-reconciliation
description: Use when reconciling bank statements with journal or ledger exports, mapping customer formats, matching exact amounts, dates, and references, and producing reviewable outputs.
---

<!-- VERA_OPENAI_ONBOARDING_BEGIN -->
Before substantive work in desktop Codex or local ChatGPT Work, follow the
mandatory one-off local onboarding gate in `../vera/references/local-onboarding.md`.
Load the same local professional profile on every session. A verified paired
lesson worker follows only its active lesson handoff; never recursively onboard
it. Tutorial runs and their feedback stay local. Current user requests take
precedence over saved preferences. This gate does not apply to Claude Cowork.
<!-- VERA_OPENAI_ONBOARDING_END -->

# Journal-Bank Reconciliation

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.

Resolve `../../modules/journal-bank-reconciliation` from this skill directory
when it exists; otherwise resolve `../../../journal-bank-reconciliation` in the
repository. Read that module's `skills/journal-bank-reconciliation/SKILL.md`
completely and follow it. Treat the resolved module root as the plugin working
directory for all commands.

The base bounded source contract is `journal_bank.tabular.v6`: ambiguous
day/month text requires a source-bound `day_first` or `month_first` receipt.
The additive `journal_bank.tabular.v7` contract requires an exact current
mapping receipt for Italian textual-month dates (`date_locale: it`) or reviewed
blank-date/no-reference summary labels; it never silently upgrades v6 sources.
Before reporting native values, require the module's fresh
`material_value_ledger.json` replay and review the unclassified exact
`relationship_residuals.csv`; do not infer a residual disposition.

If either source is a generic or OCR-only PDF, follow the module's unsupported
PDF hard stop even when the user asks to proceed anyway. Do not switch to
generic Codex extraction, ad hoc scripts, or another parser inside this Vera
run. Preserve `vera:journal-bank-reconciliation` as the workflow provenance,
report zero emitted movements and no reconciliation deliverable, request a
reviewed CSV/XLSX export, and stop dependent work.
