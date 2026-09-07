# Bandi — contributi prodotti dopo la ripresa

Le sessioni Astra Medium autorizzate sono state eseguite. Le aspettative dei casi sintetici già approvate restano valide. Questo documento raccoglie i risultati effettivi: non è una nuova richiesta di approvare le stesse aspettative, né una dichiarazione di ammissibilità di una domanda reale. I contributi restano MODEL_SUGGESTED; nessuna accettazione professionale è stata inventata.

INTEL-000004 è escluso da questa raccolta: il comando di registrazione aveva ricostruito uno scope diverso dal packet letto. L’originale è conservato per tracciabilità; INTEL-000005 è stato prodotto in un’altra sessione realmente nuova, con hash del packet coincidente fra lettura e registrazione.

## INTEL-000001 — Decreto 4 dicembre 2020

Proposta esatta: [model-output.json](/private/tmp/vera-remediation-01a07083/bandi-fresh-review/model-output.json). SHA-256: `b31a5f7a19f8e81b26098736613485a0dc7921b79db14bdb46335f681812e67b`.

Interpretazione circoscritta del decreto ON-DECREE-2020: proposti separatamente i due test di maggioranza dell’art. 5, comma 1, lettera d), con il riferimento temporale del comma 5; proposta un’issue aperta sulla disciplina attuativa e sull’applicabilità attuale. Il contesto è sufficiente solo per queste proposizioni del testo storico. Non è una ricostruzione completa dei requisiti, una verifica di ammissibilità del cliente o una conferma dell’apertura della misura.

- **REQ-ON-A5D-NUMERIC**: La componente costituita da soggetti di età compresa tra diciotto e trentacinque anni ovvero da donne deve superare la metà numerica dei soci.

  Fonte: ON-DECREE-2020 — PDF p. 5/15, art. 5, comma 1, lettera d); ON-DECREE-2020 — PDF p. 5/15, art. 5, comma 5, prima parte; ON-DECREE-2020 — PDF p. 6/15, art. 5, comma 5, continuazione

- **REQ-ON-A5D-SHARES**: La componente costituita da soggetti di età compresa tra diciotto e trentacinque anni ovvero da donne deve detenere oltre la metà delle quote di partecipazione.

  Fonte: ON-DECREE-2020 — PDF p. 5/15, art. 5, comma 1, lettera d); ON-DECREE-2020 — PDF p. 5/15, art. 5, comma 5, prima parte; ON-DECREE-2020 — PDF p. 6/15, art. 5, comma 5, continuazione

- **ISS-ON-TEMPORAL-BASELINE**: Il solo decreto storico selezionato non dimostra apertura dello sportello, disponibilità delle risorse o applicabilità alla data di riferimento 2026-09-06. Art. 7, comma 2 e art. 22, comma 1 rinviano a un successivo provvedimento per i termini e la decorrenza. Passaggi esatti: [{"source_id": "ON-DECREE-2020", "locator": "PDF p. 6/15, art. 7, comma 2", "excerpt": "  2. I termini e le  modalita'  di  presentazione  delle  domande  di \nagevolazioni sono definiti con successivo provvedimento del direttore \ngenerale per gli incentivi alle imprese del Ministero, pubblicato nel \nsito internet del soggetto gestore www.invitalia.it  e in quello  del \nMinistero www.mise.gov.it   ferma  restando  la  pubblicazione  nella \nGazzetta  Ufficiale  della  Repubblica  italiana.  Con  il   medesimo \nprovvedimento sono, altresi', definiti i punteggi di cui  all'art.  8 \ndel  presente  decreto  nonche'  gli  ulteriori  elementi   utili   a \ndisciplinare l'attuazione dell'intervento agevolativo,  ivi  comprese \neventuali specificazioni in ordine alle spese ammissibili.", "excerpt_sha256": "a12ff33a7f62d232b2ad00ab730f9f19e5fc4b486247d4874e9576eb635165f2"}, {"source_id": "ON-DECREE-2020", "locator": "PDF p. 15/15, art. 22, comma 1", "excerpt": "  1. Le disposizioni di cui al presente  decreto  si  applicano  alle \ndomande di agevolazione presentate a partire dalla data stabilita con \nil provvedimento di cui all'art. 7, comma 2. Per le medesime  domande \nnon trovano piu' applicazione le diposizioni di cui  al  decreto  del \nMinistro dello  sviluppo  economico,  di  concerto  con  il  Ministro \ndell'economia e delle finanze, 8 luglio 2015, n.  140,  e  successive \nmodifiche e integrazioni.", "excerpt_sha256": "2b84c8677919288834c891928ea7aaf3ce1404fd5e47efd505973c4adbfaa332"}]

## INTEL-000002 — Avviso Invitalia del 30 giugno 2026

Proposta esatta: [model-output.json](/private/tmp/vera-remediation-01a07083/bandi-fresh-notice-review/model-output.json). SHA-256: `189ae095067f29a1ad5efa4273f4d576ce6e95fcd45866844419fd9413731ed6`.

Contesto sufficiente soltanto per interpretare i bytes dell’avviso conservato ON-FINANCING-NOTICE-2026: tre requisiti procedurali atomici proposti e un problema aperto sulla baseline e sull’attualità. Nessuna evidenza cliente esaminata, nessuna conclusione di ammissibilità, nessuna ricerca esaustiva di normativa vigente e nessuna accettazione professionale.

- **REQ-ON-NOTICE-FINANCING-ONLY**: Per le domande ON presentate a partire dal 1° luglio 2026, l’avviso indica la concessione delle agevolazioni soltanto nella forma del finanziamento agevolato.

  Fonte: ON-FINANCING-NOTICE-2026 — HTML conservato SHA-256 ed38ea001b3bfc77758cbed1b9a951fece30c32900290a461cc6789de08522af; main p, paragrafo 3 (indice 1); testo DOM con spazi normalizzati

- **REQ-ON-NOTICE-CHANNEL**: L’avviso mantiene la presentazione della domanda tramite la piattaforma informatica di Invitalia.

  Fonte: ON-FINANCING-NOTICE-2026 — HTML conservato SHA-256 ed38ea001b3bfc77758cbed1b9a951fece30c32900290a461cc6789de08522af; main p, paragrafo 4 (indice 1); testo DOM con spazi normalizzati

- **REQ-ON-NOTICE-ORDER**: L’avviso indica che le richieste sono esaminate secondo l’ordine cronologico di arrivo.

  Fonte: ON-FINANCING-NOTICE-2026 — HTML conservato SHA-256 ed38ea001b3bfc77758cbed1b9a951fece30c32900290a461cc6789de08522af; main p, paragrafo 4 (indice 1); testo DOM con spazi normalizzati

- **ISS-ON-NOTICE-AUTHORITY-CURRENTNESS**: Il solo avviso Invitalia del 30 giugno 2026 riferisce l’esaurimento delle risorse a fondo perduto e la sola forma del finanziamento agevolato per domande dal 1° luglio 2026; dichiara altresì la misura attiva in tutta Italia. Il packet include una sola fonte candidate/clarifying, nessun atto collegato e nessuna revisione del merito. Non prova disponibilità delle risorse o assenza di aggiornamenti al 6 settembre 2026, né disciplina transitoria delle domande anteriori, percentuali, massimali o requisiti di ammissibilità. Occorre selezionare e rivedere il raccordo con gli atti formali e gli eventuali aggiornamenti prima di applicare l’indicazione al caso. Non è dimostrato alcun conflitto con altra fonte, perché qui non è stata inclusa né letta.

## INTEL-000003 — FAQ Invitalia ON

Proposta esatta: [model-output.json](/private/tmp/vera-remediation-01a07083/bandi-fresh-faq-review/model-output.json). SHA-256: `5a0de1c2f9988339dc65f5151f88c621970e2f2abc8195272c6448af147faec4`.

Sette proposte atomiche limitate alle FAQ ON: anzianità, data pertinente per forma societaria, inattività e duplice maggioranza. Il contesto è sufficiente per queste sole proposte di lettura della FAQ; non per vigenza attuale, ammissibilità, completezza dei requisiti o prevalenza sugli atti formali. Nessun dato cliente letto.

- **REQ-FAQ-AGE-60**: La società già costituita deve essere costituita da non più di 60 mesi alla presentazione della domanda.

  Fonte: INVITALIA-FAQ-ON — FAQ 1, prima risposta; selected-source-text.txt righe 117-117; HTML SHA-256 c5c67ee2c6f05a9d8df6fd7a79d22d1dc833e992a795edb82ade7d403cd78aa4

- **REQ-FAQ-DATE-PERSONE**: Per le società di persone, la data di costituzione coincide con la data dell’atto costitutivo.

  Fonte: INVITALIA-FAQ-ON — FAQ 12; selected-source-text.txt righe 205-206; HTML SHA-256 c5c67ee2c6f05a9d8df6fd7a79d22d1dc833e992a795edb82ade7d403cd78aa4

- **REQ-FAQ-DATE-CAPITALI**: Per le società di capitali, la data di costituzione coincide con la data di iscrizione presso la CCIAA competente.

  Fonte: INVITALIA-FAQ-ON — FAQ 12; selected-source-text.txt righe 205-206; HTML SHA-256 c5c67ee2c6f05a9d8df6fd7a79d22d1dc833e992a795edb82ade7d403cd78aa4

- **REQ-FAQ-INATTIVA-60**: L’inattività non esonera la società dal limite di costituzione di non più di 60 mesi.

  Fonte: INVITALIA-FAQ-ON — FAQ 13; selected-source-text.txt righe 207-208; HTML SHA-256 c5c67ee2c6f05a9d8df6fd7a79d22d1dc833e992a795edb82ade7d403cd78aa4

- **REQ-FAQ-INATTIVA-CAPO-II**: Una società costituita da oltre 36 mesi non può accedere alle agevolazioni del CAPO II per il solo fatto di essere inattiva.

  Fonte: INVITALIA-FAQ-ON — FAQ 14; selected-source-text.txt righe 209-210; HTML SHA-256 c5c67ee2c6f05a9d8df6fd7a79d22d1dc833e992a795edb82ade7d403cd78aa4

- **REQ-FAQ-MAJ-NUM**: Alla presentazione della domanda i soci con i requisiti soggettivi devono rappresentare oltre la metà numerica dei soci.

  Fonte: INVITALIA-FAQ-ON — FAQ 4, domanda e risposta, intestazioni della tabella; selected-source-text.txt righe 142-153; HTML SHA-256 c5c67ee2c6f05a9d8df6fd7a79d22d1dc833e992a795edb82ade7d403cd78aa4

- **REQ-FAQ-MAJ-QUOTE**: Alla presentazione della domanda i soci con i requisiti soggettivi devono detenere oltre la metà delle quote di partecipazione.

  Fonte: INVITALIA-FAQ-ON — FAQ 4, domanda e risposta, intestazioni della tabella; selected-source-text.txt righe 142-153; HTML SHA-256 c5c67ee2c6f05a9d8df6fd7a79d22d1dc833e992a795edb82ade7d403cd78aa4

## INTEL-000005 — Circolare 8 aprile 2021 n. 117378

Proposta esatta: [model-output.json](/private/tmp/vera-remediation-01a07083/bandi-fresh-circular-exact-review/model-output.json). SHA-256: `ec479619c9ae46f3bb248850851eeec2bc25133977f46f435150ca16885ca6d1`.

Interpretazione source-only di ON-CIRCULAR-2021: quattro requisiti atomici proposti su decorrenza 19 maggio 2021, costituzione entro 60 mesi e maggioranze cumulative di soci e quote. Applicabilità corrente non verificata; nessun dato cliente letto e nessuna accettazione.

- **ON-EXACT-OPENING-2021**: Il punto 8.2 consente la presentazione delle domande a partire dal giorno 19 maggio 2021. Non indica un orario. Il punto 17.1 applica la circolare alle domande presentate da quella data.

  Fonte: ON-CIRCULAR-2021 — PDF p. 10, punto 8.2; ON-CIRCULAR-2021 — PDF p. 20, punto 17.1

- **ON-EXACT-AGE-60M**: Per le imprese già costituite, la costituzione deve risalire a non più di 60 mesi alla data di presentazione della domanda.

  Fonte: ON-CIRCULAR-2021 — PDF p. 3, punto 4.1(a); ON-CIRCULAR-2021 — PDF p. 4, punto 4.4

- **ON-EXACT-MAJORITY-HEADS**: La compagine deve comprendere, per oltre la metà numerica dei soci, soggetti di età compresa tra 18 e 35 anni ovvero donne; deve ricorrere anche la maggioranza delle quote richiesta dal medesimo punto 4.1(d).

  Fonte: ON-CIRCULAR-2021 — PDF p. 3, punto 4.1(d); ON-CIRCULAR-2021 — PDF p. 4, punto 4.4

- **ON-EXACT-MAJORITY-SHARES**: La compagine deve essere composta, per oltre la metà delle quote di partecipazione, da soggetti di età compresa tra 18 e 35 anni ovvero donne; deve ricorrere anche la maggioranza numerica dei soci richiesta dal medesimo punto 4.1(d).

  Fonte: ON-CIRCULAR-2021 — PDF p. 3, punto 4.1(d); ON-CIRCULAR-2021 — PDF p. 4, punto 4.4

- **REC-ON-EXACT-HISTORICAL-LIMIT**: Conservare il limite storico: PDF p. 10, punto 8.3 — 8.3. Ai sensi dell’articolo 2, comma 3, del citato decreto legislativo 31 marzo 1998, n. 123, 
i soggetti interessati hanno diritto alle agevolazioni esclusivamente nei limiti delle disponibilità 
finanziarie. L’eventuale esaurimento delle risorse disponibili comporta la chiusura dello sportello. 
Il Ministero, sulla base dei dati trasmessi dal Soggetto gestore, comunica tempestivamente, con 
avviso da pubblicare nella Gazzetta Ufficiale della Repubblica italiana, l’avvenuto esaurimento 
delle risorse finanziarie disponibili . Nel caso in cui si rendano successivamente disponibili 
ulteriori risorse finanziarie per la concessione delle agevolazioni, il Ministero provvede alla 
riapertura dei termini per la presentazione delle domande mediante avviso a firma del Direttore 
generale per gli incentivi alle imprese, pubblicato nel sito internet del Soggetto gestore e in quello 
del Ministero, ferma restando la pubblicazione nella Gazzetta Ufficiale della Repubblica italiana. Il solo PDF del 2021 non permette di stabilire vigenza integrale, disponibilità finanziaria o apertura dello sportello al 2026-09-06. I punti 17.3-17.4, PDF p. 21, preservano specifiche situazioni della disciplina previgente: non applicare retroattivamente in blocco queste proposte. Nessuna accettazione professionale o decisione di eleggibilità.

## Limite della verifica

Ogni contributo riguarda soltanto le fonti selezionate e identifica le incertezze temporali. Il decreto e la circolare storici non dimostrano da soli la disponibilità attuale delle risorse. Le FAQ hanno ruolo chiarificatore. L’avviso è conservato con data, autorità e contenuto propri; non è trasformato automaticamente in una modifica normativa. La registrazione tecnica e il controllo degli hash non sostituiscono la valutazione professionale delle fonti o dei risultati.
