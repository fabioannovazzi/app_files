# Prove e stato riprendibile

L'adattatore del prodotto stabilisce il suo root, l'ambiente condiviso, il
percorso assoluto `<helper-dir>` e la cartella di lavoro autorizzata. Esegui
prima il controllo delle dipendenze dichiarate. `prepare` richiede una directory
nuova: se il contenitore autorizzato esiste, scegli una sottocartella nuova
per `<run>`. Non passare un output Archive già creato e non reinizializzare
una run esistente. Riprendi la stessa directory per stato e report.
Se le dipendenze non sono disponibili, continua
con i materiali leggibili in chat e indica quali helper non sono stati eseguiti.
Non installare un ambiente nuovo nella pratica né aggirare limiti di rete.

```bash
python <helper-dir>/legal_documents.py prepare --run-dir <run> --workflow revisione-documentale --file <atto> --file <ricevuta> --topic "Evento e prova"
python <helper-dir>/legal_matter.py init --run-dir <run> --kind contenzioso-tributario --purpose "Obiettivo dell'incarico"
```

Scegli file e voci dal caso. Il motore copia originali, crea `evidence.json`,
checksum e `review.json`. Supporta PDF testuali, DOCX e TXT/Markdown UTF-8.
Leggi avvertenze e originali: una pagina senza testo non prova assenza del fatto.
Le ancore PDF sono pagine fisiche; quelle DOCX sono parti XML e paragrafi,
incluse tabelle, intestazioni, note, commenti e revisioni. Layout e oggetti
richiedono ispezione visiva. Conserva copertura e lacune, senza leggere contenuti
estranei soltanto perché estratti. Per nuove prove prepara una run successiva
e collega risposte e risultati ancora supportati senza mutare gli snapshot.

Leggi `legal_documents_review.schema.json` accanto al helper. Compila il
contesto (parte, legge, foro, periodo, istruzioni, fatti e presupposti), la
copertura realmente letta, ogni cella documento/voce e i riepiloghi. Le citazioni
usano source_id, ancora e testo letterale di quella fonte. `supported` riguarda
il riscontro testuale, non la correttezza giuridica. `not-stated` richiede
copertura completa e avvertenze risolte; conserva lacune come non esaminate o
illeggibili. Il modello controlla significato, eccezioni e applicabilità.

```bash
python <helper-dir>/legal_documents.py render --run-dir <run> --review <run>/review.json --product <Vera-or-Lucia>
```

Consegna HTML/CSV/XLSX realmente verificati. Una validazione fallita ritira il
rapporto precedente; non consegnarlo come risultato attuale.

Leggi `legal_matter.schema.json` accanto al helper e `matter.json`. Prepara un
file JSON distinto con fasi (pending/done/not-required, motivazione, outputs
relativi alla run) e domande (motivo, fasi dipendenti, stato, risposta e origine).
Il modello sceglie le dipendenze: continua i passaggi indipendenti e chiede solo
fatti materialmente necessari. Una preparazione completata non chiude una fase
di notifica, deposito o pagamento senza prova dell'azione esterna.

```bash
python <helper-dir>/legal_matter.py save --run-dir <run> --state <proposta.json> --expected-revision <revisione-letta>
python <helper-dir>/legal_matter.py status --run-dir <run>
python <helper-dir>/legal_matter.py render --run-dir <run>
```

Non sovrascrivere `matter.json`. Storia, revisioni e hash preservano domande,
risposte e file; gli aggiornamenti obsoleti sono rifiutati. Riprendi stato,
output e domande irrisolte prima di nuova produzione. Non eliminare un lock
prima di aver verificato l'arresto dello scrittore e la revisione corrente.
Consegna `matter.html` con gli elaborati: lo stato non prova completezza legale,
immutabilità della legge o approvazione del professionista.
