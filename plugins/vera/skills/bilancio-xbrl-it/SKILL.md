---
name: bilancio-xbrl-it
description: Use when an Italian professional accounting studio asks Vera to understand accounting evidence and intelligently prepare, update, reconcile, review, validate, or export an individual OIC civil-law annual financial statement; XBRL is a final output format, not the workflow identity.
---

# Bilancio intelligente

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.

Resolve `../../modules/bilancio-xbrl-it` from this skill directory when it
exists; otherwise resolve `../../../bilancio-xbrl-it` in repository source.
Read that module's `skills/bilancio-xbrl-it/SKILL.md` and
all references it requires completely and follow them. Treat the resolved
module root as the plugin working directory.

Run `python scripts/check_dependencies.py` before helper scripts. Do not
install undeclared or missing requirements at runtime.

Never write run outputs inside this Git workspace. Use the selected Studio
Archive engagement run. Vera prepares a reviewable draft; it does not sign,
approve corporate accounts, automate TEBENI, or file with Registro Imprese.
