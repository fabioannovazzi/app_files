# Registra il flusso di download delle fatture dall'Agenzia

Questo strumento di Vera permette a un operatore autorizzato di eseguire una
volta, sul proprio computer, il percorso di download delle fatture. Produce una
piccola mappa JSON da controllare, utile agli sviluppatori per realizzare il
flusso guidato.

Non è il collegamento definitivo al portale e non scarica fatture per Vera.

## Che cosa registra

- le identità sanificate dei controlli cliccati o modificati dall'operatore;
- origine e percorso delle pagine Agenzia, senza query string o frammenti;
- inventari sanificati dei controlli interattivi dopo le transizioni;
- il suffisso e un hash del nome suggerito per gli eventuali download.

Non registra valori digitati o selezionati, credenziali, codici monouso,
cookie, memoria del browser, HTML, schermate, richieste o risposte di rete,
percorsi dei download, file delle fatture o contenuto delle fatture.

## Prima di iniziare

L'operatore deve avere:

- l'autorizzazione per accedere al profilo del contribuente interessato;
- Google Chrome installato;
- Python 3.11 o successivo;
- il requisito Python del registratore installato in un ambiente isolato.

Dalla cartella del plugin:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-portal-recorder.txt
```

In Windows PowerShell, attiva invece l'ambiente con
`.venv\Scripts\Activate.ps1`.

Lo script usa Google Chrome già installato e non richiede il download di un
browser separato.

## Esecuzione

```bash
source .venv/bin/activate
python scripts/record_agenzia_invoice_flow.py \
  --output-dir ~/Desktop/registrazione-flusso-fatture-agenzia
```

1. Facoltativamente, inserisci nomi di clienti o altre diciture riservate da
   oscurare. I termini non sono mostrati nel terminale, rimangono soltanto in
   memoria e non vengono salvati.
2. Verifica che sia comparsa una finestra Chrome dedicata. In Windows il
   registratore interrompe il flusso prima dell'accesso se rileva soltanto
   processi Chrome in background senza una finestra desktop visibile.
3. Accedi personalmente nella finestra Chrome dedicata.
4. Seleziona il contribuente o la delega corretta.
5. Raggiungi la pagina autenticata **Fatture e Corrispettivi**.
6. Quando le schermate di autenticazione non sono più visibili, di' a voce
   oppure scrivi `pronto` a Vera. Va bene anche `ready`.
7. Esegui un percorso rappresentativo di download. Se disponibili nella stessa
   sessione, mostra la scelta tra fatture attive e passive e il recupero di uno
   ZIP completato.
8. Quando hai finito, di' a voce oppure scrivi `fatto` a Vera. Va bene anche
   `done`.

Vera conferma i due messaggi nel terminale. Il profilo Chrome temporaneo e gli
eventuali byte di download gestiti da Playwright vengono eliminati alla fine.

## Controllo e condivisione

Prima di condividerlo, apri questo file:

```text
agenzia_invoice_flow_recording.json
```

Cerca nomi di clienti o contribuenti, codici fiscali, partite IVA, indirizzi
email, riferimenti a fatture, identificativi di sessione e qualsiasi altra
informazione riservata. Se rimane un'informazione di questo tipo, elimina la
registrazione invece di condividerla.

Condividi soltanto il JSON controllato. Non condividere mai il profilo Chrome
temporaneo, la cartella dati del browser, una sessione esportata, cookie, file
HAR o trace, schermate o ZIP contenenti fatture.

Se la richiesta asincrona e il successivo recupero dello ZIP non possono essere
completati nella stessa sessione, prepara due registrazioni controllate
separate: una per l'invio della richiesta massiva e una per il recupero del
risultato completato.
