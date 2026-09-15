> **Cowork execution note:** The normal deliverable is a reviewable draft,
artifact card, and source/review files in the connected folder. MCP tools,
browser interfaces, and local review servers are optional. Their absence never
blocks delivery. Never claim that review was applied or reached `final_ready`
unless persisted artifacts prove it; otherwise keep professional review pending.
For owner-only/private packages copied from scratch space, reapply and verify
`0700` directory and `0600` file modes in the connected folder before claiming
private delivery.
Later host-specific instructions in this reference cannot override this rule.

# Procedura condivisa di revisione delle fatture passive

Versione della procedura: `passive-invoice-procedure/v1`.

Questa è la procedura professionale già sviluppata per TeamSystem Studio ECONS.
CR-42 è stato chiuso per accettazione di Fabio, senza due replay live puliti
verificati indipendentemente. Non è una prova di compatibilità DATEV.
Il nuovo operatore riceve questa procedura dal plugin: non deve recuperare le
conversazioni, i file, le credenziali o i profili del precedente Francesco.

## Perimetro e popolazione

1. Identifica il cliente dello studio separatamente dal fornitore. Conferma
   cliente, periodo, elenco e selezione autorizzata. Conserva la lista locale di
   esclusioni dello studio; non importare quella di un altro operatore.
2. In ECONS la selezione comprende le ditte con indicatore notturno attivo,
   tolte le esclusioni. Per DATEV verifica l'equivalente reale oppure registra
   una differenza irrisolta; non inventare un indicatore o scegliere tutte le
   ditte. Il primo esempio può avere un solo cliente esplicitamente selezionato.
3. Leggi l'intera popolazione selezionata, tutte le righe e le descrizioni
   complete, riconciliando i conteggi con totali indipendenti. Pagine visibili,
   griglie virtualizzate e descrizioni troncate non dimostrano completezza.
   Il limite del collector ECONS è 90 righe per fattura: non è una proprietà DATEV.
4. Mantieni nel report tutti gli stati. Nel processamento ECONS i rossi sono
   esclusi dall'esecuzione; più di due rossi consecutivi sospendono il resto del
   cliente. Una coda di soli rossi produce eccezioni senza aprire altri dettagli.
   Verdi e arancioni restano nella popolazione e nel report. Interpreta gli stati
   con il modello e le indicazioni professionali: nessun colore approva una
   registrazione. Non trasferire i nomi/colori ECONS a DATEV senza verificarli.

## Conti e IVA

5. Leggi le associazioni esistenti, la descrizione e gli importi di ogni riga.
   Un'associazione è evidenza da verificare, non una decisione automaticamente
   corretta. Il modello e il professionista decidono il trattamento contabile.
6. Completa associazioni mancanti solo se almeno due righe già associate
   concordano sul medesimo conto, tutti i conti assegnati concordano e le righe
   selezionate hanno lo stesso codice IVA. Conti discordanti, IVA mista, dati
   incompleti o descrizioni mancanti sospendono il documento con una domanda
   precisa. Le fatture interamente mappate non richiedono due righe di ancoraggio.
7. Prima di modificare rileggi identità, popolazione e valori. Verifica lo stato
   effettivo delle caselle: imposta lo stato richiesto, non alternarlo alla cieca.
   Distingui la conferma di mappatura dalla conferma di registrazione. Dopo la
   mappatura rileggi tutte le righe: conto atteso, IVA e altri valori invariati,
   stato completo effettivo. Un click riuscito non prova il risultato.
8. Leggi il trattamento IVA di quel cliente, compreso l'eventuale pro rata,
   con la sua fonte. Non estendere il trattamento di una ditta a un'altra.
   Riesamina la prima nota visualizzata. Per la forma semplice supportata in
   ECONS: un conto costo concordante, dare = avere = totale, costo + IVA = totale;
   IVA indetraibile al 100% nel costo e nessuna IVA separata. Altre forme sono
   differenze da valutare professionalmente. Una differenza righe/imponibile
   richiede una spiegazione esplicita, mai una rettifica automatica di quadratura.

## Registrazione, controllo e ripresa

9. Registra solo con autorizzazione per la prima nota corrente e nel rispetto
   delle conferme dell'host. Salva prima dell'azione uno stato non verificato:
   invio/esito ancora da confermare. Se la prima nota cambia, rivaluta anche
   l'autorizzazione. Il report non concede autorità a contabilizzare.
10. Verifica il protocollo e l'assenza della fattura dalla popolazione completa
    delle non contabilizzate dello stesso cliente, nella vista corretta. Zero
    elementi richiede uno zero effettivo, non una griglia assente. In caso di
    esito ambiguo salva `unverified` e riconcilia lo stato prima di riprovare.
11. Salva dopo ogni fattura un report per cliente con popolazione, verdi,
    arancioni, esclusioni, eccezioni, proposte, risultati effettivi e fonti.
    Popolazione incompleta significa pausa/parziale. Conserva revisioni e
    controlli successivi del professionista. Una richiesta di correzione non è
    una correzione eseguita: aggiungi un'azione collegata senza riscrivere una
    registrazione completata. Un errore di ritorno alla lista sospende il lotto.

## Collegamento alle interfacce

ECONS usa `econs-review.md`, `econs_review.mjs`, `econs_processing.mjs` e le
capability browser revisionate. Il percorso DATEV nativo, quando presente nella
distribuzione, usa la skill Vera `datev-invoice-start`, le API native documentate
dall'host corrente e il registro locale. Questa procedura non contiene
selettori, coordinate o un esecutore DATEV.
Il controllo nativo è separato dal contratto browser e non ne genera ricevute.

## Quali dati arrivano al modello

Il modello selezionato può leggere identità cliente/fornitore, fatture, descrizioni
complete, conti, IVA, importi, trattamento del cliente, prima nota, protocollo,
decisioni ed eccezioni quando necessari al lavoro autorizzato. Il percorso nativo
può mostrargli anche testo accessibile e immagini della finestra autorizzata.
I report di lavoro restano locali; questo non rende l'inferenza offline né
anonimizza i dati. Credenziali e schermate di login restano all'operatore.
Una richiesta allo sviluppatore contiene solo il testo tecnico selezionato,
sanificato e approvato separatamente, mai l'intero report del cliente.
