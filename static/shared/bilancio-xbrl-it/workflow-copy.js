(() => {
  "use strict";

  // Function-specific website copy; the shared registry retains the reviewed model-data block.
  const copy = {
    it: {
      summary: "Accompagna la chiusura dei conti: verifica i documenti, prepara rettifiche da approvare e riconcilia i nuovi saldi, prima di prospetti OIC, nota integrativa e XBRL.",
      useWhen: "Per un bilancio civilistico italiano, con contabilità tenuta dallo studio o ricevuta da un altro soggetto. La provenienza va dichiarata prima dell'importazione.",
      input: "Bilancio di verifica CSV, Excel o PDF supportato, origine della contabilità, documenti di chiusura e informazioni confermate. Dati estratti e decisioni dell'anno precedente richiedono revisione.",
      work: "Verifica sufficienza documentale e saldi, propone rettifiche Dare/Avere, controlla il raccordo del nuovo bilancio di verifica e sospende le verifiche dipendenti da fatti cambiati.",
      output: "Proposte di rettifica, differenze riconciliate, registro delle decisioni e punti aperti; quindi prospetti, nota e XBRL, quando i controlli e le approvazioni richiesti sono completati.",
      responsibilityIntro: "Il modello propone e interpreta le evidenze; il professionista decide. Le verifiche di importi, versioni e autorizzazioni sono eseguite dal codice.",
      productRole: "Conserva fonti e versioni, prepara bozze, verifica quadrature e differenze e segnala revisioni da ripetere. Non registra automaticamente scritture in contabilità, invia richieste al cliente, approva o deposita il bilancio.",
      professionalRole: "Conferma sufficienza dei documenti, significato contabile, applicabilità e rettifiche. Preparatore e approvatore restano distinti; il revisore autorizzato registra le decisioni e ripete i controlli sospesi prima dell'approvazione finale.",
      prompt: "Usa Bilancio OIC sui materiali di questa cartella. Registra chi tiene la contabilità, verifica i documenti e i saldi, proponi le rettifiche con le fonti e mostrami che cosa richiede approvazione. Riconcilia ogni nuovo bilancio di verifica e segnala i controlli da ripetere.",
      workflow: [
        "Chiusura dei conti", "Dai documenti ai saldi da approvare",
        "Il fascicolo conserva lo stesso caso e la storia delle revisioni. Una nuova informazione può riaprire una decisione e sospendere i controlli che ne dipendono.",
        [
          ["Origine e documenti", "Si dichiara se la contabilità è interna o esterna. Vera propone i documenti necessari e segnala quelli mancanti; il professionista ne valuta la sufficienza. L'eventuale richiesta al cliente resta una bozza non inviata."],
          ["Verifica del bilancio di verifica", "I dati estratti vengono rivisti prima di mappare i conti. Lo screening distingue saldi disponibili e scritture di chiusura ancora necessarie: la sola quadratura non dimostra che i conti siano corretti."],
          ["Rettifiche con prove e approvazione", "Ogni proposta Dare/Avere collega conti, importi e documenti. La preparazione non vale come approvazione; un soggetto distinto e autorizzato conferma la rettifica."],
          ["Raccordo del nuovo bilancio di verifica", "Il candidato deve coincidere, conto per conto, con il bilancio iniziale più le sole rettifiche approvate ed efficaci. Un candidato che quadra ma contiene altre variazioni viene respinto senza sostituire i saldi accettati."],
          ["Fatti nuovi e sospensioni", "Una revisione conserva la decisione precedente e indica autore, ruolo, data, motivazione e prove. Le aree, i mapping e la validazione interessati restano sospesi anche dopo la chiusura del riesame, finché saldi e controlli non sono nuovamente verificati."],
          ["Prospetti, nota e XBRL", "Dopo le revisioni necessarie si prosegue con forma di bilancio, mapping, informative e validazione. Questioni aperte e controlli sospesi restano visibili e possono bloccare approvazione ed esportazione."]
        ],
        "Il registro conserva gli eventi precedenti e collega le revisioni con impronte di integrità. Le carte di lavoro per area, i controlli professionali, la dashboard e il documento Excel proseguono sullo stesso fascicolo."
      ],
      acceptance: [
        "Collaudo documentato", "Alfa v3: risultati e sospensioni",
        "Il 15 ottobre 2026 il caso sintetico Alfa SRL, esercizio 2025 e contabilità esterna, ha superato 131/131 controlli sul servizio MCP estratto dal pacchetto Vera 0.1.394, componente Bilancio 0.1.20.",
        "Totali Dare = Avere; importi in euro. A1: ammortamenti 12.000; A2: interessi 1.000; A2-bis: interessi 1.125 in sostituzione di A2.",
        ["Passaggio", "Risultato osservato"],
        [
          ["Documenti 01 e 10", "Saldi iniziali: 807.800; comparativo: 727.200. Con A1 + A2: 820.800 e risultato ante imposte 48.600. Raccordo esatto per conto."],
          ["E1 · documento 13", "Respinta una variazione non autorizzata di 500 su crediti e ricavi, pur essendo in quadratura. Saldi e decisioni precedenti conservati."],
          ["20–22 gennaio · riesame A2", "A2 resta efficace ma richiede riesame; A1 resta valida. Sospese tre aree, i mapping dei conti 4210 e 2410 e la validazione complessiva."],
          ["A2-bis approvata, prima del documento 12", "A2 è superata da A2-bis e il riesame è chiuso. I controlli dipendenti restano sospesi; il documento 10 non è più il bilancio valido."],
          ["E2 · documento 14", "Respinto il doppio conteggio di A2 e A2-bis: eccedenza di 1.000 su interessi e ratei. Nessuna decisione D-SCR3 e sospensioni invariate."],
          ["Documento 12", "Saldi con A1 + A2-bis: 820.925; risultato ante imposte: 48.475. Registrata D-SCR3; i controlli interessati devono essere ripetuti, senza validazione finale automatica."],
          ["Registro e stato finale", "12 eventi al 22 gennaio, 13 dopo D-SCR3; eventi precedenti invariati. Imposte e contenzioso restano aperti: nessuna approvazione o esportazione del bilancio completo."]
        ],
        "La suite Bilancio della stessa implementazione ha superato 447 test, con copertura dell'86,03% nel perimetro dichiarato. Il collaudo verifica anche salvataggio e riapertura, ruoli, date e collegamenti documentali.",
        "P1 e C1 sono identità simulate e le decisioni professionali sono dati del test. Il risultato non qualifica il giudizio semantico del modello, l'interfaccia nativa, una nuova sessione installata o il lavoro su clienti reali. La demo PagoPA qui sotto è un esempio distinto; il corso esistente parte da saldi di chiusura già forniti.",
        "Leggi evidenze, metodo e limiti del collaudo (in inglese)"
      ]
    },
    en: {
      summary: "Supports the closing process: reviews documents, prepares adjustments for approval and reconciles replacement balances before OIC statements, notes and XBRL.",
      useWhen: "For Italian statutory accounts, whether bookkeeping is performed by the firm or supplied externally. Its origin must be recorded before import.",
      input: "A trial balance in CSV, Excel or supported PDF, bookkeeping origin, closing evidence and confirmed information. Extracted data and prior-year decisions require review.",
      work: "Reviews document sufficiency and balances, proposes debit/credit adjustments, reconciles replacement trial balances and suspends checks that depend on changed facts.",
      output: "Adjustment proposals, reconciled differences, a decision register and open issues; then statements, notes and XBRL once the required checks and approvals are complete.",
      responsibilityIntro: "The model proposes and interprets evidence; the professional decides. Code checks amounts, versions and authority.",
      productRole: "Retains sources and versions, prepares drafts, checks balances and differences and identifies reviews to repeat. It does not automatically post entries, send client requests, approve accounts or file them.",
      professionalRole: "Confirms document sufficiency, accounting meaning, applicability and adjustments. Preparer and approver remain distinct; an authorized reviewer records decisions and repeats suspended checks before final approval.",
      prompt: "Use OIC accounts on this folder. Record who keeps the books, review documents and balances, propose evidence-linked adjustments and show what needs approval. Reconcile every replacement trial balance and identify checks to repeat.",
      workflow: [
        "Closing accounts", "From evidence to balances for approval",
        "The file retains the same case and revision history. New information can reopen a decision and suspend the checks that depend on it.",
        [
          ["Bookkeeping origin and documents", "Record internal or external bookkeeping. Vera proposes document requirements and identifies gaps; the professional assesses sufficiency. Any client request remains an unsent draft."],
          ["Trial-balance review", "Review extracted data before mapping accounts. Screening distinguishes available balances from closing entries still needed: a balanced trial balance alone does not prove that the accounts are correct."],
          ["Evidence-linked adjustments and approval", "Each debit/credit proposal links accounts, amounts and documents. Preparation does not constitute approval; a separate authorized person confirms the adjustment."],
          ["Replacement trial-balance reconciliation", "A candidate must match the initial trial balance plus only approved, effective adjustments, account by account. A balanced candidate containing other changes is rejected without replacing accepted balances."],
          ["New facts and suspended checks", "A review retains the earlier decision and records author, role, date, reason and evidence. Affected areas, mappings and validation remain suspended after the reconsideration closes until balances and checks have been reviewed again."],
          ["Statements, notes and XBRL", "After the necessary reviews, continue with statement form, mappings, disclosures and validation. Open issues and suspended checks remain visible and can block approval and export."]
        ],
        "The register retains earlier events and links revisions with integrity hashes. Area workpapers, professional controls, the dashboard and the Excel review document continue in the same case."
      ],
      acceptance: [
        "Documented acceptance test", "Alfa v3: results and suspensions",
        "On 15 October 2026, the synthetic Alfa SRL case for FY2025, with external bookkeeping, passed 131/131 checks through the MCP service extracted from Vera 0.1.394, Bilancio component 0.1.20.",
        "Debit totals = credit totals; amounts in euros. A1: depreciation 12,000; A2: interest 1,000; A2-bis: interest 1,125 replacing A2.",
        ["Stage", "Observed result"],
        [
          ["Documents 01 and 10", "Initial balances: 807,800; comparative: 727,200. With A1 + A2: 820,800 and pre-tax result 48,600. Exact match for every account."],
          ["E1 · document 13", "Rejected an unauthorized 500 change to receivables and revenue despite balanced totals. Previous balances and decisions retained."],
          ["20–22 January · A2 reconsideration", "A2 remains effective but requires review; A1 remains valid. Three areas, account mappings 4210 and 2410 and overall validation are suspended."],
          ["A2-bis approved, before document 12", "A2 is superseded by A2-bis and reconsideration closes. Dependent checks remain suspended; document 10 is no longer the valid trial balance."],
          ["E2 · document 14", "Rejected double counting of A2 and A2-bis: excess 1,000 in interest and accruals. No D-SCR3 decision; suspension unchanged."],
          ["Document 12", "Balances with A1 + A2-bis: 820,925; pre-tax result: 48,475. D-SCR3 recorded; affected checks must be repeated, with no automatic final validation."],
          ["Register and final state", "12 events on 22 January, 13 after D-SCR3; earlier events unchanged. Taxes and litigation remain open: no approval or export of complete accounts."]
        ],
        "The Bilancio suite for the same implementation passed 447 tests, with 86.03% coverage over its declared scope. Acceptance also checks save/reopen, roles, dates and documentary links.",
        "P1 and C1 are simulated identities and professional decisions are test inputs. This does not qualify the model's semantic judgment, the native UI, a fresh installed session or real-client work. The PagoPA demo below is a separate example; the existing course starts from supplied closing balances.",
        "Read the test evidence, method and limits"
      ]
    },
    fr: {
      summary: "Accompagne la clôture : examine les pièces, prépare les écritures à approuver et rapproche les nouveaux soldes avant les états OIC, l'annexe et le fichier XBRL.",
      useWhen: "Pour les comptes annuels italiens, avec une comptabilité tenue par le cabinet ou reçue d'un tiers. Son origine doit être déclarée avant l'importation.",
      input: "Balance en CSV, Excel ou PDF pris en charge, origine de la comptabilité, pièces de clôture et informations confirmées. Les données extraites et décisions antérieures doivent être revues.",
      work: "Examine la suffisance des pièces et les soldes, propose des écritures débit/crédit, rapproche les nouvelles balances et suspend les contrôles dépendant de faits modifiés.",
      output: "Propositions d'écritures, écarts rapprochés, registre des décisions et questions ouvertes ; puis états, annexe et XBRL après les contrôles et approbations requis.",
      responsibilityIntro: "Le modèle propose et interprète les éléments ; le professionnel décide. Le code vérifie montants, versions et habilitations.",
      productRole: "Conserve sources et versions, prépare les projets, vérifie équilibres et écarts et signale les examens à refaire. N'enregistre pas automatiquement d'écritures, n'envoie pas de demandes au client et n'approuve ni ne dépose les comptes.",
      professionalRole: "Confirme la suffisance des pièces, le sens comptable, l'applicabilité et les ajustements. Préparateur et approbateur restent distincts ; le réviseur habilité consigne les décisions et répète les contrôles suspendus avant l'approbation finale.",
      prompt: "Utilise Comptes OIC sur ce dossier. Enregistre qui tient la comptabilité, examine les pièces et les soldes, propose les écritures avec leurs sources et montre ce qui nécessite une approbation. Rapproche chaque nouvelle balance et indique les contrôles à refaire.",
      workflow: [
        "Clôture des comptes", "Des pièces aux soldes à approuver",
        "Le dossier conserve le même cas et l'historique des révisions. Une information nouvelle peut rouvrir une décision et suspendre les contrôles qui en dépendent.",
        [
          ["Origine et pièces", "Déclarer une comptabilité interne ou externe. Vera propose les pièces nécessaires et signale les manques ; le professionnel apprécie leur suffisance. Toute demande au client reste un projet non envoyé."],
          ["Examen de la balance", "Les données extraites sont revues avant l'affectation des comptes. L'examen distingue les soldes disponibles des écritures de clôture manquantes : une balance équilibrée ne prouve pas à elle seule l'exactitude des comptes."],
          ["Écritures justifiées et approbation", "Chaque proposition débit/crédit relie comptes, montants et pièces. La préparation ne vaut pas approbation ; une autre personne habilitée confirme l'écriture."],
          ["Rapprochement de la nouvelle balance", "Le candidat doit correspondre, compte par compte, à la balance initiale augmentée des seuls ajustements approuvés et effectifs. Un candidat équilibré contenant d'autres variations est rejeté sans remplacer les soldes acceptés."],
          ["Faits nouveaux et suspensions", "La révision conserve la décision précédente et indique auteur, rôle, date, motif et preuves. Les domaines, affectations et validations concernés restent suspendus après la clôture du réexamen, jusqu'à une nouvelle vérification des soldes et contrôles."],
          ["États, annexe et XBRL", "Après les révisions nécessaires, poursuivre avec la forme des comptes, les affectations, les informations annexes et la validation. Les questions ouvertes et contrôles suspendus restent visibles et peuvent bloquer approbation et export."]
        ],
        "Le registre conserve les événements antérieurs et relie les révisions par des empreintes d'intégrité. Les feuilles de travail par domaine, contrôles professionnels, tableau de bord et document Excel prolongent le même dossier."
      ],
      acceptance: [
        "Test de réception documenté", "Alfa v3 : résultats et suspensions",
        "Le 15 octobre 2026, le cas synthétique Alfa SRL, exercice 2025 et comptabilité externe, a réussi 131/131 contrôles via le service MCP extrait de Vera 0.1.394, composant Bilancio 0.1.20.",
        "Total débit = total crédit ; montants en euros. A1 : amortissements 12 000 ; A2 : intérêts 1 000 ; A2-bis : intérêts 1 125 remplaçant A2.",
        ["Étape", "Résultat observé"],
        [
          ["Documents 01 et 10", "Soldes initiaux : 807 800 ; comparatif : 727 200. Avec A1 + A2 : 820 800 et résultat avant impôt de 48 600. Rapprochement exact par compte."],
          ["E1 · document 13", "Variation non autorisée de 500 sur créances et produits rejetée malgré l'équilibre. Soldes et décisions précédents conservés."],
          ["20–22 janvier · réexamen A2", "A2 reste effective mais doit être revue ; A1 reste valide. Trois domaines, les affectations des comptes 4210 et 2410 et la validation globale sont suspendus."],
          ["A2-bis approuvée, avant le document 12", "A2 est remplacée par A2-bis et le réexamen est clos. Les contrôles dépendants restent suspendus ; le document 10 n'est plus la balance valide."],
          ["E2 · document 14", "Double comptabilisation d'A2 et A2-bis rejetée : excédent de 1 000 sur intérêts et charges à payer. Aucune décision D-SCR3 ; suspensions inchangées."],
          ["Document 12", "Soldes avec A1 + A2-bis : 820 925 ; résultat avant impôt : 48 475. D-SCR3 enregistrée ; contrôles concernés à répéter, sans validation finale automatique."],
          ["Registre et état final", "12 événements au 22 janvier, 13 après D-SCR3 ; événements antérieurs inchangés. Fiscalité et contentieux restent ouverts : aucune approbation ou export des comptes complets."]
        ],
        "La suite Bilancio de cette implémentation a réussi 447 tests, avec une couverture de 86,03 % sur le périmètre déclaré. Le test contrôle aussi sauvegarde et réouverture, rôles, dates et liens documentaires.",
        "P1 et C1 sont des identités simulées et les décisions professionnelles sont des données du test. Le résultat ne qualifie ni le jugement sémantique du modèle, ni l'interface native, ni une nouvelle session installée, ni le travail sur de vrais clients. La démonstration PagoPA ci-dessous est distincte ; le cours existant part de soldes de clôture déjà fournis.",
        "Lire les preuves, la méthode et les limites du test (en anglais)"
      ]
    },
    de: {
      summary: "Begleitet den Kontenabschluss: prüft Belege, bereitet Abschlussbuchungen zur Freigabe vor und stimmt neue Salden vor OIC-Abschluss, Anhang und XBRL ab.",
      useWhen: "Für italienische Jahresabschlüsse mit interner oder extern geführter Buchhaltung. Deren Herkunft wird vor dem Import erfasst.",
      input: "Saldenliste als CSV, Excel oder unterstütztes PDF, Herkunft der Buchhaltung, Abschlussbelege und bestätigte Angaben. Extrahierte Daten und Vorjahresentscheidungen müssen geprüft werden.",
      work: "Prüft Belegvollständigkeit und Salden, schlägt Soll-/Haben-Buchungen vor, stimmt neue Saldenlisten ab und setzt von geänderten Fakten abhängige Prüfungen aus.",
      output: "Buchungsvorschläge, abgestimmte Differenzen, Entscheidungsregister und offene Fragen; danach Abschluss, Anhang und XBRL nach den erforderlichen Prüfungen und Freigaben.",
      responsibilityIntro: "Das Modell schlägt vor und interpretiert Nachweise; der Berufsträger entscheidet. Der Code prüft Beträge, Versionen und Berechtigungen.",
      productRole: "Bewahrt Quellen und Versionen, erstellt Entwürfe, prüft Summen und Differenzen und zeigt erneut nötige Prüfungen. Bucht nicht automatisch, versendet keine Mandantenanfragen und genehmigt oder hinterlegt keinen Abschluss.",
      professionalRole: "Bestätigt ausreichende Belege, Bilanzierungsfragen, Anwendbarkeit und Abschlussbuchungen. Ersteller und Genehmiger bleiben getrennt; ein berechtigter Prüfer erfasst Entscheidungen und wiederholt ausgesetzte Prüfungen vor der endgültigen Freigabe.",
      prompt: "Verwende OIC-Abschluss für diesen Ordner. Erfasse, wer die Buchhaltung führt, prüfe Belege und Salden, schlage belegte Abschlussbuchungen vor und zeige nötige Freigaben. Stimme jede neue Saldenliste ab und benenne zu wiederholende Prüfungen.",
      workflow: [
        "Kontenabschluss", "Von Belegen zu freizugebenden Salden",
        "Die Akte behält denselben Fall und seine Änderungshistorie. Neue Informationen können eine Entscheidung erneut öffnen und abhängige Prüfungen aussetzen.",
        [
          ["Herkunft und Belege", "Interne oder externe Buchhaltung angeben. Vera schlägt benötigte Belege vor und zeigt Lücken; der Berufsträger beurteilt, ob sie ausreichen. Eine Mandantenanfrage bleibt ein nicht versandter Entwurf."],
          ["Prüfung der Saldenliste", "Extrahierte Daten werden vor der Kontenzuordnung geprüft. Die Prüfung unterscheidet vorhandene Salden von noch nötigen Abschlussbuchungen: ausgeglichene Summen allein beweisen keine richtigen Konten."],
          ["Belegte Buchungen und Freigabe", "Jeder Soll-/Haben-Vorschlag verknüpft Konten, Beträge und Belege. Die Vorbereitung ist keine Genehmigung; eine andere berechtigte Person bestätigt die Buchung."],
          ["Abstimmung der neuen Saldenliste", "Ein Kandidat muss je Konto der Ausgangsliste zuzüglich ausschließlich genehmigter, wirksamer Buchungen entsprechen. Ausgeglichene Kandidaten mit weiteren Änderungen werden abgelehnt, ohne akzeptierte Salden zu ersetzen."],
          ["Neue Fakten und Aussetzungen", "Eine Revision bewahrt die frühere Entscheidung und erfasst Urheber, Rolle, Datum, Grund und Nachweise. Betroffene Bereiche, Zuordnungen und Validierung bleiben nach Abschluss der erneuten Entscheidungskontrolle ausgesetzt, bis Salden und Prüfungen erneut geprüft wurden."],
          ["Abschluss, Anhang und XBRL", "Nach den nötigen Revisionen folgen Abschlussform, Zuordnungen, Angaben und Validierung. Offene Fragen und ausgesetzte Prüfungen bleiben sichtbar und können Freigabe und Export blockieren."]
        ],
        "Das Register bewahrt frühere Ereignisse und verknüpft Revisionen mit Integritäts-Hashes. Bereichsarbeitspapiere, fachliche Kontrollen, Dashboard und Excel-Prüfungsdokument führen dieselbe Akte weiter."
      ],
      acceptance: [
        "Dokumentierter Abnahmetest", "Alfa v3: Ergebnisse und Aussetzungen",
        "Am 15. Oktober 2026 bestand der synthetische Fall Alfa SRL, Geschäftsjahr 2025 mit externer Buchhaltung, 131/131 Prüfungen über den aus Vera 0.1.394 extrahierten MCP-Dienst, Bilancio-Komponente 0.1.20.",
        "Sollsumme = Habensumme; Beträge in Euro. A1: Abschreibung 12.000; A2: Zinsen 1.000; A2-bis: Zinsen 1.125 als Ersatz für A2.",
        ["Schritt", "Beobachtetes Ergebnis"],
        [
          ["Dokumente 01 und 10", "Ausgangssalden: 807.800; Vergleich: 727.200. Mit A1 + A2: 820.800 und Ergebnis vor Steuern 48.600. Exakte Abstimmung je Konto."],
          ["E1 · Dokument 13", "Nicht genehmigte Änderung von 500 bei Forderungen und Erlösen trotz ausgeglichener Summen abgelehnt. Frühere Salden und Entscheidungen erhalten."],
          ["20.–22. Januar · erneute Prüfung A2", "A2 bleibt wirksam, muss aber geprüft werden; A1 bleibt gültig. Drei Bereiche, die Zuordnungen der Konten 4210 und 2410 und die Gesamtvalidierung sind ausgesetzt."],
          ["A2-bis genehmigt, vor Dokument 12", "A2 ist durch A2-bis ersetzt und die erneute Entscheidungskontrolle geschlossen. Abhängige Prüfungen bleiben ausgesetzt; Dokument 10 ist keine gültige Saldenliste mehr."],
          ["E2 · Dokument 14", "Doppelte Berücksichtigung von A2 und A2-bis abgelehnt: 1.000 zu viel bei Zinsen und Abgrenzungen. Keine Entscheidung D-SCR3; Aussetzungen unverändert."],
          ["Dokument 12", "Salden mit A1 + A2-bis: 820.925; Ergebnis vor Steuern: 48.475. D-SCR3 erfasst; betroffene Prüfungen sind zu wiederholen, ohne automatische endgültige Validierung."],
          ["Register und Endzustand", "12 Ereignisse am 22. Januar, 13 nach D-SCR3; frühere Ereignisse unverändert. Steuern und Rechtsstreit bleiben offen: keine Genehmigung oder Ausfuhr des vollständigen Abschlusses."]
        ],
        "Die Bilancio-Testsuite dieser Implementierung bestand 447 Tests mit 86,03 % Abdeckung im angegebenen Umfang. Der Test prüft auch Speichern und Wiederöffnen, Rollen, Daten und Belegverknüpfungen.",
        "P1 und C1 sind simulierte Identitäten; berufliche Entscheidungen sind Testeingaben. Das Ergebnis qualifiziert weder semantische Modellurteile noch die native Oberfläche, eine neue installierte Sitzung oder echte Mandantenarbeit. Die PagoPA-Demo unten ist ein eigenes Beispiel; der bestehende Kurs beginnt mit bereits gelieferten Abschlusssalden.",
        "Testnachweise, Methode und Grenzen lesen (auf Englisch)"
      ]
    },
    es: {
      summary: "Acompaña el cierre: revisa documentos, prepara ajustes para su aprobación y concilia los nuevos saldos antes de los estados OIC, la memoria y el XBRL.",
      useWhen: "Para cuentas anuales italianas, con contabilidad llevada por el despacho o recibida de terceros. Su origen debe declararse antes de importar.",
      input: "Balance de comprobación CSV, Excel o PDF compatible, origen de la contabilidad, justificantes de cierre e información confirmada. Los datos extraídos y decisiones del ejercicio anterior requieren revisión.",
      work: "Revisa suficiencia documental y saldos, propone ajustes de debe/haber, concilia los nuevos balances y suspende controles que dependen de hechos modificados.",
      output: "Propuestas de ajuste, diferencias conciliadas, registro de decisiones y cuestiones abiertas; después estados, memoria y XBRL tras los controles y aprobaciones necesarios.",
      responsibilityIntro: "El modelo propone e interpreta las evidencias; el profesional decide. El código verifica importes, versiones y autorizaciones.",
      productRole: "Conserva fuentes y versiones, prepara borradores, verifica saldos y diferencias y señala revisiones que deben repetirse. No contabiliza asientos automáticamente, envía solicitudes al cliente, aprueba ni presenta las cuentas.",
      professionalRole: "Confirma suficiencia documental, significado contable, aplicabilidad y ajustes. Preparador y aprobador son personas distintas; el revisor autorizado registra decisiones y repite controles suspendidos antes de la aprobación final.",
      prompt: "Usa Cuentas OIC con esta carpeta. Registra quién lleva la contabilidad, revisa documentos y saldos, propone ajustes con sus fuentes y muestra qué necesita aprobación. Concilia cada nuevo balance de comprobación e indica los controles que deben repetirse.",
      workflow: [
        "Cierre de cuentas", "De los documentos a los saldos por aprobar",
        "El expediente conserva el mismo caso y el historial de revisiones. Una nueva información puede reabrir una decisión y suspender los controles que dependen de ella.",
        [
          ["Origen y documentos", "Se declara si la contabilidad es interna o externa. Vera propone los documentos necesarios y señala carencias; el profesional evalúa su suficiencia. Cualquier solicitud al cliente sigue siendo un borrador no enviado."],
          ["Revisión del balance de comprobación", "Los datos extraídos se revisan antes de mapear las cuentas. La revisión distingue saldos disponibles y asientos de cierre pendientes: que el balance cuadre no demuestra por sí solo que las cuentas sean correctas."],
          ["Ajustes documentados y aprobación", "Cada propuesta de debe/haber vincula cuentas, importes y documentos. La preparación no equivale a aprobación; otra persona autorizada confirma el ajuste."],
          ["Conciliación del nuevo balance", "El candidato debe coincidir, cuenta por cuenta, con el balance inicial más solo los ajustes aprobados y efectivos. Se rechaza un candidato que cuadre pero incluya otros cambios, sin sustituir los saldos aceptados."],
          ["Nuevos hechos y suspensiones", "La revisión conserva la decisión anterior y registra autor, función, fecha, motivo y pruebas. Áreas, mapeos y validaciones afectados siguen suspendidos al cerrar la reconsideración, hasta revisar de nuevo saldos y controles."],
          ["Estados, memoria y XBRL", "Tras las revisiones necesarias se continúa con la forma de las cuentas, mapeos, información y validación. Las cuestiones abiertas y controles suspendidos siguen visibles y pueden bloquear aprobación y exportación."]
        ],
        "El registro conserva los eventos anteriores y vincula revisiones mediante huellas de integridad. Los papeles de trabajo por área, controles profesionales, panel y documento Excel continúan en el mismo expediente."
      ],
      acceptance: [
        "Prueba de aceptación documentada", "Alfa v3: resultados y suspensiones",
        "El 15 de octubre de 2026, el caso sintético Alfa SRL, ejercicio 2025 con contabilidad externa, superó 131/131 controles mediante el servicio MCP extraído de Vera 0.1.394, componente Bilancio 0.1.20.",
        "Total debe = total haber; importes en euros. A1: amortización 12.000; A2: intereses 1.000; A2-bis: intereses 1.125 en sustitución de A2.",
        ["Paso", "Resultado observado"],
        [
          ["Documentos 01 y 10", "Saldos iniciales: 807.800; comparativo: 727.200. Con A1 + A2: 820.800 y resultado antes de impuestos 48.600. Conciliación exacta por cuenta."],
          ["E1 · documento 13", "Rechazada una variación no autorizada de 500 en créditos e ingresos pese a cuadrar. Saldos y decisiones anteriores conservados."],
          ["20–22 de enero · reconsideración A2", "A2 sigue siendo efectiva pero requiere revisión; A1 sigue válida. Tres áreas, los mapeos de las cuentas 4210 y 2410 y la validación global están suspendidos."],
          ["A2-bis aprobada, antes del documento 12", "A2 queda sustituida por A2-bis y la reconsideración se cierra. Los controles dependientes siguen suspendidos; el documento 10 deja de ser el balance válido."],
          ["E2 · documento 14", "Rechazado el doble cómputo de A2 y A2-bis: exceso de 1.000 en intereses y periodificaciones. Sin decisión D-SCR3; suspensiones sin cambios."],
          ["Documento 12", "Saldos con A1 + A2-bis: 820.925; resultado antes de impuestos: 48.475. D-SCR3 registrada; los controles afectados deben repetirse, sin validación final automática."],
          ["Registro y estado final", "12 eventos al 22 de enero, 13 tras D-SCR3; eventos anteriores sin cambios. Impuestos y litigio siguen abiertos: sin aprobación ni exportación de las cuentas completas."]
        ],
        "La suite Bilancio de la misma implementación superó 447 pruebas, con una cobertura del 86,03 % en el alcance declarado. La aceptación comprueba también guardado y reapertura, funciones, fechas y vínculos documentales.",
        "P1 y C1 son identidades simuladas y las decisiones profesionales son datos de la prueba. El resultado no acredita el juicio semántico del modelo, la interfaz nativa, una nueva sesión instalada ni trabajo con clientes reales. La demostración PagoPA siguiente es un ejemplo distinto; el curso existente parte de saldos de cierre ya proporcionados.",
        "Leer evidencias, método y límites de la prueba (en inglés)"
      ]
    }
  };

  const areaCopy = {
    it: ["Revisione per area", "Conti, documenti e controlli nello stesso fascicolo", "Il professionista conferma la popolazione dei conti e le aree da lavorare. Anche un contratto o un verbale può attivare un’area senza saldi contabili: la proposta conserva il brano e il periodo della fonte.", "Le carte collegano conti, mapping, fatti, prospetti, questioni aperte e nota integrativa. Dal pannello si aprono aree, controlli e brani dei documenti registrati. Una fonte reimportata in una nuova versione riapre i controlli dipendenti; le altre decisioni restano consultabili.", "Il percorso snello per micro e abbreviati semplici con contabilità interna raggruppa gli stessi obiettivi; ordinario e casi complessi mantengono il percorso completo. L’Excel è un documento della revisione: modificarlo non cambia il fascicolo.", "Il catalogo indicizza 29 principi e propone 96 controlli professionali su 12 principi, con copertura parziale dichiarata. Il revisore verifica le fonti rispetto al pacchetto OIC dell’esercizio. Il collaudo è sintetico; la verifica professionale su casi reali resta da svolgere."],
    en: ["Area review", "Accounts, documents and controls in one case", "The professional confirms account populations and areas to review. A contract or resolution can activate an area without an account balance: the proposal retains the quoted passage and source period.", "Workpapers connect accounts, mappings, facts, schedules, open issues and notes. The panel opens areas, controls and registered document excerpts. Reimporting a changed source reopens dependent controls while retaining other decisions.", "The streamlined route for simple micro and abbreviated cases with internal bookkeeping groups the same objectives; ordinary and complex cases retain full depth. Excel is a review document: editing it does not change the case.", "The index covers 29 standards and proposes 96 professional controls for 12 standards, with explicit partial coverage. The reviewer checks sources against the reporting-period OIC pack. Tests are synthetic; independent professional acceptance on real cases remains pending."],
    fr: ["Révision par domaine", "Comptes, documents et contrôles dans le même dossier", "Le professionnel confirme les populations de comptes et les domaines à examiner. Un contrat ou un procès-verbal peut activer un domaine sans solde comptable : la proposition conserve le passage cité et sa période.", "Les feuilles de travail relient comptes, correspondances, faits, tableaux, questions ouvertes et annexe. Le panneau ouvre domaines, contrôles et extraits enregistrés. La réimportation d’une source modifiée rouvre les contrôles dépendants et conserve les autres décisions.", "Le parcours allégé des cas micro et abrégés simples à comptabilité interne regroupe les mêmes objectifs ; les cas ordinaires et complexes gardent le parcours complet. Excel reste un document de révision : sa modification ne change pas le dossier.", "L’index recense 29 normes et propose 96 contrôles professionnels pour 12 normes, avec une couverture partielle explicite. Le réviseur vérifie les sources selon le paquet OIC de l’exercice. Les tests sont synthétiques ; la validation professionnelle sur cas réels reste ouverte."],
    de: ["Prüfung nach Bereichen", "Konten, Dokumente und Kontrollen in einer Akte", "Die Fachperson bestätigt Kontenpopulationen und Prüfungsbereiche. Ein Vertrag oder Beschluss kann auch ohne Kontensaldo einen Bereich aktivieren; der Vorschlag bewahrt Textstelle und Berichtszeitraum.", "Arbeitspapiere verbinden Konten, Zuordnungen, Fakten, Tabellen, offene Fragen und Anhang. Das Panel öffnet Bereiche, Kontrollen und registrierte Dokumentauszüge. Eine geänderte, erneut importierte Quelle öffnet abhängige Kontrollen und bewahrt andere Entscheidungen.", "Der schlanke Ablauf für einfache Mikro- und verkürzte Abschlüsse mit interner Buchhaltung bündelt dieselben Prüfziele; ordentliche und komplexe Fälle behalten den vollständigen Ablauf. Excel ist ein Prüfungsdokument; Änderungen daran verändern die Akte nicht.", "Der Index enthält 29 Standards und 96 fachliche Prüffragen zu 12 Standards bei ausdrücklich teilweiser Abdeckung. Die Fachperson prüft Quellen anhand des OIC-Pakets für das Geschäftsjahr. Die Tests sind synthetisch; die fachliche Abnahme an realen Fällen steht aus."],
    es: ["Revisión por área", "Cuentas, documentos y controles en el mismo expediente", "El profesional confirma las poblaciones de cuentas y áreas que deben revisarse. Un contrato o acta puede activar un área sin saldo contable: la propuesta conserva el pasaje citado y su período.", "Los papeles de trabajo vinculan cuentas, mapeos, hechos, cuadros, cuestiones abiertas y memoria. El panel abre áreas, controles y extractos registrados. Reimportar una fuente modificada reabre los controles dependientes y conserva las otras decisiones.", "El recorrido simplificado para casos micro y abreviados sencillos con contabilidad interna agrupa los mismos objetivos; los casos ordinarios y complejos mantienen el recorrido completo. Excel es un documento de revisión: editarlo no cambia el expediente.", "El índice contiene 29 normas y propone 96 controles profesionales sobre 12 normas, con cobertura parcial explícita. El revisor verifica las fuentes según el paquete OIC del ejercicio. Las pruebas son sintéticas; la aceptación profesional en casos reales sigue pendiente."]
  };

  const modelDataCopy = {
    it: "Il modello può leggere i dati della società forniti per il caso, saldi e mappature selezionati, prospetti, risposte, testi di nota, rilievi, decisioni e brani documentali con fonte e periodo. Le viste richieste esplicitamente sono paginate; l’interpretazione resta una proposta. Il codice locale esegue calcoli, quadrature, controlli di versione e genera l’Excel, scaricato dal pannello senza allegarne automaticamente i byte al modello. Nomi e dati personali non sono anonimizzati automaticamente: si applica l’account Codex o Cowork scelto dallo studio e l’elaborazione non è garantita locale. L’eventuale invio a TEBENI resta una scelta esterna del professionista.",
    en: "The model may read company details supplied for the case, selected balances and mappings, schedules, answers, draft notes, issues, decisions and document excerpts with source and period. Explicitly requested views are paginated; interpretation remains a proposal. Local code calculates, reconciles, checks versions and generates the Excel document, downloaded from the panel without automatically attaching its bytes to the model. Names and personal data are not automatically anonymized: the firm’s selected Codex or Cowork account applies and processing is not guaranteed local. Any TEBENI upload remains a separate professional choice.",
    fr: "Le modèle peut lire les données de la société fournies pour le dossier, soldes et correspondances sélectionnés, tableaux, réponses, textes d’annexe, questions, décisions et extraits avec source et période. Les vues expressément demandées sont paginées ; l’interprétation reste une proposition. Le code local calcule, rapproche, vérifie les versions et génère le document Excel, téléchargé depuis le panneau sans joindre automatiquement ses octets au modèle. Les noms et données personnelles ne sont pas anonymisés automatiquement : le compte Codex ou Cowork choisi par le cabinet s’applique et un traitement uniquement local n’est pas garanti. Tout envoi à TEBENI reste un choix distinct du professionnel.",
    de: "Das Modell kann bereitgestellte Unternehmensdaten, ausgewählte Salden und Zuordnungen, Tabellen, Antworten, Anhangsentwürfe, Fragen, Entscheidungen und Dokumentauszüge mit Quelle und Zeitraum lesen. Ausdrücklich angeforderte Ansichten sind paginiert; Interpretationen bleiben Vorschläge. Lokaler Code berechnet, gleicht ab, prüft Versionen und erzeugt das Excel-Dokument. Beim Download aus dem Panel werden dessen Bytes nicht automatisch an das Modell angehängt. Namen und personenbezogene Daten werden nicht automatisch anonymisiert; maßgeblich ist das gewählte Codex- oder Cowork-Konto der Kanzlei, eine ausschließlich lokale Verarbeitung ist nicht garantiert. Ein TEBENI-Upload bleibt eine gesonderte fachliche Entscheidung.",
    es: "El modelo puede leer los datos de la sociedad aportados al expediente, saldos y mapeos seleccionados, cuadros, respuestas, borradores de memoria, cuestiones, decisiones y extractos con fuente y período. Las vistas solicitadas expresamente se paginan; la interpretación sigue siendo una propuesta. El código local calcula, concilia, comprueba versiones y genera el documento Excel, descargado del panel sin adjuntar automáticamente sus bytes al modelo. Los nombres y datos personales no se anonimizan automáticamente: se aplica la cuenta Codex o Cowork elegida por el despacho y no se garantiza un procesamiento solo local. Cualquier envío a TEBENI sigue siendo una decisión profesional separada."
  };

  const evidenceHref = "https://github.com/fabioannovazzi/app_files/blob/56a1c90f69591e852ba4fa3ca43e9fb68da34ed8/docs/bilancio-oic-alfa-v3-acceptance-2026-10-15.md";
  const page = window.MPARANZA_FUNCTION_PAGES["bilancio-xbrl-it"];
  for (const [language, localized] of Object.entries(copy)) {
    const { workflow, acceptance, ...overview } = localized;
    Object.assign(page.copy[language], overview, {
      modelDataStatus: "relevant", modelData: modelDataCopy[language],
      detailSections: [
        {
          id: "closing-workflow", label: workflow[0], title: workflow[1], intro: workflow[2],
          steps: workflow[3].map(([title, stepCopy]) => ({ title, copy: stepCopy })),
          notes: [workflow[4]]
        },
        {
          id: "area-review", label: areaCopy[language][0], title: areaCopy[language][1], intro: areaCopy[language][2],
          notes: areaCopy[language].slice(3)
        },
        {
          id: "alfa-v3-acceptance", label: acceptance[0], title: acceptance[1], intro: acceptance[2],
          table: { caption: acceptance[3], headings: acceptance[4], rows: acceptance[5] },
          notes: [acceptance[6], acceptance[7]],
          evidence: { href: evidenceHref, label: acceptance[8] }
        }
      ]
    });
  }
})();
