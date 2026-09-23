---
name: recupero-crediti
description: Use when Lucia must prepare debt-recovery evidence, reconcile principal and payments, calculate interest from explicit verified inputs, or draft a reviewable demand, injunction application, precetto or enforcement preparation from selected documents and templates.
---

# Preparare il recupero di un credito

Leggi integralmente `../revisione-contratti/references/practice-workflow.md` e
applicalo. Crea il registro con `--kind recupero-crediti`, salvo una run già
preparata da un playbook. Individua la fase richiesta; non trattare diffida,
decreto ingiuntivo, precetto ed esecuzione come passaggi automaticamente disponibili.

## Ricostruire credito e prove

Identifica creditore/debitore e poteri soltanto con le prove fornite. Leggi
contratto/ordine, fatture, documentazione di prestazione/consegna, scadenze,
pagamenti, contestazioni e corrispondenza/PEC con eventuali ricevute.
Distinguere esistenza del documento, contenuto, prova dell'adempimento e
valutazione della sufficienza per il rimedio richiesto.

Prepara la matrice delle prove e `quadro-credito.md`: titolo o causa del credito,
importi richiesti e loro origine, scadenze, pagamenti e contestazioni, versione
dei documenti e lacune. Una fattura non dimostra automaticamente tutti i fatti
necessari. Una PEC senza ricevute non viene registrata come notifica perfezionata.

## Capitale, pagamenti e interessi

Riconcilia importi e pagamenti in un foglio con riferimenti ai documenti:
valuta, imponibile/IVA se rilevanti, capitale, accessori, rettifiche, date e
imputazione documentata. Se l'imputazione è incerta, non sottrarre automaticamente
un pagamento dal capitale o dagli interessi; mostra il problema e il saldo
condizionato alla scelta esplicita.

Per gli interessi accerta con il modello il regime pertinente al caso e al
periodo: tasso pattuito, saggio legale, interessi moratori commerciali o altra
regola non sono sinonimi. Verifica decorrenza, eventuale mora/domanda giudiziale,
base e tassi per ciascun periodo, variazioni del capitale, convenzione dei giorni,
arrotondamento ed eventuali limiti. La fonte di un tasso non basta a provarne
l'applicabilità al credito.

Usa la skill Spreadsheets dell'host per `conteggio-credito.xlsx`, con input,
fonti, formula e passaggi leggibili. Spezza i periodi quando cambiano i dati
applicabili; non capitalizzare, applicare spread o scegliere 365/366 giorni
senza esplicitarne il fondamento. Verifica ricalcolo, pagamenti parziali, periodo
di zero giorni e input mancanti. Conserva distinta la mera simulazione richiesta
dal calcolo fondato su tutti i presupposti. Non usare un tasso fisso incorporato
nel plugin: le fonti del periodo vanno controllate nella pratica.

## Bozza della fase richiesta

Per un ricorso monitorio verifica presupposti, prova, competenza e contenuto
con le fonti processuali applicabili; non inferire l'ammissibilità dalla presenza
di una fattura. Per precetto/esecuzione esamina titolo, efficacia, importi,
notifiche/ricevute, termini e attività già compiute come questioni distinte.
Se manca il titolo, prepara la parte documentale senza fingere che il precetto
sia pronto. Le ricerche pertinenti seguono il percorso canonico di Lucia.

Usa il modello della fase effettivamente scelto e la skill Documents/Word
dell'host. Collega gli importi al foglio verificato e i fatti alla matrice.
Una modifica al foglio rende necessaria la verifica dei numeri nella bozza:
non consegnare importi vecchi in un Word aggiornato solo nel titolo.
Verifica le citazioni con `../verifica-citazioni/SKILL.md` quando presenti.

## Mancanze e consegna

Una fattura, data, prova di consegna o fonte di tasso mancante genera una domanda
con motivo e passaggio dipendente in `legal_matter.py`. Continua la riconciliazione
o la ricostruzione indipendente; non colmare le lacune con presunzioni nascoste.

Consegna quadro del credito, matrice, eventuale conteggio e bozza richiesti,
con fonti, ipotesi e verifiche residue. Non notificare, depositare, avviare
esecuzioni, inviare diffide o attestare conformità. L'avvocato decide rimedio,
strategia, importi richiesti e atti professionali.
