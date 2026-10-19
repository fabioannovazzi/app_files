---
name: contenzioso-tributario
description: "Prepare or resume Italian tax litigation for an authorized commercialista: reuse notice intake, verify procedural steps and sourced deadlines, organize evidence and prepare ricorsi, appelli or memorie with saved progress. Does not file, serve, sign, pay or activate reminders."
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

# Contenzioso tributario con Vera

Vera fornisce il metodo procedurale. Il commercialista conferma fatti, ricevute,
incarico e abilitazione e compie gli atti professionali; non deve programmare
la sequenza. Verifica la Sezione A e la competenza per la fase effettiva.
Il nome Vera non prova l'abilitazione dell'utente. Mantieni i limiti della guida
per Cassazione, revocazione e ottemperanza.

## Metodo condiviso

Risolvi `../../vendor/modules/italian_tax_litigation` dalla directory di questa
skill se presente; nel repository risolvi invece
`../../../_shared/vendor/modules/italian_tax_litigation`. Leggi `workflow.md`
integralmente e tutti i suoi riferimenti. Non parafrasare, abbreviare o sostituire
il metodo. Leggi anche `../quesito-legale-fiscale/SKILL.md` quando il metodo
richiede ricerca. I passaggi e i termini dipendono dai fatti e dalle fonti,
non da un classificatore o dal nome della professione.

Dal root del prodotto controlla `python scripts/check_dependencies.py` e
`python scripts/managed_python_runtime.py status`; usa il Python dell'ambiente
condiviso riportato per i helper. Le dipendenze sono dichiarate nei requirements
del prodotto e nella ricetta condivisa, fuori dalle cartelle dei clienti.

Il root è `../..` da questa skill. Nel pacchetto `<helper-dir>` è
`../../vendor/modules/scripts`; nel repository, se quel percorso manca, è
`../../../lucia/scripts`. Risolvilo in assoluto. I pacchetti includono gli
stessi helper canonici di Lucia; non richiedono un'installazione di Lucia.

Per una pratica Studio Archive risolvi cliente e incarico tramite
`../studio-archive/SKILL.md` e usa cartelle e output autorizzati. Se l'utente
fornisce direttamente un atto per una nuova analisi, continua il lavoro
autorizzato e chiedi solo il contesto che cambia l'esecuzione; non inventare
cliente, incarico, percorso o stato di un intake. Se l'atto deve ancora essere
preparato, leggi `../avviso-intake/SKILL.md` e segui il suo contratto una volta.
Riusa l'intake già esaminato e gli originali pertinenti. Per un incarico
gestito in Studio Archive avvia una run distinta di contenzioso nel medesimo
incarico e usa il suo output autorizzato. Per `legal_documents.py prepare`,
`<run>` è una nuova sottocartella di quell’`output_dir`, non l’`output_dir`
già creato da Archive. Riprendi la stessa sottocartella e il suo `matter.json`
finché la run Archive è aperta e non sigillata. Se è sigillata o completata,
per gli aggiornamenti richiesti prepara una run successiva del medesimo incarico
con originali e nuove prove selezionati e con lo stato/elaborati precedenti come
upstream. Prepara un nuovo evidence pack e riporta soltanto risposte e fasi
ancora sostenute, con provenienza e citazioni verificate sul nuovo pack; non
mutare gli snapshot o il `matter.json` della run precedente. Non scrivere in un intake completato
o sigillato. Registra gli elaborati e i report della nuova run prima di
completarla. Preserva risultati, ricevute e prove delle run anteriori.

Per il Word usa Documents/Word dell'host e il modello scelto. Verifica
fonti, citazioni, testo e layout nel medesimo lavoro. Alla consegna leggi e
segui `../vera/references/model-data-report-contract.md`: mostra il report
leggibile della lavorazione e collega il file salvato, indicando materiali
realmente letti, attività locali e servizi esterni realmente usati. Il report
non prova elaborazione offline né anonimizzazione degli atti.

After substantive use of this workflow, read and follow the `Plugin Improvement Feedback` section in `../vera/SKILL.md`.


## Optional maintained Codex review panel

Read `../vera/references/native-workspace.md` before opening the panel.

On Codex, the optional **Pratiche e formato documenti** panel opens an existing, explicitly connected tax matter. Read `../vera/references/native-practice-reviews.md` for the trusted local-service binding. It shows saved questions, stages, outputs and a source-linked calendar. Enter actual event/date/term/status, basis and reviewer; attach literal citations to existing source units. Save only after explicit confirmation. The unchanged public matter writer retains the prior version and verifies citations and dates. The calendar does not calculate or certify legal deadlines, authenticate the reviewer, notify, file or update an external calendar. Discussion reads only the exact saved selected item and its cited units.

The ordinary connected-file workflow remains available when the native panel is unavailable.
