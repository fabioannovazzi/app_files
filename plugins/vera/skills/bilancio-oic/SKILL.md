---
name: bilancio-oic
description: Use to prepare or review an individual Italian bilancio civilistico OIC from a bilancio di verifica in CSV/XLSX or readable/scanned PDF, prior XBRL and supporting schedules. Produces reviewed mappings, prospetti, nota integrativa and validation before XBRL export. For historical ratios or comparison alone use financial-analysis. Does not sign, approve corporate accounts or deposit/file them.
---

<!-- VERA_WORKFLOW_USAGE_BEGIN -->
## Task usage and user feedback

Before substantive work, follow `../vera/references/workflow-usage.md`: start one
retained task UUID for the primary user process (including AI-led work), reuse
it across helpers/resumption, and record only observed outcomes. Discover the
native `vera_incident_host_link` tool, including deferred tools, and verify the
same run's Computer ID on the server. Privacy reporting applies only to the fixed pipeline list in
`../vera/references/selective-reporting.md`, using the exact Studio Archive run.
Archive finalization generates eligible reports from saved execution evidence;
never create a report for other pipelines or a chat-only task. Link a signed
receipt only when one actually exists. After delivery ask once for the user's 1–5 stars and optional
comment; never infer a score. Studio Archive is infrastructure, not another rated
process. Synthetic/agent tests are marked and excluded. Flush pending delivery
at task startup and after outcomes. The shared contract applies even on direct
skill invocation and on both Codex and Cowork.
<!-- VERA_WORKFLOW_USAGE_END -->


<!-- VERA_CONNECTED_KNOWLEDGE_BEGIN -->
## Connected studio knowledge

When the user or an adopted studio instruction requests relevant repository
evidence, read `../vera/references/connected-studio-knowledge.md` before the
dependent work, including direct specialist invocation. Use only callable host
search/read tools; preserve citations and this workflow's qualification gates.
Without a repository, continue ordinary work. Studio skills remain independently
invoked by the user; Vera does not dispatch them.
<!-- VERA_CONNECTED_KNOWLEDGE_END -->

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

Per chiudere i conti prima di forma e mapping, segui anche
`skills/bilancio-oic/references/closing-workflow.md` del modulo risolto sotto:
fascicolo e screening rivisti, proposte di rettifica, decisioni professionali,
confronto esatto del nuovo bilancio di verifica e riesame delle verifiche
interessate. Nessuna registrazione contabile o richiesta al cliente è automatica.

Per carte di lavoro per area, applicabilità ricavata dai documenti, controlli OIC,
percorso proporzionato, dashboard ed Excel di revisione, segui anche
`skills/bilancio-oic/references/area-review.md` nel modulo risolto. Il pannello
esistente apre le aree e i documenti registrati; fonti reimportate e controlli
riaperti conservano le decisioni precedenti. I giudizi richiedono conferma
professionale separata.

For an existing Bilancio case, use `vera_workspace_open` when callable and the
exact case and Studio Archive run have trusted operator bindings. Read
`../vera/references/native-workspace.md` before the handoff. The panel inspects
issues and their sources through the canonical case service, and records an
explicit human issue decision against the exact revision. A decision invalidates
the current validation; it does not approve the accounts or authorize export,
signing or filing. Intake, mappings, source qualification, validation and final
handoff retain the specialist's existing gates. Without native tools or exact
bindings, continue persistent specialist work, including in Cowork.

For a Geneva (CH-GE) mandate, read `../vera/references/localization/geneva.md` first and use this existing function’s Geneva adaptation in its resolved component skill. Language alone never selects jurisdiction.


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
