---
name: journal-bank-reconciliation
description: Use when reconciling bank statements with journal or ledger exports, mapping customer formats, matching exact amounts, dates, and references, and producing reviewable outputs.
---

<!-- VERA_OPENAI_ONBOARDING_BEGIN -->
Onboarding is optional. Continue ordinary professional work immediately,
including direct specialist invocation, without checking or completing a local
onboarding profile. Missing, unfinished, inaccessible or corrupt onboarding state,
or unavailable voice/window controls, must never block ordinary work. Do not
automatically start, resume or repeatedly offer onboarding.
Only for a user-requested tutorial or a native teaching handoff, read
`../vera/references/local-onboarding.md`. A verified paired lesson worker
executes only its bound lesson and token; never bypass tutorial validation.
Tutorial profiles, progress, examples and feedback remain local; never send a
change request, stamp a tutorial receipt or call hosted interviews for a tutorial.
Current user requests take precedence over saved preferences.
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

The module may admit a text PDF only when inspection recovers a consistent,
labelled physical table and the professional approves a source-bound mapping
of date, incoming/outgoing or signed amount, sign convention, and every
excluded monetary column such as running balance. If either source is generic,
inconsistent, or OCR-only PDF text, follow the module's unsupported PDF hard
stop even when the user asks to proceed anyway. Do not switch to generic Codex
extraction, ad hoc scripts, or another parser inside this Vera run. Preserve
`vera:journal-bank-reconciliation` as the workflow provenance, report zero
emitted movements and no reconciliation deliverable, request a labelled text
PDF table or reviewed CSV/XLSX export, and stop dependent work.
