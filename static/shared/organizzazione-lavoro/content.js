window.MPARANZA_FUNCTION_PAGES = {
  "organizzazione-lavoro": {
    "product": "Vera",
    "defaultLanguage": "it",
    "copy": {
      "it": {
        "name": "Organizzazione del lavoro di studio",
        "summary": "Conserva appuntamenti, attività, scadenze, deleghe e azioni delle riunioni. Usa il calendario collegato per le operazioni richieste e ne verifica il risultato.",
        "useWhen": "Per registrare un impegno con una frase, pianificare la giornata o ritrovare ciò che è ancora aperto in una nuova conversazione.",
        "input": "Richieste scritte o trascritte dalla voce, appunti delle riunioni, calendario scelto, orari di lavoro, durate e preferenze dello studio. La voce richiede gli strumenti della sessione Codex.",
        "work": "Interpreta gli impegni, chiede i dettagli essenziali mancanti e conserva fonte, responsabile, data e stato. Controlla disponibilità e carico di lavoro. Registra ogni operazione sul calendario prima di eseguirla e controlla il risultato; dopo una interruzione verifica prima di ripetere.",
        "output": "Registro persistente, riepiloghi delle riunioni con azioni successive, piano giornaliero e risultati delle operazioni sul calendario. Attese, deleghe e operazioni con esito incerto restano visibili.",
        "responsibilityIntro": "Il registro locale richiede esecuzione in Codex o Cowork e un ambiente Vera configurato. Collegamenti e permessi si verificano nella sessione effettiva.",
        "productRole": "Propone priorità e spazi disponibili; esegue le modifiche autorizzate. Una richiesta di riepilogo non modifica il calendario. I briefing ricorrenti richiedono una automazione del sistema ospite configurata e verificata: non è presente un ascolto continuo di email, Discord o WhatsApp.",
        "professionalRole": "Sceglie calendario e preferenze, chiarisce impegni ambigui e comunica completamenti e variazioni. Scadenze legali, rassegna professionale, insoluti e tesoreria seguono i rispettivi workflow specialistici.",
        "prompt": "Organizzami la giornata: leggi il calendario e gli impegni aperti, proponi le priorità e segnala le informazioni mancanti.",
        "modelData": "Il modello riceve richieste scritte o trascritte dalla voce, preferenze, impegni selezionati, riepiloghi recenti delle riunioni e risposte dei connettori: possono includere nomi, clienti, incarichi, note e date. Non vengono anonimizzati automaticamente. Il servizio locale conserva registro, cronologia e ricevute in SQLite, fuori dalle versioni del plugin; non conserva audio grezzo e non effettua chiamate di rete. Il connettore invia i campi degli eventi al calendario scelto quando viene eseguita una operazione autorizzata. Registrazione e trascrizione vocale appartengono al sistema ospite. Il trattamento del modello segue l’account del provider scelto e non è soltanto locale.",
        "modelDataStatus": "relevant"
      },
      "en": {
        "name": "Studio work organisation",
        "summary": "Retains appointments, tasks, deadlines, delegations and meeting actions. Uses the connected calendar for requested operations and checks their outcome.",
        "useWhen": "To capture a commitment in a sentence, plan the day or retrieve unfinished work in a new conversation.",
        "input": "Typed or voice-transcribed requests, meeting notes, selected calendar, working hours, durations and studio preferences. Voice requires the tools available in the Codex session.",
        "work": "Interprets commitments, asks for essential missing details and retains source, owner, date and status. Checks availability and workload. Records calendar intent before execution and reads back the result; interrupted operations require recovery before another attempt.",
        "output": "A persistent register, meeting summaries with follow-up actions, daily plans and calendar operation results. Waiting items, delegations and uncertain operations remain visible.",
        "responsibilityIntro": "The local register requires execution in Codex or Cowork and a configured Vera environment. Connections and permissions must be checked in the actual session.",
        "productRole": "Proposes priorities and available slots; executes authorised changes. A briefing request does not change the calendar. Recurring briefings require configured and verified host automation; there is no continuous email, Discord or WhatsApp listener.",
        "professionalRole": "Selects the calendar and preferences, clarifies ambiguous commitments and reports completion and changes. Legal deadlines, professional news, open items and treasury follow their specialist workflows.",
        "prompt": "Plan my day: read the calendar and open commitments, propose priorities and identify missing information.",
        "modelData": "The model receives typed or transcribed requests, preferences, selected commitments, recent meeting summaries and connector responses, potentially including names, clients, engagements, notes and dates. These are not automatically anonymised. The local service retains the register, history and receipts in SQLite outside plugin versions; it stores no raw audio and makes no network calls. The connector sends event fields to the selected calendar when an authorised operation runs. Voice recording and transcription belong to the host. Model processing follows the selected provider account and is not local only.",
        "modelDataStatus": "relevant"
      },
      "fr": {
        "name": "Organisation du travail du cabinet",
        "summary": "Conserve les rendez-vous, tâches, échéances, délégations et actions issues des réunions. Utilise le calendrier connecté pour les opérations demandées et vérifie leur résultat.",
        "useWhen": "Pour noter un engagement en une phrase, préparer la journée ou retrouver le travail ouvert dans une nouvelle conversation.",
        "input": "Demandes écrites ou transcrites depuis la voix, notes de réunion, calendrier choisi, horaires, durées et préférences du cabinet. La voix dépend des outils de la session Codex.",
        "work": "Interprète les engagements, demande les précisions essentielles et conserve source, responsable, date et état. Vérifie disponibilité et charge. Enregistre chaque intention avant la modification du calendrier, puis vérifie le résultat ; une interruption impose une vérification avant toute nouvelle tentative.",
        "output": "Registre persistant, comptes rendus avec actions de suivi, plan de journée et résultats des opérations. Attentes, délégations et opérations incertaines restent visibles.",
        "responsibilityIntro": "Le registre local nécessite une exécution dans Codex ou Cowork et un environnement Vera configuré. Connexions et permissions se vérifient dans la session réelle.",
        "productRole": "Propose priorités et créneaux ; exécute les changements autorisés. Un récapitulatif ne modifie pas le calendrier. Les briefings récurrents nécessitent une automatisation du système hôte configurée et vérifiée ; aucune écoute permanente des emails, de Discord ou de WhatsApp n’est fournie.",
        "professionalRole": "Choisit calendrier et préférences, précise les engagements ambigus et signale les réalisations et changements. Échéances légales, actualités professionnelles, impayés et trésorerie suivent leurs workflows spécialisés.",
        "prompt": "Organise ma journée : consulte le calendrier et les engagements ouverts, propose les priorités et signale les informations manquantes.",
        "modelData": "Le modèle reçoit demandes écrites ou transcrites, préférences, engagements sélectionnés, comptes rendus récents et réponses des connecteurs, pouvant inclure noms, clients, missions, notes et dates. Il n’y a pas d’anonymisation automatique. Le service local conserve registre, historique et reçus dans SQLite, indépendamment des versions du plugin ; il ne stocke aucun audio brut et ne fait aucun appel réseau. Le connecteur envoie les champs des événements au calendrier choisi lors d’une opération autorisée. Enregistrement et transcription vocale relèvent du système hôte. Le traitement du modèle suit le compte du fournisseur choisi et n’est pas uniquement local.",
        "modelDataStatus": "relevant"
      },
      "de": {
        "name": "Organisation der Kanzleiarbeit",
        "summary": "Speichert Termine, Aufgaben, Fristen, Delegationen und Besprechungsaktionen. Verwendet den verbundenen Kalender für angeforderte Vorgänge und prüft deren Ergebnis.",
        "useWhen": "Um eine Verpflichtung in einem Satz festzuhalten, den Tag zu planen oder offene Arbeit in einem neuen Gespräch wiederzufinden.",
        "input": "Geschriebene oder aus Sprache transkribierte Anfragen, Besprechungsnotizen, ausgewählter Kalender, Arbeitszeiten, Zeitbedarf und Kanzleipräferenzen. Sprache setzt die Werkzeuge der Codex-Sitzung voraus.",
        "work": "Interpretiert Verpflichtungen, fragt wesentliche fehlende Angaben ab und speichert Quelle, Verantwortliche, Datum und Status. Prüft Verfügbarkeit und Arbeitslast. Hält den Kalenderauftrag vor der Ausführung fest und prüft danach das Ergebnis; Unterbrechungen erfordern eine Prüfung vor einem weiteren Versuch.",
        "output": "Dauerhaftes Register, Besprechungszusammenfassungen mit Folgeaufgaben, Tagespläne und Kalenderergebnisse. Wartende, delegierte und unklare Vorgänge bleiben sichtbar.",
        "responsibilityIntro": "Das lokale Register benötigt Ausführung in Codex oder Cowork sowie eine konfigurierte Vera-Umgebung. Verbindungen und Berechtigungen werden in der tatsächlichen Sitzung geprüft.",
        "productRole": "Schlägt Prioritäten und freie Zeiten vor; führt autorisierte Änderungen aus. Eine Tagesübersicht verändert den Kalender nicht. Wiederkehrende Briefings benötigen eine konfigurierte und geprüfte Automatisierung des Hostsystems; keine dauerhafte Überwachung von E-Mail, Discord oder WhatsApp.",
        "professionalRole": "Wählt Kalender und Präferenzen, klärt mehrdeutige Verpflichtungen und meldet Erledigungen und Änderungen. Rechtliche Fristen, Fachnachrichten, offene Posten und Liquidität folgen eigenen Fachworkflows.",
        "prompt": "Plane meinen Tag: prüfe Kalender und offene Verpflichtungen, schlage Prioritäten vor und benenne fehlende Informationen.",
        "modelData": "Das Modell erhält geschriebene oder transkribierte Anfragen, Präferenzen, ausgewählte Verpflichtungen, aktuelle Besprechungszusammenfassungen und Connector-Antworten. Darin können Namen, Mandanten, Mandate, Notizen und Daten enthalten sein; sie werden nicht automatisch anonymisiert. Der lokale Dienst speichert Register, Verlauf und Belege in SQLite außerhalb der Plugin-Versionen; er speichert kein Rohaudio und sendet keine Netzwerkanfragen. Der Connector übermittelt Ereignisfelder bei autorisierten Vorgängen an den gewählten Kalender. Sprachaufnahme und Transkription gehören zum Hostsystem. Die Modellverarbeitung folgt dem ausgewählten Anbieterkonto und erfolgt nicht ausschließlich lokal.",
        "modelDataStatus": "relevant"
      },
      "es": {
        "name": "Organización del trabajo del despacho",
        "summary": "Conserva citas, tareas, plazos, delegaciones y acciones de reuniones. Usa el calendario conectado para las operaciones solicitadas y verifica el resultado.",
        "useWhen": "Para registrar un compromiso con una frase, planificar el día o recuperar trabajo abierto en una nueva conversación.",
        "input": "Solicitudes escritas o transcritas desde la voz, notas de reuniones, calendario elegido, horarios, duraciones y preferencias del despacho. La voz requiere las herramientas de la sesión Codex.",
        "work": "Interpreta compromisos, pide los detalles esenciales que faltan y conserva fuente, responsable, fecha y estado. Comprueba disponibilidad y carga. Registra la intención antes de modificar el calendario y verifica después el resultado; una interrupción exige recuperación antes de repetir.",
        "output": "Registro persistente, resúmenes de reuniones con acciones posteriores, plan diario y resultados del calendario. Esperas, delegaciones y operaciones inciertas permanecen visibles.",
        "responsibilityIntro": "El registro local requiere ejecución en Codex o Cowork y un entorno Vera configurado. Conexiones y permisos se verifican en la sesión real.",
        "productRole": "Propone prioridades y huecos disponibles; ejecuta cambios autorizados. Un resumen no modifica el calendario. Los informes recurrentes requieren una automatización del sistema anfitrión configurada y verificada; no hay escucha continua de correo, Discord o WhatsApp.",
        "professionalRole": "Elige calendario y preferencias, aclara compromisos ambiguos y comunica finalizaciones y cambios. Plazos legales, novedades profesionales, partidas abiertas y tesorería siguen sus workflows especializados.",
        "prompt": "Organiza mi día: consulta el calendario y los compromisos abiertos, propone prioridades e indica la información que falta.",
        "modelData": "El modelo recibe solicitudes escritas o transcritas, preferencias, compromisos seleccionados, resúmenes recientes y respuestas de conectores, que pueden incluir nombres, clientes, encargos, notas y fechas. No se anonimizan automáticamente. El servicio local conserva registro, historial y recibos en SQLite fuera de las versiones del plugin; no guarda audio bruto ni realiza llamadas de red. El conector envía los campos de eventos al calendario elegido cuando ejecuta una operación autorizada. Grabación y transcripción de voz pertenecen al sistema anfitrión. El tratamiento del modelo sigue la cuenta del proveedor elegido y no es únicamente local.",
        "modelDataStatus": "relevant"
      }
    }
  }
};
