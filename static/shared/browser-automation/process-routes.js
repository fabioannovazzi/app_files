(() => {
  "use strict";

  const routes = {
    it: {
      summary: "Esegue processi web implementati per TeamSystem ECONS e Agenzia delle Entrate, oppure acquisisce un nuovo processo da sviluppare e validare.",
      useWhen: "Per il lavoro quotidiano, chiedi direttamente l'operazione. Per una nuova automazione, chiedi di imparare il processo o di prepararlo per lo sviluppatore.",
      input: "Una sessione Google Chrome collegata a Codex Desktop, il cliente e il lavoro autorizzato. Esegui personalmente l'accesso e la scelta del profilo o dell'azienda.",
      work: "Vera usa il tuo Chrome collegato, conserva la scheda nelle pause e verifica gli esiti. Un passaggio che richiede una finestra del sistema operativo viene affidato all'operatore.",
      output: "Report locali con risultati, eccezioni e passaggi incompleti; per lo sviluppo, evidenze salvate e un pacchetto da revisionare.",
      useTitle: "Usare un processo esistente", developTitle: "Sviluppare un nuovo processo",
      useIntro: "Indica cliente, operazione e periodo o popolazione da elaborare. Vera riusa la procedura implementata e la configurazione locale disponibile; completa i collegamenti mancanti dalla schermata corrente.",
      econs: "Per registrare fatture passive, Vera esamina descrizioni complete, conti, codici IVA e trattamento del cliente, propone o completa le associazioni e verifica il giornale. La registrazione richiede conferma finale, protocollo e assenza dalla coda Non contab. Il report comprende esiti ed eccezioni. Puoi anche chiedere soltanto una revisione senza registrare.",
      econsLimits: "Il supporto è implementato; la validazione sul gestionale di destinazione richiede ancora due esecuzioni pulite. Una configurazione salvata non prova la compatibilità con ogni cliente o schermata.",
      econsPrompt: "@Vera registra le fatture passive non contabilizzate di [cliente] in TeamSystem ECONS e prepara il report con esiti ed eccezioni.",
      agenzia: "Vera verifica periodo, categorie e conteggi osservati, scarica le fatture e archivia per anno e categoria. Conserva gli originali XML o P7M, estrae l'XML dal P7M collegandolo con hash e riconcilia pagine e totale. La ripresa verifica lo stato e i file già conservati prima di proseguire.",
      agenziaLimits: "L'acquisizione resta un prototipo fino alla validazione sul portale di destinazione. La stampa in PDF è un passaggio dell'operatore; Vera verifica il file salvato. L'estrazione P7M non verifica la firma digitale. Formati indisponibili e differenze di conteggio sono riportati.",
      agenziaPrompt: "@Vera scarica dall'Agenzia delle Entrate le fatture emesse e ricevute di [cliente] per il [anno], conserva gli originali e verifica i conteggi.",
      developIntro: "Usa questa parte quando il processo deve essere appreso, adattato o preparato per uno sviluppatore che non può accedere al sito.",
      developItem: "Dimostrazione, sviluppo e validazione",
      develop: "Puoi mostrare il percorso, lasciare che Vera esplori passaggi sicuri o combinare i due metodi. Vera avvia un checkpoint locale, salva decisioni, rami, prove e passaggi mancanti e produce un report anche nelle pause. Prepara poi un developer pack sanitizzato, cioè un pacchetto di evidenze da revisionare prima del trasferimento. L'implementazione della capability, la procedura eseguibile, richiede un'approvazione distinta.",
      developLimits: "Una dimostrazione o un pacchetto non sono un'automazione validata. Servono due replay puliti sul sistema di destinazione; recuperi di selettori e interventi fuori dal browser non valgono come replay puliti. Credenziali e sessione Chrome non vengono trasferite.",
      developPrompt: "@Vera impara questo processo nel mio Chrome: ti mostro il percorso e ti spiego le decisioni. Salva i passaggi e le eccezioni e prepara il materiale da revisionare per lo sviluppatore.",
      useData: "Uso — TeamSystem ECONS: il modello può leggere identità autorizzate di azienda, fattura e fornitore, stato della fattura, descrizioni complete, conti, codici IVA, importi, pro rata, giornali proposti o visualizzati, protocollo, decisioni ed eccezioni. Legge anche la configurazione locale selezionata, incluse esclusioni, collegamenti alle schermate e note incomplete. I valori non sono anonimizzati automaticamente. Report e configurazione restano locali, ma l'elaborazione del modello non è solo locale; questi dati non entrano nel developer pack.",
      discoveryLabel: "Sviluppo — discovery e trasferimento del pacchetto:"
    },
    en: {
      summary: "Runs implemented web processes for TeamSystem ECONS and Agenzia delle Entrate, or captures a new process to develop and validate.",
      useWhen: "For everyday work, request the operation directly. For a new automation, ask Vera to learn the process or prepare it for a developer.",
      input: "A Google Chrome session connected to Codex Desktop, the client and authorized task. Personally complete login and select the profile or company.",
      work: "Vera uses your connected Chrome, preserves the task tab during pauses and checks outcomes. Steps requiring an operating-system window are handed to the operator.",
      output: "Local reports with results, exceptions and incomplete steps; for development, saved evidence and a package to review.",
      useTitle: "Use an existing process", developTitle: "Develop a new process",
      useIntro: "Specify the client, operation and period or invoice population. Vera reuses the implemented procedure and available local setup, completing missing screen bindings from the current screen.",
      econs: "To register purchase invoices, Vera reviews complete descriptions, accounts, VAT codes and client-specific treatment, proposes or completes mappings and checks the journal. Registration requires final confirmation, a protocol and absence from the unposted queue. The report includes outcomes and exceptions. You can also request review without posting.",
      econsLimits: "Support is implemented; validation on the target management system still requires two clean runs. Saved setup does not establish compatibility with every client or screen.",
      econsPrompt: "@Vera register the unposted purchase invoices for [client] in TeamSystem ECONS and prepare the report with outcomes and exceptions.",
      agenzia: "Vera checks the period, categories and observed counts, downloads invoices and archives by year and category. It preserves XML or P7M originals, extracts XML from P7M with a hash binding and reconciles pages and totals. Resume verifies retained state and files before continuing.",
      agenziaLimits: "Acquisition remains a prototype until target-portal validation. Printing to PDF is an operator step; Vera checks the saved file. P7M extraction does not validate the digital signature. Unavailable formats and count differences are reported.",
      agenziaPrompt: "@Vera download the issued and received invoices for [client] for [year] from Agenzia delle Entrate, preserve the originals and reconcile the counts.",
      developIntro: "Use this section when a process needs to be learned, adapted or prepared for a developer who cannot access the site.",
      developItem: "Demonstration, development and validation",
      develop: "Demonstrate the route, let Vera explore safe steps, or combine both. Vera starts a local checkpoint, saves decisions, branches, evidence and gaps, and produces a report even when paused. It then prepares a sanitized developer pack: evidence reviewed before transfer. Implementing the capability, the executable procedure, requires separate approval.",
      developLimits: "A demonstration or package is not a validated automation. Two clean replays on the target system are required; selector recovery and steps outside the browser do not count as clean replays. Credentials and the Chrome session are never transferred.",
      developPrompt: "@Vera learn this process in my Chrome: I will demonstrate the route and explain the decisions. Save the steps and exceptions and prepare material for developer review.",
      useData: "Use — TeamSystem ECONS: the model can read authorized company, invoice and supplier identities, invoice state, complete descriptions, accounts, VAT codes, amounts, pro rata, proposed or displayed journals, registration protocol, decisions and exceptions. It also reads the selected local setup, including exclusions, screen bindings and incomplete notes. Values are not automatically anonymized. Reports and setup stay local, but model processing is not local-only; these data do not enter the developer pack.",
      discoveryLabel: "Development — discovery and package transfer:"
    },
    fr: {
      summary: "Exécute les processus web implémentés pour TeamSystem ECONS et Agenzia delle Entrate, ou recueille un nouveau processus à développer et valider.",
      useWhen: "Pour le travail quotidien, demandez directement l'opération. Pour une nouvelle automatisation, demandez à Vera d'apprendre le processus ou de le préparer pour un développeur.",
      input: "Une session Google Chrome connectée à Codex Desktop, le client et le travail autorisé. Effectuez personnellement la connexion et le choix du profil ou de l'entreprise.",
      work: "Vera utilise votre Chrome connecté, conserve l'onglet pendant les pauses et vérifie les résultats. Les étapes nécessitant une fenêtre du système sont confiées à l'opérateur.",
      output: "Rapports locaux avec résultats, exceptions et étapes incomplètes ; pour le développement, preuves sauvegardées et paquet à réviser.",
      useTitle: "Utiliser un processus existant", developTitle: "Développer un nouveau processus",
      useIntro: "Précisez le client, l'opération et la période ou population de factures. Vera réutilise la procédure implémentée et la configuration locale disponible, puis complète les liens manquants depuis l'écran actuel.",
      econs: "Pour comptabiliser les factures d'achat, Vera examine descriptions complètes, comptes, codes TVA et traitement du client, propose ou complète les correspondances et vérifie le journal. L'enregistrement exige confirmation finale, protocole et absence de la file Non contab. Le rapport comprend résultats et exceptions. Une révision sans comptabilisation peut aussi être demandée.",
      econsLimits: "Le support est implémenté ; la validation sur le logiciel cible exige encore deux exécutions propres. Une configuration sauvegardée ne prouve pas la compatibilité avec chaque client ou écran.",
      econsPrompt: "@Vera comptabilise les factures d'achat non comptabilisées de [client] dans TeamSystem ECONS et prépare le rapport avec résultats et exceptions.",
      agenzia: "Vera vérifie période, catégories et nombres observés, télécharge les factures et les archive par année et catégorie. Elle conserve les originaux XML ou P7M, extrait le XML du P7M avec une liaison par empreinte et rapproche pages et total. La reprise vérifie l'état et les fichiers conservés avant de continuer.",
      agenziaLimits: "L'acquisition reste un prototype jusqu'à la validation sur le portail cible. L'impression PDF appartient à l'opérateur ; Vera vérifie le fichier sauvegardé. L'extraction P7M ne valide pas la signature numérique. Formats indisponibles et écarts de nombre sont signalés.",
      agenziaPrompt: "@Vera télécharge les factures émises et reçues de [client] pour [année] depuis Agenzia delle Entrate, conserve les originaux et rapproche les nombres.",
      developIntro: "Utilisez cette partie pour apprendre, adapter ou préparer un processus pour un développeur sans accès au site.",
      developItem: "Démonstration, développement et validation",
      develop: "Montrez le parcours, laissez Vera explorer les étapes sûres ou combinez les deux. Vera crée un checkpoint local, sauvegarde décisions, branches, preuves et lacunes, et produit un rapport même en pause. Elle prépare ensuite un developer pack assaini, un paquet de preuves à réviser avant transfert. L'implémentation de la capability, la procédure exécutable, exige une approbation distincte.",
      developLimits: "Une démonstration ou un paquet ne constitue pas une automatisation validée. Deux répétitions propres sur le système cible sont requises ; récupération de sélecteurs et étapes hors navigateur ne comptent pas. Identifiants et session Chrome ne sont jamais transférés.",
      developPrompt: "@Vera apprends ce processus dans mon Chrome : je montre le parcours et explique les décisions. Sauvegarde les étapes et exceptions et prépare le matériel à réviser pour le développeur.",
      useData: "Utilisation — TeamSystem ECONS : le modèle peut lire les identités autorisées d'entreprise, facture et fournisseur, état, descriptions complètes, comptes, codes TVA, montants, prorata, journaux proposés ou affichés, protocole, décisions et exceptions. Il lit aussi la configuration locale sélectionnée, exclusions, liens aux écrans et notes incomplètes. Les valeurs ne sont pas automatiquement anonymisées. Rapports et configuration restent locaux, mais le traitement du modèle n'est pas uniquement local ; ces données n'entrent pas dans le developer pack.",
      discoveryLabel: "Développement — découverte et transfert du paquet :"
    },
    de: {
      summary: "Führt implementierte Webprozesse für TeamSystem ECONS und Agenzia delle Entrate aus oder erfasst einen neuen Prozess zur Entwicklung und Validierung.",
      useWhen: "Fordern Sie für die tägliche Arbeit direkt den Vorgang an. Für eine neue Automatisierung bitten Sie Vera, den Prozess zu lernen oder für einen Entwickler vorzubereiten.",
      input: "Eine mit Codex Desktop verbundene Google-Chrome-Sitzung, den Mandanten und den autorisierten Auftrag. Anmeldung und Profil- oder Unternehmensauswahl erfolgen persönlich.",
      work: "Vera verwendet Ihren verbundenen Chrome, bewahrt den Tab bei Pausen und prüft Ergebnisse. Schritte mit Betriebssystemfenstern werden dem Bediener übergeben.",
      output: "Lokale Berichte mit Ergebnissen, Ausnahmen und offenen Schritten; bei Entwicklung gespeicherte Nachweise und ein Paket zur Prüfung.",
      useTitle: "Einen bestehenden Prozess verwenden", developTitle: "Einen neuen Prozess entwickeln",
      useIntro: "Nennen Sie Mandant, Vorgang und Zeitraum oder Rechnungspopulation. Vera verwendet die implementierte Anleitung und vorhandene lokale Einrichtung und ergänzt fehlende Bildschirmbindungen am aktuellen Bildschirm.",
      econs: "Zur Buchung von Eingangsrechnungen prüft Vera vollständige Beschreibungen, Konten, Umsatzsteuercodes und die Behandlung des Mandanten, schlägt Zuordnungen vor oder ergänzt sie und prüft das Journal. Die Buchung erfordert abschließende Bestätigung, Protokoll und Abwesenheit in Non contab. Der Bericht enthält Ergebnisse und Ausnahmen. Eine Prüfung ohne Buchung ist ebenfalls möglich.",
      econsLimits: "Die Unterstützung ist implementiert; die Validierung im Zielsystem erfordert noch zwei saubere Läufe. Gespeicherte Einrichtung belegt keine Kompatibilität mit jedem Mandanten oder Bildschirm.",
      econsPrompt: "@Vera buche die ungebuchten Eingangsrechnungen von [Mandant] in TeamSystem ECONS und erstelle den Bericht mit Ergebnissen und Ausnahmen.",
      agenzia: "Vera prüft Zeitraum, Kategorien und beobachtete Anzahlen, lädt Rechnungen herunter und archiviert nach Jahr und Kategorie. XML- oder P7M-Originale bleiben erhalten; XML wird mit Hash-Verknüpfung aus P7M extrahiert. Seiten und Gesamtzahl werden abgeglichen. Vor der Fortsetzung werden gespeicherter Zustand und Dateien geprüft.",
      agenziaLimits: "Die Erfassung bleibt bis zur Validierung im Zielportal ein Prototyp. PDF-Druck ist ein Bedienerschritt; Vera prüft die gespeicherte Datei. P7M-Extraktion validiert keine digitale Signatur. Fehlende Formate und Anzahlabweichungen werden gemeldet.",
      agenziaPrompt: "@Vera lade die ausgestellten und empfangenen Rechnungen von [Mandant] für [Jahr] aus Agenzia delle Entrate herunter, bewahre Originale auf und gleiche die Anzahlen ab.",
      developIntro: "Verwenden Sie diesen Teil, um einen Prozess zu lernen, anzupassen oder für einen Entwickler ohne Websitezugang vorzubereiten.",
      developItem: "Demonstration, Entwicklung und Validierung",
      develop: "Zeigen Sie den Ablauf, lassen Sie Vera sichere Schritte erkunden oder kombinieren Sie beides. Vera startet einen lokalen Checkpoint, speichert Entscheidungen, Zweige, Nachweise und Lücken und erstellt auch bei Pausen einen Bericht. Danach entsteht ein bereinigtes Entwicklerpaket zur Prüfung vor der Übertragung. Die Implementierung der Capability, der ausführbaren Anleitung, erfordert eine eigene Freigabe.",
      developLimits: "Eine Demonstration oder ein Paket ist keine validierte Automatisierung. Zwei saubere Wiederholungen im Zielsystem sind erforderlich; Selektorwiederherstellung und Schritte außerhalb des Browsers zählen nicht. Zugangsdaten und Chrome-Sitzung werden nie übertragen.",
      developPrompt: "@Vera lerne diesen Prozess in meinem Chrome: Ich zeige den Ablauf und erkläre die Entscheidungen. Speichere Schritte und Ausnahmen und bereite das Material zur Entwicklerprüfung vor.",
      useData: "Nutzung — TeamSystem ECONS: Das Modell kann autorisierte Unternehmens-, Rechnungs- und Lieferantenidentitäten, Rechnungsstatus, vollständige Beschreibungen, Konten, Umsatzsteuercodes, Beträge, Pro-rata, vorgeschlagene oder angezeigte Journale, Protokoll, Entscheidungen und Ausnahmen lesen. Es liest auch die gewählte lokale Einrichtung mit Ausschlüssen, Bildschirmbindungen und offenen Notizen. Werte werden nicht automatisch anonymisiert. Berichte und Einrichtung bleiben lokal, die Modellverarbeitung ist jedoch nicht ausschließlich lokal; diese Daten gelangen nicht in das Entwicklerpaket.",
      discoveryLabel: "Entwicklung — Erkundung und Paketübertragung:"
    },
    es: {
      summary: "Ejecuta procesos web implementados para TeamSystem ECONS y Agenzia delle Entrate, o recoge un nuevo proceso para desarrollar y validar.",
      useWhen: "Para el trabajo diario, solicita directamente la operación. Para una nueva automatización, pide a Vera aprender el proceso o prepararlo para un desarrollador.",
      input: "Una sesión Google Chrome conectada a Codex Desktop, el cliente y el trabajo autorizado. Realiza personalmente el acceso y la selección del perfil o empresa.",
      work: "Vera usa tu Chrome conectado, conserva la pestaña durante las pausas y verifica resultados. Los pasos que requieren ventanas del sistema se entregan al operador.",
      output: "Informes locales con resultados, excepciones y pasos incompletos; para desarrollo, evidencias guardadas y un paquete para revisar.",
      useTitle: "Usar un proceso existente", developTitle: "Desarrollar un nuevo proceso",
      useIntro: "Indica cliente, operación y periodo o población de facturas. Vera reutiliza el procedimiento implementado y la configuración local disponible y completa vínculos faltantes desde la pantalla actual.",
      econs: "Para contabilizar facturas de compra, Vera revisa descripciones completas, cuentas, códigos IVA y tratamiento del cliente, propone o completa correspondencias y verifica el diario. El registro requiere confirmación final, protocolo y ausencia de Non contab. El informe incluye resultados y excepciones. También puedes pedir una revisión sin contabilizar.",
      econsLimits: "El soporte está implementado; la validación en el sistema destino aún requiere dos ejecuciones limpias. Una configuración guardada no demuestra compatibilidad con cada cliente o pantalla.",
      econsPrompt: "@Vera contabiliza las facturas de compra no contabilizadas de [cliente] en TeamSystem ECONS y prepara el informe con resultados y excepciones.",
      agenzia: "Vera comprueba periodo, categorías y recuentos observados, descarga facturas y archiva por año y categoría. Conserva originales XML o P7M, extrae XML del P7M con un vínculo de hash y concilia páginas y total. Al reanudar verifica estado y archivos conservados antes de continuar.",
      agenziaLimits: "La adquisición sigue siendo un prototipo hasta la validación en el portal destino. La impresión PDF corresponde al operador; Vera verifica el archivo guardado. La extracción P7M no valida la firma digital. Se informan formatos no disponibles y diferencias de recuento.",
      agenziaPrompt: "@Vera descarga de Agenzia delle Entrate las facturas emitidas y recibidas de [cliente] para [año], conserva los originales y concilia los recuentos.",
      developIntro: "Usa esta parte para aprender, adaptar o preparar un proceso para un desarrollador sin acceso al sitio.",
      developItem: "Demostración, desarrollo y validación",
      develop: "Muestra el recorrido, deja que Vera explore pasos seguros o combina ambos. Vera inicia un checkpoint local, guarda decisiones, ramas, pruebas y lagunas y produce un informe incluso al pausar. Después prepara un developer pack saneado, evidencias para revisar antes de transferir. Implementar la capability, el procedimiento ejecutable, requiere una aprobación separada.",
      developLimits: "Una demostración o paquete no es una automatización validada. Se requieren dos repeticiones limpias en el sistema destino; recuperación de selectores y pasos fuera del navegador no cuentan. Credenciales y sesión Chrome nunca se transfieren.",
      developPrompt: "@Vera aprende este proceso en mi Chrome: mostraré el recorrido y explicaré las decisiones. Guarda pasos y excepciones y prepara el material para revisión del desarrollador.",
      useData: "Uso — TeamSystem ECONS: el modelo puede leer identidades autorizadas de empresa, factura y proveedor, estado, descripciones completas, cuentas, códigos IVA, importes, prorrata, diarios propuestos o mostrados, protocolo, decisiones y excepciones. También lee la configuración local seleccionada, exclusiones, vínculos de pantalla y notas incompletas. Los valores no se anonimizan automáticamente. Informes y configuración quedan locales, pero el procesamiento del modelo no es solo local; estos datos no entran en el developer pack.",
      discoveryLabel: "Desarrollo — descubrimiento y transferencia del paquete:"
    }
  };

  Object.entries(routes).forEach(([language, route]) => {
    const page = window.MPARANZA_FUNCTION_PAGES["browser-automation"].copy[language];
    for (const key of ["summary", "useWhen", "input", "work", "output"]) page[key] = route[key];
    page.processSections = [
      { id: "use", label: "01", title: route.useTitle, intro: route.useIntro, items: [
        { title: "TeamSystem ECONS", copy: route.econs, limits: route.econsLimits, prompt: route.econsPrompt },
        { title: "Agenzia delle Entrate", copy: route.agenzia, limits: route.agenziaLimits, prompt: route.agenziaPrompt }
      ] },
      { id: "develop", label: "02", title: route.developTitle, intro: route.developIntro, items: [
        { title: route.developItem, copy: route.develop, limits: route.developLimits, prompt: route.developPrompt }
      ] }
    ];
    page.modelData = route.useData + "\n\n" + route.discoveryLabel + "\n\n" + page.modelData;
  });
})();
