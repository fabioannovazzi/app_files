---
name: contenzioso-tributario
description: Use when Lucia must prepare or resume an Italian tax-litigation matter, identify required procedural steps and deadlines from the actual case, analyze a tax act or judgment, research grounds and precedents, or prepare a reviewable first-instance appeal, appellate pleading or subsequent submission. Covers preparation and progress, not filing, service, signature or background reminders.
---

# Preparare e riprendere un contenzioso tributario italiano

Lucia fornisce il metodo procedurale: l'avvocato descrive l'incarico e i fatti,
non deve scrivere una sequenza di comandi o ricordare ogni passaggio successivo.
Leggi integralmente `references/procedura-italiana.md`,
`references/termini-e-ripresa.md` e `references/fonti.md` prima dell'analisi.
Le fonti incorporate sono una base editoriale datata, da verificare nella pratica,
non una banca dati aggiornata automaticamente né una garanzia di completezza.

## Inquadrare il lavoro

Identifica parte assistita, obiettivo, tributo/periodo, atto e autorità, fase,
provvedimenti, fatti di notifica e attività già compiute. Leggi i materiali scelti
prima di chiedere ciò che manca. Non dedurre competenza, impugnabilità, validità
della notifica o decorrenza dal titolo del file, dalla lingua o da una data isolata.
Se il lavoro riguarda solo un atto o una memoria, limita la produzione a quello,
ma segnala i passaggi procedurali conseguenti o imminenti pertinenti al caso.

## Prove, ricerca e registro

Riusa la preparazione locale di
`../revisione-contratti/references/document-workflow.md`: ambiente condiviso,
controllo dipendenze, copie originali, ancore, copertura e matrice. Prepara con
`legal_documents.py prepare --workflow revisione-documentale` e voci scelte dal
caso. Registra il lavoro con `legal_matter.py init --kind contenzioso-tributario`;
per stato, salvataggi e ripresa segui
`../revisione-contratti/references/matter-progress.md`. Non riaprire da zero una
run esistente e non sovrascrivere le prove originali.

La verifica delle regole processuali e la ricerca dei precedenti sono parte
obbligatoria di questo percorso quando servono per il risultato richiesto.
Usa `../quesito-legale-fiscale/SKILL.md` e il suo metodo condiviso con il modello
e gli strumenti della sessione: investigazione, validazione continua, verifica
delle prove contrarie e revisione finale. Per una posizione concreta conserva
l'esame contrapposto finale salvo esclusione dell'utente. Non aprire un secondo
percorso indipendente per la stessa ricerca già validata; riusa fonti e record
ancora attuali e riapri le questioni cambiate. Il limite alla ricerca automatica
dei percorsi documentali di base non esclude questa ricerca specialistica.

Nelle query esterne usa riferimenti generali a norme e questioni, senza nomi,
identificativi, importi identificanti, citazioni private o allegati del cliente.
Il modello decide pertinenza, regime e passaggi; gli helper controllano soltanto
struttura, citazioni letterali, dipendenze dichiarate e integrità dei file.

## Elaborati e verifica

Consegna `inquadramento.md`, matrice delle prove e `piano-procedurale.md` con
azioni necessarie, condizionali, già compiute e aperte; per ciascuna indica evento,
fonte/versione, prova, dipendenza, responsabile e risultato richiesto.
`termini.md` distingue scadenze verificate, calcoli condizionati e termini ancora
non determinabili, con un calcolo leggibile. Non chiamare «eseguito» un deposito
perché esiste una bozza o un file scelto per l'upload.

Per la bozza richiesta usa il modello scelto e Documents/Word dell'host secondo
`../revisione-contratti/references/word-handoff.md`; se manca la capacità o un
modello essenziale, conserva l'analisi e rendi esplicito il passaggio aperto.
Verifica citazioni con `../verifica-citazioni/SKILL.md`, riferimenti e coerenza
con `../controllo-documento/SKILL.md`; ispeziona il documento renderizzato.
Non attestare che un ricorso è pronto al deposito con verifiche materiali aperte.

Prima della consegna cerca un evento non considerato, una parte o ricevuta
mancante, una regola superata, un presupposto di sospensione non provato e un
passaggio successivo omesso. Correggi e riverifica gli elaborati effettivi.
Il registro `matter.html` accompagna i file; il suo stato non certifica correttezza
giuridica né approvazione professionale. Firma, notifica, deposito, pagamento e
scelte processuali restano all'avvocato. Nessun alert futuro è attivo senza un
servizio dell'host effettivamente configurato su richiesta dell'utente.

## Quali dati arrivano al modello

Il modello della conversazione può leggere gli atti fiscali e giudiziari scelti,
nomi, codici fiscali e altri identificativi presenti, periodi d'imposta, importi,
ricevute PEC/postali, allegati, modello dello studio, risposte dell'avvocato,
cronologia, analisi, calendario e bozze; anche le pagine renderizzate quando
ispezionate. Le copie e il registro restano nella cartella locale scelta; gli
helper non inviano atti a Mike, agli enti o alle corti. La ricerca dell'host usa
questioni e riferimenti generali e può trasmettere quelle query ai siti consultati,
senza allegare il fascicolo. Conservare i file localmente non significa che il
modello li elabori offline o che siano anonimizzati. Indica i materiali realmente
letti e i limiti osservabili del percorso dell'host.
