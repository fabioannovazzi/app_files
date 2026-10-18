---
name: lavoro
description: Use when Lucia must review employment documents, prepare a dismissal-file chronology and evidence matrix, extract pay and employment terms, or calculate a specifically defined employment amount from documented inputs and verified applicable rules.
---
<!-- MPARANZA_REPORTING_BEGIN -->
## Task reporting and recovery

For every substantive user mandate, follow
`skills/lucia/references/workflow-usage.md` from this installation's root.
Start one primary task before preparation, using `usage/pipelines.json`; nested
specialists, retries and Studio Archive infrastructure reuse that task. Record
only the observed whole-task outcome. Build and show the readable local model-data
report under `skills/lucia/references/model-data-report-contract.md`, link its
actual signed receipt, and ask once for the user's 1–5 stars after delivery.
Only user-authored feedback is submitted; tests remain explicitly marked.
Follow `skills/lucia/references/incident-recovery.md` for automatic technical
reporting, evidence requests and targeted remedies. Use `luciaIncidents` if
local execution is unavailable. Never ask the user to relay logs or repeat consent
for technical reporting. Recovery requires an observed successful retry of the
original task and inputs, bound to the original report and current remedy.
Tutorials remain local-only and are excluded from task usage and ratings.
<!-- MPARANZA_REPORTING_END -->


# Preparare e controllare una pratica di lavoro

Leggi integralmente `../revisione-contratti/references/practice-workflow.md` e
applicalo. Crea il registro con `--kind lavoro`, salvo una run già preparata da
un playbook. Il modello seleziona le questioni dal caso; nessun classificatore
deduce contratto collettivo, regime del licenziamento o indennità da un'etichetta.

## Leggere il rapporto concreto

Identifica parte assistita, datore effettivo, rapporto, data di assunzione e
successive variazioni, mansioni/qualifica/livello documentati, periodo, sede e
fonti contrattuali. Registra orario e retribuzione con unità e periodo. Non
confondere netto, lordo mensile, RAL, imponibile previdenziale e costo azienda.

Il contratto collettivo applicato va verificato da documenti e contesto, con
versione e rinnovi pertinenti. L'[Archivio CNEL](https://www.cnel.it/archivio-contratti)
consente di reperire testi depositati; un codice o l'associazione con il settore
non prova da solo l'applicabilità alla persona. Annotare eventuali accordi
individuali, aziendali o territoriali rilevanti, senza ricercare archivi estranei
ai materiali selezionati.

## Prodotti concreti

Per revisione del contratto consegna una matrice dei termini con fonti,
ambiguità, scostamenti dall'incarico e proposte. Per un insieme di rapporti usa
`../revisione-documentale/SKILL.md`; non attribuire a tutti i lavoratori condizioni
lette in un solo contratto.

Per una pratica di licenziamento prepara `cronologia-lavoro.md` e la matrice:
fatti allegati, contestazione e ricezione, difese, provvedimento, comunicazioni,
documenti e date effettivamente disponibili. Distingui data della lettera da
data di ricezione. Il regime applicabile dipende dai fatti e dalle fonti del
periodo; verifica separatamente i presupposti rilevanti invece di imporre una
formula universale. Una domanda mancante sul regime non blocca la cronologia.

Per estrazione retributiva consegna dati per persona e periodo, fonte e limiti:
componenti fisse/variabili, mensilità, part-time, assenze, ratei e quanto richiesto
dal calcolo. Spiega i criteri di lettura; una busta paga non dimostra da sola il
numero di mensilità annuali o l'importo di un'indennità spettante.

Per danni o differenze richiesti definisci prima la voce e la base: regola
verificata, periodo, componenti incluse/escluse, quantità, eventuali detrazioni,
tassi, rivalutazione e fatti ancora mancanti. Produci con la skill Spreadsheets
dell'host un foglio ricalcolabile con fonti e formule, distinguendo simulazione da
somma giuridicamente dovuta. Nessun forfait o moltiplicatore viene ricavato dal
nome "licenziamento". Se manca una base, il risultato resta non disponibile e
il foglio mostra la domanda precisa; non inserire uno zero sostitutivo.

Le bozze di lettere/atti richieste usano il modello scelto e la skill
Documents/Word dell'host. Verifica norme e decisioni pertinenti tramite
`../verifica-citazioni/SKILL.md`, senza esporre dati del lavoratore nelle query.

## Consegna

Consegna il prodotto richiesto, dati/versioni/fonti utilizzati e scelte residue.
Non concludere che un recesso è valido o invalido dal solo esito di controlli
meccanici. Non comunicare con datore, lavoratore, enti o giudice; non trasmettere
lettere, scegliere un licenziamento o assumere decisioni professionali.
