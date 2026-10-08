# Vera 0.1.352: acquisizione Agenzia delle Entrate

## Decisione e provenienza

La richiesta di Fabio è adottare il procedimento operativo di Francesco Platania,
riscriverlo dove necessario, ritirare la precedente implementazione AdE e fornire
un unico percorso in Vera, con pagina esplicativa, corso e pannello nativo.
Non viene richiesto a Francesco di dimostrare nuovamente il suo risultato prima
dell'integrazione. La provenienza del suo codice dalla precedente Vera non è
stabilita dalle evidenze disponibili e non è dichiarata.

Sorgente esaminata: `Documents/per vera/scarica_fatture_standalone`.
Le impronte identificano i tre file Python esaminati; configurazioni, credenziali,
elenco clienti, log con dati di studio e ambiente Windows non sono distribuiti.

| File | SHA-256 |
| --- | --- |
| scarica_fatture.py | 4084f620a29330d58f93a5d471cdcd70393045aec9860896ac6fa3c8a5a6ef15 |
| bolli_f24.py | 3b1a7df106ac1173f5fc4c76f0786c45639a3233e1f23fc5ea7e28af5e8bc70a |
| esplora_bollo.py | 0368cad99f28ab23156d4e5068ec2980041c2f4b02357385b505fd116b5ce019 |

Sono stati conservati il flusso di delega, le destinazioni del portale, le query
per intervallo e partita IVA, la navigazione ai dettagli e l'acquisizione degli
originali. I log forniti indicano esecuzioni di Francesco con risultati e anche
errori; non legano ogni esecuzione a un'impronta del codice. La discussione
WhatsApp Progetto Vera AI dell'8 ottobre descrive l'interesse per un contenitore
Vera, il recupero dei documenti e il successivo confronto con la contabilità.
Il confronto contabile e l'importazione nel gestionale non sono implementati da
questa acquisizione.

## Un solo motore e interventi effettuati

Il motore Python in `plugins/browser-automation/scripts/ade_acquisition` serve
sia `agenzia_acquire.py` sia il pannello MCP App. La sorgente della lezione è
esplicitamente fittizia e usa quel medesimo motore. Il pannello è un'estensione
thread secondo [Plugin Extensions](https://developers.openai.com/plugins/build/extensions),
non un secondo archivio clienti: importa nello Studio Archive esistente solo
con associazioni esplicite a cliente e incarico.

Sono eliminati i tre runner `agenzia_download.mjs`, `agenzia_acquisition.mjs`,
`agenzia_artifacts.mjs`, la capability `agenzia-invoice-zip`, le due vecchie
reference e i relativi test. Il percorso generico per insegnare procedure web
e il processo ECONS rimangono distinti e non eseguono l'acquisizione AdE.
I riferimenti pubblici e il catalogo indirizzano alla nuova funzione.

| Aspetto esaminato | Comportamento adottato |
| --- | --- |
| Configurazione con credenziali | Accesso personale nel Chrome locale; nessun salvataggio di password, PIN, cookie o profilo |
| Identità e selezione cliente | CF/P.IVA validati, selezione esatta; nessun ripiego silenzioso su altra posizione |
| Oltre 50 risultati | Suddivisione del periodo, paginazione anche nel singolo giorno e verifica dei conteggi |
| Ripresa e duplicati | Nuova enumerazione, registro SQLite, hash e byte originali verificati; file in cartelle uniche |
| Fatture firmate | Conservazione dell'originale e lettura locale CMS; nessuna pretesa di validazione della firma |
| Fallimenti o arresto | Eventi persistenti, esiti parziali, lock del worker, avvii idempotenti e ripresa |
| Completamento | Stato finale presentato solo dopo la produzione dei report |
| Corrispettivi | Tutti i tipi di dispositivo e tutte le pagine; importi assenti segnalati, mai sostituiti con zero |
| Bolli | Tutti i trimestri, incluso il quarto; importo portale e stato pagamento conservati separatamente |
| Prospetto F24 | Residuo, scadenza e motivazione forniti dall'operatore; nessun pagamento o invio |
| Dipendenze | Requisiti dichiarati nell'ambiente Python condiviso; nessun pip durante l'acquisizione |
| Dati al modello | Worker senza chiamate a modelli; dettagli del pannello in metadati app, riepilogo nel testo; letture in chat da registrare separatamente |

## Materiali e verifica

La nuova pagina `agenzia-acquisition` è disponibile in cinque lingue e termina
con la descrizione specifica dei dati al modello. Il corso italiano esegue una
prima acquisizione parziale e una ripresa, con originali, Excel, CSV, HTML e
rapporto dati realmente prodotti. La review editoriale e le impronte degli
output sono in `scripts/course_materials/release_reviews/vera/agenzia-acquisition.json`.
Il corso generale sulle procedure web conserva il proprio scopo.

Verifica locale dell'8 ottobre: 67 test del motore, adapter Playwright su DOM
locale, servizio UI, pannello nel browser e corso; copertura 81,57%. Quattro
test MCP verificano risorsa autonoma, metadati, binding e separazione dei dati.
È stato verificato anche un import reale nel CLI Studio Archive, su archivio
temporaneo fittizio: ripetere l’import mantiene un solo originale.
Black, Isort, Mypy e Bandit sono superati. Dodici esecuzioni delle due lezioni
(10 della lezione generica e 2 della nuova) sono superate. Codex, Cowork e
Antigravity sono costruiti dalla stessa versione canonica.

Queste prove non sono un accesso reale al portale AdE, un test nell'utenza di
Francesco, un'accettazione professionale, un test del pannello dentro un host
nativo installato o una dimostrazione del funzionamento sul suo PC Windows.
Il lavoro reale richiede un host locale con Chrome grafico e l'accesso personale
dell'operatore. Il percorso a file rimane disponibile quando il pannello manca.
CI, merge, deploy, integrità del download pubblico e messaggio Discord sono
verificati separatamente nel PR e nel resoconto finale, non attestati da questo
file. Nessuna pubblicazione Marketplace è inclusa.
