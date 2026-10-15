# Caso sintetico «Alfa Servizi S.r.l.» — dal fascicolo alla rettifica approvata e a una modifica successiva

**Tutti i dati sono inventati.** Società, banca, fornitore, importi e documenti sono fittizi; non ci sono partite IVA,
codici fiscali o nomi reali. I numeri sono stati generati e verificati con uno script: ogni bilancio di verifica quadra
e ogni rettifica è bilanciata.

**Scopo:** rendere verificabile la proposta di integrazione nella funzione Bilancio OIC e XBRL (`bilancio-oic`). Il caso
indica, fase per fase, cosa deve succedere (risultato atteso) e cosa non deve mai succedere.

**Perimetro:** il caso non tratta il calcolo delle imposte dell'esercizio (resta una questione aperta) né il raccordo dei
comparativi con l'XBRL dell'anno precedente (non fornito). Non contiene la nota integrativa.

---

## 1. La società

| Voce | 2025 | 2024 |
|---|---|---|
| Attività | servizi, nessun magazzino | servizi, nessun magazzino |
| Ricavi delle prestazioni | 560.000,00 | 500.000,00 |
| Totale attivo netto (dopo le rettifiche) | 279.400,00 | 227.200,00 |
| Dipendenti medi | 6 | 6 |
| Contabilità | tenuta da un consulente esterno | — |

Esercizio 2025, chiusura al 31/12/2025. Lo studio prepara il bilancio nei primi mesi del 2026.

## 2. I documenti

| File | Documento | Quando arriva |
|---|---|---|
| `dati/01_bilancio_verifica_2025_prima_chiusure.csv` | Bilancio di verifica 2025 **prima delle scritture di chiusura**, con colonna 2024 | Fascicolo iniziale |
| `dati/02_registro_cespiti_2025.csv` | Registro cespiti 2025 | Fascicolo iniziale |
| `dati/03_contratto_finanziamento.md` | Contratto di finanziamento (100.000 €, 4%, interessi posticipati 31/3 e 30/9) | Fascicolo iniziale |
| `dati/04_estratto_conto_banca_al_30_11_2025.csv` | Estratto conto bancario **solo fino al 30/11/2025** | Fascicolo iniziale |
| `dati/05_verbale_assemblea_28_04_2025.md` | Verbale di assemblea: vertenza in corso con un fornitore | Fascicolo iniziale |
| `dati/06_estratto_conto_banca_dicembre_2025.csv` | Estratto conto di dicembre, saldo al 31/12/2025 | Dopo la richiesta al cliente |
| `dati/07_prospetto_TFR_2025.csv` | Prospetto TFR al 31/12/2025 | Dopo la richiesta al cliente |
| `dati/10_bilancio_verifica_2025_dopo_rettifiche_A1_A2.csv` | Bilancio di verifica che recepisce le rettifiche approvate A1 e A2 | Dopo l'approvazione delle rettifiche |
| `dati/11_comunicazione_banca_revisione_tasso.md` | Comunicazione della banca: tasso 4,50% dal 01/10/2025 | **Dopo** l'approvazione (20/01/2026) |
| `dati/12_bilancio_verifica_2025_dopo_rettifiche_A1_A2bis.csv` | Bilancio di verifica che recepisce A1 e la rettifica sostitutiva A2-bis | Dopo la nuova approvazione (23/01/2026) |
| `dati/13_prova_errore_E1_bdv_con_conti_estranei.csv` | **Prova di errore E1**: bilancio di verifica che quadra ma modifica anche conti estranei alle rettifiche approvate | Solo nella prova E1, al posto del documento 10 |
| `dati/14_prova_errore_E2_bdv_con_A2_e_A2bis.csv` | **Prova di errore E2**: bilancio di verifica che conta insieme A2 e A2-bis | Solo nella prova E2, al posto del documento 12 |

Il consulente esterno dichiara che il fascicolo iniziale «è completo».

---

## 3. Fasi e risultati attesi

### Fase 1 — Apertura del caso
- L'origine della contabilità va indicata esplicitamente: **contabilità esterna** (`CONTABILITA_ESTERNA`). Non va dedotta
  da nomi, documenti o casi precedenti. La indica il professionista P1 all'apertura del caso (08/01/2026); resta nella
  scheda del caso con autore e data. È un dato di apertura, non una decisione sul merito: per questo non compare nel
  registro delle decisioni.
- I documenti del fascicolo iniziale (01-05) entrano nell'inventario prima di essere usati.
- La dichiarazione «il fascicolo è completo» **non** equivale a «le evidenze sono sufficienti».

### Fase 2 — Valutazione del fascicolo

| Requisito | Documento | Stato atteso | Conseguenza |
|---|---|---|---|
| R1 Bilancio di verifica corrente e comparativo | 01 | Disponibile e sufficiente (`AVAILABLE_SUFFICIENT`) | — |
| R2 Registro cespiti | 02 | Disponibile e sufficiente | — |
| R3 Contratti di finanziamento | 03 | Disponibile e sufficiente | — |
| R4 Estratti conto bancari al 31/12 | 04 | **Disponibile ma non aggiornato** (`AVAILABLE_STALE`): arriva solo al 30/11 | Carenza confermata → richiesta |
| R5 Prospetto TFR al 31/12 | — | **Mancante** (`MISSING`) | Carenza confermata → richiesta |
| R6 Inventario di magazzino | — | **Non applicabile, con motivo**: società di servizi, nessun conto di magazzino | Nessuna richiesta |
| R7 Contenziosi e rischi | 05 | **Da sottoporre a revisione** (`REVIEW_REQUIRED`): il verbale cita una vertenza da 8.000 € | Nessuna richiesta automatica; blocca l'avanzamento finché il professionista non decide |

**Esito atteso:**
- fascicolo **insufficiente** per due carenze confermate (R4, R5);
- **una sola bozza** di richiesta al cliente con **due voci** (estratto conto di dicembre, prospetto TFR al 31/12);
- R7 **non** compare nella bozza;
- la bozza **non viene inviata**: resta una bozza da approvare;
- il professionista conferma le due carenze e la non applicabilità di R6 e approva la richiesta (record **D-FASC1**,
  09/01/2026). Solo dopo l'approvazione lo studio invia la richiesta al cliente.

### Fase 3 — Integrazione del fascicolo
- Arrivano i documenti 06 e 07:
  - R4 → sufficiente: il saldo bancario al 31/12 dell'estratto (**129.800,00**) coincide con il conto 1410 del bilancio
    di verifica;
  - R5 → sufficiente: il fondo TFR del prospetto (**18.500,00**) coincide con il conto 2110.
- Il professionista decide su R7: la vertenza sarà valutata nell'area «Fondi per rischi e oneri». La decisione viene
  registrata con autore, motivo ed evidenza (record **D-R7**, 12/01/2026, documento 05). D-R7 decide **dove** si valuta
  la vertenza, non **se** accantonare: quella decisione resta aperta (vedi fase 7).
- **Esito atteso:** fascicolo **sufficiente per iniziare**, confermato dal professionista (record **D-FASC2**,
  12/01/2026). Si apre lo screening del bilancio di verifica, **non ancora** la scelta della forma né il mapping.

### Fase 4 — Screening del bilancio di verifica (documento 01)

| Controllo | Risultato atteso |
|---|---|
| Periodo | 2025, comparativo 2024 presente |
| Quadratura 2025 | Dare = Avere = **807.800,00** |
| Quadratura 2024 | Dare = Avere = **727.200,00** |
| Convenzione Dare/Avere | Confermata |
| Scritture di chiusura | **Non incluse** |

**Perché le chiusure risultano mancanti:**
- conto 4140 «Ammortamento impianti e macchinari» a zero nel 2025, mentre il registro cespiti indica una quota 2025 di
  12.000,00 (nel 2024 era registrata);
- conto 2410 «Ratei passivi» a zero nel 2025, mentre il contratto prevede interessi posticipati al 31/3 e al 30/9: al
  31/12 maturano tre mesi di interessi non ancora pagati (nel 2024 il rateo era 1.000,00).

**Esito atteso:** il professionista rivede lo screening controllo per controllo e lo conferma (record **D-SCR1**,
13/01/2026). Solo allora si apre la **fase delle rettifiche di chiusura**. Forma e mapping restano bloccati.

### Fase 5 — Rettifiche di chiusura

| Rettifica | Dare | Avere | Importo | Fonte | Calcolo |
|---|---|---|---|---|---|
| **A1** Ammortamento 2025 | 4140 Ammortamento impianti e macchinari | 1015 Fondo ammortamento impianti e macchinari | 12.000,00 | 02 registro cespiti | 80.000 × 15% |
| **A2** Rateo interessi ott-dic 2025 | 4210 Interessi passivi su finanziamenti | 2410 Ratei passivi | 1.000,00 | 03 contratto | 100.000 × 4% × 3/12 |

**Risultati attesi:**
- ogni proposta è **bilanciata** e collegata alla sua fonte;
- il professionista le approva. L'approvazione significa solo che le scritture **possono essere registrate in
  contabilità**: nessuna registrazione automatica e nessuna modifica del bilancio di verifica originale;
- il registro delle decisioni contiene, oltre ai record delle fasi 2-4 (D-FASC1, D-R7, D-FASC2, D-SCR1), un record per
  ciascuna rettifica, con autore e ruolo diversi da chi l'ha proposta (il registro completo è alla fase 8):

| Record | Oggetto | Proposta da (ruolo) | Decisione | Decisa da (ruolo) | Data | Motivazione | Evidenze | Stato |
|---|---|---|---|---|---|---|---|---|
| D-A1 | Rettifica A1 | Collaboratore C1 (preparatore) | Approvata | Professionista P1 (approvatore) | 15/01/2026 | Quota 2025 del registro cespiti non registrata | doc. 02 | Valida |
| D-A2 | Rettifica A2 | Collaboratore C1 (preparatore) | Approvata | Professionista P1 (approvatore) | 15/01/2026 | Interessi ott-dic 2025 maturati e non pagati al 31/12 | doc. 03 | Valida (fino alla fase 8) |

  C1 e P1 sono persone fittizie: conta solo che preparatore e approvatore siano distinti e tracciati;
- lo studio carica il nuovo bilancio di verifica (documento 10). Deve valere **esattamente**: documento 10 = documento 01 + A1 + A2;
- conti cambiati: 1015 (18.000 → 30.000 Avere), 4140 (0 → 12.000 Dare), 4210 (3.000 → 4.000 Dare), 2410 (0 → 1.000 Avere);
- totali 2025 del documento 10: Dare = Avere = **820.800,00**;
- risultato ante imposte 2025: da 61.600,00 a **48.600,00**;
- nuovo screening sul documento 10: le due rettifiche previste dal caso risultano recepite e il professionista lo
  conferma (record **D-SCR2**, 16/01/2026). **Solo ora** si aprono la forma e il mapping;
- l'apertura di forma e mapping **consente di proseguire il lavoro, ma non attesta che il bilancio sia completo**:
  restano aperte almeno le imposte 2025 (area Imposte) e la valutazione della vertenza (area Fondi per rischi e oneri).

### Fase 6 — Forma del bilancio
- **Micro-impresa (art. 2435-ter): non ammissibile.** Ricavi, attivo e dipendenti superano i limiti in entrambi gli
  esercizi.
- **Abbreviato (art. 2435-bis): ammissibile.** I valori sono molto inferiori ai limiti in entrambi gli esercizi.
- La scelta resta del professionista. Nel caso: **abbreviato**. La scelta viene registrata (record **D-FORMA**,
  16/01/2026) con autore, motivazione ed evidenze: documento 10 per ricavi e attivo dei due esercizi, dipendenti medi
  dalla scheda della società (sezione 1).

### Fase 7 — Aree

| Area | Atteso | Segnali |
|---|---|---|
| Immobilizzazioni materiali | Attiva | Conti 1010, 1015, 4140; registro cespiti |
| Crediti e ricavi | Attiva | Conti 1210, 3010 |
| Cassa e banche | Attiva | Conti 1410, 1420; estratti conto |
| Debiti e finanziamenti | Attiva | Conti 2210, 2310, 4210; contratto |
| Personale e TFR | Attiva | Conti 2110, 2230, 4110-4130; prospetto TFR |
| Imposte | Attiva | Conti 1250, 2220, 4910. **Questione aperta:** imposte 2025 da determinare (fuori perimetro del caso) |
| Ratei e risconti | Attiva | Conto 2410: saldo comparativo 2024 e, nel 2025, dopo A2 |
| Patrimonio netto | Attiva | Conti 2010, 2020, 2030; verbale (destinazione dell'utile 2024) |
| Fondi per rischi e oneri | Attiva per valutazione | Proposta dal documento 05: **non determinabile**, con brano e periodo; serve una decisione professionale motivata. Il caso **non** stabilisce se accantonare: verifica solo che la decisione sia richiesta e registrata |
| Altre componenti economiche | Attiva | Conti 4010, 4020, 4310 |
| Rimanenze | **Esclusione proposta, poi confermata (D-ESCL)** | Nessun conto e nessun documento; società di servizi. L'esclusione non prova da sola l'assenza della fattispecie |
| Rendiconto finanziario | **Esclusione proposta, poi confermata (D-ESCL)** | Bilancio abbreviato: rendiconto non obbligatorio |
| Cambiamenti, errori e fatti successivi | **Esclusione proposta e confermata (D-ESCL)**, poi **attiva** nella fase 8 (D-FS) | Nessun segnale finché non arriva il documento 11 (vedi fase 8) |
| Immobilizzazioni immateriali | Esclusione proposta, poi confermata (D-ESCL) | Nessun conto e nessun documento |
| Partecipazioni e gruppo | Esclusione proposta, poi confermata (D-ESCL) | Nessun conto e nessun documento |
| Leasing | Esclusione proposta, poi confermata (D-ESCL) | Nessun contratto di leasing; il conto 4020 è l'affitto dei locali, come indicato nella sua descrizione |
| Patrimoni e finanziamenti destinati | Esclusione proposta, poi confermata (D-ESCL) | Nessun segnale |
| Fusioni e scissioni | Esclusione proposta, poi confermata (D-ESCL) | Nessun segnale |
| Quote di emissione | Esclusione proposta, poi confermata (D-ESCL) | Nessun segnale |
| Titoli di debito | Esclusione proposta, poi confermata (D-ESCL) | Nessun conto e nessun documento |
| Lavori in corso su ordinazione | Esclusione proposta, poi confermata (D-ESCL) | Nessun conto e nessun documento |
| Operazioni in valuta estera | Esclusione proposta, poi confermata (D-ESCL) | Nessun conto né documento in valuta |
| Bilanci intermedi | Esclusione proposta, poi confermata (D-ESCL) | Non richiesti: bilancio d'esercizio |
| Strumenti finanziari derivati | Esclusione proposta, poi confermata (D-ESCL) | Nessun conto; il contratto di finanziamento (doc. 03) non prevede derivati |
| Passaggio ai principi contabili nazionali | Esclusione proposta, poi confermata (D-ESCL) | Società già redatta secondo OIC negli esercizi precedenti |

Totale: 25 aree, di cui 10 attive, 2 escluse con motivo specifico (Rimanenze, Rendiconto finanziario) e 13 escluse per
assenza di segnali. Una di queste, «Cambiamenti, errori e fatti successivi», si attiva nella fase 8.

**Esclusione proposta ed esclusione confermata.** Le 15 esclusioni nascono come **proposte** del sistema, motivate
dall'assenza di segnali. L'assenza di conti o documenti, da sola, non dimostra che l'area non sia applicabile:
- finché il professionista non decide, lo stato atteso è «esclusione proposta», non «esclusa»;
- l'esclusione diventa **confermata** solo con la decisione del professionista: record D-ESCL del 16/01/2026, vedi
  registro alla fase 8.

### Fase 8 — Modifica successiva: arriva il documento 11
Il 20/01/2026, **dopo** l'approvazione di A1 e A2, lo studio riceve la comunicazione della banca: dal 01/10/2025 il tasso
è il 4,50%.

La comunicazione arriva dopo la data di chiusura, ma riguarda una condizione già esistente al 31/12/2025: il tasso del
4,50% si applica dal 01/10/2025. È quindi un **fatto successivo da recepire nei valori di bilancio** (OIC 29).

**Stato atteso tra l'arrivo del documento 11 (20/01/2026) e l'approvazione di A2-bis (22/01/2026):**
- l'arrivo del documento 11 apre un **riesame di A2** e dell'**esclusione dell'area «Cambiamenti, errori e fatti
  successivi»**, registrato come nuovo evento (record R-A2). Il documento 11 è proprio il segnale che mancava a
  quell'area. D-A2 e D-ESCL non vengono modificati;
- **A2 è «da riesaminare»**: è ancora la rettifica in vigore, ma non può più essere considerata definitiva;
- l'esclusione dell'area **«Cambiamenti, errori e fatti successivi» è «da riesaminare»**; le altre 14 esclusioni
  confermate restano valide;
- la **validazione è sospesa** per ciò che dipende da A2 e dal documento 11: aree Ratei e risconti, Debiti e
  finanziamenti e Cambiamenti, errori e fatti successivi; mapping dei conti 4210 e 2410; validazione complessiva;
- **A1 resta valida**; fascicolo e forma restano confermati;
- il documento 10 resta l'ultimo bilancio di verifica acquisito, ma il lavoro non può arrivare alla chiusura finché il
  riesame è aperto; in ogni caso restano aperte imposte 2025 e valutazione della vertenza;
- nessuna rettifica è ancora sostituita: **la sostituzione di A2 scatta solo con l'approvazione di A2-bis**.

**Risultati attesi dal 22/01/2026, con l'approvazione di A2-bis:**
- si **attiva** l'area **«Cambiamenti, errori e fatti successivi»**. Il documento 11 viene qualificato come fatto
  successivo da recepire, con decisione professionale registrata (D-FS);
- la rettifica sostitutiva **A2-bis** viene proposta e approvata: Dare 4210 / Avere 2410 per **1.125,00**
  (100.000 × 4,5% × 3/12), con fonte il documento 11;
- la decisione su **A2 resta consultabile** con lo stato «sostituita» e il riferimento ad A2-bis. **Non vale più** sul caso;
- **A1 resta valida**: non è toccata dalla modifica;
- il registro delle decisioni si aggiorna così:

| Record | Oggetto | Proposta da (ruolo) | Decisione | Decisa da (ruolo) | Data | Motivazione | Evidenze | Stato |
|---|---|---|---|---|---|---|---|---|
| D-FASC1 | Valutazione del fascicolo iniziale: carenze R4 e R5, non applicabilità di R6, richiesta al cliente (2 voci) | Sistema (proposta) | Carenze e non applicabilità confermate; richiesta approvata | Professionista P1 (approvatore) | 09/01/2026 | Estratto conto fermo al 30/11; prospetto TFR assente; società di servizi senza conti di magazzino | doc. 01, doc. 04 | Valida |
| D-R7 | R7 Contenziosi e rischi: dove valutare la vertenza citata nel verbale | Sistema (segnalazione) | Vertenza da valutare nell'area «Fondi per rischi e oneri»; nessuna richiesta al cliente | Professionista P1 (approvatore) | 12/01/2026 | La richiesta di penali da 8.000 € richiede una valutazione professionale, non documenti dal cliente | doc. 05 | Valida; la decisione se accantonare resta aperta |
| D-FASC2 | Sufficienza del fascicolo dopo l'integrazione | Sistema (controlli meccanici) | Fascicolo sufficiente per iniziare | Professionista P1 (approvatore) | 12/01/2026 | Saldo banca al 31/12 e fondo TFR coincidono con i conti 1410 e 2110; R7 decisa con D-R7 | doc. 06, doc. 07; decisione collegata: D-R7 | Valida |
| D-SCR1 | Screening del bilancio di verifica (doc. 01), controllo per controllo | Sistema (controlli meccanici) | Confermato: chiusure non incluse, si apre la fase delle rettifiche | Professionista P1 (approvatore) | 13/01/2026 | Quadrature 807.800,00 e 727.200,00; convenzione Dare/Avere confermata; ammortamento e rateo 2025 a zero nonostante registro cespiti e contratto | doc. 01, doc. 02, doc. 03 | Valida |
| D-A1 | Rettifica A1 | Collaboratore C1 (preparatore) | Approvata | Professionista P1 (approvatore) | 15/01/2026 | Quota 2025 del registro cespiti non registrata | doc. 02 | **Valida** |
| D-A2 | Rettifica A2 | Collaboratore C1 (preparatore) | Approvata | Professionista P1 (approvatore) | 15/01/2026 | Interessi ott-dic 2025 maturati e non pagati al 31/12 | doc. 03 | **Sostituita da D-A2-bis**: consultabile, non più valida |
| D-SCR2 | Screening del bilancio di verifica (doc. 10) | Sistema (controlli meccanici) | Confermato: recepisce esattamente A1 e A2; si aprono forma e mapping | Professionista P1 (approvatore) | 16/01/2026 | Documento 10 = documento 01 + A1 + A2; quadratura 820.800,00 | doc. 01, doc. 10; decisioni collegate: D-A1, D-A2 | Superata dal 22/01: il doc. 10 recepisce A2, sostituita; serve un nuovo screening sul doc. 12 (D-SCR3) |
| D-FORMA | Forma del bilancio | Sistema (proposta) | Abbreviato (art. 2435-bis) | Professionista P1 (approvatore) | 16/01/2026 | Micro-impresa non ammissibile: limiti superati in entrambi gli esercizi; abbreviato ammissibile | doc. 10; dipendenti medi dalla scheda della società | Valida |
| D-ESCL | Conferma delle 15 esclusioni proposte (fase 7) | Sistema (proposta) | Confermata | Professionista P1 (approvatore) | 16/01/2026 | Nessuna fattispecie emersa dal bilancio di verifica e dai documenti 01-07 | doc. 01-07 | Valida; per «Cambiamenti, errori e fatti successivi» da riesaminare dal 20/01 (R-A2) e superata da D-FS |
| R-A2 | Apertura del riesame di A2 e dell'esclusione dell'area «Cambiamenti, errori e fatti successivi» | Collaboratore C1 (preparatore) | Riesame aperto | — | 20/01/2026 | Nuova evidenza sul tasso, che è anche un segnale per l'area esclusa | doc. 11 | Chiuso dall'approvazione di D-A2-bis |
| D-FS | Qualificazione del doc. 11 come fatto successivo da recepire | Collaboratore C1 (preparatore) | Confermata | Professionista P1 (approvatore) | 22/01/2026 | Condizione esistente al 31/12 (tasso dal 01/10/2025) | doc. 11 | Valida |
| D-A2-bis | Rettifica A2-bis | Collaboratore C1 (preparatore) | Approvata | Professionista P1 (approvatore) | 22/01/2026 | Rateo ricalcolato al 4,50% | doc. 03, doc. 11 | Valida; indica D-A2 come decisione sostituita |

  Al 22/01 il registro è **completo**: dodici record in ordine di data, cioè le undici decisioni professionali del
  caso più l'apertura del riesame (R-A2). Non contiene:
  - l'origine della contabilità, che è un dato di apertura del caso (fase 1);
  - i singoli esiti dei controlli automatici (stato dei requisiti, quadrature, confronto tra bilanci di verifica):
    nel registro ci sono le conferme del professionista che li rivede (D-FASC1, D-FASC2, D-SCR1, D-SCR2);
  - la decisione se accantonare per la vertenza: il caso si ferma prima che venga presa.

  Con il documento 12 si aggiunge un nuovo record, D-SCR3 (vedi sotto). D-SCR2 resta com'è, «superata».

  I record restano **identici** a quando sono stati creati: D-A1 e D-A2 hanno gli stessi campi e la stessa motivazione
  della fase 5. La colonna «Stato» è una **vista calcolata**:
  - dal 20/01 al 22/01 D-A2 e l'esclusione dell'area «Cambiamenti, errori e fatti successivi» (parte di D-ESCL)
    risultano «da riesaminare», per effetto di R-A2;
  - dal 22/01 D-A2 risulta «sostituita», perché D-A2-bis la indica come decisione sostituita, e D-SCR2 risulta
    «superata», perché il documento 10 recepisce A2.

  In nessun momento D-A2 o D-ESCL vengono modificati.

**Stato atteso dopo l'approvazione di A2-bis (22/01/2026) e prima dell'acquisizione e del controllo del documento 12:**
- il riesame R-A2 è chiuso: A2 è sostituita, A2-bis è la rettifica valida, l'area «Cambiamenti, errori e fatti
  successivi» è attiva;
- la chiusura del riesame **non sblocca da sola** le validazioni dipendenti. Restano **sospese**: aree Ratei e risconti,
  Debiti e finanziamenti e Cambiamenti, errori e fatti successivi; mapping dei conti 4210 e 2410; validazione
  complessiva;
- il documento 10 non è più una base valida, perché recepisce A2 e non A2-bis; il nuovo bilancio di verifica non è
  ancora arrivato;
- le validazioni dipendenti possono riprendere solo quando il documento 12 è acquisito e il nuovo screening, confermato
  dal professionista (D-SCR3), verifica che corrisponde esattamente al documento 01 + A1 + A2-bis; si chiudono solo dopo aver
  ripetuto carte di lavoro e controlli;
- se al posto del documento 12 arriva il documento 14 (prova E2), lo stato resta questo;
- imposte 2025 e valutazione della vertenza restano aperte in ogni caso: nessuna chiusura è possibile.

**Risultati attesi con l'acquisizione del documento 12 (23/01/2026):**
- si riapre lo **screening** sul nuovo bilancio di verifica. Deve valere **esattamente**: documento 12 = documento 01 +
  A1 + A2-bis;
- differenze rispetto al documento 10: conto 4210 +125,00 e conto 2410 +125,00;
- totali 2025 del documento 12: Dare = Avere = **820.925,00**; risultato ante imposte **48.475,00**;
- il professionista conferma il nuovo screening. Al registro si aggiunge un record, senza modificare i precedenti:

| Record | Oggetto | Proposta da (ruolo) | Decisione | Decisa da (ruolo) | Data | Motivazione | Evidenze | Stato |
|---|---|---|---|---|---|---|---|---|
| D-SCR3 | Screening del bilancio di verifica (doc. 12) | Sistema (controlli meccanici) | Confermato: recepisce esattamente A1 e A2-bis; riprendono le validazioni dipendenti | Professionista P1 (approvatore) | 23/01/2026 | Documento 12 = documento 01 + A1 + A2-bis; quadratura 820.925,00 | doc. 01, doc. 12; decisioni collegate: D-A1, D-A2-bis | Valida |

  Dal 23/01 D-SCR2 risulta «superata da D-SCR3»;
- superato e confermato lo screening, si riaprono e vanno ripetuti:
  - la revisione del mapping dei conti 4210 e 2410;
  - le aree **Ratei e risconti** e **Debiti e finanziamenti**, con carte di lavoro e controlli;
  - l'area **Cambiamenti, errori e fatti successivi**, appena attivata;
  - la validazione complessiva.
- non si riaprono: le decisioni sul fascicolo (D-FASC1, D-R7, D-FASC2), lo screening del documento 01 (D-SCR1), la
  rettifica A1, la scelta della forma (D-FORMA). La forma resta abbreviata, ma la validazione va ripetuta;
- imposte 2025 e valutazione della vertenza restano aperte: anche con il documento 12 il bilancio non è completo.

### Prove di errore

**E1 — Bilancio di verifica che quadra ma contiene conti estranei.** Al posto del documento 10 arriva il documento 13:
contiene A1 e A2, ma anche +500,00 su 1210 Crediti verso clienti (Dare) e +500,00 su 3010 Ricavi delle prestazioni
(Avere), per una scrittura non approvata. Quadra lo stesso: Dare = Avere = **821.300,00**.

Atteso:
- il confronto con documento 01 + A1 + A2 rileva differenze **non autorizzate** su 1210 e 3010 (500,00 ciascuna);
- il bilancio di verifica **non viene accettato** come base del lavoro e forma e mapping restano bloccati;
- si apre una questione per il professionista (chiarimento con il consulente esterno), senza correzioni automatiche.

**E2 — A2 e A2-bis contate insieme.** Al posto del documento 12 arriva il documento 14: contiene A1, A2 e A2-bis.
Interessi 4210 = **5.125,00**, ratei 2410 = **2.125,00**; quadra: **821.925,00**.

Atteso:
- il confronto con documento 01 + A1 + A2-bis rileva una differenza di 1.000,00 su 4210 e 2410, pari ad A2, già
  sostituita;
- il bilancio di verifica **non viene accettato**, e il sistema segnala che A2 non può essere contata insieme ad A2-bis;
- nel registro non deve essere possibile avere due rettifiche valide sullo stesso rateo: A2-bis può essere approvata
  solo indicando A2 come sostituita;
- nessuno screening può essere confermato: D-SCR3 non viene creato e resta lo stato «dopo l'approvazione di A2-bis e
  prima del controllo del documento 12».

---

## 4. Cosa non deve mai succedere
1. Partire con forma o mapping prima che fascicolo, screening e rettifiche siano rivisti.
2. Trattare la dichiarazione «fascicolo completo» come sufficienza delle evidenze.
3. Chiedere al cliente documenti già presenti, o inserire R7 nella richiesta.
4. Inviare la richiesta al cliente o registrare le rettifiche in contabilità in automatico.
5. Accettare un nuovo bilancio di verifica che non corrisponde esattamente al precedente più le rettifiche approvate.
6. Cancellare o sovrascrivere la decisione su A2: va sostituita, restando consultabile.
7. Riaprire ciò che la modifica non tocca (A1, fascicolo, forma) o non riaprire ciò che tocca (aree Ratei e risconti, Debiti e finanziamenti, Cambiamenti, errori e fatti successivi).
8. Decidere in automatico sull'accantonamento per la vertenza, o trattare come definitiva un'esclusione di area non
   confermata dal professionista.
9. Accettare un bilancio di verifica che quadra ma contiene variazioni su conti estranei alle rettifiche approvate
   (prova E1).
10. Considerare valide insieme A2 e A2-bis (prova E2).
11. Considerare «bilancio completo» il solo fatto che forma e mapping siano aperti.
12. Riprendere le validazioni dipendenti con la sola chiusura del riesame, senza il nuovo bilancio di verifica
    acquisito e controllato.
13. Prendere una decisione professionale senza registrarla con autore, motivazione ed evidenze.

## 5. Numeri di controllo

| Controllo | Valore atteso |
|---|---|
| Totali bilancio di verifica 2025 prima delle chiusure (doc. 01) | 807.800,00 |
| Totali bilancio di verifica 2024 (comparativo) | 727.200,00 |
| Totali dopo A1 + A2 (doc. 10) | 820.800,00 |
| Totali dopo A1 + A2-bis (doc. 12) | 820.925,00 |
| Totali prova E1 (doc. 13) | 821.300,00 |
| Totali prova E2 (doc. 14) | 821.925,00 |
| Prova E2: interessi passivi / ratei passivi | 5.125,00 / 2.125,00 |
| Saldo banca al 31/12/2025 | 129.800,00 |
| Fondo TFR al 31/12/2025 | 18.500,00 |
| Fondo ammortamento impianti dopo A1 | 30.000,00 |
| Interessi passivi 2025: prima / dopo A2 / dopo A2-bis | 3.000,00 / 4.000,00 / 4.125,00 |
| Ratei passivi 2025: prima / dopo A2 / dopo A2-bis | 0,00 / 1.000,00 / 1.125,00 |
| Risultato ante imposte 2025: prima / dopo A1 + A2 / dopo A1 + A2-bis | 61.600,00 / 48.600,00 / 48.475,00 |
| Utile 2024 (dal comparativo) | 18.000,00 |

Gli interessi 2025 prima delle chiusure valgono 3.000,00: due pagamenti da 2.000,00 (31/3 e 30/9), meno lo storno del
rateo 2024 di 1.000,00.

I risultati attesi in forma leggibile da un programma sono in `risultati_attesi.json`.
