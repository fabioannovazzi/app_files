(() => {
  "use strict";

  const currentScript = document.currentScript;
  const languages = new Set(["it", "en", "fr", "de", "es"]);
  const assistantNames = { vera: "Vera", lucia: "Lucia", clara: "Clara" };
  const areaLabels = {
    vera: {
      "area-clients": {
        it: "Clienti e fascicoli",
        en: "Clients and files",
        fr: "Clients et dossiers",
        de: "Mandanten und Akten",
        es: "Clientes y expedientes",
      },
      "area-accounting": {
        it: "Controlli e analisi",
        en: "Checks and analysis",
        fr: "Contrôles et analyses",
        de: "Kontrollen und Analysen",
        es: "Controles y análisis",
      },
      "area-outputs": {
        it: "Report, comunicazione e ricerca",
        en: "Reports, communication, and research",
        fr: "Rapports, communication et recherche",
        de: "Berichte, Kommunikation und Recherche",
        es: "Informes, comunicación e investigación",
      },
      jurisdiction: {
        it: "Formati, enti e procedure italiane",
        en: "Functions available for the United Kingdom",
        fr: "Fonctions disponibles pour Genève",
        de: "Verfügbare Funktionen für Zürich",
        es: "Funciones disponibles para el mercado seleccionado",
      },
    },
    lucia: {
      "area-research": {
        it: "Ricerca legale",
        en: "Legal research",
        fr: "Recherche juridique",
        de: "Juristische Recherche",
        es: "Investigación jurídica",
      },
      "area-matters": {
        it: "Fascicoli",
        en: "Matter files",
        fr: "Dossiers",
        de: "Akten",
        es: "Expedientes",
      },
      "area-studio": {
        it: "Comunicazione e sito",
        en: "Communication and website",
        fr: "Communication et site",
        de: "Kommunikation und Website",
        es: "Comunicación y sitio web",
      },
    },
    clara: {
      "area-deliverables": {
        it: "Presentazioni, video e documenti",
        en: "Presentations, videos, and documents",
        fr: "Présentations, vidéos et documents",
        de: "Präsentationen, Videos und Dokumente",
        es: "Presentaciones, vídeos y documentos",
      },
      "area-recordings": {
        it: "Interviste e registrazioni",
        en: "Interviews and recordings",
        fr: "Entretiens et enregistrements",
        de: "Interviews und Aufnahmen",
        es: "Entrevistas y grabaciones",
      },
      "area-retail": {
        it: "Analisi retail",
        en: "Retail analysis",
        fr: "Analyse retail",
        de: "Retail-Analyse",
        es: "Análisis retail",
      },
      "area-analysis": {
        it: "Analisi aziendale",
        en: "Business analysis",
        fr: "Analyse d'entreprise",
        de: "Unternehmensanalyse",
        es: "Análisis empresarial",
      },
    },
  };

  const pageContexts = {
    "apertura-pratica": [["lucia", "area-matters"]],
    "archive-organization": [["vera", "area-clients"]],
    "avviso-intake": [["vera", "area-clients"]],
    "bandi-agevolazioni": [["vera", "area-outputs"], ["vera", "jurisdiction"]],
    "bilancio-xbrl-it": [["vera", "area-accounting"], ["vera", "jurisdiction"]],
    "browser-automation": [["vera", "area-clients"]],
    "check-entries": [["vera", "area-accounting"]],
    "clara-brand-fit": [["clara", "area-retail"]],
    "clara-advisory-planning": [["clara", "area-analysis"]],
    "clara-data-analysis": [["clara", "area-analysis"]],
    "clara-advisory-deliverable-validator": [["clara", "area-deliverables"]],
    "clara-documents": [["clara", "area-deliverables"]],
    "clara-interview": [["clara", "area-recordings"]],
    "clara-presentations": [["clara", "area-deliverables"]],
    "clara-research-video": [["clara", "area-deliverables"]],
    "clara-retailer-signals": [["clara", "area-retail"]],
    "clara-transcribe": [["clara", "area-recordings"]],
    "comunicazione-professionale": [["lucia", "area-studio"], ["vera", "area-outputs"]],
    "concordato-plan-review": [["vera", "area-outputs"], ["vera", "jurisdiction"]],
    "dati-fiscali-strutturati": [["vera", "area-clients"]],
    "deep-research-validator": [["lucia", "area-research"], ["vera", "area-outputs"]],
    "email-cliente": [["vera", "area-clients"]],
    "fatture-xml-check": [["vera", "area-clients"], ["vera", "jurisdiction"]],
    "financial-analysis": [["vera", "area-accounting"]],
    "journal-bank-reconciliation": [["vera", "area-accounting"]],
    "journal-sampling": [["vera", "area-accounting"]],
    "new-client": [["vera", "area-clients"]],
    "new-client/geneva": [["vera", "area-clients"], ["vera", "jurisdiction"]],
    "new-client/uk": [["vera", "area-clients"], ["vera", "jurisdiction"]],
    "new-client/zurich": [["vera", "area-clients"], ["vera", "jurisdiction"]],
    "presenza-digitale-studio": [["lucia", "area-studio"], ["vera", "area-outputs"]],
    "previdenza-inps": [["vera", "area-clients"], ["vera", "jurisdiction"]],
    "prompt-optimizer": [["lucia", "area-research"], ["vera", "area-outputs"]],
    "quesito-legale-fiscale": [["lucia", "area-research"], ["vera", "area-outputs"]],
    "registro-imprese-sari": [["vera", "area-clients"], ["vera", "jurisdiction"]],
    "report-builder": [["vera", "area-outputs"]],
    "report-enti-locali": [["vera", "jurisdiction"]],
    "riconciliazione-partite": [["vera", "area-accounting"]],
    "sales-plan": [["vera", "area-accounting"]],
    "studio-archive": [["vera", "area-clients"]],
    "variance-analysis": [["vera", "area-accounting"]],
  };

  const fallbackNames = {
    "browser-automation": {
      it: "Automazione web",
      en: "Web automation",
      fr: "Automatisation web",
      de: "Web-Automatisierung",
      es: "Automatización web",
    },
    "studio-archive": {
      it: "Ricerca nei documenti, nelle email e in WhatsApp",
      en: "Studio archive",
      fr: "Archives du cabinet",
      de: "Kanzleiarchiv",
      es: "Archivo del despacho",
    },
  };

  const canonicalNames = {
    "clara-advisory-planning": {
      it: "Pianificare un incarico di consulenza",
      en: "Plan an advisory assignment",
      fr: "Planifier une mission de conseil",
      de: "Beratungsauftrag planen",
      es: "Planificar un encargo de consultoría",
    },
    "archive-organization": {
      it: "Riordino della cartella cliente",
      en: "Reorganize the client folder",
      fr: "Réorganiser le dossier client",
      de: "Mandantenordner neu ordnen",
      es: "Reorganizar la carpeta del cliente",
    },
    "check-entries": {
      it: "Verifica delle scritture con i documenti di supporto",
      en: "Check entries against supporting documents",
      fr: "Vérifier les écritures avec les justificatifs",
      de: "Buchungen mit Belegen prüfen",
      es: "Comprobar los asientos con los documentos justificativos",
    },
    "concordato-plan-review": {
      it: "Revisione del concordato preventivo",
      en: "Review an Italian concordato preventivo",
      fr: "Réviser un concordato preventivo italien",
      de: "Italienischen Concordato Preventivo prüfen",
      es: "Revisar un concordato preventivo italiano",
    },
    "deep-research-validator": {
      it: "Validazione ricerca",
      en: "Verify research sources and conclusions",
      fr: "Vérifier les sources et les conclusions de la recherche",
      de: "Quellen und Schlussfolgerungen der Recherche prüfen",
      es: "Verificar las fuentes y conclusiones de la investigación",
    },
    "financial-analysis": {
      it: "Analisi finanziaria e due diligence",
      en: "Financial analysis and due diligence",
      fr: "Analyse financière et due diligence",
      de: "Finanzanalyse und Due Diligence",
      es: "Análisis financiero y due diligence",
    },
    "journal-bank-reconciliation": {
      it: "Riconciliazione banca-contabilità",
      en: "Reconcile bank and accounting records",
      fr: "Rapprocher les relevés bancaires et la comptabilité",
      de: "Bank und Buchhaltung abstimmen",
      es: "Conciliar los registros bancarios y contables",
    },
    "journal-sampling": {
      it: "Campionamento del giornale contabile",
      en: "Sample the accounting journal",
      fr: "Échantillonner le journal comptable",
      de: "Buchungsjournal stichprobenartig prüfen",
      es: "Muestrear el diario contable",
    },
    "new-client": {
      it: "Preparazione del fascicolo del nuovo cliente",
      en: "Prepare the new client file",
      fr: "Préparer le dossier du nouveau client",
      de: "Neue Mandantenakte vorbereiten",
      es: "Preparar el expediente del nuevo cliente",
    },
    "new-client/geneva": {
      fr: "Préparer le dossier d’un nouveau client · Genève",
    },
    "new-client/uk": {
      en: "Prepare a new client file · United Kingdom",
    },
    "new-client/zurich": {
      de: "Neue Mandantenakte vorbereiten · Zürich",
    },
    "previdenza-inps": {
      it: "Revisione di una pratica previdenziale INPS",
      en: "Review an Italian INPS social-security case",
      fr: "Réviser un dossier de prévoyance INPS italien",
      de: "Italienischen INPS-Sozialversicherungsfall prüfen",
      es: "Revisar un expediente de previsión social INPS italiano",
    },
    "prompt-optimizer": {
      it: "Ottimizzazione prompt",
      en: "Prepare a legal or tax research question",
      fr: "Préparer une question de recherche juridique ou fiscale",
      de: "Juristische oder steuerliche Recherchefrage vorbereiten",
      es: "Preparar una consulta de investigación jurídica o fiscal",
    },
    "quesito-legale-fiscale": {
      it: "Risposta a quesiti legali e fiscali",
      en: "Answer legal and tax questions",
      fr: "Répondre aux questions juridiques et fiscales",
      de: "Rechtliche und steuerliche Fragen beantworten",
      es: "Responder consultas jurídicas y fiscales",
    },
    "registro-imprese-sari": {
      it: "Preparazione di pratiche Registro Imprese, REA e DIRE",
      en: "Prepare Italian Business Register, REA, and DIRE filings",
      fr: "Préparer les formalités italiennes Registro Imprese, REA et DIRE",
      de: "Italienische Register-, REA- und DIRE-Meldungen vorbereiten",
      es: "Preparar trámites italianos del Registro Imprese, REA y DIRE",
    },
    "report-builder": {
      it: "Creazione di report Word da Excel, CSV e PDF",
      en: "Create Word reports from Excel, CSV, and PDF",
      fr: "Créer des rapports Word depuis Excel, CSV et PDF",
      de: "Word-Berichte aus Excel, CSV und PDF erstellen",
      es: "Crear informes Word desde Excel, CSV y PDF",
    },
    "riconciliazione-partite": {
      it: "Riconciliazione delle partite aperte",
      en: "Reconcile open items",
      fr: "Rapprocher les postes ouverts",
      de: "Offene Posten abstimmen",
      es: "Conciliar partidas abiertas",
    },
    "sales-plan": {
      it: "Preparazione del piano delle vendite",
      en: "Prepare the sales plan",
      fr: "Préparer le plan des ventes",
      de: "Vertriebsplan erstellen",
      es: "Preparar el plan de ventas",
    },
    "studio-archive": {
      it: "Ricerca nei documenti, nelle email e in WhatsApp",
      en: "Search documents, email, and WhatsApp",
      fr: "Rechercher dans les documents, les e-mails et WhatsApp",
      de: "Dokumente, E-Mails und WhatsApp durchsuchen",
      es: "Buscar en documentos, correos y WhatsApp",
    },
  };

  const ariaLabels = {
    it: "Percorso pagina",
    en: "Page path",
    fr: "Parcours de la page",
    de: "Seitenpfad",
    es: "Ruta de la página",
  };

  const headingLabels = {
    inputsResult: { it: "Input e risultato", en: "Inputs and result", fr: "Entrées et résultat", de: "Eingaben und Ergebnis", es: "Entradas y resultado" },
    steps: { it: "Passaggi", en: "Steps", fr: "Étapes", de: "Schritte", es: "Pasos" },
    video: { it: "Video", en: "Video", fr: "Vidéo", de: "Video", es: "Vídeo" },
    startingPrompt: { it: "Prompt iniziale", en: "Starting prompt", fr: "Prompt initial", de: "Start-Prompt", es: "Prompt inicial" },
    relatedFunction: { it: "Funzione collegata", en: "Related function", fr: "Fonction associée", de: "Verknüpfte Funktion", es: "Función relacionada" },
    relatedFunctions: { it: "Funzioni collegate", en: "Related functions", fr: "Fonctions associées", de: "Verknüpfte Funktionen", es: "Funciones relacionadas" },
    processingMethod: { it: "Metodo di elaborazione", en: "Processing method", fr: "Méthode de traitement", de: "Verarbeitungsmethode", es: "Método de tratamiento" },
    documentSources: { it: "Origine dei documenti", en: "Document sources", fr: "Origine des documents", de: "Dokumentquellen", es: "Origen de los documentos" },
    proposedStructure: { it: "Struttura proposta", en: "Proposed structure", fr: "Structure proposée", de: "Vorgeschlagene Struktur", es: "Estructura propuesta" },
    approval: { it: "Approvazione prima delle modifiche", en: "Approval before changes", fr: "Approbation avant les modifications", de: "Freigabe vor Änderungen", es: "Aprobación antes de los cambios" },
    planContents: { it: "Contenuto del piano di riordino", en: "Contents of the reorganization plan", fr: "Contenu du plan de réorganisation", de: "Inhalt des Neuordnungsplans", es: "Contenido del plan de reorganización" },
    excludedChanges: { it: "Modifiche non eseguite automaticamente", en: "Changes not made automatically", fr: "Modifications non exécutées automatiquement", de: "Nicht automatisch ausgeführte Änderungen", es: "Cambios no realizados automáticamente" },
    sourceVerification: { it: "Verifica delle fonti", en: "Source verification", fr: "Vérification des sources", de: "Quellenprüfung", es: "Verificación de fuentes" },
    technicalDetails: { it: "Dettagli tecnici", en: "Technical details", fr: "Détails techniques", de: "Technische Details", es: "Detalles técnicos" },
    analysisInputs: { it: "Dati utilizzati nell’analisi", en: "Analysis inputs", fr: "Données utilisées dans l’analyse", de: "Eingaben der Analyse", es: "Datos utilizados en el análisis" },
    dueDiligenceCalculations: { it: "Calcoli per la due diligence", en: "Due-diligence calculations", fr: "Calculs de due diligence", de: "Due-Diligence-Berechnungen", es: "Cálculos de due diligence" },
    calculationMethod: { it: "Metodo di calcolo", en: "Calculation method", fr: "Méthode de calcul", de: "Berechnungsmethode", es: "Método de cálculo" },
    calculationControls: { it: "Controlli prima del calcolo", en: "Checks before calculation", fr: "Contrôles avant le calcul", de: "Kontrollen vor der Berechnung", es: "Controles antes del cálculo" },
    professionalReview: { it: "Revisione professionale", en: "Professional review", fr: "Revue professionnelle", de: "Fachliche Prüfung", es: "Revisión profesional" },
    newClientWorkflow: { it: "Preparazione del fascicolo", en: "Client-file preparation", fr: "Préparation du dossier client", de: "Vorbereitung der Mandantenakte", es: "Preparación del expediente del cliente" },
    initialFileReview: { it: "Esame iniziale dei documenti", en: "Initial document review", fr: "Examen initial des documents", de: "Erste Dokumentenprüfung", es: "Examen inicial de los documentos" },
    missingItems: { it: "Documenti e chiarimenti mancanti", en: "Missing documents and clarifications", fr: "Documents et précisions manquants", de: "Fehlende Unterlagen und Rückfragen", es: "Documentos y aclaraciones pendientes" },
    italyChecks: { it: "Documenti e controlli per l’Italia", en: "Italy-specific documents and checks", fr: "Documents et contrôles propres à l’Italie", de: "Italienspezifische Dokumente und Kontrollen", es: "Documentos y controles específicos de Italia" },
    engagementFile: { it: "Fascicolo dell’incarico", en: "Engagement file", fr: "Dossier de mission", de: "Mandatsakte", es: "Expediente del encargo" },
    engagementDetails: { it: "Dati dell’incarico", en: "Engagement details", fr: "Données de la mission", de: "Mandatsdaten", es: "Datos del encargo" },
    documentPlan: { it: "Piano dei documenti", en: "Document plan", fr: "Plan des documents", de: "Dokumentenplan", es: "Plan de documentos" },
    amlAssessment: { it: "Valutazione antiriciclaggio", en: "Anti-money-laundering assessment", fr: "Évaluation anti-blanchiment", de: "Geldwäscheprüfung", es: "Evaluación de prevención del blanqueo" },
    fileStatus: { it: "Stato del fascicolo e punti da rivedere", en: "File status and review points", fr: "État du dossier et points à réviser", de: "Aktenstatus und Prüfpunkte", es: "Estado del expediente y puntos de revisión" },
    assumptions: { it: "Ipotesi da confermare", en: "Assumptions to confirm", fr: "Hypothèses à confirmer", de: "Zu bestätigende Annahmen", es: "Supuestos que confirmar" },
    outputs: { it: "Output", en: "Outputs", fr: "Livrables", de: "Ergebnisse", es: "Resultados" },
    setup: { it: "Configurazione", en: "Setup", fr: "Configuration", de: "Einrichtung", es: "Configuración" },
    searchMethod: { it: "Metodo di ricerca", en: "Search method", fr: "Méthode de recherche", de: "Suchmethode", es: "Método de búsqueda" },
    searchedSources: { it: "Fonti consultate", en: "Sources searched", fr: "Sources consultées", de: "Durchsuchte Quellen", es: "Fuentes consultadas" },
    searchExample: { it: "Esempio di ricerca", en: "Search example", fr: "Exemple de recherche", de: "Suchbeispiel", es: "Ejemplo de búsqueda" },
    sharedUse: { it: "Uso condiviso", en: "Shared use", fr: "Utilisation partagée", de: "Gemeinsame Nutzung", es: "Uso compartido" },
    dataHandling: { it: "Trattamento dei dati", en: "Data handling", fr: "Traitement des données", de: "Datenverarbeitung", es: "Tratamiento de datos" },
    openCodex: { it: "Apertura in Codex Desktop", en: "Open in Codex Desktop", fr: "Ouverture dans Codex Desktop", de: "In Codex Desktop öffnen", es: "Abrir en Codex Desktop" },
    originalFileLocation: { it: "Posizione dei file originali", en: "Location of original files", fr: "Emplacement des fichiers originaux", de: "Speicherort der Originaldateien", es: "Ubicación de los archivos originales" },
    privateLocalIndex: { it: "Indice locale privato", en: "Private local index", fr: "Index local privé", de: "Privater lokaler Index", es: "Índice local privado" },
    reviewMethod: { it: "Metodo di revisione", en: "Review method", fr: "Méthode de revue", de: "Prüfmethode", es: "Método de revisión" },
    judgmentChecks: { it: "Giudizio professionale e controlli", en: "Professional judgment and checks", fr: "Jugement professionnel et contrôles", de: "Fachliches Urteil und Kontrollen", es: "Juicio profesional y controles" },
    requiredInputs: { it: "Documenti e data di riferimento", en: "Documents and reference date", fr: "Documents et date de référence", de: "Dokumente und Stichtag", es: "Documentos y fecha de referencia" },
    sourcesAssumptions: { it: "Dati sorgente e ipotesi", en: "Source data and assumptions", fr: "Données source et hypothèses", de: "Quelldaten und Annahmen", es: "Datos fuente y supuestos" },
    calculationControlsPlan: { it: "Controlli del piano", en: "Plan checks", fr: "Contrôles du plan", de: "Plankontrollen", es: "Controles del plan" },
    calculationAndReconciliation: { it: "Regole di calcolo e riconciliazione", en: "Calculation and reconciliation rules", fr: "Règles de calcul et de rapprochement", de: "Berechnungs- und Abstimmungsregeln", es: "Reglas de cálculo y conciliación" },
    outputFiles: { it: "File prodotti", en: "Files produced", fr: "Fichiers produits", de: "Erzeugte Dateien", es: "Archivos generados" },
    accountingCheck: { it: "Controllo contabile", en: "Accounting check", fr: "Contrôle comptable", de: "Buchhaltungsprüfung", es: "Control contable" },
    fatturaCheck: { it: "Controllo delle fatture FatturaPA", en: "Checking FatturaPA invoices", fr: "Contrôle des factures FatturaPA", de: "Prüfung von FatturaPA-Rechnungen", es: "Control de facturas FatturaPA" },
    initialInventory: { it: "Inventario dello stato iniziale", en: "Initial-state inventory", fr: "Inventaire de l’état initial", de: "Inventar des Ausgangszustands", es: "Inventario del estado inicial" },
    localAuthorityPreset: { it: "Preset per i report degli enti locali", en: "Preset for local-government reports", fr: "Préréglage pour les rapports des collectivités", de: "Voreinstellung für Kommunalberichte", es: "Configuración para informes de entidades locales" },
    processingLocations: { it: "Dove viene elaborata ogni fonte", en: "Where each source is processed", fr: "Où chaque source est traitée", de: "Wo die einzelnen Quellen verarbeitet werden", es: "Dónde se procesa cada fuente" },
    localDocumentResult: { it: "Risultati dai documenti locali", en: "Results from local documents", fr: "Résultats des documents locaux", de: "Ergebnisse aus lokalen Dokumenten", es: "Resultados de los documentos locales" },
    gmailResult: { it: "Risultati da Gmail", en: "Results from Gmail", fr: "Résultats de Gmail", de: "Ergebnisse aus Gmail", es: "Resultados de Gmail" },
    whatsappResult: { it: "Risultati da WhatsApp", en: "Results from WhatsApp", fr: "Résultats de WhatsApp", de: "Ergebnisse aus WhatsApp", es: "Resultados de WhatsApp" },
    method: { it: "Metodo", en: "Method", fr: "Méthode", de: "Methode", es: "Método" },
    result: { it: "Risultato", en: "Output", fr: "Résultat", de: "Ergebnis", es: "Resultado" },
    sources: { it: "Fonti", en: "Sources", fr: "Sources", de: "Quellen", es: "Fuentes" },
    example: { it: "Esempio", en: "Example", fr: "Exemple", de: "Beispiel", es: "Ejemplo" },
    details: { it: "Dettagli", en: "Details", fr: "Détails", de: "Details", es: "Detalles" },
  };

  const literalHeadingKeys = {
    "archive-organization": { journey: "inputsResult", method: "processingMethod", storage: "documentSources", policy: "proposedStructure", review: "approval", "review.sees": "planContents", "review.safety": "excludedChanges", prompt: "startingPrompt" },
    "deep-research-validator": { proof: "sourceVerification", next: "relatedFunction", starter: "startingPrompt", details: "technicalDetails" },
    "financial-analysis": { packs: "analysisInputs", fdd: "dueDiligenceCalculations", method: "calculationMethod", controls: "calculationControls", boundary: "professionalReview", prompt: "startingPrompt", related: "relatedFunctions" },
    "new-client": { journey: "newClientWorkflow", prepare: "initialFileReview", "prepare.result": "missingItems", "prepare.videos": "video", italy: "italyChecks", relationship: "engagementFile", documents: "documentPlan", aml: "amlAssessment", proof: "fileStatus", prompt: "startingPrompt" },
    "previdenza-inps": { journey: "inputsResult", workflow: "steps", result: "video", next: "relatedFunction", prompt: "startingPrompt", technical: "technicalDetails" },
    "prompt-optimizer": { proof: "inputsResult", next: "relatedFunction", starter: "startingPrompt", details: "technicalDetails" },
    "registro-imprese-sari": { journey: "inputsResult", workflow: "steps", result: "video", next: "relatedFunction", prompt: "startingPrompt", technical: "technicalDetails" },
    "sales-plan": { method: "sourcesAssumptions", assumptions: "assumptions", controls: "calculationAndReconciliation", outputs: "outputs", boundary: "professionalReview", prompt: "startingPrompt" },
    "studio-archive": { archive: "setup", method: "searchMethod", sources: "searchedSources", example: "searchExample", people: "sharedUse", video: "video", data: "dataHandling", setup: "openCodex" },
  };

  const factualCopy = {
    fileSteps: { it: "Passaggi del fascicolo", en: "Client-file steps", fr: "Étapes du dossier client", de: "Schritte der Mandantenakte", es: "Pasos del expediente del cliente" },
    fileStepsCopy: {
      it: "Le cinque fasi usano i documenti e i dati già raccolti nel fascicolo.",
      en: "The five stages use the documents and data already collected in the client file.",
      fr: "Les cinq étapes utilisent les documents et les données déjà réunis dans le dossier client.",
      de: "Die fünf Schritte verwenden die bereits in der Mandantenakte erfassten Dokumente und Daten.",
      es: "Las cinco fases utilizan los documentos y datos ya reunidos en el expediente del cliente.",
    },
    socialSecurityCopy: {
      it: "Il fascicolo collega la richiesta, i documenti del caso, i calcoli e il risultato da rivedere.",
      en: "The file links the question, case documents, calculations, and the result to review.",
      fr: "Le dossier relie la question, les pièces du cas, les calculs et le résultat à réviser.",
      de: "Die Akte verbindet Fragestellung, Falldokumente, Berechnungen und das zu prüfende Ergebnis.",
      es: "El expediente vincula la pregunta, los documentos del caso, los cálculos y el resultado que debe revisarse.",
    },
    registerCopy: {
      it: "Il piano collega i fatti del caso, la Camera competente, le fonti applicabili, i passaggi e gli allegati.",
      en: "The plan links the case facts, competent Chamber, applicable sources, filing steps, and attachments.",
      fr: "Le plan relie les faits, la Chambre compétente, les sources applicables, les étapes et les pièces jointes.",
      de: "Der Plan verbindet Fallfakten, zuständige Kammer, anwendbare Quellen, Schritte und Anlagen.",
      es: "El plan vincula los hechos del caso, la Cámara competente, las fuentes aplicables, los pasos y los anexos.",
    },
    viewSteps: { it: "Vedi i passaggi", en: "View steps", fr: "Voir les étapes", de: "Schritte anzeigen", es: "Ver los pasos" },
    italyDocuments: { it: "Documenti e controlli per l’Italia", en: "Italy-specific documents and checks", fr: "Documents et contrôles propres à l’Italie", de: "Italienspezifische Dokumente und Kontrollen", es: "Documentos y controles específicos de Italia" },
  };

  const sharedFunctionNouns = {
    it: "La funzione",
    en: "The function",
    fr: "La fonction",
    de: "Die Funktion",
    es: "La función",
  };

  if (currentScript && !document.querySelector("link[data-function-page-navigation-style]")) {
    const stylesheet = document.createElement("link");
    stylesheet.rel = "stylesheet";
    stylesheet.href = new URL("function-page-navigation.css", currentScript.src).href;
    stylesheet.dataset.functionPageNavigationStyle = "";
    document.head.append(stylesheet);
  }

  function pageKey() {
    const parts = window.location.pathname.split("/").filter(Boolean);
    const filename = parts.at(-1) || "index.html";
    const parent = parts.at(-2) || "";
    if (filename === "index.html") return parent;
    return `${parent}/${filename.replace(/\.html$/, "")}`;
  }

  function language() {
    const requested = (document.documentElement.lang || new URLSearchParams(window.location.search).get("lang") || "it")
      .slice(0, 2)
      .toLowerCase();
    return languages.has(requested) ? requested : "it";
  }

  function selectedContext(key) {
    const contexts = pageContexts[key];
    if (!contexts) return null;

    const params = new URLSearchParams(window.location.search);
    const requestedProduct = params.get("from");
    const requestedArea = params.get("area");
    return (
      contexts.find(([product, area]) => product === requestedProduct && area === requestedArea) ||
      contexts.find(([product]) => product === requestedProduct) ||
      contexts[0]
    );
  }

  function currentName(existing, key, currentLanguage) {
    const explicit = document.querySelector("main[data-function-name]")?.dataset.functionName;
    if (explicit) return explicit.trim();

    const canonical = canonicalNames[key]?.[currentLanguage];
    if (canonical) return canonical;

    const heading = document.querySelector("main h1")?.textContent?.trim();
    if (heading) return heading;

    const currentNode = existing?.querySelector("strong, [aria-current='page']");
    let name = currentNode?.textContent?.trim() || existing?.textContent?.trim() || "";
    if (name.includes("/")) name = name.split("/").at(-1).trim();
    if (name.includes("·")) name = name.split("·").at(-1).trim();
    if (name) return name;

    const fallback = fallbackNames[key]?.[currentLanguage];
    return fallback || "";
  }

  function setHeading(selector, labelKey, currentLanguage) {
    const node = document.querySelector(selector);
    const value = headingLabels[labelKey]?.[currentLanguage];
    if (node && value) node.textContent = value;
  }

  function setFactualCopy(selector, copyKey, currentLanguage) {
    const node = document.querySelector(selector);
    const value = factualCopy[copyKey]?.[currentLanguage];
    if (node && value) node.textContent = value;
  }

  function directPrompt(prompt, assistant, currentLanguage) {
    let trimmed = prompt.trim();
    for (const [opening, closing] of [["“", "”"], ["«", "»"], ["„", "“"]]) {
      if (trimmed.startsWith(opening) && trimmed.endsWith(closing)) {
        trimmed = trimmed.slice(opening.length, -closing.length).trim();
        break;
      }
    }
    if (!trimmed) return trimmed;
    if (/^@(Vera|Lucia|Clara)\b/.test(trimmed)) {
      return trimmed.replace(/^@(Vera|Lucia|Clara)\b/, `@${assistant}`);
    }

    const financialAnalysisOpeners = {
      it: ["Usa Vera per preparare", "Prepara"],
      en: ["Use Vera to prepare", "Prepare"],
      fr: ["Utilise Vera pour préparer", "Prépare"],
      de: [
        "Verwende Vera, um die Finanzanalyse oder Financial Due Diligence für diesen Ordner vorzubereiten.",
        "Bereite die Finanzanalyse oder Financial Due Diligence für diesen Ordner vor.",
      ],
      es: ["Usa Vera para preparar", "Prepara"],
    };
    const [opener, replacement] = financialAnalysisOpeners[currentLanguage];
    const command = trimmed.startsWith(opener)
      ? `${replacement}${trimmed.slice(opener.length)}`
      : trimmed;
    const directCommand = `${command.charAt(0).toLocaleLowerCase(currentLanguage)}${command.slice(1)}`;
    return `@${assistant} ${directCommand}`;
  }

  function renderStartingPrompts(product, currentLanguage) {
    const assistant = assistantNames[product];
    if (!assistant) return;

    document
      .querySelectorAll(
        '#prompt-example, [data-journey="prompt.text"], [data-i18n="example.prompt"], .pf-prompt',
      )
      .forEach((node) => {
        node.textContent = directPrompt(node.textContent, assistant, currentLanguage);
      });
  }

  function neutralizeSharedResearchPage(key, currentLanguage) {
    if (key !== "prompt-optimizer" && key !== "deep-research-validator") return;

    const replacement = sharedFunctionNouns[currentLanguage];
    for (const selector of [
      '[data-i18n="hero.lead"]',
      '[data-i18n="route.prepare.label"]',
      '[data-i18n="workflow.copy"]',
      '[data-i18n="workflow.item2.copy"]',
      '[data-i18n="starter.copy"]',
    ]) {
      const node = document.querySelector(selector);
      if (node) node.textContent = node.textContent.replace(/\bVera\b/g, replacement);
    }

    const title = canonicalNames[key]?.[currentLanguage];
    if (title) {
      document.title = `${title} | Mparanza`;
      document.querySelector('[data-i18n="footer"]')?.replaceChildren(title);
      document.querySelector('meta[property="og:title"]')?.setAttribute("content", document.title);
    }
    for (const selector of ['meta[name="description"]', 'meta[property="og:description"]']) {
      const node = document.querySelector(selector);
      if (node) node.setAttribute("content", node.content.replace(/\bVera\b/g, replacement));
    }
  }

  function renderLiteralHeadings(key, currentLanguage) {
    document.querySelectorAll('[data-journey="overview.title"]').forEach((node) => {
      node.textContent = headingLabels.inputsResult[currentLanguage];
    });
    document.querySelectorAll('[data-journey="workflow.title"]').forEach((node) => {
      node.textContent = headingLabels.steps[currentLanguage];
    });
    document.querySelectorAll('[data-journey="proof.title"]').forEach((node) => {
      node.textContent = headingLabels.video[currentLanguage];
    });
    document.querySelectorAll('[data-journey="prompt.title"]').forEach((node) => {
      node.textContent = headingLabels.startingPrompt[currentLanguage];
    });

    Object.entries(literalHeadingKeys[key] || {}).forEach(([copyKey, labelKey]) => {
      setHeading(`[data-i18n="${copyKey}.title"]`, labelKey, currentLanguage);
    });

    if (key === "concordato-plan-review") {
      setHeading('[data-copy="journey.title"]', "inputsResult", currentLanguage);
      setHeading("#video-proof h2", "video", currentLanguage);
      setHeading('[data-copy="method.title"]', "reviewMethod", currentLanguage);
      setHeading('[data-copy="boundary.title"]', "judgmentChecks", currentLanguage);
      setHeading('[data-copy="outputs.title"]', "outputs", currentLanguage);
      setHeading('[data-copy="start.title"]', "requiredInputs", currentLanguage);
      setHeading('[data-copy="cta.title"]', "relatedFunctions", currentLanguage);
    }

    if (key.startsWith("new-client/")) {
      setHeading("#workflow h2", "steps", currentLanguage);
      setHeading("[data-video-section] h2", "video", currentLanguage);
      setHeading("#outputs h2", "outputFiles", currentLanguage);
    }

    if (key === "journal-bank-reconciliation") {
      setHeading('[data-i18n="hero.eyebrow"]', "accountingCheck", currentLanguage);
    }

    if (key === "check-entries") {
      setHeading('[data-i18n="what.title"]', "fatturaCheck", currentLanguage);
    }

    if (key === "archive-organization") {
      setHeading('[data-i18n="journey.2.title"]', "initialInventory", currentLanguage);
    }

    if (key === "report-builder") {
      setHeading('[data-i18n="preset.title"]', "localAuthorityPreset", currentLanguage);
    }

    if (key === "new-client") {
      setHeading('[data-i18n="relationship.kicker"]', "engagementDetails", currentLanguage);
    }

    if (key === "studio-archive") {
      setHeading('[data-i18n="data.title"]', "processingLocations", currentLanguage);
      setHeading('[data-i18n="archive.originals.title"]', "originalFileLocation", currentLanguage);
      setHeading('[data-i18n="archive.index.title"]', "privateLocalIndex", currentLanguage);
      setHeading('[data-i18n="example.step1.title"]', "localDocumentResult", currentLanguage);
      setHeading('[data-i18n="example.step2.title"]', "gmailResult", currentLanguage);
      setHeading('[data-i18n="example.step3.title"]', "whatsappResult", currentLanguage);
    }

    if (key === "prompt-optimizer" || key === "deep-research-validator") {
      setHeading('[data-i18n="nav.workflow"]', "steps", currentLanguage);
      setHeading('[data-i18n="nav.proof"]', "result", currentLanguage);
      setHeading('[data-i18n="nav.starter"]', "startingPrompt", currentLanguage);
      setHeading('[data-i18n="nav.details"]', "details", currentLanguage);
    }

    if (key === "financial-analysis" || key === "sales-plan") {
      setHeading('[data-i18n="nav.method"]', "method", currentLanguage);
    }

    if (key === "studio-archive") {
      setHeading('[data-i18n="nav.archive"]', "setup", currentLanguage);
      setHeading('[data-i18n="nav.method"]', "searchMethod", currentLanguage);
      setHeading('[data-i18n="nav.sources"]', "sources", currentLanguage);
      setHeading('[data-i18n="nav.example"]', "example", currentLanguage);
      setHeading('[data-i18n="nav.data"]', "dataHandling", currentLanguage);
    }

    if (key === "new-client") {
      setHeading('[data-i18n="nav.journey"]', "steps", currentLanguage);
      setHeading('[data-i18n="nav.prepare"]', "initialFileReview", currentLanguage);
      setHeading('[data-i18n="nav.relationship"]', "engagementFile", currentLanguage);
      setHeading('[data-i18n="nav.proof"]', "result", currentLanguage);
      setFactualCopy('[data-i18n="journey.kicker"]', "fileSteps", currentLanguage);
      setFactualCopy('[data-i18n="journey.copy"]', "fileStepsCopy", currentLanguage);
      setFactualCopy('[data-i18n="hero.primary"]', "viewSteps", currentLanguage);
      setFactualCopy('[data-i18n="hero.secondary"]', "italyDocuments", currentLanguage);
    }

    if (key.startsWith("new-client/")) {
      setHeading('a[href="#workflow"]', "steps", currentLanguage);
      setHeading('a[href="#outputs"]', "outputs", currentLanguage);
      setHeading('a[href="#download"]', "openCodex", currentLanguage);
    }

    if (key === "previdenza-inps") {
      setFactualCopy('[data-i18n="journey.copy"]', "socialSecurityCopy", currentLanguage);
    }

    if (key === "registro-imprese-sari") {
      setFactualCopy('[data-i18n="journey.copy"]', "registerCopy", currentLanguage);
    }
  }

  function render() {
    const key = pageKey();
    const context = selectedContext(key);
    const main = document.querySelector("main");
    if (!context || !main) return;

    const currentLanguage = language();
    const [product, area] = context;
    renderStartingPrompts(product, currentLanguage);
    const existing = document.querySelector(
      ".function-breadcrumb, .pf-breadcrumb, .journey-breadcrumb, main > .breadcrumb, .page > .breadcrumb, body > .breadcrumb",
    );
    const functionName = currentName(existing, key, currentLanguage);
    if (!functionName) return;

    const canonical = canonicalNames[key]?.[currentLanguage];
    const heading = document.querySelector("main h1");
    if (canonical && heading) heading.textContent = canonical;
    renderLiteralHeadings(key, currentLanguage);
    neutralizeSharedResearchPage(key, currentLanguage);

    const breadcrumb = document.createElement("nav");
    breadcrumb.className = "function-breadcrumb";
    breadcrumb.setAttribute("aria-label", ariaLabels[currentLanguage]);

    const areaLink = document.createElement("a");
    areaLink.href = `../${product}/index.html?lang=${currentLanguage}#${area}`;
    areaLink.textContent = areaLabels[product][area][currentLanguage];

    const separator = document.createElement("span");
    separator.setAttribute("aria-hidden", "true");
    separator.textContent = "/";

    const current = document.createElement("strong");
    current.setAttribute("aria-current", "page");
    current.textContent = functionName;

    breadcrumb.append(areaLink, separator, current);
    existing?.remove();
    main.parentNode.insertBefore(breadcrumb, main);
  }

  window.MPARANZA_FUNCTION_NAVIGATION = { directPrompt, render };
  render();
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", render, { once: true });
  }
  document.querySelectorAll("[data-lang], [data-language]").forEach((control) => {
    if (control.dataset.functionNavigationBound === "true") return;
    control.dataset.functionNavigationBound = "true";
    control.addEventListener("click", () => window.setTimeout(render, 0));
  });
})();
