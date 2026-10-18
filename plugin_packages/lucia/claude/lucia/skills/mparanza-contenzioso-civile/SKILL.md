---
name: mparanza-contenzioso-civile
description: Use when Lucia must prepare a civil litigation chronology, allegations and evidence matrix, procedural-date inputs or a reviewable pleading draft from selected matter files. Covers preparation and verification, not filing, notification, signature or litigation decisions.
---
<!-- MPARANZA_REPORTING_BEGIN -->
## Task reporting and recovery

For every substantive user mandate, follow
`skills/mparanza-lucia/references/workflow-usage.md` from this installation's root.
Start one primary task before preparation, using `usage/pipelines.json`; nested
specialists, retries and Studio Archive infrastructure reuse that task. Record
only the observed whole-task outcome. Discover `lucia_incident_host_link`,
including deferred tools, and verify this run's Computer ID on the server.
Build the report input from actual phases even for chat-only drafts; missing
client files or a prepared input JSON do not waive reporting. Show the readable
local model-data report under `skills/mparanza-lucia/references/model-data-report-contract.md`, link its
actual signed receipt, and ask once for the user's 1–5 stars after delivery.
Only user-authored feedback is submitted; tests remain explicitly marked.
Follow `skills/mparanza-lucia/references/incident-recovery.md` for automatic technical
reporting, evidence requests and targeted remedies. Use `luciaIncidents` if
local execution is unavailable. Never ask the user to relay logs or repeat consent
for technical reporting. Recovery requires an observed successful retry of the
original task and inputs, bound to the original report and current remedy.
Tutorials remain local-only and are excluded from task usage and ratings.
<!-- MPARANZA_REPORTING_END -->


# Preparare una pratica di contenzioso civile

Leggi integralmente `../mparanza-revisione-contratti/references/practice-workflow.md` e
applicalo. Crea il registro con `--kind contenzioso-civile`, salvo una run già
preparata da un playbook. Questo percorso usa gli stessi helper documentali;
non richiede installazioni aggiuntive o una banca dati separata.

## Impostare il caso

Ricava parte assistita, controparte, domanda/difesa, fase, giudice eventualmente
adito, data rilevante e materiali disponibili. Il titolo "comparsa" o un nome di
file non prova rito, competenza o scadenza. Leggi atto introduttivo, provvedimenti,
notifiche e ricevute effettivamente forniti. Conserva differenze tra allegazione,
ammissione, contestazione, prova e inferenza dell'avvocato.

Prepara temi come fatti, domande, eccezioni, prove, comunicazioni e date solo
quando pertinenti. Associa le prove alla proposizione che si intende sostenere;
spiega se il documento la sostiene, la contraddice o non basta. Non dedurre la
forza probatoria dal solo tipo di file.

## Prodotti concreti

Per una preparazione del fascicolo consegna `cronologia.md` e la matrice
`review.xlsx`/`review.html`, con fonti, eventi incerti e lacune. Una lista di
documenti non sostituisce una cronologia; una cronologia non è una ricostruzione
di fatti già accertati in giudizio.

Per date processuali prepara un `termini.md` con: evento iniziale e sua prova,
regola/versione realmente verificata, regime processuale e transitorio,
eventuali sospensioni/proroghe, calendario e calcolo dichiarato. Distingui
"data estratta da un provvedimento" da "scadenza calcolata". Se manca un
presupposto, lascia aperta soltanto quella scadenza e continua il resto del lavoro.
Non usare un numero fisso di giorni da una vecchia pratica o dal nome dell'atto.

Per una bozza usa il modello della comparsa/memoria/atto selezionato e la skill
Documents/Word dell'host. Mappa ogni fatto ai documenti; lascia visibili richieste,
eccezioni o conclusioni ancora da scegliere. Mantieni distinta la ricostruzione
avversaria da quella della parte assistita. Le conclusioni devono derivare dalla
scelta professionale documentata, non dalla compilazione meccanica del modello.
Verifica le citazioni richieste con `../mparanza-verifica-citazioni/SKILL.md` e controlla
errori/rinvii con `../mparanza-controllo-documento/SKILL.md` quando pertinente alla consegna.

## Fonti e domande mirate

Il [Codice di procedura civile su Normattiva](https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:regio.decreto:1940-10-28;1443)
è un punto di accesso: leggere disposizioni e versione applicabili al caso,
non citare il collegamento generale come verifica di un termine. Eventuali
provvedimenti del giudice e relative notifiche sono prove distinte dalla norma.

Chiedi fatti che cambiano un passaggio: quale atto e versione usare; prova e data
della notifica; mandato difensivo; documenti mancanti per una specifica allegazione.
Registra perché la domanda serve e quale prodotto blocca. Non bloccare la matrice
per una sola data ignota. Consegna bozze e scelte residue all'avvocato; nessun
deposito, notifica o attestazione di conformità fa parte di questo percorso.
