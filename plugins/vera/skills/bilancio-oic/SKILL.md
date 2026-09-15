---
name: bilancio-oic
description: Use when an Italian professional accounting studio asks Vera to understand spreadsheet or readable/scanned PDF accounting evidence and intelligently prepare, update, reconcile, review, validate, or export an individual OIC civil-law annual financial statement; XBRL is a final output format, not the workflow identity.
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

# Bilancio intelligente

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.

Resolve `../../modules/bilancio-xbrl-it` from this skill directory when it
exists; otherwise resolve `../../../bilancio-xbrl-it` in repository source.
Read that module's `skills/bilancio-oic/SKILL.md` and
all references it requires completely and follow them. Treat the resolved
module root as the plugin working directory.

Run `python scripts/check_dependencies.py` before helper scripts, adding
`--input <trial-balance.pdf>` for PDF intake. Do not install undeclared or
missing core requirements at runtime. Follow the resolved module skill's exact
approval-gated managed OCR setup when the checker reports
`OCR_SETUP_REQUIRED`.

Never write run outputs inside this Git workspace. Use the selected Studio
Archive engagement run. Vera prepares a reviewable draft; it does not sign,
approve corporate accounts, automate TEBENI, or file with Registro Imprese.
