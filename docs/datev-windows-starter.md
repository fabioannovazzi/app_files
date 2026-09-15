# Avvio Vera su DATEV Windows

## Cosa introduce

`datev-invoice-start` guida una prova reale di una fattura usando la procedura
già sviluppata per ECONS. Il router la seleziona prima dell'onboarding generico
e dell'automazione browser. La procedura è inclusa nella distribuzione Vera;
Francesco non deve recuperare il materiale del precedente tester.

La skill verifica gli strumenti nativi dell'host e i fatti dell'installazione,
guida il primo esempio, salva progressi e report per cliente, e prepara una
richiesta tecnica da evidenza anche parziale. Il codice locale registra la
provenienza e le revisioni; le azioni native sono compiute tramite i soli strumenti
documentati dall'host corrente. Non è un esecutore DATEV unattended.

## Evidenza e limite di piattaforma

- Versione candidata DATEV: 0.1.256. La 0.1.255 appartiene al rilascio di
  recupero della PR #635; prima della pubblicazione DATEV occorre integrare
  quel rilascio, ricostruire e verificare i pacchetti combinati.
- Base sorgente ispezionata: `8d555b00`, coincidente con `origin/main` il
  15 settembre 2026; Vera sorgente e Marketplace Published 0.1.254. Il registro
  pubblico del sito era ancora 0.1.253. Questi sono gli stati iniziali osservati,
  non il certificato di pubblicazione della nuova versione.
- Le regole condivise provengono da `econs-review.md`, `econs_review.mjs`,
  `econs_processing.mjs` e dai relativi test. CR-42 è un'accettazione di Fabio;
  non sono stati verificati indipendentemente due replay live puliti.
- La [documentazione ufficiale OpenAI](https://learn.chatgpt.com/docs/computer-use)
  consultata il 15 settembre supporta Computer Use nativo su Windows nelle
  regioni supportate. DATEV deve essere visibile sul desktop attivo e sbloccato;
  il controllo occupa mouse e tastiera. Disponibilità e permessi si verificano
  nell'host reale, non da un'importazione Playwright.
- Questo sviluppo è avvenuto su macOS, senza DATEV o accesso al PC di Francesco.
  Restano da osservare prodotto/versione, contesto locale o remoto, finestra,
  controlli, popolazioni, mappature, trattamento del cliente e risultati reali.
- La route nativa viene distribuita per OpenAI; il builder Cowork la esclude
  esplicitamente. I pacchetti mantengono la versione canonica del prodotto.

## Struttura e verifiche

| Elemento | Responsabilità |
| --- | --- |
| `plugins/browser-automation/references/passive-invoice-procedure.md` | Procedura condivisa, con regole ed evidenza di origine |
| `plugins/vera/skills/datev-invoice-start/SKILL.md` | Percorso italiano, verifica host, esempio, salvataggio e trasmissione revisionata |
| `plugins/vera/scripts/datev_starter.py` | `start`, `record`, `resume`, `save-review`, `prepare-request` |
| `teaching_checkpoint.py`, `batch_review.py`, `development_request.py` | Contratti esistenti riusati; nessuna nuova forma di ricevuta browser |
| `plugins/vera/scripts/change_requests.py submit-suggestion` | Invio del solo testo con consenso e CR restituito dal server |

La sorgente dell'evidenza nativa resta esplicita (`host_tool`, operatore,
riferimento o ignoto). La categoria di trasporto storica `operator_report`
non certifica un'osservazione browser. Nessun hash di cattura è inventato.
Le revisioni del report conservano anche controlli e richieste di correzione
successivi; i risultati ambigui devono essere riconciliati prima di riprovare.

La suite `test_vera_datev_starter.py` verifica il flusso locale completo, compreso
un host indisponibile, ripresa, report per cliente, correzioni, richiesta parziale,
archivio revisionato, chiamata API simulata e confini di provenienza/percorso.
Il job CI lo esegue su Linux e Windows con copertura minima 80%.
`test_browser_econs_review.mjs` mantiene la regressione della procedura ECONS.
Questi sono test sintetici: non attestano una fattura letta o contabilizzata in DATEV.

## Accettazione sul PC del tester

1. Versione Vera effettiva e prodotto/versione DATEV registrati; nessun dato
   del precedente tester utilizzato.
2. Finestra effettivamente osservata con gli strumenti nativi autorizzati,
   oppure limite host preciso salvato senza azioni simulate.
3. Una fattura reale nel report del cliente, con descrizioni complete,
   mappature attuali, trattamento proposto e provenienza. Il perimetro di una
   fattura non dimostra la completezza dell'intero portafoglio.
4. Ripresa della stessa sessione da una revisione verificata, senza ripetere
   la spiegazione professionale o un'azione dall'esito ambiguo.
5. Se richieste mappatura e registrazione: condizioni della procedura
   soddisfatte, autorizzazione effettiva, protocollo e assenza dalla lista
   completa delle non contabilizzate dello stesso cliente verificati.
6. Per un adattamento mancante: testo tecnico esatto mostrato e sanificato,
   autorizzazione di invio, CR-N reale. Un eventuale ZIP resta un invio separato.

## Messaggio breve per Francesco

Da inviare quando la versione con questa funzione è disponibile nella sua
installazione; il semplice messaggio non aggiorna il plugin.

> Ciao Francesco, aggiorna Vera nell'app desktop di ChatGPT, apri Codex sul PC
> Windows con DATEV e incolla il testo qui sotto. Vera contiene già la procedura
> delle fatture passive: partirete da una sola fattura. Tieni DATEV aperto e il
> PC sbloccato durante la prova.

> Vera, iniziamo la prova delle fatture passive su DATEV installato come programma
> Windows. Usa la procedura già predisposta: verifica la mia installazione e gli
> strumenti nativi, guidami su una fattura e salva risultati e punti da chiarire.
> Se serve un adattamento, preparami la richiesta tecnica da rivedere prima dell'invio.

## Quali dati arrivano al modello

Finestre autorizzate, testo accessibile, immagini e dati di fattura selezionati
possono entrare nel contesto del modello dell'host; il salvataggio locale non è
inferenza offline. Login e credenziali sono gestiti dall'operatore fuori
dall'osservazione. Report e documenti del cliente restano nella cartella privata;
non sono automaticamente allegati a richieste tecniche. Il testo tecnico passa
a Mparanza soltanto dopo revisione e consenso. La ricevuta ordinaria del report
privacy usa separatamente il servizio esistente, con digest, ID casuale, schema
e versione Vera, senza il contenuto del report.
