# Specifica funzionale — Patent Box per Vera

## 1. Obiettivo e perimetro

Il commercialista deve poter iniziare dicendo «valutiamo il Patent Box per questa impresa e questo periodo». Vera ricostruisce il caso, propone verifiche e richieste motivate, prepara elaborati e rende ricostruibile ogni conclusione. Il professionista non deve conoscere nomi di file o regole interne.

Il perimetro è il nuovo regime ex art. 6 D.L. 146/2021. Il vecchio regime entra come storia, transizione o possibile sovrapposizione, non come algoritmo equivalente. Il pacchetto specifica un workflow completo; implementa solo il nucleo quantitativo e la comparazione di fonti già acquisite. Le capacità mancanti sono elencate in INTEGRAZIONE_VERA.md.

Invarianti:

- Ogni importo candidato collega contribuente, esercizio, documento, costo, attività, progetto e bene.
- Ogni decisione collega fatti, evidenze, fonte pertinente, motivazione e revisore.
- La valutazione sostanziale resta separata dalla preparazione della penalty protection.
- Una fonte nuova genera un riesame tracciato, conservando la precedente versione approvata.
- L'assenza di dati non si trasforma in una conclusione negativa certa o in un dato inventato.
- Un blocco su un bene o costo non deve fermare le altre componenti valutabili.

## 2. Apertura e dialogo

Raccogliere contribuente, periodo, attività, obiettivo dell'incarico, opzioni pregresse, beni, progetti, fornitori e incentivi. Recuperare le informazioni già presenti negli input selezionati; chiedere in piccoli gruppi solo ciò che manca. Chiarire se si richiedono ordinario, premiale, fascicolo documentale o riesame di una pratica.

Output iniziale: mappa della pratica e richiesta documenti prioritaria con motivo, destinatario interno, conseguenza della mancanza e prossimo passo. La richiesta comprende secondo necessità:

| Area | Input attesi |
|---|---|
| Impresa e opzione | Dati fiscali, regime, dichiarazioni, ricevute, opzioni e accordi precedenti |
| Beni e diritti | Descrizione precisa, titoli/domande, licenze, cessioni, contratti con autori/sviluppatori, uso |
| Attività | Relazioni tecniche, periodi, persone, deliverable, versioni, funzione dei componenti |
| Costi | Mastri, dettaglio fatture/costi, personale, cespiti, timesheet, driver, riconciliazioni |
| Esterni | Contratti, gruppo, subfornitura, localizzazione effettiva, rischi e direzione tecnica |
| Incentivi | Crediti, contributi, costi condivisi, dichiarazioni, fruizione e restituzioni |
| Adempimenti | Richiesta penalty protection, file firmati/marcati, dichiarazioni e conservazione |

Non richiedere accesso indiscriminato all'archivio o l'intero repository software. Il tecnico può fornire una relazione e le evidenze necessarie; il commercialista decide se occorre un professionista della proprietà intellettuale.

## 3. Fasi e blocchi

Il file `config/workflow.json` è la definizione delle dipendenze da implementare. La sequenza comprende intake, fonti, soggetto, bene, diritti, attività, outsourcing, costi, premiale, incentivi, calcolo, documentazione, raccordo dichiarativo, riesame e approvazione.

Una fase condizionale non applicabile produce una motivazione di non applicabilità. Non obbligare il contribuente a richiedere la penalty protection per accedere al percorso sostanziale. La preparazione dei materiali documentali può procedere durante l'istruttoria; la versione conclusiva deve riflettere gli esiti delle verifiche.

| Stato del controllo | Significato | Effetto |
|---|---|---|
| PASS | Verifica positiva con riferimenti e decisione registrati | Consente il passaggio per la componente |
| WARNING | Questione interpretativa o riserva da risolvere | Sospende l'importo candidato nel prototipo |
| FAIL | Requisito esaminato e non soddisfatto | Esclude la componente motivando |
| BLOCKED | Evidenza o presupposto di verifica mancante | Sospende senza dichiarare inammissibilità definitiva |
| NOT_TESTED | Verifica ancora da effettuare | Nessuna conclusione di spettanza |

Il prototipo considera un gate assente come NOT_TESTED. Un PASS senza evidenze, fonti e revisore non libera l'importo. Il catalogo contiene sottocontrolli più dettagliati dei gate del motore: l'orchestratore dovrà aggregare solo quelli applicabili e non consentire un PASS globale se un sottocontrollo necessario resta aperto.

## 4. Qualificazione sostanziale

### Soggetto e opzione

Verificare reddito d'impresa, esclusioni, investitore effettivo, rischi e risultati. Ricostruire opzione, durata quinquennale, rinnovi, adempimenti e rimedi con fonti dell'anno; non assumere che l'assenza della casella dimostri da sola la soluzione finale. Le procedure concorsuali e le operazioni straordinarie aprono verifiche specifiche.

### Bene, diritti e uso

Assegnare un ID stabile a ogni bene e una versione ove necessaria. Evitare descrizioni come «progetto innovazione». Distinguere titolo giuridico, diritto di sfruttamento economico e utilizzo effettivo. Software, brevetti e design hanno istruttorie dedicate. Marchi, know-how e altre categorie non entrano automaticamente nel nuovo regime.

Per il software: autori, origine, componente originale, preesistenze, moduli di terzi, diritti, licenze, versione e uso. Esaminare separatamente l'eventuale registrazione utile al premiale. Per brevetti: domanda/concessione, rivendicazioni, territorio, validità e legame con il progetto. Per design: oggetto tutelato, tutela applicabile e separazione delle attività estetiche da quelle funzionali. Più beni complementari non devono generare duplicazioni dei costi.

### Attività e terzi

Classificare le attività concrete in base alle fonti applicabili. Ricostruire persone, periodo, deliverable, ruolo nella creazione/sviluppo/mantenimento/protezione del bene. Non trasferire automaticamente al Patent Box una qualificazione utilizzata per un diverso incentivo.

Per l'outsourcing verificare indipendenza o rapporti di gruppo, commissionari/subfornitori, direzione tecnica, rischio tecnico/economico, risultati e territorio di svolgimento. Una fattura o l'indirizzo del fornitore non provano da soli questi elementi.

## 5. Costi e calcolo

L'importazione deve creare una popolazione chiusa con totale di controllo e provenienza. Preservare gli originali. Mantenere importo contabile, base candidata redditi, base candidata IRAP, quota allocata, quota esclusa, sospesa e non allocata. Il totale di controllo del prototipo riguarda la popolazione selezionata, non certifica l'intera contabilità.

Ogni costo ha un `ledger_row_key` stabile: non basta cambiare `cost_id` per ricaricare la stessa riga. Il motore controlla duplicati esatti di chiave e sovra-allocazioni; la rilevazione di duplicati economici con chiavi diverse resta da implementare nell'importazione.

Gli importi sono stringhe decimali EUR con due decimali. Non usare floating point. L'input del nucleo è già normalizzato: cambio valuta, rettifiche negative, aggregazione di paghe e trattamento fiscale delle spese richiedono un prospetto a monte riesaminato. Un dato fuori contratto blocca il calcolo, non viene corretto silenziosamente.

I driver dei costi promiscui devono essere documentati e riproducibili; il modello può proporli, ma nessuna percentuale inventata diventa una quota ammessa. La somma delle allocazioni di ciascuna base fiscale non deve superare il relativo massimale riesaminato del costo. Il motore usa `Decimal` e arrotonda la variazione dopo l'aggregazione esatta.

La formula di riferimento è `base ammessa × 1,10` per la deduzione aggiuntiva. Non confonderla con il costo complessivamente deducibile o con un credito. Redditi e IRAP sono basi separate. Eventuale IRAP non applicabile: base zero motivata e riesaminata a monte. Nessuna aliquota fiscale o capienza è preimpostata per stimare il risparmio.

Output quantitativi: esito per allocazione, motivi, basi per stato, basi incluse per IP, non allocato, variazioni redditi/IRAP, hash di input e regole. Per quote sospese non viene prodotto un beneficio affermato come spettante.

## 6. Premiale e storia

Il premiale è un ramo separato. Identificare evento qualificante, prima data rilevante, tipo di bene, periodo fiscale dell'evento, utilizzo e periodo di fruizione. Ricostruire gli otto periodi fiscali precedenti all'evento con una sequenza completa. Non sostituirli con «anno meno otto».

Conservare le spese che hanno contribuito alla creazione, la relativa attività e la prova. Il motore verifica l'intervallo, non decide semanticamente se una spesa ha contribuito alla creazione. Eventuali spese correnti restano nel ramo ordinario. La fruizione in un periodo successivo non sposta automaticamente la finestra storica.

Il registro degli utilizzi precedenti deve coprire nuovo e vecchio regime e le eventuali vicende del bene. Se quote già utilizzate e nuove allocazioni superano la base disponibile, il prototipo sospende le componenti interessate. Per vecchio regime, transizioni e operazioni straordinarie è necessaria una decisione specifica prima di normalizzare le quote; non presumere equivalenza fra basi di regimi diversi.

## 7. Coordinamento con incentivi

Usare `templates/incentive_matrix.csv`: costo, progetto, periodo, regime del credito, base, credito maturato, fruito/non fruito, contributi, quota Patent Box, imposta pertinente, importo da ricalcolare, azione e scadenza con fonte.

L'esito INCENTIVES deve spiegare «assenza di sovrapposizione» oppure contenere un calcolo e una decisione riesaminati. Un semplice sì/no non basta. Il nucleo consegnato non calcola nettizzazioni, riversamenti, perdite o capienza: blocca le quote prive di revisione del coordinamento.

La risposta 102/2026 affronta un caso di software e credito R&S con profili di restituzione e capienza. Lo sviluppatore deve distinguere la soluzione proposta dall'istante dal parere dell'Agenzia, confrontare i fatti e ricavare una regola versionata; non impostare una scadenza universale al 30 giugno o rinviare automaticamente tutto al successivo assorbimento delle perdite. [Testo dell'Agenzia, parere da pagina 7](https://www.quotidianofiscale.it/wp-content/uploads/2026/05/Risposta-n.-102_2026.pdf).

## 8. Fascicolo e adempimenti

Seguire l'indice vigente del provvedimento, verificato per la pratica. Il template A/B incluso è una struttura di lavoro, non una dichiarazione di conformità al provvedimento. Per ogni paragrafo registrare testo, fatti, evidenze e stato della verifica. Nessun fatto privo di prova deve apparire come accertato.

A: impresa, organizzazione, beni, investitore, associate, attività e contratti, funzioni/rischi, relazione tecnica. B: spese, allocazioni, personale, driver, riconciliazioni contabili/fiscali e variazioni. Verificare le eventuali semplificazioni applicabili con la fonte e la motivazione.

Firma, poteri del firmatario, marca, termine applicabile, comunicazione in dichiarazione e conservazione hanno esiti distinti. Un hash SHA-256 non equivale a firma elettronica o marca temporale. Le scadenze devono distinguere invio, termine ordinario, integrativa/tardiva, eventuali deroghe o rimedi. La sola formula «entro il termine della dichiarazione» non basta a implementare tutti i casi; confrontare il provvedimento aggiornato e i paragrafi 7 e 7.2 della [circolare 5/E/2023](https://www.informazionefiscale.it/IMG/pdf/circolare_nuovo_patent_box_24.02.23.pdf).

L'esito positivo interno significa che le verifiche previste sono state riesaminate. Non deve essere presentato come riconoscimento dell'idoneità da parte dell'Amministrazione. Tenere anche un ramo «richiesta dell'Ufficio»: data ricezione, oggetto, termine di consegna, eventuale integrazione, versione consegnata e ricevuta, ciascuno con fonte.

## 9. Raccordo dichiarativo

Il modello dell'anno deve essere acquisito e versionato. Memorizzare anno modello, periodo fiscale, versione istruzioni, quadro/rigo/campo, importo atteso, importo riportato e quadratura. Distinguere opzione, comunicazione documentazione, variazioni redditi e IRAP e rettifiche di altri incentivi.

Non inserire numeri di rigo permanenti nel prompt. Non firmare, trasmettere dichiarazioni o F24 dal prototipo. Prima dell'approvazione professionale verificare anche che le fonti e il modello non siano cambiati.

## 10. Fonti, versioni e monitor

Il registro deve conservare autorità, tipo documento, numero/data, URL, acquisizione, hash del file, periodo di efficacia, periodi fiscali interessati, rapporto con versioni precedenti e regole collegate. Non equiparare data di pubblicazione ed efficacia, né considerare una modifica parziale come abrogazione dell'intero documento.

Distinguere norma, attuazione, prassi generale, interpello, giurisprudenza e fonti tecniche. Queste funzioni non si riducono a una graduatoria numerica: una sentenza richiede analisi di organo, grado, fatti, principio, definitività quando nota e conflitti. Un interpello non è automaticamente una norma universale.

Il monitor richiesto ha due momenti: prima dell'apertura/conclusione della pratica e periodicamente quando il servizio sarà configurato. Lo stato consegnato è disattivato. La soglia proposta di sette giorni è una politica di prodotto da configurare, non un termine di legge.

Pipeline da integrare:

1. Scansionare gli ambiti istituzionali configurati, con finestre temporali e paginazione tracciate.
2. Scoprire nuovi documenti e confrontare quelli già noti; non basta controllare sei URL statici.
3. Salvare originali, metadati e hash; segnalare blocchi, errori e copertura incompleta.
4. Proporre classificazione e regole interessate, spiegando il rapporto fra fatti e fonte.
5. Far riesaminare portata, periodi e modifiche; creare una nuova versione delle regole.
6. Produrre la coda delle pratiche interessate; conservare le decisioni precedenti.
7. Rieseguire i controlli e i test interessati, quindi consentire una nuova decisione professionale.

Il codice incluso implementa confronto e coda a partire da snapshot forniti. Un hash cambiato è «contenuto da riesaminare», non prova di modifica normativa. Un download fallito non significa «nessuna novità». Una mappatura non riesaminata amplia il riesame invece di nascondere pratiche potenzialmente rilevanti.

## 11. Approvazione, riesame e output

Il riesame finale confronta la posizione favorevole con le contestazioni più forti sostenute dai fatti. Per ciascuna: fonte, evidenza, impatto quantitativo, documenti mancanti e decisione da assumere. Non generare un punteggio di probabilità di spettanza.

Output del futuro prodotto:

- Sintesi professionale con componenti supportate, escluse, sospese e questioni aperte.
- Matrice requisiti con fonti/evidenze/decisioni e registro IP/diritti/attività.
- Riconciliazioni e calcoli riproducibili, registro storico e matrice incentivi.
- Fascicolo A/B, raccordo dichiarativo e riepilogo adempimenti.
- Registro fonti, copertura della ricerca, riesame critico e log delle decisioni.
- Versione approvata vincolata a input, prove, regole, output e identità del revisore.

La funzione `approval_record` prepara il legame crittografico della decisione ma non autentica il professionista. Il sistema ospitante deve verificare identità, poteri, autorizzazioni e immutabilità. Un cambio di input o regole invalida il precedente risultato; un file approvato si conserva e si sostituisce con una nuova versione, non si sovrascrive.

## 12. Accettazione

Eseguire i test automatici e i 32 scenari in `tests/acceptance_scenarios.json`. Gli scenari distinguono verifica meccanica e verifica professionale. Un test che cambia `RIGHTS` in BLOCKED prova la gestione del blocco, non la capacità di valutare una catena di diritti.

Il rilascio richiede anche prove end-to-end di dialogo, acquisizione fonti nuove, falsi positivi/negativi del monitor, importazione documenti, firma/marca, mapping dichiarativo, isolamento fra clienti, autorizzazioni e riapertura controllata. Nessuna di queste prove si considera superata dal solo successo dei test Python.
