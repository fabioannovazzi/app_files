---
name: purchase-invoice-review
description: Use to check a population of fatture passive FatturaPA XML against actual prima nota or booked ledger entries. Produces an exception workpaper for amounts, IVA, duplicates, reconciliation and reviewed account coherence. For only an already qualified journal sample use vouching; for XML validity without accounting entries use fatture-xml-check. Does not book invoices or write to the gestionale.
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

# Intelligent Passive-Invoice Audit

For a Geneva (CH-GE) mandate, read `../vera/references/localization/geneva.md` first and use this existing function’s Geneva adaptation in its resolved component skill. Language alone never selects jurisdiction.


After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.

Resolve `../../modules/passive-invoice-audit` from this skill directory when it
exists; otherwise resolve `../../../passive-invoice-audit` in the repository.
Read that module's `skills/purchase-invoice-review/SKILL.md` completely and follow
it. Treat the resolved module root as the plugin working directory for all
commands.
