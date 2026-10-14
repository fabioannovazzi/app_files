(() => {
  window.MPARANZA_FUNCTION_PAGES = window.MPARANZA_FUNCTION_PAGES || {};
  window.MPARANZA_FUNCTION_PAGES["posizioni-negoziali"] = {
    product: "Vera e Lucia", shared: true, defaultLanguage: "it",
    copy: {
  "it": {
    "name": "Sintetizza le revisioni in posizioni negoziali",
    "summary": "Da un Word revisionato prepara le scelte negoziali da discutere, con clausole, effetti e conto completo delle modifiche.",
    "useWhen": "Adatta il workflow <a href=\"https://github.com/open-legal-products/mike-workflows/blob/65c987e33045ac1beb5c7490859efb64a057bfbe/assistant-workflows/deal-redux/SKILL.md\">Deal Redux di Mike</a>, licenza MIT. È utile quando molte revisioni descrivono poche scelte: ad esempio, varie modifiche rendono reciproci gli obblighi di riservatezza.",
    "input": "Il DOCX originale con revisioni e commenti, la parte assistita, l’obiettivo e le istruzioni dello studio. Per confrontare i round, scegli anche la review precedente. Una copia pulita o un PDF può non conservare le revisioni.",
    "work": "Legge il testo precedente e proposto e inventaria le modifiche, compresi spostamenti, proprietà, tabelle e commenti. Il modello raggruppa le modifiche che vanno decise insieme e spiega l’effetto se accettate. Ogni modifica resta collegata a una posizione o a un’altra voce motivata; nessun foro, rinvio o formato è considerato automaticamente marginale.",
    "output": "Tabella delle posizioni in HTML e Excel, CSV e registro completo di revisioni e commenti. Le risposte sono vuote salvo richiesta. Conserva la review e può confrontarla con il round successivo. Un Word della tabella può essere preparato dai modelli dello studio tramite Documents/Word dell’host.",
    "responsibilityIntro": "Il conteggio riguarda unità tracciate nel file, non azioni dell’autore o importanza negoziale. Fonti o verifiche visive mancanti restano limiti. Il workflow conserva l’originale e non accetta né invia le modifiche.",
    "professionalRole": "Sceglie le posizioni e le risposte, conferma le istruzioni e valuta gli effetti. Il riscontro dei conteggi e delle citazioni non approva la scelta negoziale.",
    "prompt": "Da questo Word revisionato prepara le posizioni negoziali: clausole, effetto se accettate e conteggio completo delle modifiche. Mantieni distinti i commenti e lascia vuote le risposte.",
    "modelData": "Il modello può leggere il contratto scelto, nomi e importi, testo eliminato e proposto, revisioni, autori e date registrati, proprietà Word, commenti e ancore, istruzioni dello studio, raggruppamenti, risposte richieste, review precedente e pagine renderizzate ispezionate. Originali, inventario, review e output sono locali; i helper non chiamano modelli, Mike o servizi di editing. La ricerca giuridica eventualmente necessaria usa gli strumenti dell’host con questioni generali senza documenti o dati identificanti del cliente nelle query. In Vera entrano solo i materiali Archive selezionati; il report può trasmettere a Mparanza schema, UUID, versione Vera e digest del report, senza contratti o contenuto del report. Il modo locale richiesto esclude quella ricevuta esterna. Elaborazione del modello e Documents/Word seguono l’account dell’host; i dati non sono automaticamente anonimizzati.",
    "modelDataStatus": "relevant",
    "productRole": "Preparano la tabella richiesta, conservano le fonti e mostrano modifiche assegnate, verifiche pendenti e limiti.",
    "productRoleTitle": "Vera e Lucia preparano"
  },
  "en": {
    "name": "Summarize redlines into negotiating positions",
    "summary": "Turns a tracked Word agreement into the negotiating choices to discuss, with clauses, effects and complete change accounting.",
    "useWhen": "Adapts Mike’s MIT-licensed <a href=\"https://github.com/open-legal-products/mike-workflows/blob/65c987e33045ac1beb5c7490859efb64a057bfbe/assistant-workflows/deal-redux/SKILL.md\">Deal Redux workflow</a>. Useful when many edits represent a few choices: for example, several changes make confidentiality obligations mutual.",
    "input": "The original DOCX with tracked changes and comments, represented party, objective and firm instructions. Select the earlier review for a round comparison. A clean copy or PDF may not retain the revisions.",
    "work": "Reads original and proposed text and inventories changes, including moves, properties, tables and comments. The model groups changes that need a joint decision and explains the effect if accepted. Every change belongs to a position or another explained entry; venue, cross-references and formatting are never automatically treated as immaterial.",
    "output": "Position table in HTML and Excel, CSV and a complete revision/comment ledger. Responses stay blank unless requested. Retains the review and can compare it with a later round. A Word table can use firm templates through the host’s Documents/Word capability.",
    "responsibilityIntro": "Counts refer to tracked file units, not author actions or negotiating importance. Missing sources or visual checks remain limitations. Preserves the original without accepting or sending changes.",
    "professionalRole": "Chooses positions and responses, confirms instructions and assesses effects. Count and quotation checks do not approve a negotiating choice.",
    "prompt": "Turn this tracked Word agreement into negotiating positions: clauses, effect if accepted and complete change accounting. Keep comments distinct and leave responses blank.",
    "modelData": "The model may read the selected agreement, names and amounts, deleted and proposed text, revisions, recorded authors/dates, Word properties, comments/anchors, firm instructions, groups, requested responses, earlier review and inspected rendered pages. Originals, inventory, reviews and outputs remain local; helpers call no models, Mike or editing service. Any necessary legal research uses host tools with general questions, without client documents or identifying data in queries. Vera reads only selected Archive materials; its report can send Mparanza schema, UUID, Vera version and report digest, without contracts or report contents. User-requested local mode excludes that external receipt. Model processing and Documents/Word follow the host account; content is not automatically anonymized.",
    "modelDataStatus": "relevant",
    "productRole": "Prepare the requested table, retain sources and show accounted changes, pending checks and limitations.",
    "productRoleTitle": "Vera and Lucia prepare"
  },
  "fr": {
    "name": "Résumer les révisions en positions de négociation",
    "summary": "Transforme un contrat Word révisé en choix à discuter, avec clauses, effets et comptage complet des modifications.",
    "useWhen": "Adaptation du workflow MIT <a href=\"https://github.com/open-legal-products/mike-workflows/blob/65c987e33045ac1beb5c7490859efb64a057bfbe/assistant-workflows/deal-redux/SKILL.md\">Deal Redux de Mike</a>. Utile lorsque de nombreuses révisions expriment quelques choix : plusieurs modifications rendent, par exemple, la confidentialité réciproque.",
    "input": "Le DOCX original avec révisions et commentaires, la partie représentée, l’objectif et les instructions du cabinet. Sélectionner aussi la revue précédente pour comparer les tours. Une copie propre ou un PDF peut perdre les révisions.",
    "work": "Lit le texte antérieur et proposé et inventorie déplacements, propriétés, tableaux et commentaires. Le modèle regroupe les changements à décider ensemble et explique l’effet de leur acceptation. Chaque changement appartient à une position ou une autre entrée motivée ; for, renvois et format ne sont jamais présumés secondaires.",
    "output": "Tableau des positions en HTML et Excel, CSV et registre complet des révisions et commentaires. Réponses vides sauf demande. Conserve la revue et la compare à un tour ultérieur. Un tableau Word peut suivre les modèles du cabinet via Documents/Word de l’hôte.",
    "responsibilityIntro": "Le comptage concerne les unités suivies, pas les actions de l’auteur ni leur importance. Sources ou contrôles visuels manquants restent des limites. L’original est préservé ; aucune modification n’est acceptée ou envoyée.",
    "professionalRole": "Choisit positions et réponses, confirme les instructions et évalue les effets. Le contrôle des comptes et citations n’approuve pas un choix de négociation.",
    "prompt": "À partir de ce Word révisé, prépare les positions de négociation : clauses, effet si acceptées et comptage complet. Sépare les commentaires et laisse les réponses vides.",
    "modelData": "Le modèle peut lire le contrat choisi, noms et montants, texte supprimé/proposé, révisions, auteurs/dates enregistrés, propriétés Word, commentaires/repères, instructions, groupes, réponses demandées, revue antérieure et pages rendues inspectées. Originaux, inventaire, revues et sorties sont locaux ; les helpers n’appellent ni modèle, Mike ou service d’édition. La recherche juridique utilise les outils de l’hôte avec questions générales sans documents ou données identifiantes du client dans les requêtes. Vera lit seulement les pièces Archive choisies ; son rapport peut transmettre à Mparanza schéma, UUID, version Vera et empreinte du rapport, sans contrats ni contenu du rapport. Le mode local demandé exclut ce reçu externe. Modèle et Documents/Word suivent le compte hôte ; aucune anonymisation automatique.",
    "modelDataStatus": "relevant",
    "productRole": "Préparent le tableau demandé, conservent les sources et indiquent changements affectés, contrôles en attente et limites.",
    "productRoleTitle": "Vera et Lucia préparent"
  },
  "de": {
    "name": "Revisionen in Verhandlungspositionen zusammenfassen",
    "summary": "Erstellt aus einem Word-Vertrag mit Revisionen die zu besprechenden Entscheidungen mit Klauseln, Wirkungen und vollständiger Änderungszuordnung.",
    "useWhen": "Anpassung von Mikes MIT-lizenziertem <a href=\"https://github.com/open-legal-products/mike-workflows/blob/65c987e33045ac1beb5c7490859efb64a057bfbe/assistant-workflows/deal-redux/SKILL.md\">Deal-Redux-Workflow</a>. Hilfreich, wenn viele Änderungen wenige Entscheidungen ausdrücken, etwa gegenseitige Vertraulichkeitspflichten.",
    "input": "Ursprüngliche DOCX-Datei mit Revisionen und Kommentaren, vertretene Partei, Ziel und Kanzleivorgaben. Für Rundenvergleiche auch die frühere Prüfung auswählen. Eine bereinigte Datei oder PDF kann die Revisionen verlieren.",
    "work": "Liest vorherigen und vorgeschlagenen Text und erfasst Verschiebungen, Eigenschaften, Tabellen und Kommentare. Das Modell gruppiert gemeinsam zu entscheidende Änderungen und beschreibt die Wirkung bei Annahme. Jede Änderung wird genau einer Position oder begründeten weiteren Eintragung zugeordnet; Gerichtsstand, Verweise und Format gelten nie automatisch als unwesentlich.",
    "output": "Positionstabelle als HTML und Excel, CSV und vollständiges Revisions-/Kommentarregister. Antworten bleiben ohne Auftrag leer. Bewahrt die Prüfung und vergleicht weitere Runden. Eine Word-Tabelle kann Kanzleivorlagen über Documents/Word des Hosts verwenden.",
    "responsibilityIntro": "Gezählt werden markierte Einheiten, nicht Autorenaktionen oder Bedeutung. Fehlende Quellen und Sichtprüfungen bleiben Grenzen. Das Original bleibt erhalten; Änderungen werden weder angenommen noch versendet.",
    "professionalRole": "Wählt Positionen und Antworten, bestätigt Vorgaben und bewertet Wirkungen. Zähl- und Zitatprüfungen genehmigen keine Verhandlungsentscheidung.",
    "prompt": "Erstelle aus diesem Word-Vertrag mit Revisionen die Verhandlungspositionen: Klauseln, Wirkung bei Annahme und vollständige Änderungszuordnung. Kommentare getrennt halten und Antworten leer lassen.",
    "modelData": "Das Modell kann den gewählten Vertrag, Namen/Beträge, gelöschten/vorgeschlagenen Text, Revisionen, erfasste Autoren/Daten, Word-Eigenschaften, Kommentare/Anker, Kanzleivorgaben, Gruppen, gewünschte Antworten, frühere Prüfung und gesichtete gerenderte Seiten lesen. Originale, Inventar, Prüfungen und Ergebnisse sind lokal; Helfer rufen weder Modelle, Mike noch Editing-Dienste auf. Rechtsrecherche verwendet Host-Werkzeuge mit allgemeinen Fragen ohne Mandantendokumente oder identifizierende Daten in Suchanfragen. Vera liest nur gewählte Archive-Unterlagen; ihr Bericht kann Schema, UUID, Vera-Version und Berichts-Hash an Mparanza senden, keine Verträge oder Berichtsinhalte. Gewünschter lokaler Modus schließt diesen externen Beleg aus. Modell und Documents/Word folgen dem Host-Konto; keine automatische Anonymisierung.",
    "modelDataStatus": "relevant",
    "productRole": "Erstellen die gewünschte Tabelle, erhalten Quellen und zeigen zugeordnete Änderungen, offene Prüfungen und Grenzen.",
    "productRoleTitle": "Vera und Lucia bereiten vor"
  },
  "es": {
    "name": "Resumir revisiones en posiciones de negociación",
    "summary": "Convierte un contrato Word revisado en decisiones que discutir, con cláusulas, efectos y recuento completo de cambios.",
    "useWhen": "Adapta el workflow MIT <a href=\"https://github.com/open-legal-products/mike-workflows/blob/65c987e33045ac1beb5c7490859efb64a057bfbe/assistant-workflows/deal-redux/SKILL.md\">Deal Redux de Mike</a>. Útil cuando muchas revisiones expresan pocas decisiones: por ejemplo, varios cambios hacen recíproca la confidencialidad.",
    "input": "DOCX original con revisiones y comentarios, parte representada, objetivo e instrucciones del despacho. Selecciona la revisión anterior para comparar rondas. Una copia limpia o PDF puede perder las revisiones.",
    "work": "Lee texto anterior y propuesto e inventaría movimientos, propiedades, tablas y comentarios. El modelo agrupa cambios que deben decidirse juntos y explica su efecto si se aceptan. Cada cambio pertenece a una posición u otra entrada motivada; foro, referencias y formato nunca se consideran secundarios automáticamente.",
    "output": "Tabla de posiciones en HTML y Excel, CSV y registro completo de revisiones/comentarios. Respuestas vacías salvo solicitud. Conserva la revisión y permite compararla con otra ronda. La tabla Word puede seguir los modelos del despacho mediante Documents/Word del anfitrión.",
    "responsibilityIntro": "El recuento corresponde a unidades marcadas, no acciones del autor o importancia. Fuentes y controles visuales pendientes siguen siendo límites. Conserva el original sin aceptar ni enviar cambios.",
    "professionalRole": "Elige posiciones y respuestas, confirma instrucciones y valora los efectos. Comprobar recuentos y citas no aprueba una decisión de negociación.",
    "prompt": "De este Word revisado prepara posiciones de negociación: cláusulas, efecto si se aceptan y recuento completo. Mantén separados los comentarios y deja las respuestas vacías.",
    "modelData": "El modelo puede leer contrato elegido, nombres/importes, texto eliminado/propuesto, revisiones, autores/fechas registrados, propiedades Word, comentarios/anclas, instrucciones, grupos, respuestas solicitadas, revisión anterior y páginas renderizadas inspeccionadas. Originales, inventario, revisiones y resultados son locales; los ayudantes no llaman modelos, Mike ni servicios de edición. La investigación jurídica usa herramientas del anfitrión con preguntas generales sin documentos o datos identificativos del cliente en consultas. Vera lee solo materiales Archive seleccionados; su informe puede enviar a Mparanza esquema, UUID, versión Vera y digest del informe, sin contratos ni contenido del informe. El modo local solicitado excluye ese recibo externo. Modelo y Documents/Word siguen la cuenta anfitriona; no hay anonimización automática.",
    "modelDataStatus": "relevant",
    "productRole": "Preparan la tabla solicitada, conservan fuentes y muestran cambios asignados, controles pendientes y límites.",
    "productRoleTitle": "Vera y Lucia preparan"
  }
}
  };
})();
