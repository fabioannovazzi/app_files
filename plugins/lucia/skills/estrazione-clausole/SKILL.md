---
name: estrazione-clausole
description: Use when Lucia must extract key terms from one legal document into a readable, source-linked table, including parties, term, renewal, termination, amounts, liability, governing law or forum, with missing and ambiguous terms visible.
---
<!-- MPARANZA_REPORTING_BEGIN -->
## Task reporting and recovery

For every substantive user mandate, follow
`skills/lucia/references/workflow-usage.md` from this installation's root.
Start one primary task before preparation, using `usage/pipelines.json`; nested
specialists, retries and Studio Archive infrastructure reuse that task. Record
only the observed whole-task outcome. Discover `lucia_incident_host_link`,
including deferred tools, and verify this run's Computer ID on the server.
Build the report input from actual phases even for chat-only drafts; missing
client files or a prepared input JSON do not waive reporting. Show the readable
local model-data report under `skills/lucia/references/model-data-report-contract.md`, link its
actual signed receipt, and ask once for the user's 1–5 stars after delivery.
Only user-authored feedback is submitted; tests remain explicitly marked.
Follow `skills/lucia/references/incident-recovery.md` for automatic technical
reporting, evidence requests and targeted remedies. Use `luciaIncidents` if
local execution is unavailable. Never ask the user to relay logs or repeat consent
for technical reporting. Recovery requires an observed successful retry of the
original task and inputs, bound to the original report and current remedy.
Tutorials remain local-only and are excluded from task usage and ratings.
<!-- MPARANZA_REPORTING_END -->


# Estrarre le clausole in una tabella

Leggi integralmente `../revisione-documentale/SKILL.md` e il suo contratto
documentale condiviso. Riusa quel motore con `--workflow revisione-documentale`:
non esiste un secondo estrattore. Il metodo di base deriva dalla revisione
tabellare di Mike; provenienza e licenza sono conservate nella skill riusata.

Questo percorso serve a leggere i termini di un contratto e ritrovarli nel testo.
Non trasformare una richiesta di estrazione in un parere negoziale o in un elenco
di clausole che dovrebbero esserci. Scegli i campi richiesti dal caso. Se l'utente
vuole una scheda generale, considera parti, oggetto, durata, rinnovo, uscita,
importi e termini di pagamento, responsabilità, legge e foro, rimuovendo ciò che
non serve. Usa termini del documento e spiega abbreviazioni ambigue.

Per ogni campo restituisci valore, clausola/ancora, citazione, eventuali condizioni
o eccezioni e incertezza. Esempio di forma, non di dato da riempire:

| Campo | Risultato | Fonte | Condizione o lacuna |
| --- | --- | --- | --- |
| Rinnovo | Il periodo espressamente previsto | Articolo e citazione effettivi | Preavviso/forma della disdetta se presenti |

Un rinnovo non può essere estratto ignorando l'eccezione nel comma seguente.
Distinguere recesso, disdetta e risoluzione; legge e foro sono due campi diversi.
Conserva valuta, unità, periodicità e imponibile/IVA come documentati. Non
calcolare RAL, prezzo annuo o penale totale da un importo privo di base temporale.

Gli allegati o le modifiche forniti restano fonti distinte; spiega quale testo
integra o modifica il dato e con quale prova. Non dichiarare "non previsto" se
una parte del documento o un allegato necessario non è leggibile. Le ancore DOCX
sono paragrafi XML, non numeri di pagina.

Consegna la scheda leggibile in HTML e la tabella Excel tramite il renderer
comune. La scheda ha una sola fonte principale salvo allegati/modifiche
selezionati. Per confrontare molti contratti usa direttamente la revisione
documentale a matrice. Mostra i termini realmente estratti, non un modulo vuoto
con istruzioni per l'avvocato.
