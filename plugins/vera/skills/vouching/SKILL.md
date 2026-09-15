---
name: vouching
description: Use when comparing qualified Journal Sampling entries with FatturaPA XML or supporting PDFs, running exact evidence checks, and producing lineage-bound review outputs.
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

# Vouching

Use the localized public name: **Vouching** (en), **Verifica documentale** (it),
**Contrôle sur pièces** (fr), **Belegprüfung** (de), and
**Verificación documental** (es). Explain that the workflow compares sampled
entries with supporting documents. The skill identifier is `vouching`.

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
module's `skills/vouching/SKILL.md` completely and follow it. Treat the
resolved module root as the plugin working directory for all commands.
