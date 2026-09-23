# Esecuzione delle pratiche specialistiche

Questo contratto collega i percorsi contenzioso civile, M&A, lavoro e recupero
crediti agli strumenti documentali effettivi. Non è un nuovo backend e non
trasforma un'area di pratica in una classificazione automatica del diritto.

## Aprire il lavoro richiesto

Leggi `document-workflow.md` e `prassi-italiana.md`. Individua parte assistita,
obiettivo, fase, documenti selezionati, periodo e questioni ancora aperte. Se
esiste una pratica con output già assegnato, usalo; altrimenti scegli con il
contesto disponibile una cartella locale del lavoro, esterna al plugin. Non
obbligare a un'apertura anagrafica o a una lezione per usare questi percorsi.

Prepara le prove con `legal_documents.py prepare --workflow revisione-documentale`,
usando voci pertinenti al caso. Il risultato comprende copie, ancore e matrice
inizialmente non esaminata. Se le istruzioni dello studio sono un playbook
selezionato, usa `legal_playbook.py prepare` e riusa la sua run e il suo registro.

Crea o riprendi il registro con `legal_matter.py`, secondo `matter-progress.md`.
Per una run nuova usa il `kind` della skill specialistica. Scegli i passaggi dal
lavoro effettivo, non da una checklist da completare sempre. Ogni passaggio concluso
deve avere un file reale, un motivo e nessuna domanda materiale ancora bloccante.
Non marcare "non richiesto" un risultato che l'avvocato ha richiesto ma manca.

## Leggere e produrre

Compila la matrice `review.json` con una voce per documento/tema, citazioni
esatte, ragionamento, proposte e copertura. Conserva le celle mancanti, ambigue o
illeggibili. La skill specialistica indica le domande e i prodotti pertinenti;
non attivare tutti i suoi esempi a prescindere dal caso.

Le cronologie, le liste di questioni e le bozze devono rinviare a queste prove:
data o intervallo come documentato; evento; soggetto; fonte/ancora; grado di
certezza; versione; conflitti con altre fonti. Distingui data del documento,
data dell'evento, data di ricezione/notifica e data riferita da una parte. Non
assegnare una data precisa a un evento incerto per poterlo ordinare. Una lettera
di parte prova che quella dichiarazione esiste, non automaticamente il fatto
dichiarato. Non trattare assenza nel materiale selezionato come prova di inesistenza.

Per ogni output derivato controlla che non introduca fatti, importi, date,
citazioni o conclusioni che la matrice non sostiene. Esegui
`legal_documents.py render` per il rapporto e la matrice con i loro controlli.
I passaggi di ricerca e interpretazione giuridica richiesti usano
`../../verifica-citazioni/SKILL.md` o, per un nuovo quesito/parere, il percorso completo
`../../quesito-legale-fiscale/SKILL.md`. Non replicare la review canonica già eseguita.

## Word e calcoli

Per atti, contratti, lettere, revisioni e commenti usa la skill Documents/Word
disponibile nell'host e `word-handoff.md`. Riusa il modello effettivamente scelto.
Se manca un modello essenziale all'incarico, chiedilo e continua sulle prove.
Se l'utente vuole una bozza strutturata senza modello, dichiarane la natura e
mantieni segnaposto visibili; non presentarla come atto pronto al deposito.

Per un calcolo usa la capacità Spreadsheets dell'host, leggendo integralmente
la sua skill, con formule visibili, input separati dai risultati e fonti accanto
ai valori. Non creare un motore giuridico a soglie o installare pacchetti per
calcolare. Verifica aritmetica e ricalcolo su valori noti, zero e dati mancanti,
e riapri il file esportato. Se il motore non ricalcola, dichiara la limitazione;
valori memorizzati e formule scritte non provano da soli che il foglio funzioni.

Il modello e l'avvocato definiscono il regime e i presupposti, con fonti e fatti:
tipo di somma, base, periodo, decorrenza, inclusione/esclusione dei giorni,
pagamenti/imputazioni, tasso, divisore, arrotondamento, eventuali sospensioni e
capitalizzazioni. Il foglio applica soltanto quei dati. Un input assente produce
un risultato non disponibile, non zero. Un numero preciso non risolve una
questione giuridica incerta. Conserva scenari alternativi solo se utili all'incarico
e spiega quale scelta fa variare il risultato.

## Consegna e ripresa

Consegna i prodotti effettivamente richiesti, matrice delle prove, domande residue
e registro `matter.html`. Per ciascuno indica scopo, fonti, stato e limiti.
Riapri stato e hash per riprendere il lavoro, senza chiedere di nuovo risposte
già documentate. Mantieni separati preparazione, controllo e approvazione finale.
Questi percorsi non firmano, notificano, depositano, inviano o eseguono atti.

I file letti, compresi nomi, fatti riservati, importi e bozze, entrano nel contesto
del modello della conversazione. I nuovi helper locali non fanno richieste di
rete. Le eventuali ricerche dell'host usano riferimenti giuridici generali;
nessun documento cliente deve finire nelle query o in un servizio esterno.
