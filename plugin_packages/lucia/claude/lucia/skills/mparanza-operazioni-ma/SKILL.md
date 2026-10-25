---
name: mparanza-operazioni-ma
description: "Use when Lucia must prepare buyer- or seller-side M&A document work: NDA review, contract extraction, due-diligence matrices, SPA issue lists and disclosure cross-checks tied to selected documents and firm instructions."
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
reporting, evidence requests and targeted remedies. Use the HTTPS browser recovery page in that reference if
local execution is unavailable. Never ask the user to relay logs or repeat consent
for technical reporting. Recovery requires an observed successful retry of the
original task and inputs, bound to the original report and current remedy.
Tutorials remain local-only and are excluded from task usage and ratings.
<!-- MPARANZA_REPORTING_END -->


# Rivedere documenti di un'operazione M&A

Leggi integralmente `../mparanza-revisione-contratti/references/practice-workflow.md` e
applicalo. Crea il registro con `--kind operazioni-ma`, salvo una run già
preparata da un playbook. Seleziona il prodotto richiesto: non imporre una due
diligence completa a chi chiede la revisione di un solo NDA.

## Perimetro dell'operazione

Identifica parte rappresentata, acquirente/venditore, struttura dell'operazione
come documentata, società/ramo interessato, fase, legge e documenti inclusi.
Non dedurre una cessione di quote da un generico "acquisto". Versioni, allegati,
side letter, modifiche e periodo sono parte del perimetro; il solo contratto
originario può non descrivere i termini attuali.

Le posizioni dello studio e del cliente orientano la negoziazione. Seleziona il
playbook effettivo con `../mparanza-metodo-studio/SKILL.md`; non importare massimali o
periodi standard da operazioni estranee. Obiezione giuridica e preferenza della
parte vanno motivate separatamente, anche per testi in inglese regolati da altro
diritto. Non tradurre automaticamente una categoria di common law in un rimedio
italiano equivalente.

## Prodotti concreti

- Per un NDA usa `../mparanza-revisione-contratti/SKILL.md`: finalità, destinatari, uso,
  divulgazioni consentite, durata, restituzione, responsabilità e foro sono temi
  da selezionare sul testo, non un elenco di difetti presunti. Se richiesto,
  consegna il Word con revisioni native e commenti verificati.
- Per contratti o due diligence usa `../mparanza-revisione-documentale/SKILL.md`: matrice
  per documento con termini, fonti e questioni. Change of control, cessione,
  recesso, esclusiva o cap sono colonne solo se pertinenti all'operazione.
  Conserva contratti illeggibili, versioni mancanti e conflitti tra allegati.
- Per lo SPA prepara `questioni-spa.md`: clausola/versione, posizione della
  parte, prova o istruzione di riferimento, conseguenza ipotizzata, proposta,
  scelta ancora aperta. Può diventare un redline Word tramite la skill documentale.
- Per le disclosure prepara `riscontro-disclosure.md`: dichiarazione/garanzia,
  disclosure corrispondente, documenti citati, coerenza e lacune. Distinguere
  "nessuna disclosure nel materiale ricevuto" da "nessuna eccezione esiste".

Usa la matrice verificata come base di ogni sintesi. Un valore estratto è un dato
del documento, non una conclusione su validità, trasferibilità o opponibilità.
La ricerca giuridica richiesta deve controllare fonti e periodo pertinenti con
il percorso canonico; il codice non classifica automaticamente i rischi.

## Ripresa e consegna

Per un termine, allegato o posizione mancante registra una domanda che blocchi
soltanto la conclusione dipendente. Riepiloga perimetro letto, esclusioni,
operazioni sul testo e decisioni da assumere. Consegna matrice e prodotto
richiesto con un registro delle fonti, versioni e istruzioni applicate.
Non promettere copertura di tutta la data room se è stato letto un sottoinsieme.
Questo percorso non esegue closing, firma, comunicazioni a controparti o depositi.
