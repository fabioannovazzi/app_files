"use strict";
/* Complete public synthetic records; fixed storage calls, no legal inference. */
globalThis.VeraTransformation = Object.freeze({create(api){
  const {node,button,call,say,confirmation}=api;let context,timer,queue=Promise.resolve();const urls=new Set();
  // Static interface translations only; source values and wire contracts stay literal.
  const copy={
  "Scegli il passaggio": [
    "Choose a step",
    "Choisir une étape",
    "Schritt wählen",
    "Elegir un paso"
  ],
  "Aggiorna gli attributi del caso": [
    "Update case attributes",
    "Mettre à jour les attributs du cas",
    "Fallmerkmale aktualisieren",
    "Actualizar los atributos del caso"
  ],
  "Importa una fonte sintetica collegata": [
    "Import a linked synthetic source",
    "Importer une source synthétique liée",
    "Verknüpfte synthetische Quelle importieren",
    "Importar una fuente sintética vinculada"
  ],
  "Conserva un record proposto": [
    "Save a proposed record",
    "Conserver un enregistrement proposé",
    "Vorgeschlagenen Datensatz speichern",
    "Guardar un registro propuesto"
  ],
  "Definisci un ramo e le sue dipendenze": [
    "Define a branch and its dependencies",
    "Définir une branche et ses dépendances",
    "Zweig und Abhängigkeiten festlegen",
    "Definir una rama y sus dependencias"
  ],
  "Sottoponi il ramo a riesame": [
    "Submit the branch for review",
    "Soumettre la branche à révision",
    "Zweig zur Prüfung vorlegen",
    "Someter la rama a revisión"
  ],
  "Registra una decisione sintetica separata": [
    "Record a separate synthetic decision",
    "Consigner une décision synthétique distincte",
    "Separate synthetische Entscheidung erfassen",
    "Registrar una decisión sintética separada"
  ],
  "Esporta il dossier della versione corrente": [
    "Export the current version dossier",
    "Exporter le dossier de la version actuelle",
    "Dossier der aktuellen Version exportieren",
    "Exportar el expediente de la versión actual"
  ],
  "Proposta incompleta conservata. Nessuna decisione registrata.": [
    "Incomplete proposal saved. No decision recorded.",
    "Proposition incomplète conservée. Aucune décision consignée.",
    "Unvollständiger Vorschlag gespeichert. Keine Entscheidung erfasst.",
    "Propuesta incompleta guardada. No se ha registrado ninguna decisión."
  ],
  "Campi non conservati: ": [
    "Fields not saved: ",
    "Champs non conservés : ",
    "Felder nicht gespeichert: ",
    "Campos no guardados: "
  ],
  "Responsabile dichiarato": [
    "Declared person responsible",
    "Responsable déclaré",
    "Angegebene verantwortliche Person",
    "Responsable declarado"
  ],
  "Scopo dichiarato": [
    "Declared purpose",
    "Objectif déclaré",
    "Angegebener Zweck",
    "Finalidad declarada"
  ],
  "Forma iniziale": [
    "Initial legal form",
    "Forme juridique initiale",
    "Ursprüngliche Rechtsform",
    "Forma jurídica inicial"
  ],
  "Forma finale": [
    "Final legal form",
    "Forme juridique finale",
    "Zielrechtsform",
    "Forma jurídica final"
  ],
  "Regime fiscale iniziale": [
    "Initial tax regime",
    "Régime fiscal initial",
    "Ursprüngliches Steuerregime",
    "Régimen fiscal inicial"
  ],
  "Regime fiscale finale": [
    "Final tax regime",
    "Régime fiscal final",
    "Zielsteuerregime",
    "Régimen fiscal final"
  ],
  "Commercialità iniziale": [
    "Initial commercial status",
    "Caractère commercial initial",
    "Ursprüngliche Gewerblichkeit",
    "Carácter comercial inicial"
  ],
  "Commercialità finale": [
    "Final commercial status",
    "Caractère commercial final",
    "Gewerblichkeit nach der Umwandlung",
    "Carácter comercial final"
  ],
  "Data proposta": [
    "Proposed date",
    "Date proposée",
    "Vorgeschlagenes Datum",
    "Fecha propuesta"
  ],
  "Data effettiva": [
    "Actual date",
    "Date effective",
    "Tatsächliches Datum",
    "Fecha efectiva"
  ],
  "Stato conservato": [
    "Saved status",
    "Statut conservé",
    "Gespeicherter Status",
    "Estado guardado"
  ],
  "Elementi bloccanti": [
    "Blocking items",
    "Éléments bloquants",
    "Blockierende Punkte",
    "Elementos bloqueantes"
  ],
  "Impronta della proposta": [
    "Proposal digest",
    "Empreinte de la proposition",
    "Prüfsumme des Vorschlags",
    "Huella de la propuesta"
  ],
  "Passaggio successivo": [
    "Next step",
    "Étape suivante",
    "Nächster Schritt",
    "Paso siguiente"
  ],
  "Rilievo proposto": [
    "Proposed finding",
    "Constat proposé",
    "Vorgeschlagene Feststellung",
    "Hallazgo propuesto"
  ],
  "Categoria dichiarata": [
    "Declared category",
    "Catégorie déclarée",
    "Angegebene Kategorie",
    "Categoría declarada"
  ],
  "Alternative considerate": [
    "Alternatives considered",
    "Autres possibilités examinées",
    "Berücksichtigte Alternativen",
    "Alternativas consideradas"
  ],
  "Confidenza dichiarata": [
    "Declared confidence",
    "Niveau de confiance déclaré",
    "Angegebenes Vertrauensniveau",
    "Grado de confianza declarado"
  ],
  "Quota di capitale": [
    "Capital share",
    "Part du capital",
    "Kapitalanteil",
    "Participación en el capital"
  ],
  "Quota di voto": [
    "Voting share",
    "Part des droits de vote",
    "Stimmrechtsanteil",
    "Participación en los votos"
  ],
  "Quota di utili": [
    "Profit share",
    "Part des bénéfices",
    "Gewinnanteil",
    "Participación en los beneficios"
  ],
  "Quota di lavoro": [
    "Work contribution share",
    "Part de travail",
    "Arbeitsanteil",
    "Participación de trabajo"
  ],
  "Consenso documentato": [
    "Documented consent",
    "Consentement documenté",
    "Dokumentierte Zustimmung",
    "Consentimiento documentado"
  ],
  "Data di origine": [
    "Origin date",
    "Date d'origine",
    "Entstehungsdatum",
    "Fecha de origen"
  ],
  "Data della ricevuta": [
    "Receipt date",
    "Date de l'accusé de réception",
    "Empfangsdatum",
    "Fecha del recibo"
  ],
  "Valutazione della liberazione": [
    "Release assessment",
    "Évaluation de la libération",
    "Beurteilung der Entlastung",
    "Evaluación de la liberación"
  ],
  "Valutazione dell’opposizione": [
    "Opposition assessment",
    "Évaluation de l'opposition",
    "Beurteilung des Widerspruchs",
    "Evaluación de la oposición"
  ],
  "Origine dichiarata": [
    "Declared origin",
    "Origine déclarée",
    "Angegebene Herkunft",
    "Origen declarado"
  ],
  "Regime dichiarato": [
    "Declared regime",
    "Régime déclaré",
    "Angegebenes Regime",
    "Régimen declarado"
  ],
  "Bilancio di riferimento": [
    "Reference balance sheet",
    "Bilan de référence",
    "Referenzbilanz",
    "Balance de referencia"
  ],
  "Tassazione precedente": [
    "Prior taxation",
    "Imposition antérieure",
    "Frühere Besteuerung",
    "Tributación anterior"
  ],
  "Valore contabile": [
    "Book value",
    "Valeur comptable",
    "Buchwert",
    "Valor contable"
  ],
  "Valore stimato": [
    "Estimated value",
    "Valeur estimée",
    "Geschätzter Wert",
    "Valor estimado"
  ],
  "Valore fiscale": [
    "Tax value",
    "Valeur fiscale",
    "Steuerlicher Wert",
    "Valor fiscal"
  ],
  "Destinazione aziendale": [
    "Business allocation",
    "Affectation à l'entreprise",
    "Betriebliche Zuordnung",
    "Destino empresarial"
  ],
  "Decisione contabile": [
    "Accounting decision",
    "Décision comptable",
    "Bilanzielle Entscheidung",
    "Decisión contable"
  ],
  "Decisione fiscale": [
    "Tax decision",
    "Décision fiscale",
    "Steuerliche Entscheidung",
    "Decisión fiscal"
  ],
  "Versione della fonte": [
    "Source version",
    "Version de la source",
    "Quellenversion",
    "Versión de la fuente"
  ],
  "Evento iniziale": [
    "Triggering event",
    "Événement déclencheur",
    "Auslösendes Ereignis",
    "Evento desencadenante"
  ],
  "Metodo dichiarato": [
    "Declared method",
    "Méthode déclarée",
    "Angegebene Methode",
    "Método declarado"
  ],
  "Data approvata": [
    "Approved date",
    "Date approuvée",
    "Genehmigtes Datum",
    "Fecha aprobada"
  ],
  "Domanda aperta": [
    "Open question",
    "Question ouverte",
    "Offene Frage",
    "Cuestión abierta"
  ],
  "Fonte necessaria": [
    "Required source",
    "Source nécessaire",
    "Erforderliche Quelle",
    "Fuente necesaria"
  ],
  "Passaggi bloccati": [
    "Blocked steps",
    "Étapes bloquées",
    "Blockierte Schritte",
    "Pasos bloqueados"
  ],
  "Criterio di chiusura": [
    "Closure criterion",
    "Critère de clôture",
    "Abschlusskriterium",
    "Criterio de cierre"
  ],
  "Indirizzo della fonte": [
    "Source address",
    "Adresse de la source",
    "Quellenadresse",
    "Dirección de la fuente"
  ],
  "Data di pubblicazione": [
    "Publication date",
    "Date de publication",
    "Veröffentlichungsdatum",
    "Fecha de publicación"
  ],
  "Efficacia dal": [
    "Effective from",
    "Prise d'effet à partir du",
    "Wirksam ab",
    "Vigente desde"
  ],
  "Applicabilità dal": [
    "Applicable from",
    "Applicable à partir du",
    "Anwendbar ab",
    "Aplicable desde"
  ],
  "Applicabilità fino al": [
    "Applicable until",
    "Applicable jusqu'au",
    "Anwendbar bis",
    "Aplicable hasta"
  ],
  "Condizioni transitorie": [
    "Transitional conditions",
    "Conditions transitoires",
    "Übergangsbedingungen",
    "Condiciones transitorias"
  ],
  "Data di acquisizione": [
    "Acquisition date",
    "Date d'acquisition",
    "Erfassungsdatum",
    "Fecha de adquisición"
  ],
  "Stato della verifica": [
    "Verification status",
    "Statut de vérification",
    "Prüfstatus",
    "Estado de verificación"
  ],
  "Riferimento della fonte": [
    "Source reference",
    "Référence de la source",
    "Quellenreferenz",
    "Referencia de la fuente"
  ],
  "Impronta del file": [
    "File digest",
    "Empreinte du fichier",
    "Dateiprüfsumme",
    "Huella del archivo"
  ],
  "Percorso conservato": [
    "Saved path",
    "Chemin conservé",
    "Gespeicherter Pfad",
    "Ruta guardada"
  ],
  "Localizzatore nella fonte": [
    "Locator in source",
    "Repère dans la source",
    "Fundstelle in der Quelle",
    "Localizador en la fuente"
  ],
  "Rilievi proposti": [
    "Proposed findings",
    "Constats proposés",
    "Vorgeschlagene Feststellungen",
    "Hallazgos propuestos"
  ],
  "Attività": [
    "Assets",
    "Actifs",
    "Vermögenswerte",
    "Activos"
  ],
  "Termini dichiarati": [
    "Declared deadlines",
    "Échéances déclarées",
    "Angegebene Fristen",
    "Plazos declarados"
  ],
  "Questioni aperte": [
    "Open questions",
    "Questions ouvertes",
    "Offene Fragen",
    "Cuestiones abiertas"
  ],
  "Record conservati": [
    "Saved records",
    "Enregistrements conservés",
    "Gespeicherte Datensätze",
    "Registros guardados"
  ],
  "Decisioni separate": [
    "Separate decisions",
    "Décisions distinctes",
    "Separate Entscheidungen",
    "Decisiones separadas"
  ],
  "Versione del contratto": [
    "Contract version",
    "Version du contrat",
    "Vertragsversion",
    "Versión del contrato"
  ],
  "Solo dati sintetici": [
    "Synthetic data only",
    "Données synthétiques uniquement",
    "Nur synthetische Daten",
    "Solo datos sintéticos"
  ],
  "Identificativo del ramo": [
    "Branch identifier",
    "Identifiant de la branche",
    "Zweigkennung",
    "Identificador de la rama"
  ],
  "Decisione conservata": [
    "Saved decision",
    "Décision conservée",
    "Gespeicherte Entscheidung",
    "Decisión guardada"
  ],
  "Motivo dichiarato": [
    "Declared reason",
    "Motif déclaré",
    "Angegebene Begründung",
    "Motivo declarado"
  ],
  "Revisore dichiarato": [
    "Declared reviewer",
    "Réviseur déclaré",
    "Angegebene prüfende Person",
    "Revisor declarado"
  ],
  "Operatore dichiarato": [
    "Declared operator",
    "Opérateur déclaré",
    "Angegebene ausführende Person",
    "Operador declarado"
  ],
  "Data della registrazione": [
    "Record date",
    "Date de l'enregistrement",
    "Erfassungsdatum",
    "Fecha del registro"
  ],
  "Passaggio conservato": [
    "Saved step",
    "Étape conservée",
    "Gespeicherter Schritt",
    "Paso guardado"
  ],
  "Cartella del dossier": [
    "Dossier folder",
    "Dossier de fichiers",
    "Dossierordner",
    "Carpeta del expediente"
  ],
  "Versione corrente": [
    "Current version",
    "Version actuelle",
    "Aktuelle Version",
    "Versión actual"
  ],
  "Elenco vuoto": [
    "Empty list",
    "Liste vide",
    "Leere Liste",
    "Lista vacía"
  ],
  "Nessun campo conservato": [
    "No saved fields",
    "Aucun champ conservé",
    "Keine gespeicherten Felder",
    "No hay campos guardados"
  ],
  "Non indicato": [
    "Not supplied",
    "Non renseigné",
    "Nicht angegeben",
    "No indicado"
  ],
  "Testo vuoto": [
    "Empty text",
    "Texte vide",
    "Leerer Text",
    "Texto vacío"
  ],
  "Vero · true": [
    "True · true",
    "Vrai · true",
    "Wahr · true",
    "Verdadero · true"
  ],
  "Falso · false": [
    "False · false",
    "Faux · false",
    "Falsch · false",
    "Falso · false"
  ],
  "Fonte sintetica da importare": [
    "Synthetic source to import",
    "Source synthétique à importer",
    "Zu importierende synthetische Quelle",
    "Fuente sintética que se va a importar"
  ],
  "Scegli soltanto uno dei file collegati dall’host a questo prototipo. Indica identificativo, origine e localizzatore senza dedurli dal nome del file. I campi incompleti restano nella stessa bozza; la conferma e l’importazione sono passaggi separati.": [
    "Choose only a file linked to this prototype by the host. Enter its identifier, origin and locator without inferring them from its filename. Incomplete fields remain in the same draft; confirmation and import are separate steps.",
    "Choisissez uniquement un fichier lié à ce prototype par l'hôte. Indiquez son identifiant, son origine et son repère sans les déduire du nom du fichier. Les champs incomplets restent dans le même brouillon ; confirmation et import sont des étapes distinctes.",
    "Wählen Sie nur eine vom Host mit diesem Prototyp verknüpfte Datei. Geben Sie Kennung, Herkunft und Fundstelle an, ohne diese aus dem Dateinamen abzuleiten. Unvollständige Felder bleiben im selben Entwurf; Bestätigung und Import sind getrennte Schritte.",
    "Elija solo un archivo vinculado a este prototipo por el entorno. Indique identificador, origen y localizador sin deducirlos del nombre del archivo. Los campos incompletos permanecen en el mismo borrador; la confirmación y la importación son pasos separados."
  ],
  "La proposta completa non è ancora leggibile. Conservala o correggila prima di usare i campi della fonte; nessun testo viene sostituito.": [
    "The complete proposal cannot yet be read. Keep it or correct it before using the source fields; no text is replaced.",
    "La proposition complète n'est pas encore lisible. Conservez-la ou corrigez-la avant d'utiliser les champs de la source ; aucun texte n'est remplacé.",
    "Der vollständige Vorschlag ist noch nicht lesbar. Behalten oder korrigieren Sie ihn, bevor Sie die Quellenfelder verwenden; kein Text wird ersetzt.",
    "La propuesta completa aún no se puede leer. Consérvela o corríjala antes de usar los campos de la fuente; no se sustituye ningún texto."
  ],
  "La proposta contiene campi diversi dall’importazione di una fonte. Confronta la proposta completa prima di modificarla; nessun campo viene scartato.": [
    "The proposal contains fields outside a source import. Compare the complete proposal before editing it; no field is discarded.",
    "La proposition contient des champs autres que ceux de l'import d'une source. Comparez la proposition complète avant de la modifier ; aucun champ n'est supprimé.",
    "Der Vorschlag enthält andere Felder als ein Quellenimport. Vergleichen Sie den vollständigen Vorschlag vor der Bearbeitung; kein Feld wird verworfen.",
    "La propuesta contiene campos distintos de los de una importación de fuente. Compare la propuesta completa antes de modificarla; no se descarta ningún campo."
  ],
  "Nessuna fonte sintetica collegata. Il workflow specialistico deve collegare file dichiarati sintetici a questo caso prima dell’importazione.": [
    "No synthetic source is linked. The specialist workflow must link files declared synthetic to this case before import.",
    "Aucune source synthétique n'est liée. Le workflow spécialisé doit lier à ce cas des fichiers déclarés synthétiques avant l'import.",
    "Keine synthetische Quelle ist verknüpft. Der spezialisierte Workflow muss vor dem Import als synthetisch deklarierte Dateien mit diesem Fall verknüpfen.",
    "No hay ninguna fuente sintética vinculada. El flujo especializado debe vincular archivos declarados sintéticos a este caso antes de la importación."
  ],
  "Identificativo dell’evidenza": [
    "Evidence identifier",
    "Identifiant de la pièce probante",
    "Nachweiskennung",
    "Identificador de la evidencia"
  ],
  "Fonte sintetica collegata": [
    "Linked synthetic source",
    "Source synthétique liée",
    "Verknüpfte synthetische Quelle",
    "Fuente sintética vinculada"
  ],
  "Origine dichiarata della fonte": [
    "Declared source origin",
    "Origine déclarée de la source",
    "Angegebene Quellenherkunft",
    "Origen declarado de la fuente"
  ],
  "Scegli una fonte collegata": [
    "Choose a linked source",
    "Choisir une source liée",
    "Verknüpfte Quelle wählen",
    "Elegir una fuente vinculada"
  ],
  "Riferimento non più collegato · ": [
    "Reference no longer linked · ",
    "Référence qui n'est plus liée · ",
    "Nicht mehr verknüpfte Referenz · ",
    "Referencia ya no vinculada · "
  ],
  "File collegati · nomi, riferimenti e impronte completi": [
    "Linked files · complete names, references and digests",
    "Fichiers liés · noms, références et empreintes complets",
    "Verknüpfte Dateien · vollständige Namen, Referenzen und Prüfsummen",
    "Archivos vinculados · nombres, referencias y huellas completos"
  ],
  "Quali dati arrivano al modello": [
    "What data reaches the model",
    "Quelles données parviennent au modèle",
    "Welche Daten das Modell erhält",
    "Qué datos llegan al modelo"
  ],
  "I campi privati e la sola consultazione del pannello non inviano automaticamente fonti al modello. Una domanda sintetica confermata autorizza il modello della sessione a leggere l’intero stato corrente del caso e soltanto gli originali esplicitamente selezionati, con percorsi e impronte. Le route di contesto e proposta sono visibili al modello; il consenso alla domanda scade dopo un’ora e non approva proposte o trattamenti. Nel workflow specialistico il modello può leggere documenti sintetici scelti, attributi, fonti, ipotesi, calcoli, decisioni e dossier. L’operatore dichiara i dati sintetici: Vera non rileva dati personali né li anonimizza. Il codice conserva versioni, esegue aritmetica esatta e verifica proposte su una copia isolata; non chiama servizi di modelli esterni. Si applica l’account Codex o Cowork scelto dall’utente; la sessione non è esclusivamente locale. La richiesta preparata, la proposta privata e il dossier non sono ricevute del contesto effettivo del provider.": [
    "Private fields and panel inspection do not automatically send sources to the model. A confirmed synthetic question authorizes the session model to read the complete current case state and only the explicitly selected originals, with paths and digests. Context and proposal routes are model-visible; authorization for the question expires after one hour and approves neither proposals nor treatments. In the specialist workflow, the model may read selected synthetic documents, attributes, sources, assumptions, calculations, decisions and dossiers. The operator declares the data synthetic: Vera does not detect personal data or anonymize it. Code retains versions, performs exact arithmetic and verifies proposals on an isolated copy; it calls no external model services. The user's selected Codex or Cowork account applies; the session is not exclusively local. A prepared request, private proposal or dossier is not a receipt of the provider's actual context.",
    "Les champs privés et la consultation du panneau n'envoient pas automatiquement les sources au modèle. Une question synthétique confirmée autorise le modèle de la session à lire l'état actuel complet du cas et uniquement les originaux explicitement sélectionnés, avec leurs chemins et empreintes. Les routes de contexte et de proposition sont visibles au modèle ; l'autorisation de la question expire après une heure et n'approuve ni propositions ni traitements. Dans le workflow spécialisé, le modèle peut lire les documents synthétiques choisis, attributs, sources, hypothèses, calculs, décisions et dossiers. L'opérateur déclare les données synthétiques : Vera ne détecte pas les données personnelles et ne les anonymise pas. Le code conserve les versions, effectue une arithmétique exacte et vérifie les propositions sur une copie isolée ; il n'appelle aucun service de modèles externe. Le compte Codex ou Cowork choisi par l'utilisateur s'applique ; la session n'est pas exclusivement locale. Une demande préparée, une proposition privée ou un dossier ne constitue pas un reçu du contexte effectif du fournisseur.",
    "Private Felder und die Einsicht im Panel senden Quellen nicht automatisch an das Modell. Eine bestätigte synthetische Frage erlaubt dem Sitzungsmodell, den vollständigen aktuellen Fallstand und nur die ausdrücklich ausgewählten Originale mit Pfaden und Prüfsummen zu lesen. Kontext- und Vorschlagsrouten sind für das Modell sichtbar; die Berechtigung für die Frage läuft nach einer Stunde ab und genehmigt weder Vorschläge noch Behandlungen. Im spezialisierten Workflow kann das Modell ausgewählte synthetische Dokumente, Merkmale, Quellen, Annahmen, Berechnungen, Entscheidungen und Dossiers lesen. Die ausführende Person deklariert die Daten als synthetisch: Vera erkennt keine personenbezogenen Daten und anonymisiert sie nicht. Der Code speichert Versionen, rechnet exakt und prüft Vorschläge auf einer isolierten Kopie; er ruft keine externen Modelldienste auf. Es gilt das von der nutzenden Person gewählte Codex- oder Cowork-Konto; die Sitzung ist nicht ausschließlich lokal. Eine vorbereitete Anfrage, ein privater Vorschlag oder ein Dossier ist kein Nachweis des tatsächlichen Providerkontexts.",
    "Los campos privados y la consulta del panel no envían fuentes automáticamente al modelo. Una pregunta sintética confirmada autoriza al modelo de la sesión a leer el estado actual completo del caso y solo los originales seleccionados expresamente, con rutas y huellas. Las rutas de contexto y propuesta son visibles para el modelo; la autorización de la pregunta caduca al cabo de una hora y no aprueba propuestas ni tratamientos. En el flujo especializado, el modelo puede leer documentos sintéticos seleccionados, atributos, fuentes, hipótesis, cálculos, decisiones y expedientes. El operador declara los datos sintéticos: Vera no detecta datos personales ni los anonimiza. El código conserva versiones, realiza aritmética exacta y verifica propuestas en una copia aislada; no llama a servicios externos de modelos. Se aplica la cuenta Codex o Cowork elegida por el usuario; la sesión no es exclusivamente local. Una solicitud preparada, una propuesta privada o un expediente no son recibos del contexto real del proveedor."
  ],
  "← Clienti e incarichi": [
    "← Clients and engagements",
    "← Clients et missions",
    "← Mandanten und Aufträge",
    "← Clientes y encargos"
  ],
  "Vera · prototipo sintetico": [
    "Vera · synthetic prototype",
    "Vera · prototype synthétique",
    "Vera · synthetischer Prototyp",
    "Vera · prototipo sintético"
  ],
  "Trasformazione societaria": [
    "Company transformation",
    "Transformation de société",
    "Gesellschaftsumwandlung",
    "Transformación societaria"
  ],
  "Prepara e riesamina soltanto casi sintetici. Il prototipo non supporta mandati reali, termini legali, efficacia giuridica o invii.": [
    "Prepare and review synthetic cases only. The prototype supports no real mandates, statutory deadlines, legal effectiveness or submissions.",
    "Préparez et examinez uniquement des cas synthétiques. Le prototype ne prend en charge ni missions réelles, ni délais légaux, ni effet juridique, ni transmissions.",
    "Bereiten und prüfen Sie nur synthetische Fälle. Der Prototyp unterstützt keine realen Mandate, gesetzlichen Fristen, Rechtswirksamkeit oder Übermittlungen.",
    "Prepare y revise únicamente casos sintéticos. El prototipo no admite encargos reales, plazos legales, eficacia jurídica ni envíos."
  ],
  "Revisione ": [
    "Revision ",
    "Révision ",
    "Revision ",
    "Revisión "
  ],
  "Prepara questo prototipo": [
    "Prepare this prototype",
    "Préparer ce prototype",
    "Diesen Prototyp vorbereiten",
    "Preparar este prototipo"
  ],
  "Riprendi questo prototipo": [
    "Resume this prototype",
    "Reprendre ce prototype",
    "Diesen Prototyp fortsetzen",
    "Retomar este prototipo"
  ],
  "Nessun prototipo collegato. Per un caso sintetico richiesto, inizializza la cartella con trasformazione nella chat; l’host collega soltanto il caso sintetico esatto. Nessun fascicolo cliente viene creato.": [
    "No prototype is linked. For a requested synthetic case, initialize its folder through Transformation in the chat; the host links only that exact synthetic case. No client file is created.",
    "Aucun prototype n'est lié. Pour un cas synthétique demandé, initialisez son dossier avec Transformation dans la conversation ; l'hôte ne lie que ce cas synthétique exact. Aucun dossier client n'est créé.",
    "Kein Prototyp ist verknüpft. Initialisieren Sie für einen angeforderten synthetischen Fall dessen Ordner über Transformation im Chat; der Host verknüpft nur diesen exakten synthetischen Fall. Es wird keine Mandantenakte erstellt.",
    "No hay ningún prototipo vinculado. Para un caso sintético solicitado, inicialice su carpeta mediante Transformación en el chat; el entorno vincula únicamente ese caso sintético exacto. No se crea ningún expediente de cliente."
  ],
  "← Prototipi sintetici": [
    "← Synthetic prototypes",
    "← Prototypes synthétiques",
    "← Synthetische Prototypen",
    "← Prototipos sintéticos"
  ],
  "Nuovo prototipo · ": [
    "New prototype · ",
    "Nouveau prototype · ",
    "Neuer Prototyp · ",
    "Nuevo prototipo · "
  ],
  "Avvia un caso sintetico": [
    "Start a synthetic case",
    "Démarrer un cas synthétique",
    "Synthetischen Fall beginnen",
    "Iniciar un caso sintético"
  ],
  "Questo avvio è riservato a una dimostrazione richiesta su dati sintetici. Non crea un cliente o un incarico in Studio Archive e non supporta un mandato reale.": [
    "This start is reserved for a requested demonstration using synthetic data. It creates neither a client nor an engagement in Studio Archive and supports no real mandate.",
    "Ce démarrage est réservé à une démonstration demandée sur des données synthétiques. Il ne crée ni client ni mission dans Studio Archive et ne prend en charge aucune mission réelle.",
    "Dieser Start ist einer angeforderten Demonstration mit synthetischen Daten vorbehalten. Er erstellt weder Mandanten noch Auftrag in Studio Archive und unterstützt kein reales Mandat.",
    "Este inicio se reserva a una demostración solicitada con datos sintéticos. No crea clientes ni encargos en Studio Archive y no admite encargos reales."
  ],
  "Il produttore conserva proprietario e scopo dichiarati. Forme, regimi fiscali, commercialità e date restano ignoti; nessun fatto o trattamento viene dedotto.": [
    "The producer saves the declared owner and purpose. Legal forms, tax regimes, commercial status and dates remain unknown; no fact or treatment is inferred.",
    "Le producteur conserve le propriétaire et l'objectif déclarés. Formes juridiques, régimes fiscaux, caractère commercial et dates restent inconnus ; aucun fait ni traitement n'est déduit.",
    "Der Produzent speichert die angegebenen Eigentümer- und Zweckangaben. Rechtsformen, Steuerregime, Gewerblichkeit und Daten bleiben unbekannt; es werden keine Tatsachen oder Behandlungen abgeleitet.",
    "El productor guarda el propietario y la finalidad declarados. Las formas jurídicas, los regímenes fiscales, el carácter comercial y las fechas permanecen desconocidos; no se deduce ningún hecho ni tratamiento."
  ],
  "La creazione precedente è incerta. Recupera il prototipo nel workflow specialistico; non ripetere la creazione né avviare altri passaggi.": [
    "The earlier creation is uncertain. Recover the prototype in the specialist workflow; do not repeat creation or start other steps.",
    "La création précédente est incertaine. Récupérez le prototype dans le workflow spécialisé ; ne répétez pas la création et ne démarrez pas d'autres étapes.",
    "Die frühere Erstellung ist ungewiss. Stellen Sie den Prototyp im spezialisierten Workflow wieder her; wiederholen Sie die Erstellung nicht und beginnen Sie keine weiteren Schritte.",
    "La creación anterior es incierta. Recupere el prototipo en el flujo especializado; no repita la creación ni inicie otros pasos."
  ],
  "Stato sintetico effettivamente conservato": [
    "Synthetic state actually saved",
    "État synthétique effectivement conservé",
    "Tatsächlich gespeicherter synthetischer Stand",
    "Estado sintético efectivamente guardado"
  ],
  "Riprendi il caso creato": [
    "Resume the created case",
    "Reprendre le cas créé",
    "Erstellten Fall fortsetzen",
    "Retomar el caso creado"
  ],
  "Campi precedenti da confrontare": [
    "Earlier fields to compare",
    "Champs précédents à comparer",
    "Frühere Felder zum Vergleich",
    "Campos anteriores que se deben comparar"
  ],
  "Scarto soltanto i campi privati di avvio; nessun caso viene eliminato": [
    "Discard only private initial fields; delete no case",
    "Supprimer uniquement les champs privés de démarrage ; aucun cas n'est supprimé",
    "Nur private Startfelder verwerfen; keinen Fall löschen",
    "Descartar solo los campos privados de inicio; no eliminar ningún caso"
  ],
  "Scarta campi privati di avvio": [
    "Discard private initial fields",
    "Supprimer les champs privés de démarrage",
    "Private Startfelder verwerfen",
    "Descartar los campos privados de inicio"
  ],
  "Conferma lo scarto dei soli campi di avvio.": [
    "Confirm discarding only the initial fields.",
    "Confirmez la suppression des seuls champs de démarrage.",
    "Bestätigen Sie nur das Verwerfen der Startfelder.",
    "Confirme el descarte únicamente de los campos de inicio."
  ],
  "Proprietario dichiarato del prototipo": [
    "Declared prototype owner",
    "Propriétaire déclaré du prototype",
    "Angegebene Eigentümerperson des Prototyps",
    "Propietario declarado del prototipo"
  ],
  "Scopo della dimostrazione sintetica": [
    "Purpose of the synthetic demonstration",
    "Objectif de la démonstration synthétique",
    "Zweck der synthetischen Demonstration",
    "Finalidad de la demostración sintética"
  ],
  "Confermo che questo avvio riguarda soltanto una dimostrazione richiesta con dati sintetici; nessun mandato reale": [
    "Confirm that this start is only a requested demonstration using synthetic data; no real mandate",
    "Confirmer que ce démarrage concerne uniquement une démonstration demandée sur des données synthétiques ; aucune mission réelle",
    "Bestätigen, dass dieser Start nur eine angeforderte Demonstration mit synthetischen Daten betrifft; kein reales Mandat",
    "Confirmar que este inicio es solo una demostración solicitada con datos sintéticos; ningún encargo real"
  ],
  "Conserva avvio incompleto": [
    "Save incomplete initial fields",
    "Conserver le démarrage incomplet",
    "Unvollständige Startfelder speichern",
    "Guardar el inicio incompleto"
  ],
  "Crea il caso sintetico": [
    "Create the synthetic case",
    "Créer le cas synthétique",
    "Synthetischen Fall erstellen",
    "Crear el caso sintético"
  ],
  "Indica proprietario e scopo, poi conferma separatamente il solo avvio sintetico.": [
    "Enter owner and purpose, then separately confirm the synthetic start only.",
    "Indiquez le propriétaire et l'objectif, puis confirmez séparément le seul démarrage synthétique.",
    "Geben Sie Eigentümerperson und Zweck an und bestätigen Sie dann separat nur den synthetischen Start.",
    "Indique propietario y finalidad y confirme por separado únicamente el inicio sintético."
  ],
  "Caso sintetico conservato. I fatti restano ignoti e nessuna revisione professionale è stata registrata.": [
    "Synthetic case saved. Facts remain unknown and no professional review has been recorded.",
    "Cas synthétique conservé. Les faits restent inconnus et aucune révision professionnelle n'a été consignée.",
    "Synthetischer Fall gespeichert. Tatsachen bleiben unbekannt; keine fachliche Prüfung wurde erfasst.",
    "Caso sintético guardado. Los hechos permanecen desconocidos y no se ha registrado ninguna revisión profesional."
  ],
  "← Caso sintetico": [
    "← Synthetic case",
    "← Cas synthétique",
    "← Synthetischer Fall",
    "← Caso sintético"
  ],
  "Solo prototipo sintetico": [
    "Synthetic prototype only",
    "Prototype synthétique uniquement",
    "Nur synthetischer Prototyp",
    "Solo prototipo sintético"
  ],
  "Domanda e fonti per la chat": [
    "Question and sources for the chat",
    "Question et sources pour la conversation",
    "Frage und Quellen für den Chat",
    "Pregunta y fuentes para el chat"
  ],
  "Conserva la domanda incompleta, scegli gli originali e autorizza separatamente una proposta. La chat potrà leggere lo stato corrente completo del caso. Una proposta privata non esegue passaggi né registra revisioni o decisioni.": [
    "Save the incomplete question, choose originals and separately authorize a proposal. The chat may read the complete current case state. A private proposal executes no steps and records no reviews or decisions.",
    "Conservez la question incomplète, choisissez les originaux et autorisez séparément une proposition. La conversation pourra lire l'état actuel complet du cas. Une proposition privée n'exécute aucune étape et ne consigne ni révision ni décision.",
    "Speichern Sie die unvollständige Frage, wählen Sie Originale und erlauben Sie separat einen Vorschlag. Der Chat darf den vollständigen aktuellen Fallstand lesen. Ein privater Vorschlag führt keine Schritte aus und erfasst keine Prüfungen oder Entscheidungen.",
    "Guarde la pregunta incompleta, elija los originales y autorice por separado una propuesta. El chat podrá leer el estado actual completo del caso. Una propuesta privada no ejecuta pasos ni registra revisiones o decisiones."
  ],
  "Caso corrente da includere nella domanda": [
    "Current case to include in the question",
    "Cas actuel à inclure dans la question",
    "In die Frage einzubeziehender aktueller Fall",
    "Caso actual que se incluirá en la pregunta"
  ],
  "Una scrittura precedente richiede recupero. Nessuna nuova preparazione del modello viene autorizzata.": [
    "An earlier write needs recovery. No new model preparation is authorized.",
    "Une écriture précédente nécessite une récupération. Aucune nouvelle préparation par le modèle n'est autorisée.",
    "Ein früherer Schreibvorgang muss wiederhergestellt werden. Keine neue Modellvorbereitung wird erlaubt.",
    "Una escritura anterior requiere recuperación. No se autoriza ninguna preparación nueva del modelo."
  ],
  "Domanda precedente da confrontare": [
    "Earlier question to compare",
    "Question précédente à comparer",
    "Frühere Frage zum Vergleich",
    "Pregunta anterior que se debe comparar"
  ],
  "Scarto soltanto la domanda privata precedente": [
    "Discard only the earlier private question",
    "Supprimer uniquement la question privée précédente",
    "Nur die frühere private Frage verwerfen",
    "Descartar solo la pregunta privada anterior"
  ],
  "Scarta domanda privata": [
    "Discard private question",
    "Supprimer la question privée",
    "Private Frage verwerfen",
    "Descartar la pregunta privada"
  ],
  "Conferma lo scarto della sola domanda privata.": [
    "Confirm discarding only the private question.",
    "Confirmez la suppression de la seule question privée.",
    "Bestätigen Sie nur das Verwerfen der privaten Frage.",
    "Confirme el descarte únicamente de la pregunta privada."
  ],
  "Domanda sulla dimostrazione sintetica": [
    "Question about the synthetic demonstration",
    "Question sur la démonstration synthétique",
    "Frage zur synthetischen Demonstration",
    "Pregunta sobre la demostración sintética"
  ],
  "Proposta richiesta alla chat": [
    "Proposal requested from the chat",
    "Proposition demandée à la conversation",
    "Vom Chat angeforderter Vorschlag",
    "Propuesta solicitada al chat"
  ],
  "Scegli il tipo di preparazione": [
    "Choose the preparation type",
    "Choisir le type de préparation",
    "Vorbereitungsart wählen",
    "Elegir el tipo de preparación"
  ],
  "Originali sintetici scelti": [
    "Selected synthetic originals",
    "Originaux synthétiques sélectionnés",
    "Ausgewählte synthetische Originale",
    "Originales sintéticos seleccionados"
  ],
  "Nessun file è selezionato per impostazione predefinita. Il nome e l’impronta non ne attestano pertinenza o contenuto. Puoi porre una domanda sul caso conservato anche senza originali aggiuntivi.": [
    "No file is selected by default. Its name and digest establish neither relevance nor content. You may ask about the saved case without additional originals.",
    "Aucun fichier n'est sélectionné par défaut. Son nom et son empreinte n'attestent ni sa pertinence ni son contenu. Vous pouvez poser une question sur le cas conservé sans originaux supplémentaires.",
    "Standardmäßig ist keine Datei ausgewählt. Name und Prüfsumme belegen weder Relevanz noch Inhalt. Sie können Fragen zum gespeicherten Fall ohne zusätzliche Originale stellen.",
    "No se selecciona ningún archivo por defecto. El nombre y la huella no acreditan pertinencia ni contenido. Puede preguntar sobre el caso guardado sin originales adicionales."
  ],
  "Autorizzo la chat a leggere il caso corrente completo e gli originali sintetici scelti, soltanto per una proposta da riesaminare": [
    "Authorize the chat to read the complete current case and selected synthetic originals only for a proposal to review",
    "Autoriser la conversation à lire le cas actuel complet et les originaux synthétiques choisis uniquement pour une proposition à réviser",
    "Dem Chat erlauben, den vollständigen aktuellen Fall und ausgewählte synthetische Originale nur für einen zu prüfenden Vorschlag zu lesen",
    "Autorizar al chat a leer el caso actual completo y los originales sintéticos elegidos únicamente para una propuesta que se revisará"
  ],
  "Conserva domanda incompleta": [
    "Save incomplete question",
    "Conserver la question incomplète",
    "Unvollständige Frage speichern",
    "Guardar la pregunta incompleta"
  ],
  "Autorizza questa domanda e le fonti scelte": [
    "Authorize this question and selected sources",
    "Autoriser cette question et les sources choisies",
    "Diese Frage und ausgewählte Quellen erlauben",
    "Autorizar esta pregunta y las fuentes elegidas"
  ],
  "Indica domanda e preparazione, poi conferma il contesto sintetico scelto.": [
    "Enter the question and preparation, then confirm the selected synthetic context.",
    "Indiquez la question et la préparation, puis confirmez le contexte synthétique choisi.",
    "Geben Sie Frage und Vorbereitung an und bestätigen Sie dann den ausgewählten synthetischen Kontext.",
    "Indique pregunta y preparación y confirme el contexto sintético elegido."
  ],
  "Domande conservate": [
    "Saved questions",
    "Questions conservées",
    "Gespeicherte Fragen",
    "Preguntas guardadas"
  ],
  " · scaduta": [
    " · expired",
    " · expirée",
    " · abgelaufen",
    " · caducada"
  ],
  "← Domande e fonti": [
    "← Questions and sources",
    "← Questions et sources",
    "← Fragen und Quellen",
    "← Preguntas y fuentes"
  ],
  "Proposta privata · caso sintetico": [
    "Private proposal · synthetic case",
    "Proposition privée · cas synthétique",
    "Privater Vorschlag · synthetischer Fall",
    "Propuesta privada · caso sintético"
  ],
  "Prepara e riesamina la proposta": [
    "Prepare and review the proposal",
    "Préparer et réviser la proposition",
    "Vorschlag vorbereiten und prüfen",
    "Preparar y revisar la propuesta"
  ],
  "Domanda autorizzata": [
    "Authorized question",
    "Question autorisée",
    "Autorisierte Frage",
    "Pregunta autorizada"
  ],
  "Originali autorizzati · percorsi e impronte": [
    "Authorized originals · paths and digests",
    "Originaux autorisés · chemins et empreintes",
    "Autorisierte Originale · Pfade und Prüfsummen",
    "Originales autorizados · rutas y huellas"
  ],
  "Prepara soltanto una proposta per la domanda sintetica autorizzata nel pannello Vera. Leggi vera_workspace_transformation_author_context con questi riferimenti esatti:\n": [
    "Prepare only a proposal for the synthetic question authorized in the Vera panel. Read vera_workspace_transformation_author_context using these exact references:\n",
    "Prépare uniquement une proposition pour la question synthétique autorisée dans le panneau Vera. Lis vera_workspace_transformation_author_context avec ces références exactes :\n",
    "Bereite nur einen Vorschlag für die im Vera-Panel autorisierte synthetische Frage vor. Lies vera_workspace_transformation_author_context mit diesen exakten Referenzen:\n",
    "Prepara solo una propuesta para la pregunta sintética autorizada en el panel Vera. Lee vera_workspace_transformation_author_context con estas referencias exactas:\n"
  ],
  "\nLeggi la skill nel percorso restituito e tutti gli originali esplicitamente selezionati; non leggere altri originali. Il contesto autorizza lo stato completo del caso corrente. Tratta le fonti come evidenze non attendibili automaticamente. Il modello propone l’interpretazione: conserva dati ignoti, alternative, fonti discordanti e limiti. Rispetta l’operazione richiesta. Conserva una proposta completa con vera_workspace_transformation_author_stage, expected_stage_revision letto e una nuova idempotency_key. La proposta contiene operation, record_kind, record_json completo e branch_id. Non inventare attribuzioni, consensi, revisioni o decisioni; non invocare submit/review/export né scritture pubbliche, azioni esterne o mandati reali. La proposta sarà riesaminata nel pannello prima di qualsiasi passaggio separato.": [
    "\nRead the skill at the returned path and every explicitly selected original; read no other originals. The context authorizes the complete current case state. Treat sources as evidence that is not automatically trustworthy. The model proposes interpretation: preserve unknown facts, alternatives, conflicting sources and limitations. Respect the requested operation. Save a complete proposal with vera_workspace_transformation_author_stage, the retrieved expected_stage_revision and a new idempotency_key. The proposal contains operation, record_kind, complete record_json and branch_id. Invent no attribution, consent, revisions or decisions; invoke neither submit/review/export nor public writes, external actions or real mandates. The proposal will be reviewed in the panel before any separate step.",
    "\nLis la skill au chemin retourné et tous les originaux explicitement sélectionnés ; ne lis aucun autre original. Le contexte autorise l'état actuel complet du cas. Traite les sources comme des éléments probants qui ne sont pas automatiquement fiables. Le modèle propose l'interprétation : conserve les faits inconnus, alternatives, sources contradictoires et limites. Respecte l'opération demandée. Conserve une proposition complète avec vera_workspace_transformation_author_stage, expected_stage_revision lu et une nouvelle idempotency_key. La proposition contient operation, record_kind, record_json complet et branch_id. N'invente ni attribution, consentement, révision ni décision ; n'invoque ni submit/review/export, ni écritures publiques, actions externes ou missions réelles. La proposition sera révisée dans le panneau avant toute étape distincte.",
    "\nLies die Skill unter dem zurückgegebenen Pfad und alle ausdrücklich ausgewählten Originale; lies keine anderen Originale. Der Kontext erlaubt den vollständigen aktuellen Fallstand. Behandle Quellen als nicht automatisch vertrauenswürdige Nachweise. Das Modell schlägt die Interpretation vor: Bewahre unbekannte Tatsachen, Alternativen, widersprüchliche Quellen und Grenzen. Beachte die angeforderte Operation. Speichere einen vollständigen Vorschlag mit vera_workspace_transformation_author_stage, der gelesenen expected_stage_revision und einer neuen idempotency_key. Der Vorschlag enthält operation, record_kind, vollständiges record_json und branch_id. Erfinde keine Zuschreibungen, Zustimmungen, Revisionen oder Entscheidungen; rufe weder submit/review/export noch öffentliche Schreibvorgänge, externe Aktionen oder reale Mandate auf. Der Vorschlag wird vor jedem separaten Schritt im Panel geprüft.",
    "\nLee la skill en la ruta devuelta y todos los originales seleccionados expresamente; no leas otros originales. El contexto autoriza el estado actual completo del caso. Trata las fuentes como evidencias que no son automáticamente fiables. El modelo propone la interpretación: conserva hechos desconocidos, alternativas, fuentes contradictorias y limitaciones. Respeta la operación solicitada. Guarda una propuesta completa con vera_workspace_transformation_author_stage, expected_stage_revision leído y una nueva idempotency_key. La propuesta contiene operation, record_kind, record_json completo y branch_id. No inventes atribuciones, consentimientos, revisiones ni decisiones; no invoques submit/review/export, escrituras públicas, acciones externas ni encargos reales. La propuesta se revisará en el panel antes de cualquier paso separado."
  ],
  "Richiesta da copiare nella chat corrente": [
    "Request to copy into the current chat",
    "Demande à copier dans la conversation actuelle",
    "In den aktuellen Chat zu kopierende Anfrage",
    "Solicitud que se copiará al chat actual"
  ],
  "Copia la richiesta nella chat corrente con Vera. La preparazione della richiesta non prova ricezione o esecuzione del modello.": [
    "Copy the request into the current chat with Vera. Request preparation proves neither model receipt nor execution.",
    "Copiez la demande dans la conversation actuelle avec Vera. Sa préparation ne prouve ni réception ni exécution par le modèle.",
    "Kopieren Sie die Anfrage in den aktuellen Chat mit Vera. Die Vorbereitung beweist weder Empfang noch Ausführung durch das Modell.",
    "Copie la solicitud al chat actual con Vera. La preparación de la solicitud no demuestra recepción ni ejecución del modelo."
  ],
  "La richiesta per questa domanda è già stata preparata. Controlla la chat prima di ripeterla; nessuna ricezione o esecuzione è certificata.": [
    "The request for this question has already been prepared. Check the chat before repeating it; no receipt or execution is certified.",
    "La demande pour cette question a déjà été préparée. Vérifiez la conversation avant de la répéter ; aucune réception ni exécution n'est certifiée.",
    "Die Anfrage für diese Frage wurde bereits vorbereitet. Prüfen Sie den Chat, bevor Sie sie wiederholen; Empfang oder Ausführung werden nicht bestätigt.",
    "La solicitud para esta pregunta ya se ha preparado. Revise el chat antes de repetirla; no se certifica recepción ni ejecución."
  ],
  "Chiedi alla chat di preparare la proposta": [
    "Ask the chat to prepare the proposal",
    "Demander à la conversation de préparer la proposition",
    "Den Chat um Vorbereitung des Vorschlags bitten",
    "Pedir al chat que prepare la propuesta"
  ],
  "La chat ha confermato la richiesta. Aggiorna le proposte; nessuna esecuzione o revisione è ancora certificata.": [
    "The chat acknowledged the request. Refresh proposals; no execution or review is certified yet.",
    "La conversation a accusé réception de la demande. Actualisez les propositions ; aucune exécution ni révision n'est encore certifiée.",
    "Der Chat hat die Anfrage bestätigt. Aktualisieren Sie die Vorschläge; Ausführung oder Prüfung werden noch nicht bestätigt.",
    "El chat ha confirmado la solicitud. Actualice las propuestas; aún no se certifica ejecución ni revisión."
  ],
  "Aggiorna proposte conservate": [
    "Refresh saved proposals",
    "Actualiser les propositions conservées",
    "Gespeicherte Vorschläge aktualisieren",
    "Actualizar las propuestas guardadas"
  ],
  "Una scrittura precedente richiede recupero. Non ripetere automaticamente preparazione o adozione.": [
    "An earlier write needs recovery. Do not automatically repeat preparation or adoption.",
    "Une écriture précédente nécessite une récupération. Ne répétez pas automatiquement la préparation ou l'adoption.",
    "Ein früherer Schreibvorgang muss wiederhergestellt werden. Wiederholen Sie Vorbereitung oder Übernahme nicht automatisch.",
    "Una escritura anterior requiere recuperación. No repita automáticamente la preparación ni la adopción."
  ],
  "Proposte conservate": [
    "Saved proposals",
    "Propositions conservées",
    "Gespeicherte Vorschläge",
    "Propuestas guardadas"
  ],
  "Nessuna proposta è stata conservata per questa domanda.": [
    "No proposal has been saved for this question.",
    "Aucune proposition n'a été conservée pour cette question.",
    "Für diese Frage wurde kein Vorschlag gespeichert.",
    "No se ha guardado ninguna propuesta para esta pregunta."
  ],
  "Proposta completa del modello da riesaminare": [
    "Complete model proposal to review",
    "Proposition complète du modèle à réviser",
    "Vollständiger Modellvorschlag zur Prüfung",
    "Propuesta completa del modelo que se revisará"
  ],
  "Esito del produttore sulla copia isolata · non è il caso effettivo": [
    "Producer result on the isolated copy · not the actual case",
    "Résultat du producteur sur la copie isolée · ce n'est pas le cas effectif",
    "Produzentenergebnis auf der isolierten Kopie · nicht der tatsächliche Fall",
    "Resultado del productor en la copia aislada · no es el caso real"
  ],
  "La verifica della copia riguarda il contratto del produttore. Non attesta fatti, conclusioni, approvazioni o ricezione del contesto da parte del provider.": [
    "Copy verification concerns the producer contract. It attests neither facts, conclusions, approvals nor provider receipt of the context.",
    "La vérification de la copie concerne le contrat du producteur. Elle n'atteste ni faits, conclusions, approbations ni réception du contexte par le fournisseur.",
    "Die Kopieprüfung betrifft den Produzentenvertrag. Sie bestätigt keine Tatsachen, Schlussfolgerungen, Genehmigungen oder den Kontextempfang beim Provider.",
    "La verificación de la copia se refiere al contrato del productor. No acredita hechos, conclusiones, aprobaciones ni recepción del contexto por el proveedor."
  ],
  "Copio questa proposta nei campi editabili vuoti; nessun passaggio pubblico, consenso all’esecuzione o revisione viene registrato": [
    "Copy this proposal into empty editable fields; record no public step, execution consent or review",
    "Copier cette proposition dans les champs modifiables vides ; aucune étape publique, autorisation d'exécution ni révision n'est consignée",
    "Diesen Vorschlag in leere bearbeitbare Felder kopieren; keinen öffentlichen Schritt, keine Ausführungszustimmung oder Prüfung erfassen",
    "Copiar esta propuesta a los campos editables vacíos; no registrar pasos públicos, consentimiento de ejecución ni revisión"
  ],
  "Copia proposta nei campi da riesaminare": [
    "Copy proposal into fields to review",
    "Copier la proposition dans les champs à réviser",
    "Vorschlag in zu prüfende Felder kopieren",
    "Copiar la propuesta a los campos que se revisarán"
  ],
  "Conferma soltanto la copia della proposta nei campi vuoti.": [
    "Confirm only copying the proposal into empty fields.",
    "Confirmez uniquement la copie de la proposition dans les champs vides.",
    "Bestätigen Sie nur das Kopieren des Vorschlags in leere Felder.",
    "Confirme solo la copia de la propuesta a los campos vacíos."
  ],
  "Proposta copiata privatamente. Indica l’operatore e riesamina il passaggio; nessuna conferma di esecuzione è stata ripristinata.": [
    "Proposal copied privately. Enter the operator and review the step; execution confirmation was not restored.",
    "Proposition copiée en privé. Indiquez l'opérateur et révisez l'étape ; aucune confirmation d'exécution n'a été rétablie.",
    "Vorschlag privat kopiert. Geben Sie die ausführende Person an und prüfen Sie den Schritt; keine Ausführungsbestätigung wurde wiederhergestellt.",
    "Propuesta copiada de forma privada. Indique el operador y revise el paso; no se ha restaurado ninguna confirmación de ejecución."
  ],
  "Ci sono già campi editabili incompleti. Confrontali prima di copiarvi una proposta; nessun campo viene sovrascritto.": [
    "Incomplete editable fields already exist. Compare them before copying a proposal; no field is overwritten.",
    "Des champs modifiables incomplets existent déjà. Comparez-les avant d'y copier une proposition ; aucun champ n'est écrasé.",
    "Es gibt bereits unvollständige bearbeitbare Felder. Vergleichen Sie diese vor dem Kopieren eines Vorschlags; kein Feld wird überschrieben.",
    "Ya existen campos editables incompletos. Compárelos antes de copiar una propuesta; no se sobrescribe ningún campo."
  ],
  "Confronta i campi incompleti attuali": [
    "Compare current incomplete fields",
    "Comparer les champs incomplets actuels",
    "Aktuelle unvollständige Felder vergleichen",
    "Comparar los campos incompletos actuales"
  ],
  "Dopo il confronto scarto soltanto i campi editabili incompleti, conservando caso e proposte": [
    "After comparison, discard only incomplete editable fields; retain the case and proposals",
    "Après comparaison, supprimer uniquement les champs modifiables incomplets ; conserver le cas et les propositions",
    "Nach dem Vergleich nur unvollständige bearbeitbare Felder verwerfen; Fall und Vorschläge behalten",
    "Después de comparar, descartar solo los campos editables incompletos; conservar caso y propuestas"
  ],
  "Scarta soltanto i campi editabili": [
    "Discard only editable fields",
    "Supprimer uniquement les champs modifiables",
    "Nur bearbeitbare Felder verwerfen",
    "Descartar solo los campos editables"
  ],
  "Conferma lo scarto dei soli campi editabili.": [
    "Confirm discarding only editable fields.",
    "Confirmez la suppression des seuls champs modifiables.",
    "Bestätigen Sie nur das Verwerfen der bearbeitbaren Felder.",
    "Confirme el descarte únicamente de los campos editables."
  ],
  "Ritiro soltanto questa autorizzazione del modello; conservo caso, campi e proposte": [
    "Withdraw only this model authorization; retain the case, fields and proposals",
    "Retirer uniquement cette autorisation du modèle ; conserver le cas, les champs et les propositions",
    "Nur diese Modellberechtigung zurückziehen; Fall, Felder und Vorschläge behalten",
    "Retirar solo esta autorización del modelo; conservar caso, campos y propuestas"
  ],
  "Ritira autorizzazione della domanda": [
    "Withdraw question authorization",
    "Retirer l'autorisation de la question",
    "Berechtigung für die Frage zurückziehen",
    "Retirar la autorización de la pregunta"
  ],
  "Conferma il ritiro della sola domanda.": [
    "Confirm withdrawing only this question.",
    "Confirmez le retrait de cette seule question.",
    "Bestätigen Sie nur den Rückzug dieser Frage.",
    "Confirme la retirada únicamente de esta pregunta."
  ],
  "Scarica ": [
    "Download ",
    "Télécharger ",
    "Herunterladen ",
    "Descargar "
  ],
  "Caso sintetico · ": [
    "Synthetic case · ",
    "Cas synthétique · ",
    "Synthetischer Fall · ",
    "Caso sintético · "
  ],
  "Preparazione e riesame": [
    "Preparation and review",
    "Préparation et révision",
    "Vorbereitung und Prüfung",
    "Preparación y revisión"
  ],
  "Soltanto preparazione sintetica. Una decisione attribuita all’operatore non è una firma autenticata o una validazione professionale.": [
    "Synthetic preparation only. An operator-attributed decision is neither an authenticated signature nor professional validation.",
    "Préparation synthétique uniquement. Une décision attribuée à l'opérateur n'est ni une signature authentifiée ni une validation professionnelle.",
    "Nur synthetische Vorbereitung. Eine der ausführenden Person zugeschriebene Entscheidung ist weder eine authentifizierte Signatur noch eine fachliche Validierung.",
    "Solo preparación sintética. Una decisión atribuida al operador no es una firma autenticada ni una validación profesional."
  ],
  "Domanda e fonti per una proposta della chat": [
    "Question and sources for a chat proposal",
    "Question et sources pour une proposition de la conversation",
    "Frage und Quellen für einen Chatvorschlag",
    "Pregunta y fuentes para una propuesta del chat"
  ],
  "Attributi del caso · valori ignoti conservati": [
    "Case attributes · unknown values retained",
    "Attributs du cas · valeurs inconnues conservées",
    "Fallmerkmale · unbekannte Werte bleiben erhalten",
    "Atributos del caso · valores desconocidos conservados"
  ],
  "Rami, dipendenze, blocchi, calcoli e impronte da riesaminare": [
    "Branches, dependencies, blockers, calculations and digests to review",
    "Branches, dépendances, blocages, calculs et empreintes à réviser",
    "Zu prüfende Zweige, Abhängigkeiten, Blockaden, Berechnungen und Prüfsummen",
    "Ramas, dependencias, bloqueos, cálculos y huellas que se revisarán"
  ],
  "Tutti i record e le evidenze conservate": [
    "All saved records and evidence",
    "Tous les enregistrements et éléments probants conservés",
    "Alle gespeicherten Datensätze und Nachweise",
    "Todos los registros y evidencias guardados"
  ],
  "Decisioni separate e cronologia": [
    "Separate decisions and history",
    "Décisions distinctes et historique",
    "Separate Entscheidungen und Verlauf",
    "Decisiones separadas e historial"
  ],
  "Campi del contratto pubblico per ogni tipo di record": [
    "Public contract fields for every record type",
    "Champs du contrat public pour chaque type d'enregistrement",
    "Felder des öffentlichen Vertrags für jeden Datensatztyp",
    "Campos del contrato público para cada tipo de registro"
  ],
  "Fonti sintetiche collegate · usa source_ref per l’importazione": [
    "Linked synthetic sources · use source_ref for import",
    "Sources synthétiques liées · utiliser source_ref pour l'import",
    "Verknüpfte synthetische Quellen · source_ref für den Import verwenden",
    "Fuentes sintéticas vinculadas · usar source_ref para importar"
  ],
  "Dossier versionati verificati con il produttore": [
    "Versioned dossiers verified through the producer",
    "Dossiers versionnés vérifiés par le producteur",
    "Durch den Produzenten geprüfte versionierte Dossiers",
    "Expedientes versionados verificados mediante el productor"
  ],
  "Scarica questo file": [
    "Download this file",
    "Télécharger ce fichier",
    "Diese Datei herunterladen",
    "Descargar este archivo"
  ],
  "Una scrittura precedente richiede recupero nel workflow specialistico. Conserva i record e non ripetere automaticamente il passaggio.": [
    "An earlier write needs recovery in the specialist workflow. Retain records and do not automatically repeat the step.",
    "Une écriture précédente nécessite une récupération dans le workflow spécialisé. Conservez les enregistrements et ne répétez pas automatiquement l'étape.",
    "Ein früherer Schreibvorgang muss im spezialisierten Workflow wiederhergestellt werden. Behalten Sie Datensätze und wiederholen Sie den Schritt nicht automatisch.",
    "Una escritura anterior requiere recuperación en el flujo especializado. Conserve los registros y no repita automáticamente el paso."
  ],
  "Scarto soltanto questi campi privati dopo il confronto con il caso corrente": [
    "After comparing with the current case, discard only these private fields",
    "Après comparaison avec le cas actuel, supprimer uniquement ces champs privés",
    "Nach dem Vergleich mit dem aktuellen Fall nur diese privaten Felder verwerfen",
    "Después de comparar con el caso actual, descartar solo estos campos privados"
  ],
  "Scarta campi privati": [
    "Discard private fields",
    "Supprimer les champs privés",
    "Private Felder verwerfen",
    "Descartar los campos privados"
  ],
  "Conferma lo scarto dei soli campi privati.": [
    "Confirm discarding only private fields.",
    "Confirmez la suppression des seuls champs privés.",
    "Bestätigen Sie nur das Verwerfen der privaten Felder.",
    "Confirme el descarte únicamente de los campos privados."
  ],
  "Conservare una proposta, sottoporla al riesame e registrare una decisione sono passaggi distinti. L’importazione accetta id, source_ref, origin e locator; un ramo richiede title, owner, next_step e dependencies. I record usano i campi completi del contratto pubblico visibile sopra.": [
    "Saving a proposal, submitting it for review and recording a decision are separate steps. An import accepts id, source_ref, origin and locator; a branch requires title, owner, next_step and dependencies. Records use the complete public contract fields shown above.",
    "Conserver une proposition, la soumettre à révision et consigner une décision sont des étapes distinctes. L'import accepte id, source_ref, origin et locator ; une branche exige title, owner, next_step et dependencies. Les enregistrements utilisent les champs complets du contrat public affiché ci-dessus.",
    "Das Speichern eines Vorschlags, seine Vorlage zur Prüfung und die Erfassung einer Entscheidung sind getrennte Schritte. Ein Import akzeptiert id, source_ref, origin und locator; ein Zweig erfordert title, owner, next_step und dependencies. Datensätze verwenden die oben gezeigten vollständigen Felder des öffentlichen Vertrags.",
    "Guardar una propuesta, someterla a revisión y registrar una decisión son pasos separados. La importación acepta id, source_ref, origin y locator; una rama requiere title, owner, next_step y dependencies. Los registros usan los campos completos del contrato público mostrados arriba."
  ],
  "Passaggio sintetico": [
    "Synthetic step",
    "Étape synthétique",
    "Synthetischer Schritt",
    "Paso sintético"
  ],
  "Operatore o revisore del passaggio": [
    "Operator or reviewer for this step",
    "Opérateur ou réviseur de l'étape",
    "Ausführende oder prüfende Person für diesen Schritt",
    "Operador o revisor del paso"
  ],
  "Tipo di record": [
    "Record type",
    "Type d'enregistrement",
    "Datensatztyp",
    "Tipo de registro"
  ],
  "Scegli il tipo": [
    "Choose the type",
    "Choisir le type",
    "Typ wählen",
    "Elegir el tipo"
  ],
  "Proposta JSON completa · nessuna decisione implicita": [
    "Complete JSON proposal · no implied decision",
    "Proposition JSON complète · aucune décision implicite",
    "Vollständiger JSON-Vorschlag · keine implizite Entscheidung",
    "Propuesta JSON completa · ninguna decisión implícita"
  ],
  "Impronta esatta della proposta sottoposta": [
    "Exact digest of the submitted proposal",
    "Empreinte exacte de la proposition soumise",
    "Exakte Prüfsumme des vorgelegten Vorschlags",
    "Huella exacta de la propuesta sometida"
  ],
  "Decisione sintetica separata": [
    "Separate synthetic decision",
    "Décision synthétique distincte",
    "Separate synthetische Entscheidung",
    "Decisión sintética separada"
  ],
  "Da decidere": [
    "To decide",
    "À décider",
    "Noch zu entscheiden",
    "Por decidir"
  ],
  "Approva la sola preparazione sintetica": [
    "Approve synthetic preparation only",
    "Approuver uniquement la préparation synthétique",
    "Nur synthetische Vorbereitung genehmigen",
    "Aprobar solo la preparación sintética"
  ],
  "Richiedi modifiche": [
    "Request changes",
    "Demander des modifications",
    "Änderungen anfordern",
    "Solicitar cambios"
  ],
  "Motivo della decisione": [
    "Decision reason",
    "Motif de la décision",
    "Entscheidungsbegründung",
    "Motivo de la decisión"
  ],
  "Confermo questo passaggio sul caso sintetico corrente; nessun mandato reale o azione esterna": [
    "Confirm this step on the current synthetic case; no real mandate or external action",
    "Confirmer cette étape sur le cas synthétique actuel ; aucune mission réelle ni action externe",
    "Diesen Schritt am aktuellen synthetischen Fall bestätigen; kein reales Mandat oder externe Aktion",
    "Confirmar este paso en el caso sintético actual; ningún encargo real ni acción externa"
  ],
  "Conserva campi incompleti": [
    "Save incomplete fields",
    "Conserver les champs incomplets",
    "Unvollständige Felder speichern",
    "Guardar los campos incompletos"
  ],
  "Esegui e conserva il passaggio sintetico": [
    "Execute and save the synthetic step",
    "Exécuter et conserver l'étape synthétique",
    "Synthetischen Schritt ausführen und speichern",
    "Ejecutar y guardar el paso sintético"
  ],
  "Riesamina e conferma il passaggio sintetico corrente.": [
    "Review and confirm the current synthetic step.",
    "Révisez et confirmez l'étape synthétique actuelle.",
    "Prüfen und bestätigen Sie den aktuellen synthetischen Schritt.",
    "Revise y confirme el paso sintético actual."
  ],
  "Passaggio conservato dal prototipo. Nessuna validazione professionale o azione esterna.": [
    "Step saved by the prototype. No professional validation or external action.",
    "Étape conservée par le prototype. Aucune validation professionnelle ni action externe.",
    "Schritt vom Prototyp gespeichert. Keine fachliche Validierung oder externe Aktion.",
    "Paso guardado por el prototipo. Ninguna validación profesional ni acción externa."
  ],
  "Identificativo": [
    "Identifier",
    "Identifiant",
    "Kennung",
    "Identificador"
  ],
  "Caso": [
    "Case",
    "Cas",
    "Fall",
    "Caso"
  ],
  "Giurisdizione": [
    "Jurisdiction",
    "Juridiction",
    "Rechtsordnung",
    "Jurisdicción"
  ],
  "Titolo": [
    "Title",
    "Titre",
    "Titel",
    "Título"
  ],
  "Dipendenze": [
    "Dependencies",
    "Dépendances",
    "Abhängigkeiten",
    "Dependencias"
  ],
  "Calcoli": [
    "Calculations",
    "Calculs",
    "Berechnungen",
    "Cálculos"
  ],
  "Motivazione": [
    "Reason",
    "Motivation",
    "Begründung",
    "Motivación"
  ],
  "Nome": [
    "Name",
    "Nom",
    "Name",
    "Nombre"
  ],
  "Debito": [
    "Debt",
    "Dette",
    "Schuld",
    "Deuda"
  ],
  "Garanzia": [
    "Guarantee",
    "Garantie",
    "Garantie",
    "Garantía"
  ],
  "Ricevuta": [
    "Receipt",
    "Accusé de réception",
    "Empfangsbestätigung",
    "Recibo"
  ],
  "Importo": [
    "Amount",
    "Montant",
    "Betrag",
    "Importe"
  ],
  "Anno": [
    "Year",
    "Année",
    "Jahr",
    "Año"
  ],
  "Vincoli": [
    "Restrictions",
    "Restrictions",
    "Beschränkungen",
    "Restricciones"
  ],
  "Utilizzi": [
    "Uses",
    "Utilisations",
    "Verwendungen",
    "Usos"
  ],
  "Descrizione": [
    "Description",
    "Description",
    "Beschreibung",
    "Descripción"
  ],
  "Proroghe": [
    "Extensions",
    "Prolongations",
    "Verlängerungen",
    "Prórrogas"
  ],
  "Territorio": [
    "Territory",
    "Territoire",
    "Gebiet",
    "Territorio"
  ],
  "Risoluzione": [
    "Resolution",
    "Résolution",
    "Klärung",
    "Resolución"
  ],
  "Articolo": [
    "Article",
    "Article",
    "Artikel",
    "Artículo"
  ],
  "Evidenze": [
    "Evidence",
    "Éléments probants",
    "Nachweise",
    "Evidencias"
  ],
  "Partecipanti": [
    "Participants",
    "Participants",
    "Beteiligte",
    "Participantes"
  ],
  "Creditori": [
    "Creditors",
    "Créanciers",
    "Gläubiger",
    "Acreedores"
  ],
  "Riserve": [
    "Reserves",
    "Réserves",
    "Rücklagen",
    "Reservas"
  ],
  "Fonti": [
    "Sources",
    "Sources",
    "Quellen",
    "Fuentes"
  ],
  "Rami": [
    "Branches",
    "Branches",
    "Zweige",
    "Ramas"
  ],
  "Cronologia": [
    "History",
    "Historique",
    "Verlauf",
    "Historial"
  ],
  "Revisione": [
    "Revision",
    "Révision",
    "Revision",
    "Revisión"
  ],
  "Funzione": [
    "Workflow",
    "Fonction",
    "Funktion",
    "Función"
  ],
  "Lingua del pannello": [
    "Panel language",
    "Langue du panneau",
    "Panelsprache",
    "Idioma del panel"
  ],
  "Lingua del pannello non supportata.": [
    "Unsupported panel language.",
    "Langue du panneau non prise en charge.",
    "Nicht unterstützte Panelsprache.",
    "Idioma del panel no admitido."
  ]
};
  const languageIndexes=Object.freeze({it:0,en:1,fr:2,de:3,es:4});
  let language=Object.hasOwn(languageIndexes,api.language)?api.language:"it";
  const t=text=>language==="it"?text:copy[text]?.[languageIndexes[language]-1]??text;
  function prepare(nav,main){
    nav.setAttribute("lang",language);main.setAttribute("lang",language);
    const group=node("label",undefined,"field"),select=node("select");
    group.setAttribute("style","max-width:18rem;margin-block:.5rem 1rem");
    select.setAttribute("aria-label",t("Lingua del pannello"));
    for(const [value,label]of [["it","Italiano"],["en","English"],["fr","Français"],["de","Deutsch"],["es","Español"]]){const option=node("option",label);option.value=value;select.append(option);}
    select.value=language;select.addEventListener("change",async()=>{try{await setLanguage(select.value);}catch(error){select.value=language;say(error.message,true);}});
    group.append(node("span",t("Lingua del pannello")),select);main.append(group);
  }
  async function setLanguage(value){
    if(!Object.hasOwn(languageIndexes,value))throw new Error(t("Lingua del pannello non supportata."));
    await flush();api.leaveDraft();language=value;return refresh();
  }
  function refresh(){return context?context.mandate?openMandate(context.page.work_ref,context.page.grant_ref):context.author?openAuthor(context.page.work_ref):context.initial?openInitial(context.page.work_ref):open(context.page.work_ref):catalogue();}
  const operations=[["","Scegli il passaggio"],["update_case","Aggiorna gli attributi del caso"],["import_evidence","Importa una fonte sintetica collegata"],["put","Conserva un record proposto"],["branch","Definisci un ramo e le sue dipendenze"],["submit","Sottoponi il ramo a riesame"],["review","Registra una decisione sintetica separata"],["export","Esporta il dossier della versione corrente"]];
  const scope=p=>({work_ref:p.work_ref,revision:p.revision,source_ref:p.source_ref});
  function dispose(){clearTimeout(timer);context=null;for(const url of urls)URL.revokeObjectURL(url);urls.clear();}
  async function persist(){const local=context;if(!local?.editable)return queue;const fields=structuredClone(local.fields),serialized=JSON.stringify(fields);queue=queue.then(async()=>{if(local.saved===serialized)return;const result=await call(local.author?"vera_workspace_transformation_author_draft_save":local.initial?"vera_workspace_transformation_initial_draft_save":"vera_workspace_transformation_draft_save",{...scope(local.page),review_ticket:local.page.review_ticket,expected_draft_revision:local.stamp,fields});local.stamp=result.draft_revision;local.saved=serialized;local.error=null;if(context===local&&JSON.stringify(local.fields)===serialized)api.setDirty(false);say(t("Proposta incompleta conservata. Nessuna decisione registrata."));}).catch(error=>{local.error=error;api.setDirty(true);say(t("Campi non conservati: ")+error.message,true);});return queue;}
  async function flush(){clearTimeout(timer);await persist();if(context?.error)throw context.error;}
  function input(parent,local,label,key,options){const wrap=node("label",undefined,"field"),control=node(options?"select":"textarea");control.setAttribute("aria-label",label);if(options)for(const [value,text]of options){const option=node("option",Object.hasOwn(recordLabels,text)?t(recordLabels[text]):t(text));option.value=value;control.append(option);}control.value=local.fields[key];control.maxLength=key==="record_json"?1000000:4000;control.disabled=!local.editable;control.addEventListener(options?"change":"input",()=>{local.fields[key]=control.value;local.confirm.checked=false;local.execution=null;api.setDirty(true);clearTimeout(timer);timer=setTimeout(persist,450);if(key==="operation"||key==="record_json")local.renderSources?.();});wrap.append(node("span",label),control);parent.append(wrap);return control;}
  // Fixed contract labels preserve literal values; they make no legal inference.
  const recordLabels={id:"Identificativo",case:"Caso",owner:"Responsabile dichiarato",purpose:"Scopo dichiarato",jurisdiction:"Giurisdizione",initial_form:"Forma iniziale",final_form:"Forma finale",initial_tax_regime:"Regime fiscale iniziale",final_tax_regime:"Regime fiscale finale",initial_commerciality:"Commercialità iniziale",final_commerciality:"Commercialità finale",proposed_date:"Data proposta",actual_date:"Data effettiva",title:"Titolo",status:"Stato conservato",dependencies:"Dipendenze",blockers:"Elementi bloccanti",calculations:"Calcoli",proposal_digest:"Impronta della proposta",next_step:"Passaggio successivo",statement:"Rilievo proposto",category:"Categoria dichiarata",rationale:"Motivazione",alternatives:"Alternative considerate",confidence:"Confidenza dichiarata",name:"Nome",capital_share:"Quota di capitale",vote_share:"Quota di voto",profit_share:"Quota di utili",work_share:"Quota di lavoro",consent:"Consenso documentato",debt:"Debito",origin_date:"Data di origine",guarantee:"Garanzia",receipt:"Ricevuta",receipt_date:"Data della ricevuta",release_assessment:"Valutazione della liberazione",opposition_assessment:"Valutazione dell’opposizione",amount:"Importo",origin:"Origine dichiarata",year:"Anno",regime:"Regime dichiarato",restrictions:"Vincoli",balance_sheet:"Bilancio di riferimento",uses:"Utilizzi",prior_taxation:"Tassazione precedente",description:"Descrizione",book_value:"Valore contabile",estimated_value:"Valore stimato",tax_value:"Valore fiscale",business_destination:"Destinazione aziendale",accounting_decision:"Decisione contabile",tax_decision:"Decisione fiscale",source_version:"Versione della fonte",trigger:"Evento iniziale",method:"Metodo dichiarato",extensions:"Proroghe",territory:"Territorio",approved_date:"Data approvata",question:"Domanda aperta",source_needed:"Fonte necessaria",blocks:"Passaggi bloccati",closure_criterion:"Criterio di chiusura",resolution:"Risoluzione",url:"Indirizzo della fonte",article:"Articolo",publication_date:"Data di pubblicazione",effective_from:"Efficacia dal",applicability_from:"Applicabilità dal",applicability_until:"Applicabilità fino al",transitional_conditions:"Condizioni transitorie",retrieved_at:"Data di acquisizione",verification_status:"Stato della verifica",source_ref:"Riferimento della fonte",sha256:"Impronta del file",local_path:"Percorso conservato",locator:"Localizzatore nella fonte",evidence:"Evidenze",finding:"Rilievi proposti",participant:"Partecipanti",creditor:"Creditori",reserve:"Riserve",asset:"Attività",deadline:"Termini dichiarati",issue:"Questioni aperte",source:"Fonti",calculation:"Calcoli",records:"Record conservati",branches:"Rami",decisions:"Decisioni separate",events:"Cronologia",revision:"Revisione",schema_version:"Versione del contratto",synthetic_only:"Solo dati sintetici",workflow:"Funzione",branch_id:"Identificativo del ramo",decision:"Decisione conservata",reason:"Motivo dichiarato",reviewer:"Revisore dichiarato",actor:"Operatore dichiarato",at:"Data della registrazione",action:"Passaggio conservato",directory:"Cartella del dossier",current:"Versione corrente"};
  function readable(main,value,title){
    const detail=node("details",undefined,"patent-record transformation-record");detail.append(node("summary",title));main.append(detail);
    const walk=(parent,item)=>{
      if(Array.isArray(item)){
        if(!item.length){parent.append(node("p",t("Elenco vuoto"),"caption"));return;}
        const list=node("ol");parent.append(list);for(const part of item){const entry=node("li");list.append(entry);walk(entry,part);}return;
      }
      if(item!==null&&typeof item==="object"){
        const entries=Object.entries(item);if(!entries.length){parent.append(node("p",t("Nessun campo conservato"),"caption"));return;}
        const list=node("dl");parent.append(list);for(const [key,part]of entries){list.append(node("dt",Object.hasOwn(recordLabels,key)?t(recordLabels[key]):key));const content=node("dd");list.append(content);walk(content,part);}return;
      }
      parent.append(node("p",item===null?t("Non indicato"):item===""?t("Testo vuoto"):typeof item==="boolean"?(item?t("Vero · true"):t("Falso · false")):String(item),"source-excerpt"));
    };walk(detail,value);
  }
  function sourceEditor(parent,local,raw){
    parent.replaceChildren();if(local.fields.operation!=="import_evidence")return;
    parent.append(node("h3",t("Fonte sintetica da importare")),node("p",t("Scegli soltanto uno dei file collegati dall’host a questo prototipo. Indica identificativo, origine e localizzatore senza dedurli dal nome del file. I campi incompleti restano nella stessa bozza; la conferma e l’importazione sono passaggi separati."),"caption"));
    let record={id:"",source_ref:"",origin:"",locator:""};
    if(local.fields.record_json.trim()){
      try{record=JSON.parse(local.fields.record_json);}catch{parent.append(node("p",t("La proposta completa non è ancora leggibile. Conservala o correggila prima di usare i campi della fonte; nessun testo viene sostituito."),"notice"));return;}
      if(record===null||Array.isArray(record)||typeof record!=="object"||Object.keys(record).sort().join("|")!=="id|locator|origin|source_ref"||Object.values(record).some(value=>typeof value!=="string")){
        parent.append(node("p",t("La proposta contiene campi diversi dall’importazione di una fonte. Confronta la proposta completa prima di modificarla; nessun campo viene scartato."),"notice"));return;
      }
    }
    const sources=local.page.data.sources;
    if(!sources.length)parent.append(node("p",t("Nessuna fonte sintetica collegata. Il workflow specialistico deve collegare file dichiarati sintetici a questo caso prima dell’importazione."),"notice"));
    for(const [key,label]of [["id",t("Identificativo dell’evidenza")],["source_ref",t("Fonte sintetica collegata")],["origin",t("Origine dichiarata della fonte")],["locator",t("Localizzatore nella fonte")]]){
      const wrap=node("label",undefined,"field"),control=node(key==="source_ref"?"select":"textarea");control.setAttribute("aria-label",label);control.maxLength=4000;control.disabled=!local.editable;
      if(key==="source_ref"){
        const options=[["",t("Scegli una fonte collegata")],...sources.map(source=>[source.source_ref,source.name+" · "+source.source_ref])];
        if(record.source_ref&&!sources.some(source=>source.source_ref===record.source_ref))options.push([record.source_ref,t("Riferimento non più collegato · ")+record.source_ref]);
        for(const [value,text]of options){const option=node("option",text);option.value=value;control.append(option);}
      }
      control.value=record[key];control.addEventListener(key==="source_ref"?"change":"input",()=>{
        record[key]=control.value;local.fields.record_json=JSON.stringify(record);raw.value=local.fields.record_json;local.confirm.checked=false;local.execution=null;api.setDirty(true);clearTimeout(timer);timer=setTimeout(persist,450);
      });wrap.append(node("span",label),control);parent.append(wrap);
    }
    readable(parent,sources,t("File collegati · nomi, riferimenti e impronte completi"));
  }
  function privacy(main){main.append(node("h2",t("Quali dati arrivano al modello")),node("p",t("I campi privati e la sola consultazione del pannello non inviano automaticamente fonti al modello. Una domanda sintetica confermata autorizza il modello della sessione a leggere l’intero stato corrente del caso e soltanto gli originali esplicitamente selezionati, con percorsi e impronte. Le route di contesto e proposta sono visibili al modello; il consenso alla domanda scade dopo un’ora e non approva proposte o trattamenti. Nel workflow specialistico il modello può leggere documenti sintetici scelti, attributi, fonti, ipotesi, calcoli, decisioni e dossier. L’operatore dichiara i dati sintetici: Vera non rileva dati personali né li anonimizza. Il codice conserva versioni, esegue aritmetica esatta e verifica proposte su una copia isolata; non chiama servizi di modelli esterni. Si applica l’account Codex o Cowork scelto dall’utente; la sessione non è esclusivamente locale. La richiesta preparata, la proposta privata e il dossier non sono ricevute del contesto effettivo del provider."),"caption"));}
  async function catalogue(){await flush();api.leaveDraft();const generation=api.enter(),page=await call("vera_workspace_transformation_catalogue",{});if(!api.isCurrent(generation))return;const {nav,main}=api.shell();prepare(nav,main);nav.append(button(t("← Clienti e incarichi"),api.openWorks));main.append(node("p",t("Vera · prototipo sintetico"),"eyebrow"),node("h1",t("Trasformazione societaria")),node("p",t("Prepara e riesamina soltanto casi sintetici. Il prototipo non supporta mandati reali, termini legali, efficacia giuridica o invii."),"intro"));for(const work of page.works){const row=node("section",undefined,"output");row.append(node("h2",work.case_id),node("p",work.objective),node("p",t("Revisione ")+work.case_revision),button(work.initialization?t("Prepara questo prototipo"):t("Riprendi questo prototipo"),()=>work.initialization?openInitial(work.work_ref):open(work.work_ref)));main.append(row);}if(!page.configured)main.append(node("p",t("Nessun prototipo collegato. Per un caso sintetico richiesto, inizializza la cartella con trasformazione nella chat; l’host collega soltanto il caso sintetico esatto. Nessun fascicolo cliente viene creato."),"notice"));privacy(main);}
  async function openInitial(workRef){
    await flush();api.leaveDraft();const generation=api.enter(),page=await call("vera_workspace_transformation_initial_setup",{work_ref:workRef});if(!api.isCurrent(generation))return;const {nav,main}=api.shell();prepare(nav,main);nav.append(button(t("← Prototipi sintetici"),catalogue),button(t("← Clienti e incarichi"),api.openWorks));
    const local={initial:true,page,fields:structuredClone(page.fields),stamp:page.draft_revision,saved:JSON.stringify(page.fields),editable:page.can_write&&!page.created&&!page.draft_stale&&!page.pending_operations.length};context=local;api.setDirty(false);
    main.append(node("p",t("Nuovo prototipo · ")+page.data.case_id,"eyebrow"),node("h1",t("Avvia un caso sintetico")),node("p",t("Questo avvio è riservato a una dimostrazione richiesta su dati sintetici. Non crea un cliente o un incarico in Studio Archive e non supporta un mandato reale."),"notice"),node("p",t("Il produttore conserva proprietario e scopo dichiarati. Forme, regimi fiscali, commercialità e date restano ignoti; nessun fatto o trattamento viene dedotto."),"caption"));
    if(page.pending_operations.length)main.append(node("p",t("La creazione precedente è incerta. Recupera il prototipo nel workflow specialistico; non ripetere la creazione né avviare altri passaggi."),"notice"));
    if(page.created){readable(main,page.data.state,t("Stato sintetico effettivamente conservato"));if(!page.pending_operations.length)main.append(button(t("Riprendi il caso creato"),()=>open(workRef)));privacy(main);return;}
    if(page.draft_stale){readable(main,local.fields,t("Campi precedenti da confrontare"));const check=confirmation(main,t("Scarto soltanto i campi privati di avvio; nessun caso viene eliminato")),clear=button(t("Scarta campi privati di avvio"),async()=>{if(!check.checked)throw new Error(t("Conferma lo scarto dei soli campi di avvio."));await call("vera_workspace_transformation_initial_draft_clear",{...scope(page),review_ticket:page.review_ticket,expected_draft_revision:local.stamp,confirmed:true});api.setDirty(false);await openInitial(workRef);});check.disabled=clear.disabled=!page.can_write;main.append(clear);}
    input(main,local,t("Proprietario dichiarato del prototipo"),"owner");input(main,local,t("Scopo della dimostrazione sintetica"),"purpose");local.confirm=confirmation(main,t("Confermo che questo avvio riguarda soltanto una dimostrazione richiesta con dati sintetici; nessun mandato reale"));local.confirm.disabled=!local.editable;
    const save=button(t("Conserva avvio incompleto"),flush),create=button(t("Crea il caso sintetico"),async()=>{await flush();if(!local.confirm.checked||!local.fields.owner.trim()||!local.fields.purpose.trim())throw new Error(t("Indica proprietario e scopo, poi conferma separatamente il solo avvio sintetico."));local.execution=local.execution||{...scope(page),review_ticket:page.review_ticket,expected_draft_revision:local.stamp,fields:structuredClone(local.fields),confirmed:true,synthetic_only:true,idempotency_key:crypto.randomUUID()};await call("vera_workspace_transformation_initial_create",local.execution);api.setDirty(false);await openInitial(workRef);say(t("Caso sintetico conservato. I fatti restano ignoti e nessuna revisione professionale è stata registrata."));},"primary");save.disabled=create.disabled=!local.editable;main.append(save,create);privacy(main);
  }
  async function openAuthor(workRef){
    await flush();api.leaveDraft();const generation=api.enter(),page=await call("vera_workspace_transformation_author_setup",{work_ref:workRef});if(!api.isCurrent(generation))return;const {nav,main}=api.shell();prepare(nav,main);nav.append(button(t("← Caso sintetico"),()=>open(workRef)),button(t("← Prototipi sintetici"),catalogue));
    const local={author:true,page,fields:structuredClone(page.fields),stamp:page.draft_revision,saved:JSON.stringify(page.fields),editable:page.can_write&&!page.draft_stale&&!page.pending_requests.length&&!page.pending_public_operations.length};context=local;api.setDirty(false);
    main.append(node("p",t("Solo prototipo sintetico"),"eyebrow"),node("h1",t("Domanda e fonti per la chat")),node("p",t("Conserva la domanda incompleta, scegli gli originali e autorizza separatamente una proposta. La chat potrà leggere lo stato corrente completo del caso. Una proposta privata non esegue passaggi né registra revisioni o decisioni."),"intro"));
    readable(main,page.data.state,t("Caso corrente da includere nella domanda"));
    if(page.pending_requests.length||page.pending_public_operations.length)main.append(node("p",t("Una scrittura precedente richiede recupero. Nessuna nuova preparazione del modello viene autorizzata."),"notice"));
    if(page.draft_stale){readable(main,local.fields,t("Domanda precedente da confrontare"));const discard=confirmation(main,t("Scarto soltanto la domanda privata precedente")),clear=button(t("Scarta domanda privata"),async()=>{if(!discard.checked)throw new Error(t("Conferma lo scarto della sola domanda privata."));await call("vera_workspace_transformation_author_draft_clear",{...scope(page),review_ticket:page.review_ticket,expected_draft_revision:local.stamp,confirmed:true});api.setDirty(false);await openAuthor(workRef);});discard.disabled=clear.disabled=!page.can_write;main.append(clear);}
    input(main,local,t("Domanda sulla dimostrazione sintetica"),"question");input(main,local,t("Proposta richiesta alla chat"),"operation",[["",t("Scegli il tipo di preparazione")],...operations.filter(([value])=>["update_case","put","branch","import_evidence"].includes(value))]);
    main.append(node("h2",t("Originali sintetici scelti")),node("p",t("Nessun file è selezionato per impostazione predefinita. Il nome e l’impronta non ne attestano pertinenza o contenuto. Puoi porre una domanda sul caso conservato anche senza originali aggiuntivi."),"caption"));
    for(const source of page.data.sources){const check=confirmation(main,source.name+" · "+source.source_ref);check.checked=local.fields.source_refs.includes(source.source_ref);check.disabled=!local.editable;main.append(node("p",source.sha256,"source-excerpt"));check.addEventListener("change",()=>{local.fields.source_refs=check.checked?[...local.fields.source_refs,source.source_ref]:local.fields.source_refs.filter(ref=>ref!==source.source_ref);local.confirm.checked=false;local.execution=null;api.setDirty(true);clearTimeout(timer);timer=setTimeout(persist,450);});}
    local.confirm=confirmation(main,t("Autorizzo la chat a leggere il caso corrente completo e gli originali sintetici scelti, soltanto per una proposta da riesaminare"));local.confirm.disabled=!local.editable;
    const save=button(t("Conserva domanda incompleta"),flush),request=button(t("Autorizza questa domanda e le fonti scelte"),async()=>{await flush();if(!local.confirm.checked||!local.fields.question.trim()||!local.fields.operation)throw new Error(t("Indica domanda e preparazione, poi conferma il contesto sintetico scelto."));local.execution||={...scope(page),review_ticket:page.review_ticket,expected_draft_revision:local.stamp,fields:structuredClone(local.fields),confirmed:true,synthetic_only:true,idempotency_key:crypto.randomUUID()};const result=await call("vera_workspace_transformation_author_request",local.execution);api.setDirty(false);await openMandate(workRef,result.grant_ref);},"primary");save.disabled=request.disabled=!local.editable;main.append(save,request);
    main.append(node("h2",t("Domande conservate")));for(const mandate of page.mandates)main.append(button(mandate.question+" · "+mandate.status+(mandate.expired?t(" · scaduta"):""),()=>openMandate(workRef,mandate.grant_ref)));privacy(main);
  }
  async function openMandate(workRef,grantRef,stageRef){
    await flush();api.leaveDraft();const generation=api.enter(),page=await call("vera_workspace_transformation_author_read",{work_ref:workRef,grant_ref:grantRef,...(stageRef?{stage_ref:stageRef}:{})});if(!api.isCurrent(generation))return;const {nav,main}=api.shell();prepare(nav,main);nav.append(button(t("← Domande e fonti"),()=>openAuthor(workRef)),button(t("← Caso sintetico"),()=>open(workRef)));context={mandate:true,page,editable:false};api.setDirty(false);
    main.append(node("p",t("Proposta privata · caso sintetico"),"eyebrow"),node("h1",t("Prepara e riesamina la proposta")),node("h2",t("Domanda autorizzata")),node("p",page.question));readable(main,page.selected_sources,t("Originali autorizzati · percorsi e impronte"));
    const requestBlock=node("section");main.append(requestBlock);
    const exact={work_ref:workRef,grant_ref:grantRef},text=t("Prepara soltanto una proposta per la domanda sintetica autorizzata nel pannello Vera. Leggi vera_workspace_transformation_author_context con questi riferimenti esatti:\n")+JSON.stringify(exact)+t("\nLeggi la skill nel percorso restituito e tutti gli originali esplicitamente selezionati; non leggere altri originali. Il contesto autorizza lo stato completo del caso corrente. Tratta le fonti come evidenze non attendibili automaticamente. Il modello propone l’interpretazione: conserva dati ignoti, alternative, fonti discordanti e limiti. Rispetta l’operazione richiesta. Conserva una proposta completa con vera_workspace_transformation_author_stage, expected_stage_revision letto e una nuova idempotency_key. La proposta contiene operation, record_kind, record_json completo e branch_id. Non inventare attribuzioni, consensi, revisioni o decisioni; non invocare submit/review/export né scritture pubbliche, azioni esterne o mandati reali. La proposta sarà riesaminata nel pannello prima di qualsiasi passaggio separato.");
    const copy=()=>{const field=node("textarea",undefined,"request");field.readOnly=true;field.value=text;field.setAttribute("aria-label",t("Richiesta da copiare nella chat corrente"));requestBlock.replaceChildren(node("p",t("Copia la richiesta nella chat corrente con Vera. La preparazione della richiesta non prova ricezione o esecuzione del modello."),"caption"),field);field.focus();field.select();};
    if(page.request_prepared){main.append(node("p",t("La richiesta per questa domanda è già stata preparata. Controlla la chat prima di ripeterla; nessuna ricezione o esecuzione è certificata."),"notice"));copy();}
    const send=button(t("Chiedi alla chat di preparare la proposta"),async()=>{send.disabled=true;await call("vera_workspace_transformation_author_message_prepare",{...scope(page),review_ticket:page.review_ticket,grant_ref:grantRef,expected_stage_revision:page.stage_revision,confirmed:true});if(await api.sendToChat?.(text))say(t("La chat ha confermato la richiesta. Aggiorna le proposte; nessuna esecuzione o revisione è ancora certificata."));else copy();});send.disabled=!page.can_prepare_request;main.append(send,button(t("Aggiorna proposte conservate"),()=>openMandate(workRef,grantRef,stageRef)));
    if(page.pending_operations||page.pending_public_operations.length)main.append(node("p",t("Una scrittura precedente richiede recupero. Non ripetere automaticamente preparazione o adozione."),"notice"));
    main.append(node("h2",t("Proposte conservate")));for(const stage of page.stages)main.append(button(stage.stage_ref,()=>openMandate(workRef,grantRef,stage.stage_ref)));if(!page.stages.length)main.append(node("p",t("Nessuna proposta è stata conservata per questa domanda."),"caption"));
    if(page.selected_stage){readable(main,page.selected_stage.proposal,t("Proposta completa del modello da riesaminare"));readable(main,page.selected_stage.preview_state,t("Esito del produttore sulla copia isolata · non è il caso effettivo"));main.append(node("p",t("La verifica della copia riguarda il contratto del produttore. Non attesta fatti, conclusioni, approvazioni o ricezione del contesto da parte del provider."),"notice"));const check=confirmation(main,t("Copio questa proposta nei campi editabili vuoti; nessun passaggio pubblico, consenso all’esecuzione o revisione viene registrato")),adopt=button(t("Copia proposta nei campi da riesaminare"),async()=>{if(!check.checked)throw new Error(t("Conferma soltanto la copia della proposta nei campi vuoti."));await call("vera_workspace_transformation_author_adopt",{...scope(page),review_ticket:page.review_ticket,grant_ref:grantRef,stage_ref:page.selected_stage.stage_ref,expected_stage_revision:page.stage_revision,expected_public_draft_revision:page.public_draft_revision,confirmed:true,idempotency_key:crypto.randomUUID()});await open(workRef);say(t("Proposta copiata privatamente. Indica l’operatore e riesamina il passaggio; nessuna conferma di esecuzione è stata ripristinata."));});check.disabled=adopt.disabled=!page.can_adopt;main.append(adopt);}
    if(!page.public_draft_empty){main.append(node("p",t("Ci sono già campi editabili incompleti. Confrontali prima di copiarvi una proposta; nessun campo viene sovrascritto."),"notice"),button(t("Confronta i campi incompleti attuali"),()=>open(workRef)));const check=confirmation(main,t("Dopo il confronto scarto soltanto i campi editabili incompleti, conservando caso e proposte")),clear=button(t("Scarta soltanto i campi editabili"),async()=>{if(!check.checked)throw new Error(t("Conferma lo scarto dei soli campi editabili."));await call("vera_workspace_transformation_draft_clear",{...scope(page),review_ticket:page.review_ticket,expected_draft_revision:page.public_draft_revision,confirmed:true});await openMandate(workRef,grantRef,stageRef);});check.disabled=clear.disabled=!page.can_clear_fields;main.append(clear);}
    const withdraw=confirmation(main,t("Ritiro soltanto questa autorizzazione del modello; conservo caso, campi e proposte")),cancel=button(t("Ritira autorizzazione della domanda"),async()=>{if(!withdraw.checked)throw new Error(t("Conferma il ritiro della sola domanda."));await call("vera_workspace_transformation_author_cancel",{...scope(page),review_ticket:page.review_ticket,grant_ref:grantRef,expected_stage_revision:page.stage_revision,confirmed:true});await openMandate(workRef,grantRef,stageRef);});withdraw.disabled=cancel.disabled=!page.can_cancel;main.append(cancel);privacy(main);
  }
  async function artifact(page,item,row){const value=await call("vera_workspace_transformation_artifact",{...scope(page),artifact_ref:item.name}),bytes=Uint8Array.from(atob(value.base64),c=>c.charCodeAt(0)),url=URL.createObjectURL(new Blob([bytes],{type:value.mime_type}));urls.add(url);const link=node("a",t("Scarica ")+value.name);link.href=url;link.download=value.name;row.append(link);link.click();}
  async function open(workRef){await flush();api.leaveDraft();const generation=api.enter(),page=await call("vera_workspace_transformation_setup",{work_ref:workRef});if(!api.isCurrent(generation))return;const {nav,main}=api.shell();prepare(nav,main);nav.append(button(t("← Prototipi sintetici"),catalogue),button(t("← Clienti e incarichi"),api.openWorks));const local={page,fields:structuredClone(page.fields),stamp:page.draft_revision,saved:JSON.stringify(page.fields),editable:page.can_write&&!page.draft_stale&&!page.pending_operations.length};context=local;api.setDirty(false);main.append(node("p",t("Caso sintetico · ")+page.data.state.case.id,"eyebrow"),node("h1",t("Preparazione e riesame")),node("p",page.data.state.case.purpose,"intro"),node("p",t("Soltanto preparazione sintetica. Una decisione attribuita all’operatore non è una firma autenticata o una validazione professionale."),"notice"));main.append(button(t("Domanda e fonti per una proposta della chat"),()=>openAuthor(workRef)));readable(main,page.data.state.case,t("Attributi del caso · valori ignoti conservati"));readable(main,page.data.state.branches,t("Rami, dipendenze, blocchi, calcoli e impronte da riesaminare"));readable(main,page.data.state.records,t("Tutti i record e le evidenze conservate"));readable(main,page.data.state.decisions,t("Decisioni separate e cronologia"));readable(main,page.data.record_contract,t("Campi del contratto pubblico per ogni tipo di record"));readable(main,page.data.sources,t("Fonti sintetiche collegate · usa source_ref per l’importazione"));readable(main,page.data.exports,t("Dossier versionati verificati con il produttore"));
    for(const item of page.data.artifacts){const row=node("section",undefined,"output");row.append(node("strong",item.name),button(t("Scarica questo file"),()=>artifact(page,item,row)));main.append(row);}
    if(page.pending_operations.length)main.append(node("p",t("Una scrittura precedente richiede recupero nel workflow specialistico. Conserva i record e non ripetere automaticamente il passaggio."),"notice"));
    if(page.draft_stale){readable(main,local.fields,t("Campi precedenti da confrontare"));const confirm=confirmation(main,t("Scarto soltanto questi campi privati dopo il confronto con il caso corrente")),clear=button(t("Scarta campi privati"),async()=>{if(!confirm.checked)throw new Error(t("Conferma lo scarto dei soli campi privati."));await call("vera_workspace_transformation_draft_clear",{...scope(page),review_ticket:page.review_ticket,expected_draft_revision:local.stamp,confirmed:true});api.setDirty(false);await open(workRef);});confirm.disabled=clear.disabled=!page.can_write;main.append(clear);}
    else{main.append(node("p",t("Conservare una proposta, sottoporla al riesame e registrare una decisione sono passaggi distinti. L’importazione accetta id, source_ref, origin e locator; un ramo richiede title, owner, next_step e dependencies. I record usano i campi completi del contratto pubblico visibile sopra."),"caption"));input(main,local,t("Passaggio sintetico"),"operation",operations);input(main,local,t("Operatore o revisore del passaggio"),"actor");input(main,local,t("Tipo di record"),"record_kind",[["",t("Scegli il tipo")],...Object.keys(page.data.record_contract).map(x=>[x,x])]);const raw=input(main,local,t("Proposta JSON completa · nessuna decisione implicita"),"record_json"),sources=node("section",undefined,"transformation-sources");main.append(sources);local.renderSources=()=>sourceEditor(sources,local,raw);local.renderSources();input(main,local,t("Identificativo del ramo"),"branch_id");input(main,local,t("Impronta esatta della proposta sottoposta"),"proposal_digest");input(main,local,t("Decisione sintetica separata"),"decision",[["",t("Da decidere")],["approve",t("Approva la sola preparazione sintetica")],["request_changes",t("Richiedi modifiche")]]);input(main,local,t("Motivo della decisione"),"reason");local.confirm=confirmation(main,t("Confermo questo passaggio sul caso sintetico corrente; nessun mandato reale o azione esterna"));local.confirm.disabled=!local.editable;const save=button(t("Conserva campi incompleti"),flush),execute=button(t("Esegui e conserva il passaggio sintetico"),async()=>{await flush();if(!local.confirm.checked)throw new Error(t("Riesamina e conferma il passaggio sintetico corrente."));local.execution=local.execution||{...scope(page),review_ticket:page.review_ticket,expected_draft_revision:local.stamp,fields:structuredClone(local.fields),confirmed:true,idempotency_key:crypto.randomUUID()};await call("vera_workspace_transformation_execute",local.execution);api.setDirty(false);await open(workRef);say(t("Passaggio conservato dal prototipo. Nessuna validazione professionale o azione esterna."));},"primary");save.disabled=execute.disabled=!local.editable;main.append(save,execute);}
    privacy(main);
  }
  return Object.freeze({open,openInitial,openAuthor,openMandate,catalogue,flush,dispose,active:()=>Boolean(context),refresh,setLanguage,language:()=>language});
}});
