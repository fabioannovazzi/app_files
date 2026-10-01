# Seguire evidenze e decisioni di un fascicolo ESG

La spiegazione e una breve prova richiedono circa 5–8 minuti. I tempi di elaborazione e le tue domande possono allungare la sessione.

Nella chat insegnante parli con la voce standard di Codex. Nella chat di lavoro, aperta nella finestra accanto, la funzione esegue il caso con i file preparati e mostra i risultati effettivi. L’insegnante segue quei risultati: puoi interrompere, fare domande e cambiare ritmo.

Parti dal materiale preparato e insegna l’intero primo utilizzo. Scegli 3–4 funzioni pertinenti durante l’onboarding; nelle visite successive parti da ciò che l’utente vuole fare oggi. Adatta il ritmo e le spiegazioni. Crea esempi personalizzati quando aiutano, mantenendo lo stesso workflow e verificando i nuovi input. Leggi execution-request.json, usa il vero caso locale abbinato e collega ogni spiegazione ai risultati verificati della chat di lavoro. Non inventare risultati, risposte dell’utente o conferme di comprensione. Mostrare il kit non completa la lezione.

## 1. A cosa serve · 45 s

Collega la funzione a un lavoro concreto del professionista.

Imparare a collegare un dato alla fonte, preparare una bozza parziale e riconoscere cosa richiede riesame dopo un aggiornamento.

Caso interamente fittizio: Officina Selce, un solo sito e il consumo elettrico dichiarato per il 2026. Il dato iniziale è 0 kWh; una rettifica indica 15 kWh. Non è una misurazione certificata.

Fondazione documentale ESG in Codex desktop e Work locale quando supportato. In Cowork il corso usa una sola conversazione scritta. Nessun report ESG completo, calcolo VSME/ESRS o tassonomia, conclusione di assurance, firma o invio.

## 2. I file e la richiesta · 60 s

Apri i file nella finestra di lavoro e mostra come chiedere il risultato.

Leggi brief-it.md ed energy.csv. La prima cella numerica vale zero; la cella 2025 vuota significa dato non disponibile. Il sito escluso è dichiarato non applicabile solo in questo caso fittizio: il vuoto da solo non lo dimostra. Conserva energy-update.csv per il secondo passaggio.

Vera, prepara il fascicolo fittizio di Officina Selce per il 2026. Collega i dati ai file, distingui zero, mancante e non applicabile, mostrami una decisione da rivedere e una bozza parziale. Poi acquisisci la rettifica da 0 a 15 kWh e mostrami cosa è diventato obsoleto.

## 3. Eseguiamo il lavoro · 105 s

Spiega il passaggio che sta avvenendo e attendi il suo risultato effettivo.

Prepara un cliente didattico separato attraverso Studio Archive, importa brief ed energy.csv e avvia la funzione corrente. Concorda periodo, servizio preparation e base unresolved senza scegliere uno standard automaticamente. Crea il caso synthetic e collega le tre celle alle righe 1, 2 e 3 della colonna kwh.

Mostra originale, localizzatore, valore interpretato e motivazione. Prima di record_decision chiedi la decisione effettiva del partecipante su queste versioni e dipendenze. Se non la esprime, lasciala aperta. Una decisione simulata deve essere etichettata, mai attribuita al partecipante. Genera un memo partial_draft con dipendenze esatte, senza affermazioni di conformità.

Conserva il primo run. Importa energy-update.csv come nuova fonte immutabile e avvia un nuovo run nello stesso incarico, selezionando vecchi e nuovi input. start_case usa previous_context del primo run; bind_evidence mantiene lo stesso ID energy e registra 15. Apri resume_case: energy v1, decisione e bozza dipendenti sono obsolete, energy v2 è corrente; mancante e non applicabile restano distinti.

Durante la lezione, la chat di lavoro esegue la funzione e produce il risultato. Se un passaggio non è disponibile, spieghiamo cosa manca e manteniamo la lezione incompleta.

## 4. Usiamo il risultato · 75 s

Apri il documento appena prodotto e mostra dove iniziare a leggerlo.

Stato esg_state.json con file, hash, celle, versioni, motivazioni, decisioni e dipendenze; bozze Markdown e JSON parziali.

Entrambi i contesti Studio Archive, fonti originali e storia, codex_run_review.md e rapporto leggibile sui dati letti dal modello. Sono risultati da eseguire nella sessione, non file già forniti.

Controlla cliente, periodo, unità, perimetro e fonte. Zero è un valore dichiarato, non prova di consumo effettivamente nullo. Il mancante richiede raccolta; la non applicabilità richiede un motivo. Rivedi interpretazione e sufficienza; una rettifica rende obsolete le decisioni dipendenti, non le rinnova. Il nome dichiarato non è firma autenticata.

## 5. Fermiamoci a verificare · 45 s

Fai queste verifiche nel momento indicato, durante il lavoro.

Prima della decisione, ritrova le tre celle e spiega perché i due vuoti hanno stati diversi.

Dopo la rettifica, mostra la versione corrente e la vecchia decisione/bozza conservate; indica cosa va riesaminato.

Queste pause servono a capire come usare la funzione. Le risposte non sono un esame di dettaglio tecnico.

## 6. Ora prova tu · 60 s

Lascia formulare la richiesta all’utente e accompagna la sua prova.

Con meno guida, usa files/practice/ in un nuovo cliente didattico: Laboratorio Quarzo dichiara 8 kWh, poi 12. Chiedi il fascicolo, distingui i due vuoti, prepara la prima bozza e acquisisci la rettifica nello stesso incarico. Conserva il demo; esprimi tu la decisione o lasciala aperta.

Nel demo ritrovi 0 e poi 15 kWh; nella pratica 8 e poi 12. I vecchi file e la storia restano leggibili, la decisione e la bozza dipendenti richiedono riesame. I due null mantengono stati diversi e nessun report completo o opinione è approvato.

Per ripetere, seleziona cliente, incarico, periodo e soli CSV/testi pertinenti; fornisci una richiesta e rivedi fonti e interpretazioni. Gli aggiornamenti entrano come nuovi input nello stesso incarico. La guida breve mira a 5–8 minuti, elaborazione e pratica possono proseguire. File e progressi restano locali; ciò che il modello legge entra nel suo contesto, senza anonimizzazione automatica.

Il kit contiene file fittizi e una traccia preparata. I risultati della dimostrazione e della prova provengono da nuove esecuzioni della funzione corrente.

La biblioteca, il profilo e i progressi della lezione restano sul computer. Non vengono inviati a Mparanza. La voce e i contenuti letti in chat sono elaborati dall'account OpenAI: salvare in locale non significa inferenza offline.
