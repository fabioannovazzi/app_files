# Prima del grafico, il significato dei dati

Percorso guidato di circa 6 minuti e mezzo. Avvio della voce, elaborazioni esterne ed esercizio facoltativo sono separati dal tempo della lezione.

Nella chat insegnante parli con la voce standard di Codex. Nella seconda chat, aperta accanto, guardi i file e il risultato. Le due chat restano abbinate; puoi interrompere, chiedere perché o rallentare in qualsiasi momento.

Usa questi contenuti già pronti. Non riscrivere la lezione né inventare risultati. Parla in brevi turni, lascia il tempo di guardare e ascolta le risposte reali. Non leggere la soluzione prima del tentativo. I tempi includono osservazione e dialogo, non solo il testo parlato. Mostrare questi file non completa demo, pratica o comprensione nel registro locale. Il docente sceglie semanticamente il workflow adatto dal solo catalogo del proprio prodotto.

## 1. Il tuo obiettivo · 45 s

Ascolta la richiesta. Collega il caso a un lavoro che fai già.

Il dataset fittizio riporta vendite nette: gennaio 40.000 EUR e febbraio 50.000 EUR. Un campo 'Discount' non è presente. Le note della fonte confermano che Sales è già al netto degli sconti, quindi sottrarli ancora sarebbe errato.

Clara, mostrami l'andamento delle vendite e spiegami quali dati stai usando.

## 2. Da quali dati partiamo · 60 s

Guarda i documenti nella chat accanto. Individua un dato utile e un'informazione mancante.

R1 contiene due mesi; R2 definisce Sales come vendite nette. Il ruolo Discount è assente come misura separata in questo dataset, non un importo pari a zero.

[["2026-01", "40.000 EUR", "Vendite nette"], ["2026-02", "50.000 EUR", "Vendite nette"], ["Discount separato", "Assente", "Già incorporato in Sales"]]

## 3. Come lavora il workflow · 75 s

Segui i tre passaggi. Fermati sulla scelta che cambia il risultato.

Esegui l'intake e leggi dati, profilo e note. Rivedi significato, aggregazione e ruoli Sales, Discount e COGS; un'intestazione non basta.
Seleziona una capacità compatibile con le metriche rivedute e genera il grafico attraverso l'adapter di Clara. Conserva richiesta e prove dell'output.
Apri il risultato, verifica valori, unità, periodi e conclusione. Per upload successivi riusa il contratto semantico stabile quando compatibile, senza reinventarlo a ogni file.

## 4. Leggiamo il risultato · 90 s

Apri l'esempio nella seconda chat. Collega ogni conclusione alla sua fonte.

Le vendite nette passano da 40.000 a 50.000 EUR: +10.000 EUR, pari a +25%. Non disponiamo di una misura separata degli sconti o dei costi.

[["Gennaio", "40.000 EUR", "R1 · vendite nette"], ["Febbraio", "50.000 EUR", "R1 · vendite nette"], ["Variazione", "+10.000 EUR · +25%", "Base gennaio 40.000 EUR"]]

## 5. Il controllo che conta · 75 s

Prima di aprire la risposta, spiega a voce cosa controlleresti.

Compatibilità tecnica e corretto significato della metrica sono controlli diversi. Un dataset può avere colonne valide e una mappatura semanticamente sbagliata.

Non c'è Discount: possiamo dire che non sono stati concessi sconti?

Confronta il ragionamento: No. La fonte dice che Sales è netto; non fornisce una misura separata. L'assenza della colonna non dimostra assenza di sconti.

## 6. Proviamo insieme · 45 s

Scegli se provare ora o conservare l'esempio per il prossimo incarico.

Aggiungi marzo con la stessa definizione di Sales e verifica il riuso del contratto e l'aggiornamento del grafico.

Seleziona CSV, Excel o Parquet e le note che spiegano le metriche. Per Actual/Budget Clara usa la propria route di budget nello stesso workflow.

Questo è un esempio didattico preparato, non la ricevuta di una nuova esecuzione. Le fonti e le decisioni sono fittizie; nessuna approvazione del professionista è implicita. Per lavorare sui tuoi file, il workflow corrente esegue i propri controlli e conserva i risultati effettivi.

La biblioteca, il profilo e i progressi della lezione restano sul computer. Non vengono inviati a Mparanza. La voce e i contenuti letti in chat sono elaborati dall'account OpenAI: salvare in locale non significa inferenza offline.
