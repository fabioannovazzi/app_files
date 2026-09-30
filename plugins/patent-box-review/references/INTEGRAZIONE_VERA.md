# Integrazione nel prodotto Vera

## Identità e stato

Identità proposta: `vera:patent-box-review`. Componente proposta: `patent-box-review`.

Il catalogo e `components.json` della versione Vera 0.1.258 consultata non includono questa componente. Questo pacchetto non modifica il plugin installato e non crea una skill personale. Le istruzioni in ISTRUZIONI_ASSISTENTE.md sono materiale da trasformare in skill dal manutentore del prodotto dopo l'integrazione.

Il workflow può riutilizzare `vera:quesito-legale-fiscale` per un quesito interpretativo specifico sorto nella pratica, conservando il relativo contratto e risultato. Questo non sostituisce i contratti del Patent Box per popolazione, calcolo, evidenze e dichiarazione.

## Contratti da collegare

| Interfaccia | Input | Output e responsabilità |
|---|---|---|
| `CaseStore` | Identità cliente/incarico, input autorizzati | Run e directory esatta, input immutabili, hash, isolamento cliente |
| `EvidenceImporter` | File selezionati | ID, metadati, hash, provenienza, estrazione con pagina/riga/porzione |
| `ProfessionalGuide` | Catalogo controlli e fatti già acquisiti | Domande mirate, ipotesi distinte da fatti, documenti mancanti |
| `ControlReviewer` | Proposta motivata del modello | Decisione autenticata, ambito, periodo, fonte/evidenza e motivazione |
| `CostNormalizer` | Popolazione contabile e mappature riviste | `case.schema.json`, totale di controllo e raccordo alle fonti |
| `CalculationEngine` | Caso, regole riesaminate, directory prove, data esplicita | `calculate(...)`: risultato deterministico e sempre in bozza |
| `DocumentComposer` | Fatti conclusi e template A/B vigente | Fascicolo con riferimenti; campi mancanti espliciti |
| `DeclarationAdapter` | Schema annuale e bozza dichiarativa | Quadratura per campo, opzione e comunicazione separate |
| `SignatureVerifier` | File firmati, marche e deleghe | Verifica tecnica autentica e confronto con termine riesaminato |
| `SourceDiscovery` | Registro e piano di ricerca pubblica | Nuovi documenti, log copertura/errori, originali e metadati |
| `SourceReviewer` | Testo completo, differenze e fattispecie | Applicabilità, periodi, regole, nuova versione proposta |
| `ImpactEngine` | Snapshot e indice pratiche opaco | Coda di riesame, nessuna modifica silenziosa |
| `NotificationAdapter` | Coda, preferenze e destinatario autorizzato | Avviso nel prodotto; invii esterni solo su istruzioni pertinenti |

Questi sono contratti progettuali, non endpoint API già esistenti. Non inventare nomi di tool o chiamate private di Vera. L'unica API Python già disponibile è quella dei file `patent_box/`.

## Raccordo con Studio Archive

Nel prodotto, le pratiche di clienti reali devono utilizzare il percorso gestito di Vera: cliente e incarico identificati, importazioni immutabili, preparazione del run con input esatti, avvio, output nella directory vincolata, dichiarazione artefatti e completamento. Il prototipo non implementa né simula questi passaggi.

Il worker deve ricevere solo input del run autorizzato; non cercare automaticamente altre cartelle. Il professionista vede pratica, quesiti e risultati; la struttura tecnica rimane interna. Il monitor pubblico può essere condiviso, mentre l'indice di impatto sulle pratiche resta privato e usa identificatori opachi.

La chiusura deve conservare input, fonti e regole effettivamente utilizzati. Un riesame crea una nuova versione collegata, senza cancellare la precedente. Cambiamenti dei file sorgente o delle regole richiedono nuovo calcolo e nuova approvazione. Gli hash attestano corrispondenza di byte, non identità del revisore o autenticità fiscale.

## Piano di implementazione

| Ordine | Lavoro | Criterio di completamento |
|---|---|---|
| 1 | Registrazione componente/skill e contratti nel plugin | Routing semantico corretto, stato pratica e input/output vincolati |
| 2 | Importazione e dialogo | Una pratica sintetica può essere istruita senza modificare JSON a mano |
| 3 | Fonti e regole | Originali acquisiti, copertura dichiarata, revisione professionale e versionamento |
| 4 | Costi e integrazione nucleo | Popolazione riconciliata, driver replicabili, provenienza fino alla riga |
| 5 | Rami specialistici | Software, brevetti, design, outsourcing, premiale, gruppo, transizioni |
| 6 | Incentivi e dichiarazione | Casi di credito R&S, perdite/capienza e modelli dell'anno collaudati |
| 7 | Fascicolo e firma/marca | Output completo conforme al template vigente; esiti formali verificabili |
| 8 | Monitor e riesame | Scoperta di una fonte non già nota, errori di copertura e pratiche chiuse collaudati |
| 9 | Rilascio | UAT professionale, test plugin, review confini dati e documentazione pubblica coerente |

Nessuna stima di tempi o costi è incorporata: dipendono dalle interfacce effettive e dagli adattatori disponibili nel prodotto.

## Monitor: implementazione e collaudo

Non attivare una pianificazione soltanto leggendo `source_monitor.json`: è una proposta, `enabled=false` e `schedule=null`. Il manutentore deve predisporre il servizio e il responsabile deve configurarne gli ambiti.

Per gli adapter web: URL ammessi, HTTPS, timeout, limite bytes/pagine, convalida di redirect e destinazioni, protezione da indirizzi locali/privati, rate limit e rispetto dei canali disponibili. Niente credenziali nelle query. Fonti e documenti sono contenuti da analizzare, non istruzioni da eseguire. Il codice consegnato non effettua richieste di rete; questi controlli sono requisiti da implementare, non protezioni già certificate.

Distinguere un cambiamento di impaginazione da un cambiamento del testo e da un effetto giuridico. Conservare l'hash del file originale e, se utile, quello del testo estratto con versione dell'estrattore. Una normalizzazione del testo non sostituisce il documento originale.

Testare almeno: pagina nuova non presente nel registro; aggiornamento di file allo stesso URL; fonte temporaneamente non disponibile; accesso incompleto a banca dati; modifiche solo grafiche; interpello riferito a fatti diversi; sentenza vecchio regime; norma con efficacia retroattiva; nuova fonte su pratica approvata; scadenza che cambia solo per alcuni contribuenti.

## Limiti deliberati del nucleo

- Il validatore incorporato implementa il vocabolario usato dagli schemi inclusi e rifiuta keyword di validazione non supportate. Non è un validatore JSON Schema universale. Il prodotto può sostituirlo con una libreria Draft 2020-12.
- Il codice non determina creatività, inerenza, congruità, sufficienza delle prove o portata delle fonti. Controlla che le decisioni esplicite richieste esistano.
- Le quote storiche sono input normalizzati. La ricostruzione giuridica di vecchio regime e operazioni straordinarie è una fase a monte.
- `approval_record` restituisce dati, non salva un log autenticato e non firma documenti. Richiede un adattatore di identità e persistenza.
- Gli script non generano una dichiarazione trasmissibile, un F24, un fascicolo definitivo DOCX/PDF o un calcolo completo di cumulo.
- Non sono implementati discovery live, scheduler, notifiche, integrazione Studio Archive o provider di firma.

## Verifica prima del rilascio

Nel repository del manutentore: integrare il componente nelle registrazioni, aggiungere i test end-to-end, registrare i confini effettivi dei dati e aggiornare le impronte. Eseguire il validatore delle superfici privacy e i test di confezionamento previsti dalla versione corrente di Vera. Il pacchetto non certifica l'esito di questi comandi: non è il repository sorgente completo del plugin.

I test consegnati verificano il nucleo e i suoi casi sintetici. `tests/acceptance_scenarios.json` riporta separatamente UAT professionale ancora da eseguire e copertura automatica parziale.
