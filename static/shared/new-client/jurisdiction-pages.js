(() => {
  "use strict";

  const SUPPORTED_LANGUAGES = ["it", "en", "fr", "de"];
  const OPEN_VERA_URL =
    "https://chatgpt.com/auth/login?next=%2Fplugins%2Fplugins_6a57ac5ce65c8191ae7bd0a51160eb7d";
  const OG_LOCALES = {
    it: "it_IT",
    en: "en_GB",
    fr: "fr_FR",
    de: "de_DE",
  };

  const interfaceCopy = {
    it: {
      homeAria: "Home page Mparanza",
      navAria: "Sezioni della pagina",
      languageAria: "Lingua di presentazione",
      nav: {
        workflow: "Percorso",
        documents: "Documenti",
        outputs: "Risultati",
        download: "Installazione",
      },
      breadcrumbAria: "Percorso della pagina",
      breadcrumbHub: "Nuovo cliente",
      scopeTitle: "Cosa ottiene lo studio",
      scopeLabels: {
        input: "Materiale",
        processing: "Lavorazione",
        output: "Risultato",
        focus: "Perimetro",
      },
      scopeProcessing:
        "Inventario, OCR locale quando utile, classificazione, estrazione e punti da verificare",
      scopeOutput:
        "Memo dello studio, domande al cliente, stato di lettura e file CSV",
      jurisdictionLabel: "Giurisdizione",
      languageLabel: "Lingua di presentazione",
      languageName: "Italiano",
      contextAria: "Contesto della pagina",
      workflow: {
        eyebrow: "Percorso",
        title: "Dalla cartella del cliente a un dossier di lavoro",
        copy:
          "La prima lettura risponde alle domande operative: quali documenti sono arrivati, quali sono leggibili, cosa sembra mancare e cosa chiedere al cliente.",
        cards: [
          {
            title: "Inventario",
            copy:
              "Ogni file viene elencato con percorso, probabile periodo fiscale, tipo di documento, leggibilità e possibili duplicati.",
          },
          {
            title: "Lettura",
            copy:
              "Il testo viene estratto dai PDF; l'OCR locale può aiutare con scansioni e immagini quando l'ambiente lo consente.",
          },
          {
            title: "Sintesi",
            copy:
              "La sintesi collega documenti letti, stato di lettura e punti aperti a un memo conciso e a domande precise per il cliente.",
          },
        ],
      },
      outputs: {
        eyebrow: "Risultati",
        title: "Un dossier di lavoro per lo studio",
        copy:
          "Documenti, estratti, punti aperti e richieste al cliente restano collegati alle fonti lette.",
        tableAria: "Risultati per il nuovo cliente",
        headers: ["Risultato", "Utilizzo", "Dettaglio"],
        rows: [
          [
            "Inventario",
            "Aprire rapidamente il dossier e riconoscere le famiglie di documenti.",
            "Categorie prudenti, periodi fiscali e stato di lettura.",
          ],
          [
            "Documenti mancanti",
            "Trasformare le lacune in richieste chiare per il cliente.",
            "Richieste collegate ai documenti effettivamente trovati.",
          ],
          [
            "Memo dello studio",
            "Riassumere ciò che è stato trovato, ciò che è incerto e ciò che richiede seguito.",
            "Sintesi con riferimenti ai documenti e agli estratti disponibili.",
          ],
          [
            "Bozza email al cliente",
            "Chiedere i documenti o i chiarimenti necessari per proseguire.",
            "Bozza pronta per essere adattata dallo studio.",
          ],
        ],
      },
      video: {
        eyebrow: "Vera al lavoro",
        title: "Dalla cartella cliente a un dossier pronto da usare",
        copy:
          "Una breve dimostrazione del percorso tra documenti ricevuti, punti aperti e dossier di lavoro.",
        narration: {
          fr: "Guida breve · Narrazione francese",
          de: "Guida breve · Narrazione tedesca",
          en: "Guida breve · Narrazione inglese",
        },
        thumbnailAlt: "Anteprima della guida video sul nuovo cliente",
      },
      next: {
        eyebrow: "Passaggio successivo",
        title: "Continua con il rapporto professionale.",
        copy:
          "Riusa dati, memo e fonti per strutturare persone, servizi, piani documentali, attività aperte e monitoraggio nello stesso percorso Nuovo cliente.",
        button: "Continua il percorso",
      },
      download: {
        eyebrow: "Installazione",
        title: "Installa Vera e inizia dalla cartella cliente",
        button: "Installa Vera",
      },
    },
    en: {
      homeAria: "Mparanza home",
      navAria: "Page sections",
      languageAria: "Presentation language",
      nav: {
        workflow: "Workflow",
        documents: "Documents",
        outputs: "Outputs",
        download: "Installation",
      },
      breadcrumbAria: "Page path",
      breadcrumbHub: "New client",
      scopeTitle: "What the practice receives",
      scopeLabels: {
        input: "Material",
        processing: "Processing",
        output: "Output",
        focus: "Scope",
      },
      scopeProcessing:
        "Inventory, local OCR where useful, classification, extraction and review points",
      scopeOutput:
        "Practice memo, client questions, reading status and CSV files",
      jurisdictionLabel: "Jurisdiction",
      languageLabel: "Presentation language",
      languageName: "English",
      contextAria: "Page context",
      workflow: {
        eyebrow: "Workflow",
        title: "From client folder to work pack",
        copy:
          "The first pass answers the practical questions: what has arrived, what is readable, what seems to be missing and what the client needs to clarify.",
        cards: [
          {
            title: "Inventory",
            copy:
              "Each file is listed with its path, likely tax period, document type, readable-text status and possible duplicate signals.",
          },
          {
            title: "Read",
            copy:
              "Text is extracted from PDFs; local OCR can help with scans and images when the environment supports it.",
          },
          {
            title: "Summarise",
            copy:
              "The summary connects the documents read, reading status and open points to a concise practice memo and specific client questions.",
          },
        ],
      },
      outputs: {
        eyebrow: "Outputs",
        title: "A work pack for the practice",
        copy:
          "Documents, extracted passages, open points and client requests remain connected to the source material read.",
        tableAria: "New-client outputs",
        headers: ["Output", "Use", "Detail"],
        rows: [
          [
            "Inventory",
            "Open the work pack quickly and identify the document families.",
            "Conservative categories, tax periods and reading status.",
          ],
          [
            "Missing documents",
            "Turn gaps in the folder into clear client requests.",
            "Requests tied to the documents actually found.",
          ],
          [
            "Practice memo",
            "Summarise what was found, what is uncertain and what needs follow-up.",
            "A summary linked to documents and available extracts.",
          ],
          [
            "Client email draft",
            "Ask for the documents or clarifications needed to continue.",
            "A draft ready for the practice to adapt.",
          ],
        ],
      },
      video: {
        eyebrow: "Vera at work",
        title: "From a client folder to a case file you can start from",
        copy:
          "A short demonstration of the path from incoming records and open points to a usable work pack.",
        narration: {
          fr: "Short guide · French narration",
          de: "Short guide · German narration",
          en: "Short guide · English narration",
        },
        thumbnailAlt: "Preview of the new-client video guide",
      },
      next: {
        eyebrow: "Next step",
        title: "Continue with the professional relationship.",
        copy:
          "Reuse the data, memo and sources to structure people, services, document plans, open actions and monitoring in the same New Client journey.",
        button: "Continue the journey",
      },
      download: {
        eyebrow: "Installation",
        title: "Install Vera and start with the client folder",
        button: "Install Vera",
      },
    },
    fr: {
      homeAria: "Accueil Mparanza",
      navAria: "Sections de la page",
      languageAria: "Langue de présentation",
      nav: {
        workflow: "Parcours",
        documents: "Documents",
        outputs: "Livrables",
        download: "Installation",
      },
      breadcrumbAria: "Parcours de la page",
      breadcrumbHub: "Nouveau client",
      scopeTitle: "Ce que le cabinet obtient",
      scopeLabels: {
        input: "Documents",
        processing: "Traitement",
        output: "Livrables",
        focus: "Périmètre",
      },
      scopeProcessing:
        "Inventaire, OCR local lorsque nécessaire, classification, extraction et points à vérifier",
      scopeOutput:
        "Mémo cabinet, questions client, statut de lecture et fichiers CSV",
      jurisdictionLabel: "Juridiction",
      languageLabel: "Langue de présentation",
      languageName: "Français",
      contextAria: "Contexte de la page",
      workflow: {
        eyebrow: "Parcours",
        title: "Du dossier client à un dossier de travail",
        copy:
          "La première lecture répond aux questions pratiques : quels documents sont arrivés, lesquels sont lisibles, ce qui semble manquer et ce que le client doit préciser.",
        cards: [
          {
            title: "Inventorier",
            copy:
              "Chaque fichier est listé avec son chemin, sa période fiscale probable, son type, sa lisibilité et les éventuels signaux de doublon.",
          },
          {
            title: "Lire",
            copy:
              "Le texte est extrait des PDF ; l'OCR local peut aider pour les scans et les images lorsque l'environnement le permet.",
          },
          {
            title: "Synthétiser",
            copy:
              "La synthèse relie les pièces lues, le statut de lecture et les points ouverts à un mémo concis et à des questions précises pour le client.",
          },
        ],
      },
      outputs: {
        eyebrow: "Livrables",
        title: "Un dossier de travail pour le cabinet",
        copy:
          "Documents, extraits, points ouverts et demandes client restent reliés aux sources effectivement lues.",
        tableAria: "Livrables pour le nouveau client",
        headers: ["Livrable", "Utilisation", "Détail"],
        rows: [
          [
            "Inventaire",
            "Ouvrir rapidement le dossier et repérer les familles de documents.",
            "Catégories prudentes, périodes fiscales et statut de lecture.",
          ],
          [
            "Documents manquants",
            "Transformer les lacunes du dossier en demandes claires au client.",
            "Demandes reliées aux documents effectivement trouvés.",
          ],
          [
            "Mémo cabinet",
            "Résumer ce qui a été trouvé, ce qui reste incertain et ce qui demande un suivi.",
            "Synthèse reliée aux documents et extraits disponibles.",
          ],
          [
            "Brouillon d'email client",
            "Demander les documents ou précisions nécessaires pour poursuivre.",
            "Brouillon prêt à être adapté par le cabinet.",
          ],
        ],
      },
      video: {
        eyebrow: "Vera au travail",
        title: "Du dossier client à un dossier prêt à traiter",
        copy:
          "Une courte démonstration du passage entre les pièces reçues, les points ouverts et le dossier de travail.",
        narration: {
          fr: "Guide court · Narration française",
          de: "Guide court · Narration allemande",
          en: "Guide court · Narration anglaise",
        },
        thumbnailAlt: "Aperçu du guide vidéo sur le nouveau client",
      },
      next: {
        eyebrow: "Étape suivante",
        title: "Poursuivez avec la relation professionnelle.",
        copy:
          "Réutilisez les données, le mémo et les sources pour structurer personnes, services, plans documentaires, actions ouvertes et suivi dans le même parcours Nouveau client.",
        button: "Continuer le parcours",
      },
      download: {
        eyebrow: "Installation",
        title: "Installer Vera et commencer par le dossier client",
        button: "Installer Vera",
      },
    },
    de: {
      homeAria: "Mparanza Startseite",
      navAria: "Seitenabschnitte",
      languageAria: "Darstellungssprache",
      nav: {
        workflow: "Ablauf",
        documents: "Unterlagen",
        outputs: "Ergebnisse",
        download: "Installation",
      },
      breadcrumbAria: "Seitenpfad",
      breadcrumbHub: "Neuer Mandant",
      scopeTitle: "Was die Kanzlei erhält",
      scopeLabels: {
        input: "Unterlagen",
        processing: "Verarbeitung",
        output: "Ergebnisse",
        focus: "Umfang",
      },
      scopeProcessing:
        "Inventar, lokales OCR bei Bedarf, Klassifikation, Extraktion und Prüfpunkte",
      scopeOutput:
        "Kanzleinotiz, Mandantenfragen, Lesestatus und CSV-Dateien",
      jurisdictionLabel: "Rechtsraum",
      languageLabel: "Darstellungssprache",
      languageName: "Deutsch",
      contextAria: "Seitenkontext",
      workflow: {
        eyebrow: "Ablauf",
        title: "Vom Mandantenordner zur Arbeitsunterlage",
        copy:
          "Die erste Durchsicht beantwortet die praktischen Fragen: Welche Unterlagen sind eingegangen, was ist lesbar, was scheint zu fehlen und was muss der Mandant klären?",
        cards: [
          {
            title: "Inventarisieren",
            copy:
              "Jede Datei wird mit Pfad, wahrscheinlicher Steuerperiode, Dokumenttyp, Lesbarkeit und möglichen Duplikathinweisen erfasst.",
          },
          {
            title: "Auslesen",
            copy:
              "Text wird aus PDF-Dateien extrahiert; lokales OCR kann bei Scans und Bildern helfen, wenn es in der Umgebung verfügbar ist.",
          },
          {
            title: "Zusammenfassen",
            copy:
              "Die Zusammenfassung verbindet gelesene Unterlagen, Lesestatus und offene Punkte mit einer knappen Kanzleinotiz und konkreten Mandantenfragen.",
          },
        ],
      },
      outputs: {
        eyebrow: "Ergebnisse",
        title: "Arbeitsunterlagen für die Kanzlei",
        copy:
          "Dokumente, Auszüge, offene Punkte und Mandantenanfragen bleiben mit den gelesenen Quellen verbunden.",
        tableAria: "Ergebnisse für den neuen Mandanten",
        headers: ["Ergebnis", "Nutzung", "Detail"],
        rows: [
          [
            "Inventar",
            "Das Dossier schnell öffnen und Dokumentfamilien erkennen.",
            "Vorsichtige Kategorien, Steuerperioden und Lesestatus.",
          ],
          [
            "Fehlende Unterlagen",
            "Lücken im Dossier in klare Mandantenanfragen übersetzen.",
            "Anfragen auf Basis der tatsächlich gefundenen Unterlagen.",
          ],
          [
            "Kanzleinotiz",
            "Zusammenfassen, was gefunden wurde, was unsicher ist und was nachverfolgt werden muss.",
            "Zusammenfassung mit Bezug zu Dokumenten und verfügbaren Auszügen.",
          ],
          [
            "E-Mail-Entwurf",
            "Die für die weitere Bearbeitung nötigen Unterlagen oder Klärungen anfordern.",
            "Entwurf zur Anpassung durch die Kanzlei.",
          ],
        ],
      },
      video: {
        eyebrow: "Vera bei der Arbeit",
        title: "Vom Mandantenordner zur arbeitsfähigen Akte",
        copy:
          "Eine kurze Demonstration vom eingegangenen Material über offene Punkte bis zur Arbeitsakte.",
        narration: {
          fr: "Kurzanleitung · Französische Sprecherstimme",
          de: "Kurzanleitung · Deutsche Sprecherstimme",
          en: "Kurzanleitung · Englische Sprecherstimme",
        },
        thumbnailAlt: "Vorschau der Videoanleitung für neue Mandanten",
      },
      next: {
        eyebrow: "Nächster Schritt",
        title: "Mit der Mandatsbeziehung fortfahren.",
        copy:
          "Nutzen Sie Daten, Notiz und Quellen weiter, um Personen, Leistungen, Dokumentpläne, offene Aufgaben und Monitoring im selben Ablauf Neuer Mandant zu strukturieren.",
        button: "Ablauf fortsetzen",
      },
      download: {
        eyebrow: "Installation",
        title: "Vera installieren und mit dem Mandantenordner beginnen",
        button: "Vera installieren",
      },
    },
  };

  const jurisdictions = {
    geneva: {
      slug: "geneva.html",
      defaultLanguage: "fr",
      documentSectionId: "documents",
      outputSectionId: "outputs",
      videoId: "d9S4SA63sVw",
      videoLanguage: "fr",
      copy: {
        it: {
          metaTitle: "Nuovo cliente · Ginevra | Vera",
          metaDescription:
            "Prima lettura di un dossier fiscale di Ginevra: inventario, punti aperti, memo dello studio e richiesta al cliente preparati con Vera.",
          ogDescription:
            "Dal dossier fiscale ricevuto a una base di lavoro leggibile per lo studio.",
          name: "Ginevra",
          jurisdiction: "Ginevra · Svizzera",
          eyebrow: "Nuovo cliente · Ginevra",
          title: "Prima lettura di un dossier fiscale ginevrino",
          subtitle:
            "Ordina i documenti ricevuti, isola ciò che manca e prepara le domande da inviare al cliente prima della revisione fiscale.",
          heroCopy:
            "Usalo quando i giustificativi arrivano come PDF, immagini, estratti o file diversi. Codex legge la cartella localmente, prepara l'inventario, evidenzia i punti incerti e produce un memo dello studio con una bozza di email al cliente.",
          scopeInput:
            "PDF, immagini, estratti bancari e documenti fiscali",
          scopeFocus: "Dossier fiscali di Ginevra",
          documents: {
            eyebrow: "Documenti",
            title: "Documenti messi in ordine",
            copy:
              "La pagina è calibrata sulle famiglie di documenti frequenti in un dossier fiscale ginevrino: redditi, patrimonio, assicurazioni, previdenza, immobili e situazioni da chiarire.",
            cards: [
              {
                title: "Redditi e patrimonio",
                items: [
                  "Certificati di salario e attestazioni di rendita.",
                  "Estratti bancari, titoli, investimenti e disponibilità.",
                  "Documenti relativi al patrimonio mobiliare o immobiliare.",
                ],
              },
              {
                title: "Deduzioni e giustificativi",
                items: [
                  "Assicurazione malattia, secondo pilastro e terzo pilastro.",
                  "Spese mediche, custodia dei figli, formazione e donazioni.",
                  "Ipoteca, interessi, lavori e documenti di proprietà.",
                ],
              },
              {
                title: "Punti da chiarire",
                items: [
                  "Imposta alla fonte e cambiamenti di situazione.",
                  "Redditi o beni all'estero.",
                  "File illeggibili, incompleti o riferiti a un altro periodo fiscale.",
                ],
              },
            ],
          },
          installCopy:
            "Aggiungi i documenti in ChatGPT e chiedi a Vera di preparare il primo fascicolo fiscale di Ginevra.",
        },
        en: {
          metaTitle: "New client · Geneva | Vera",
          metaDescription:
            "First review of a Geneva tax file with inventory, open points, practice memo and client request prepared with Vera.",
          ogDescription:
            "From an incoming Geneva tax file to a readable work pack for the practice.",
          name: "Geneva",
          jurisdiction: "Geneva · Switzerland",
          eyebrow: "New client · Geneva",
          title: "First review of a Geneva tax file",
          subtitle:
            "Organise the documents received, isolate what is missing and prepare the questions to send the client before the tax review.",
          heroCopy:
            "Use it when supporting records arrive as PDFs, images, exports or mixed files. Codex reads the folder locally, prepares the inventory, identifies uncertain points and produces a practice memo with a draft client email.",
          scopeInput:
            "PDFs, images, bank exports and tax supporting records",
          scopeFocus: "Geneva tax files",
          documents: {
            eyebrow: "Documents",
            title: "Documents put in order",
            copy:
              "The page is calibrated for the document families commonly found in a Geneva tax file: income, wealth, insurance, pensions, property and situations to clarify.",
            cards: [
              {
                title: "Income and wealth",
                items: [
                  "Salary certificates and pension statements.",
                  "Bank statements, securities, investments and balances.",
                  "Records relating to movable or immovable wealth.",
                ],
              },
              {
                title: "Deductions and evidence",
                items: [
                  "Health insurance, second pillar and third pillar.",
                  "Medical costs, childcare, education and donations.",
                  "Mortgage, interest, works and property records.",
                ],
              },
              {
                title: "Points to clarify",
                items: [
                  "Withholding tax and changes in circumstances.",
                  "Foreign income or assets.",
                  "Unreadable, incomplete or out-of-period files.",
                ],
              },
            ],
          },
          installCopy:
            "Add the records in ChatGPT and ask Vera to prepare the first Geneva tax file.",
        },
        fr: {
          metaTitle: "Nouveau client · Genève | Vera",
          metaDescription:
            "Première revue d'un dossier fiscal genevois avec inventaire, points ouverts, mémo cabinet et demande client préparés par Vera.",
          ogDescription:
            "Du dossier fiscal reçu à une base de travail lisible pour la fiduciaire.",
          name: "Genève",
          jurisdiction: "Genève · Suisse",
          eyebrow: "Nouveau client · Genève",
          title: "Première revue d'un dossier fiscal genevois",
          subtitle:
            "Classe les pièces reçues, isole les manques et prépare les questions à envoyer au client avant la revue fiscale.",
          heroCopy:
            "Utilisez-le quand les justificatifs arrivent en PDF, images, exports ou fichiers divers. Codex lit le dossier localement, prépare l'inventaire, signale les points incertains et produit un mémo cabinet avec un brouillon d'email client.",
          scopeInput:
            "PDF, images, exports bancaires et justificatifs fiscaux",
          scopeFocus: "Dossiers fiscaux genevois",
          documents: {
            eyebrow: "Documents",
            title: "Pièces mises en ordre",
            copy:
              "La page est calibrée sur les familles de documents fréquentes dans un dossier fiscal genevois : revenus, fortune, assurances, prévoyance, immobilier et situations à clarifier.",
            cards: [
              {
                title: "Revenus et fortune",
                items: [
                  "Certificats de salaire et attestations de rente.",
                  "Relevés bancaires, titres, placements et avoirs.",
                  "Pièces relatives à la fortune mobilière ou immobilière.",
                ],
              },
              {
                title: "Déductions et justificatifs",
                items: [
                  "Assurance maladie, prévoyance 2e pilier et 3e pilier.",
                  "Frais médicaux, garde d'enfants, formation et dons.",
                  "Hypothèque, intérêts, travaux et documents de propriété.",
                ],
              },
              {
                title: "Points à clarifier",
                items: [
                  "Impôt à la source et changement de situation.",
                  "Revenus ou biens à l'étranger.",
                  "Fichiers illisibles, incomplets ou hors période fiscale.",
                ],
              },
            ],
          },
          installCopy:
            "Ajoutez les pièces dans ChatGPT et demandez à Vera de préparer le premier dossier fiscal genevois.",
        },
        de: {
          metaTitle: "Neuer Mandant · Genf | Vera",
          metaDescription:
            "Erste Prüfung eines Genfer Steuerdossiers mit Inventar, offenen Punkten, Kanzleinotiz und Mandantenanfrage, vorbereitet mit Vera.",
          ogDescription:
            "Vom eingegangenen Genfer Steuerdossier zur lesbaren Arbeitsgrundlage für die Kanzlei.",
          name: "Genf",
          jurisdiction: "Genf · Schweiz",
          eyebrow: "Neuer Mandant · Genf",
          title: "Erste Durchsicht eines Genfer Steuerdossiers",
          subtitle:
            "Eingegangene Unterlagen ordnen, Lücken erkennen und Mandantenfragen vor der steuerlichen Prüfung vorbereiten.",
          heroCopy:
            "Nutzen Sie diesen Ablauf, wenn Nachweise als PDF, Bilder, Exporte oder gemischte Dateien eintreffen. Codex liest den Ordner lokal, erstellt das Inventar, kennzeichnet unklare Punkte und bereitet eine Kanzleinotiz mit E-Mail-Entwurf vor.",
          scopeInput:
            "PDF-Dateien, Bilder, Bankexporte und Steuerbelege",
          scopeFocus: "Genfer Steuerdossiers",
          documents: {
            eyebrow: "Unterlagen",
            title: "Geordnete Dokumente",
            copy:
              "Die Seite ist auf die in Genfer Steuerdossiers häufigen Dokumentfamilien abgestimmt: Einkommen, Vermögen, Versicherungen, Vorsorge, Liegenschaften und Klärungsfälle.",
            cards: [
              {
                title: "Einkommen und Vermögen",
                items: [
                  "Lohnausweise und Rentenbescheinigungen.",
                  "Bankauszüge, Wertschriften, Anlagen und Guthaben.",
                  "Unterlagen zu beweglichem oder unbeweglichem Vermögen.",
                ],
              },
              {
                title: "Abzüge und Nachweise",
                items: [
                  "Krankenversicherung, zweite Säule und dritte Säule.",
                  "Krankheitskosten, Kinderbetreuung, Weiterbildung und Spenden.",
                  "Hypothek, Zinsen, Arbeiten und Eigentumsunterlagen.",
                ],
              },
              {
                title: "Klärungspunkte",
                items: [
                  "Quellensteuer und Änderungen der persönlichen Situation.",
                  "Ausländische Einkünfte oder Vermögenswerte.",
                  "Unlesbare, unvollständige oder periodenfremde Dateien.",
                ],
              },
            ],
          },
          installCopy:
            "Fügen Sie die Unterlagen in ChatGPT hinzu und bitten Sie Vera, die erste Genfer Steuerprüfung vorzubereiten.",
        },
      },
    },
    zurich: {
      slug: "zurich.html",
      defaultLanguage: "de",
      documentSectionId: "belege",
      outputSectionId: "output",
      videoId: "Mjfz1e98oIw",
      videoLanguage: "de",
      copy: {
        it: {
          metaTitle: "Nuovo cliente · Zurigo | Vera",
          metaDescription:
            "Prima lettura di un dossier fiscale di Zurigo con inventario, punti aperti, memo dello studio e richiesta al cliente preparati con Vera.",
          ogDescription:
            "Dal dossier fiscale ricevuto a una base di lavoro leggibile per lo studio fiduciario.",
          name: "Zurigo",
          jurisdiction: "Zurigo · Svizzera",
          eyebrow: "Nuovo cliente · Zurigo",
          title: "Prima lettura del dossier fiscale per fiduciari di Zurigo",
          subtitle:
            "Prima revisione del dossier: documenti ricevuti, punti aperti, indicazioni formali, memo interno e bozza di email al cliente.",
          heroCopy:
            "Usalo quando i documenti arrivano come PDF, immagini, estratti e giustificativi diversi. La prima lettura ordina il dossier, estrae il testo leggibile e prepara una base di lavoro per le fasi successive.",
          scopeInput:
            "Cartella cliente con PDF, immagini, estratti e giustificativi",
          scopeFocus: "Dossier fiscali di Zurigo",
          documents: {
            eyebrow: "Documenti",
            title: "Documenti ordinati per il nuovo cliente",
            copy:
              "La prima lettura di Zurigo tratta le famiglie di documenti ricorrenti nella pratica fiduciaria: redditi, patrimonio, assicurazioni, previdenza, immobili e casi da chiarire.",
            cards: [
              {
                title: "Redditi e patrimonio",
                items: [
                  "Certificato di salario e attestazioni di rendita.",
                  "Estratti bancari e postali, titoli e disponibilità.",
                  "Documenti sul patrimonio in Svizzera o all'estero.",
                ],
              },
              {
                title: "Deduzioni e giustificativi",
                items: [
                  "Premi assicurativi, secondo pilastro e pilastro 3a.",
                  "Spese mediche, formazione, custodia dei figli e donazioni.",
                  "Spese professionali, interessi ipotecari e manutenzione immobiliare.",
                ],
              },
              {
                title: "Punti da chiarire",
                items: [
                  "Imposta alla fonte e tassazione ordinaria successiva.",
                  "Redditi o beni all'estero.",
                  "File illeggibili, incompleti o riferiti a un altro periodo fiscale.",
                ],
              },
            ],
          },
          installCopy:
            "Aggiungi i documenti in ChatGPT e chiedi a Vera di preparare il primo fascicolo fiscale di Zurigo.",
        },
        en: {
          metaTitle: "New client · Zurich | Vera",
          metaDescription:
            "First review of a Zurich tax file with inventory, open points, practice memo and client request prepared with Vera.",
          ogDescription:
            "From an incoming Zurich tax file to a readable work pack for the fiduciary practice.",
          name: "Zurich",
          jurisdiction: "Zurich · Switzerland",
          eyebrow: "New client · Zurich",
          title: "First review of a Zurich client tax file",
          subtitle:
            "First pass through the file: records received, open points, formal notes, internal memo and client email draft.",
          heroCopy:
            "Use it when records arrive as mixed PDFs, images, exports and supporting documents. The first review orders the file, extracts readable text and prepares a work pack for the next stage.",
          scopeInput:
            "Client folder with PDFs, images, exports and supporting records",
          scopeFocus: "Zurich tax files",
          documents: {
            eyebrow: "Documents",
            title: "Documents organised for the new client",
            copy:
              "The Zurich first review covers the document families that recur in fiduciary practice: income, wealth, insurance, pensions, property and cases that need clarification.",
            cards: [
              {
                title: "Income and wealth",
                items: [
                  "Salary certificates and pension statements.",
                  "Bank and postal-account statements, securities and balances.",
                  "Evidence of assets in Switzerland or abroad.",
                ],
              },
              {
                title: "Deductions and evidence",
                items: [
                  "Insurance premiums, second pillar and pillar 3a.",
                  "Medical costs, further education, childcare and donations.",
                  "Employment costs, mortgage interest and property maintenance.",
                ],
              },
              {
                title: "Points to clarify",
                items: [
                  "Withholding tax and subsequent ordinary assessment.",
                  "Foreign income or assets.",
                  "Unreadable, incomplete or out-of-period files.",
                ],
              },
            ],
          },
          installCopy:
            "Add the records in ChatGPT and ask Vera to prepare the first Zurich tax file.",
        },
        fr: {
          metaTitle: "Nouveau client · Zurich | Vera",
          metaDescription:
            "Première revue d'un dossier fiscal zurichois avec inventaire, points ouverts, mémo cabinet et demande client préparés avec Vera.",
          ogDescription:
            "Du dossier fiscal reçu à une base de travail lisible pour la fiduciaire.",
          name: "Zurich",
          jurisdiction: "Zurich · Suisse",
          eyebrow: "Nouveau client · Zurich",
          title: "Première revue d'un dossier fiscal zurichois",
          subtitle:
            "Premier passage sur le dossier : pièces reçues, points ouverts, indications formelles, mémo interne et brouillon d'email client.",
          heroCopy:
            "Utilisez-le lorsque les pièces arrivent sous forme de PDF, images, exports et justificatifs divers. La première revue ordonne le dossier, extrait le texte lisible et prépare une base de travail pour la suite.",
          scopeInput:
            "Dossier client avec PDF, images, exports et justificatifs",
          scopeFocus: "Dossiers fiscaux zurichois",
          documents: {
            eyebrow: "Documents",
            title: "Documents ordonnés par l'instruction",
            copy:
              "La première revue zurichoise couvre les familles de documents récurrentes dans la pratique fiduciaire : revenus, fortune, assurances, prévoyance, immobilier et cas à clarifier.",
            cards: [
              {
                title: "Revenus et fortune",
                items: [
                  "Certificats de salaire et attestations de rente.",
                  "Relevés bancaires et postaux, titres et avoirs.",
                  "Justificatifs du patrimoine en Suisse ou à l'étranger.",
                ],
              },
              {
                title: "Déductions et justificatifs",
                items: [
                  "Primes d'assurance, deuxième pilier et pilier 3a.",
                  "Frais médicaux, formation continue, garde d'enfants et dons.",
                  "Frais professionnels, intérêts hypothécaires et entretien immobilier.",
                ],
              },
              {
                title: "Points à clarifier",
                items: [
                  "Impôt à la source et taxation ordinaire ultérieure.",
                  "Revenus ou éléments de fortune à l'étranger.",
                  "Fichiers illisibles, incomplets ou hors période fiscale.",
                ],
              },
            ],
          },
          installCopy:
            "Ajoutez les pièces dans ChatGPT et demandez à Vera de préparer le premier dossier fiscal zurichois.",
        },
        de: {
          metaTitle: "Neuer Mandant · Zürich | Vera",
          metaDescription:
            "Zürcher Mandantenunterlagen mit Vera inventarisieren, offene Punkte ordnen und eine Kanzleinotiz sowie Mandantenanfrage vorbereiten.",
          ogDescription:
            "Vom eingegangenen Steuerdossier zur lesbaren Arbeitsgrundlage für die Treuhandpraxis.",
          name: "Zürich",
          jurisdiction: "Zürich · Schweiz",
          eyebrow: "Neuer Mandant · Zürich",
          title: "Neue Mandantenakte für Zürcher Treuhänder",
          subtitle:
            "Erste Durchsicht eines Mandantendossiers: erhaltene Belege, offene Punkte, formale Hinweise, interne Notiz und E-Mail-Entwurf.",
          heroCopy:
            "Nutzen Sie es, wenn Belege als gemischte PDF-Dateien, Bilder, Exporte und Nachweise eintreffen. Vera ordnet das Dossier, extrahiert lesbaren Text und bereitet eine Arbeitsunterlage für die weitere Bearbeitung vor.",
          scopeInput:
            "Mandantenordner mit PDF-Dateien, Bildern, Exporten und Belegen",
          scopeFocus: "Zürcher Steuerdossiers",
          documents: {
            eyebrow: "Unterlagen",
            title: "Unterlagen für die neue Mandantenakte",
            copy:
              "Die Zürcher Erstprüfung behandelt die Dokumentfamilien, die in der Treuhandpraxis wiederkehren: Einkommen, Vermögen, Versicherungen, Vorsorge, Liegenschaften und unklare Fälle.",
            cards: [
              {
                title: "Einkommen und Vermögen",
                items: [
                  "Lohnausweis und Rentenbescheinigungen.",
                  "Bank-, Postkonto-, Wertschriften- und Guthabenbelege.",
                  "Nachweise zu Vermögen in der Schweiz oder im Ausland.",
                ],
              },
              {
                title: "Abzüge und Nachweise",
                items: [
                  "Versicherungsprämien, Säule 2 und Säule 3a.",
                  "Krankheitskosten, Weiterbildung, Kinderbetreuung und Spenden.",
                  "Berufsauslagen, Hypothekarzinsen und Liegenschaftsunterhalt.",
                ],
              },
              {
                title: "Klärungspunkte",
                items: [
                  "Quellensteuer und nachträgliche ordentliche Veranlagung.",
                  "Ausländische Einkünfte oder Vermögenswerte.",
                  "Unlesbare, unvollständige oder jahresfremde Dateien.",
                ],
              },
            ],
          },
          installCopy:
            "Fügen Sie die Unterlagen in ChatGPT hinzu und lassen Sie Vera die Zürcher Erstprüfung vorbereiten.",
        },
      },
    },
    uk: {
      slug: "uk.html",
      defaultLanguage: "en",
      documentSectionId: "documents",
      outputSectionId: "outputs",
      videoId: "hLhP6x00ghQ",
      videoLanguage: "en",
      copy: {
        it: {
          metaTitle: "Istruttoria Self Assessment · Regno Unito | Vera",
          metaDescription:
            "Organizza una cartella cliente per il Self Assessment nel Regno Unito, struttura i punti aperti e prepara memo ed email al cliente con Vera.",
          ogDescription:
            "Dalla cartella fiscale ricevuta a un dossier di lavoro leggibile per lo studio.",
          name: "Regno Unito",
          jurisdiction: "Regno Unito",
          eyebrow: "Nuovo cliente · Regno Unito",
          title: "Nuovo cliente per il Self Assessment",
          subtitle:
            "Prima lettura della cartella: documenti ricevuti, lacune da risolvere, memo dello studio ed email di seguito al cliente.",
          heroCopy:
            "Usalo quando il materiale del cliente arriva come PDF, immagini, estratti e giustificativi diversi. Vera classifica la cartella, estrae il testo leggibile e prepara un dossier di lavoro prima della compilazione o revisione della dichiarazione.",
          scopeInput:
            "Cartella cliente con PDF, immagini, estratti e giustificativi",
          scopeFocus: "Self Assessment del Regno Unito",
          documents: {
            eyebrow: "Documenti",
            title: "Documenti ordinati per il nuovo cliente",
            copy:
            "Il percorso è costruito sulle famiglie di documenti che arrivano normalmente prima della preparazione del Self Assessment.",
            cards: [
              {
                title: "Lavoro dipendente e pensioni",
                items: [
                  "P60, P45, P11D e buste paga.",
                  "Prospetti pensionistici e giustificativi dei benefit imponibili.",
                  "Student loan, Gift Aid e contributi pensionistici.",
                ],
              },
              {
                title: "Redditi e plusvalenze",
                items: [
                  "Lavoro autonomo, partnership e redditi immobiliari.",
                  "Redditi esteri, estratti di investimento e prospetti delle plusvalenze.",
                  "Estratti bancari, export contabili e fatture.",
                ],
              },
              {
                title: "Domande aperte",
                items: [
                  "Estratti mancanti, periodi fiscali dubbi e scansioni illeggibili.",
                  "Giustificativi di spesa, percorrenze, home office e costi immobiliari.",
                  "Registri IVA e relativi documenti di supporto.",
                ],
              },
            ],
          },
          installCopy:
            "Aggiungi i documenti in ChatGPT e chiedi a Vera di preparare il primo fascicolo Self Assessment del Regno Unito.",
        },
        en: {
          metaTitle: "New client · UK Self Assessment | Vera",
          metaDescription:
            "Organise a UK Self Assessment client folder, structure its open points and prepare a practice memo and client request with Vera.",
          ogDescription:
            "From an incoming tax folder to a readable work pack for the practice.",
          name: "United Kingdom",
          jurisdiction: "United Kingdom",
          eyebrow: "New client · United Kingdom",
          title: "New client for Self Assessment",
          subtitle:
            "First review of a Self Assessment folder: documents received, gaps to resolve, practice memo and client follow-up email.",
          heroCopy:
            "Use it when client material arrives as mixed PDFs, images, exports and supporting records. Vera classifies the folder, extracts readable text and prepares a work pack before the return is prepared or checked.",
          scopeInput:
            "A client folder with PDFs, images, exports and supporting records",
          scopeFocus: "UK Self Assessment files",
          documents: {
            eyebrow: "Documents",
            title: "Documents organised for the new client",
            copy:
              "The workflow is designed around the document families that typically arrive before Self Assessment preparation.",
            cards: [
              {
                title: "Employment and pensions",
                items: [
                  "P60, P45, P11D and payslips.",
                  "Pension statements and taxable-benefit support.",
                  "Student Loan, Gift Aid and pension-contribution support.",
                ],
              },
              {
                title: "Income and gains",
                items: [
                  "Self-employment, partnership and property records.",
                  "Foreign income, investment statements and capital-gains schedules.",
                  "Bank statements, bookkeeping exports and invoices.",
                ],
              },
              {
                title: "Open questions",
                items: [
                  "Missing statements, unclear tax years and unreadable scans.",
                  "Expense support, mileage, home-office costs and property costs.",
                  "VAT records and related supporting documents.",
                ],
              },
            ],
          },
          installCopy:
            "Add the records in ChatGPT and ask Vera to prepare the first UK Self Assessment file.",
        },
        fr: {
          metaTitle: "Instruction Self Assessment · Royaume-Uni | Vera",
          metaDescription:
            "Organisez un dossier client de Self Assessment au Royaume-Uni, structurez les points ouverts et préparez mémo et demande client avec Vera.",
          ogDescription:
            "Du dossier fiscal reçu à un dossier de travail lisible pour le cabinet.",
          name: "Royaume-Uni",
          jurisdiction: "Royaume-Uni",
          eyebrow: "Nouveau client · Royaume-Uni",
          title: "Nouveau client pour le Self Assessment",
          subtitle:
            "Première revue du dossier : documents reçus, lacunes à résoudre, mémo cabinet et email de suivi au client.",
          heroCopy:
            "Utilisez-le quand les pièces du client arrivent sous forme de PDF, images, exports et justificatifs divers. Vera classe le dossier, extrait le texte lisible et prépare un dossier de travail avant la préparation ou la revue de la déclaration.",
          scopeInput:
            "Dossier client avec PDF, images, exports et justificatifs",
          scopeFocus: "Self Assessment au Royaume-Uni",
          documents: {
            eyebrow: "Documents",
            title: "Documents ordonnés pour le nouveau client",
            copy:
              "Le parcours est conçu autour des familles de documents qui arrivent habituellement avant la préparation du Self Assessment.",
            cards: [
              {
                title: "Emploi et retraites",
                items: [
                  "P60, P45, P11D et fiches de paie.",
                  "Relevés de pension et justificatifs des avantages imposables.",
                  "Student Loan, Gift Aid et justificatifs des cotisations retraite.",
                ],
              },
              {
                title: "Revenus et plus-values",
                items: [
                  "Activité indépendante, société de personnes et revenus immobiliers.",
                  "Revenus étrangers, relevés d'investissement et tableaux de plus-values.",
                  "Relevés bancaires, exports comptables et factures.",
                ],
              },
              {
                title: "Questions ouvertes",
                items: [
                  "Relevés manquants, années fiscales incertaines et scans illisibles.",
                  "Justificatifs de frais, kilométrage, télétravail et coûts immobiliers.",
                  "Registres de TVA et justificatifs correspondants.",
                ],
              },
            ],
          },
          installCopy:
            "Ajoutez les pièces dans ChatGPT et demandez à Vera de préparer le premier dossier Self Assessment au Royaume-Uni.",
        },
        de: {
          metaTitle: "Self-Assessment-Erstprüfung · Vereinigtes Königreich | Vera",
          metaDescription:
            "Einen britischen Self-Assessment-Mandantenordner ordnen, offene Punkte strukturieren und Kanzleinotiz sowie Mandantenanfrage mit Vera vorbereiten.",
          ogDescription:
            "Vom eingegangenen Steuerordner zur lesbaren Arbeitsunterlage für die Kanzlei.",
          name: "Vereinigtes Königreich",
          jurisdiction: "Vereinigtes Königreich",
          eyebrow: "Neuer Mandant · Vereinigtes Königreich",
          title: "Neue Mandantenakte für Self Assessment",
          subtitle:
            "Erste Durchsicht des Self-Assessment-Ordners: eingegangene Unterlagen, zu klärende Lücken, Kanzleinotiz und E-Mail an den Mandanten.",
          heroCopy:
            "Nutzen Sie diesen Ablauf, wenn Mandantenunterlagen als PDF-Dateien, Bilder, Exporte und gemischte Nachweise eintreffen. Vera klassifiziert den Ordner, extrahiert lesbaren Text und bereitet eine Arbeitsunterlage vor, bevor die Erklärung erstellt oder geprüft wird.",
          scopeInput:
            "Mandantenordner mit PDF-Dateien, Bildern, Exporten und Nachweisen",
          scopeFocus: "Self Assessment im Vereinigten Königreich",
          documents: {
            eyebrow: "Unterlagen",
            title: "Unterlagen für die neue Mandantenakte",
            copy:
              "Die Erstprüfung ist auf die Dokumentfamilien ausgerichtet, die üblicherweise vor der Self-Assessment-Erstellung eingehen.",
            cards: [
              {
                title: "Beschäftigung und Pensionen",
                items: [
                  "P60, P45, P11D und Gehaltsabrechnungen.",
                  "Pensionsauszüge und Nachweise zu steuerpflichtigen Leistungen.",
                  "Student Loan, Gift Aid und Nachweise zu Pensionsbeiträgen.",
                ],
              },
              {
                title: "Einkünfte und Veräußerungsgewinne",
                items: [
                  "Selbstständigkeit, Personengesellschaften und Immobilienunterlagen.",
                  "Ausländische Einkünfte, Anlageauszüge und Aufstellungen zu Veräußerungsgewinnen.",
                  "Bankauszüge, Buchhaltungsexporte und Rechnungen.",
                ],
              },
              {
                title: "Offene Fragen",
                items: [
                  "Fehlende Auszüge, unklare Steuerjahre und unlesbare Scans.",
                  "Kostennachweise, Fahrtstrecken, Homeoffice- und Immobilienkosten.",
                  "Umsatzsteuerunterlagen und zugehörige Nachweise.",
                ],
              },
            ],
          },
          installCopy:
            "Fügen Sie die Unterlagen in ChatGPT hinzu und bitten Sie Vera, die erste britische Self-Assessment-Prüfung vorzubereiten.",
        },
      },
    },
  };

  const escapeHtml = (value) =>
    String(value).replace(
      /[&<>"']/g,
      (character) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#039;",
        })[character],
    );

  function languageUrl(language) {
    const url = new URL(window.location.href);
    url.search = "";
    url.hash = "";
    url.searchParams.set("lang", language);
    return `${url.pathname}${url.search}`;
  }

  function renderLanguageSwitch(activeLanguage) {
    return SUPPORTED_LANGUAGES.map((language) => {
      const current = language === activeLanguage;
      return `<a href="${escapeHtml(languageUrl(language))}" lang="${language}" hreflang="${language}"${
        current ? ' aria-current="page"' : ""
      }>${language.toUpperCase()}</a>`;
    }).join("");
  }

  function renderCards(cards) {
    return cards
      .map(
        (card) => `<article class="card">
          <h3>${escapeHtml(card.title)}</h3>
          <p>${escapeHtml(card.copy)}</p>
        </article>`,
      )
      .join("");
  }

  function renderDocumentCards(cards) {
    return cards
      .map(
        (card) => `<article class="card">
          <h3>${escapeHtml(card.title)}</h3>
          <ul>${card.items
            .map((item) => `<li>${escapeHtml(item)}</li>`)
            .join("")}</ul>
        </article>`,
      )
      .join("");
  }

  function renderOutputTable(outputs) {
    return `<div class="table-scroll">
      <table class="matrix" aria-label="${escapeHtml(outputs.tableAria)}">
        <thead><tr>${outputs.headers
          .map((header) => `<th scope="col">${escapeHtml(header)}</th>`)
          .join("")}</tr></thead>
        <tbody>${outputs.rows
          .map(
            (row) => `<tr>${row
              .map(
                (cell, index) =>
                  `<${
                    index === 0
                      ? 'th scope="row"'
                      : `td data-label="${escapeHtml(
                          outputs.headers[index],
                        )}"`
                  }>${escapeHtml(cell)}</${index === 0 ? "th" : "td"}>`,
              )
              .join("")}</tr>`,
          )
          .join("")}</tbody>
      </table>
    </div>`;
  }

  function setMetadata(page, pageCopy, language) {
    const canonicalUrl = `https://mparanza.com/static/shared/new-client/${page.slug}`;
    document.title = pageCopy.metaTitle;
    document.documentElement.lang = language;
    document.body.dataset.presentationLanguage = language;
    document
      .querySelector('meta[name="description"]')
      .setAttribute("content", pageCopy.metaDescription);
    document
      .querySelector('meta[property="og:locale"]')
      .setAttribute("content", OG_LOCALES[language]);
    document
      .querySelector('meta[property="og:title"]')
      .setAttribute("content", pageCopy.metaTitle);
    document
      .querySelector('meta[property="og:description"]')
      .setAttribute("content", pageCopy.ogDescription);
    document
      .querySelector('meta[property="og:url"]')
      .setAttribute("content", `${canonicalUrl}?lang=${language}`);
  }

  function renderPage(page, language) {
    const ui = interfaceCopy[language];
    const copy = page.copy[language];
    const header = document.querySelector(".topbar");
    const main = document.getElementById("page-content");
    const narration = ui.video.narration[page.videoLanguage];

    header.innerHTML = `<div class="nav-shell">
      <a class="brand" href="/?lang=${language}" aria-label="${escapeHtml(
        ui.homeAria,
      )}">
        <img src="https://mparanza.com/images/MPARANZA-HORIZONTAL.png" alt="Mparanza">
      </a>
      <nav class="nav-links" aria-label="${escapeHtml(ui.navAria)}">
        <a href="#workflow">${escapeHtml(ui.nav.workflow)}</a>
        <a href="#${escapeHtml(page.documentSectionId)}">${escapeHtml(
          ui.nav.documents,
        )}</a>
        <a href="#${escapeHtml(page.outputSectionId)}">${escapeHtml(
          ui.nav.outputs,
        )}</a>
        <a href="#download">${escapeHtml(ui.nav.download)}</a>
      </nav>
      <nav class="language-switch" aria-label="${escapeHtml(
        ui.languageAria,
      )}">${renderLanguageSwitch(language)}</nav>
    </div>`;

    main.innerHTML = `
      <nav class="jurisdiction-breadcrumb" aria-label="${escapeHtml(
        ui.breadcrumbAria,
      )}">
        <a href="../vera/index.html?lang=${language}">Vera</a><span aria-hidden="true">/</span>
        <a href="index.html?lang=${language}">${escapeHtml(
          ui.breadcrumbHub,
        )}</a><span aria-hidden="true">/</span>
        <strong>${escapeHtml(copy.name)}</strong>
      </nav>

      <section class="hero" id="hero">
        <div>
          <p class="eyebrow">${escapeHtml(copy.eyebrow)}</p>
          <h1>${escapeHtml(copy.title)}</h1>
          <p class="subtitle">${escapeHtml(copy.subtitle)}</p>
          <p class="hero-copy">${escapeHtml(copy.heroCopy)}</p>
        </div>
        <aside class="scope-panel" aria-label="${escapeHtml(ui.scopeTitle)}">
          <div>
            <h2>${escapeHtml(ui.scopeTitle)}</h2>
            <ul class="scope-list">
              <li><span>${escapeHtml(
                ui.scopeLabels.input,
              )}</span><strong>${escapeHtml(copy.scopeInput)}</strong></li>
              <li><span>${escapeHtml(
                ui.scopeLabels.processing,
              )}</span><strong>${escapeHtml(ui.scopeProcessing)}</strong></li>
              <li><span>${escapeHtml(
                ui.scopeLabels.output,
              )}</span><strong>${escapeHtml(ui.scopeOutput)}</strong></li>
              <li><span>${escapeHtml(
                ui.scopeLabels.focus,
              )}</span><strong>${escapeHtml(copy.scopeFocus)}</strong></li>
            </ul>
          </div>
        </aside>
      </section>

      <section class="jurisdiction-meta" aria-label="${escapeHtml(
        ui.contextAria,
      )}">
        <div class="jurisdiction-meta__field">
          <strong>${escapeHtml(ui.jurisdictionLabel)}</strong>
          <span>${escapeHtml(copy.jurisdiction)}</span>
        </div>
        <div class="jurisdiction-meta__field">
          <strong>${escapeHtml(ui.languageLabel)}</strong>
          <span>${escapeHtml(ui.languageName)}</span>
        </div>
      </section>

      <section class="section-block" id="workflow">
        <div class="section-head">
          <div><p class="eyebrow">${escapeHtml(
            ui.workflow.eyebrow,
          )}</p><h2>${escapeHtml(ui.workflow.title)}</h2></div>
          <p>${escapeHtml(ui.workflow.copy)}</p>
        </div>
        <div class="grid three">${renderCards(ui.workflow.cards)}</div>
      </section>

      <section class="section-block" id="${escapeHtml(
        page.documentSectionId,
      )}">
        <div class="section-head">
          <div><p class="eyebrow">${escapeHtml(
            copy.documents.eyebrow,
          )}</p><h2>${escapeHtml(copy.documents.title)}</h2></div>
          <p>${escapeHtml(copy.documents.copy)}</p>
        </div>
        <div class="grid three">${renderDocumentCards(
          copy.documents.cards,
        )}</div>
      </section>

      <section class="section-block" id="${escapeHtml(
        page.outputSectionId,
      )}">
        <div class="section-head">
          <div><p class="eyebrow">${escapeHtml(
            ui.outputs.eyebrow,
          )}</p><h2>${escapeHtml(ui.outputs.title)}</h2></div>
          <p>${escapeHtml(ui.outputs.copy)}</p>
        </div>
        ${renderOutputTable(ui.outputs)}
      </section>

      <section class="section-block" aria-labelledby="video-title">
        <a class="inline-video" href="https://youtu.be/${escapeHtml(
          page.videoId,
        )}" target="_blank" rel="noopener noreferrer">
          <span class="inline-video__thumb">
            <img src="https://i.ytimg.com/vi/${escapeHtml(
              page.videoId,
            )}/maxresdefault.jpg" alt="${escapeHtml(
              ui.video.thumbnailAlt,
            )}" width="1280" height="720" loading="lazy">
            <span class="inline-video__play" aria-hidden="true">▶</span>
          </span>
          <span>
            <span class="eyebrow">${escapeHtml(ui.video.eyebrow)}</span>
            <span class="video-language">${escapeHtml(narration)}</span>
            <h2 id="video-title">${escapeHtml(ui.video.title)}</h2>
            <p>${escapeHtml(ui.video.copy)}</p>
          </span>
        </a>
      </section>

      <section class="section-block" aria-labelledby="next-title">
        <div class="connected-panel">
          <div><p class="eyebrow">${escapeHtml(
            ui.next.eyebrow,
          )}</p><h2 id="next-title">${escapeHtml(
            ui.next.title,
          )}</h2><p>${escapeHtml(ui.next.copy)}</p></div>
          <a class="button" href="index.html?lang=${language}#relationship">${escapeHtml(
            ui.next.button,
          )}</a>
        </div>
      </section>

      <section class="section-block" id="download">
        <div class="section-head">
          <div><p class="eyebrow">${escapeHtml(
            ui.download.eyebrow,
          )}</p><h2>${escapeHtml(ui.download.title)}</h2></div>
          <p>${escapeHtml(copy.installCopy)}</p>
        </div>
        <div class="action-row">
          <a class="button" href="${OPEN_VERA_URL}" target="_blank" rel="noopener noreferrer">${escapeHtml(
            ui.download.button,
          )}</a>
        </div>
      </section>`;
  }

  const page = jurisdictions[document.body.dataset.jurisdiction];
  if (!page) return;

  const requestedLanguage = new URLSearchParams(window.location.search).get(
    "lang",
  );
  const language = SUPPORTED_LANGUAGES.includes(requestedLanguage)
    ? requestedLanguage
    : page.defaultLanguage;

  setMetadata(page, page.copy[language], language);
  renderPage(page, language);
  document.body.dataset.rendered = "true";
})();
