from __future__ import annotations

"""Localized public copy explaining Mparanza's data-handling position."""

from copy import deepcopy
from typing import Any

__all__ = ["get_data_handling_content"]


_OPENAI_CODEX_DATA_URL = (
    "https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan"
)
_OPENAI_CHATGPT_ANALYSIS_URL = (
    "https://help.openai.com/en/articles/8437071-data-analysis-with-chatgpt"
)
_ANTHROPIC_DATA_URL = (
    "https://privacy.claude.com/en/collections/10672411-data-handling-retention"
)
_GDPR_URL = "https://eur-lex.europa.eu/eli/reg/2016/679/oj"
_EDPB_AI_OPINION_URL = (
    "https://www.edpb.europa.eu/documents/opinion-of-the-board-art-64/"
    "opinion-282024-on-certain-data-protection-aspects-related-to_en"
)
_SOURCE_URL = "https://github.com/fabioannovazzi/app_files"


_DATA_HANDLING_CONTENT: dict[str, dict[str, Any]] = {
    "en": {
        "meta_description": (
            "How Mparanza plugins use your selected AI workspace, local processing, "
            "hosted services, and external destinations."
        ),
        "skip_label": "Skip to main content",
        "home_label": "Return to Mparanza",
        "language_selector_label": "Language selector",
        "eyebrow": "Security, privacy and data",
        "title": "How your data is handled.",
        "summary": (
            "Vera, Clara, and Lucia work in the AI workspace you choose. "
            "Mparanza-hosted services and other external destinations are separate."
        ),
        "video": {
            "eyebrow": "Vera + Clara · Video",
            "title": "How Vera and Clara handle data.",
            "description": (
                "See the difference between local preparation, model processing in "
                "your selected workspace, and a service hosted by Mparanza."
            ),
            "youtube_id": "HhmQgTEnl78",
            "watch_label": "Watch on YouTube",
        },
        "boundary": {
            "title": "Your selected AI workspace is the main boundary.",
            "intro": (
                "Data needed for the work may enter the model context of the OpenAI "
                "ChatGPT or Codex account, or the Anthropic Claude or Cowork account, "
                "that you select. Mparanza is not a separate recipient of ordinary "
                "plugin work."
            ),
            "local_label": "Your computer",
            "local_detail": "Local files · local Python · local outputs",
            "account_label": "Your selected AI workspace",
            "account_detail": "OpenAI ChatGPT or Codex · Anthropic Claude or Cowork",
            "exclusion": "Ordinary plugin work sends no client or work content to Mparanza.",
        },
        "sections": [
            {
                "id": "local-execution",
                "title": "Local preparation is useful, not automatic anonymisation.",
                "paragraphs": [
                    (
                        "Local Python can sort, calculate, reconcile, filter, aggregate, "
                        "and create outputs. A workflow may use it before a model step when "
                        "that improves the work."
                    ),
                    (
                        "The plugins do not automatically anonymise or pseudonymise data. "
                        "Names, documents, original language, and case facts remain when "
                        "they are useful for the professional purpose."
                    ),
                ],
            },
            {
                "id": "workflow-boundaries",
                "title": "The detailed boundary belongs to the workflow.",
                "paragraphs": [
                    (
                        "Each workflow can use data differently. Its own page explains the "
                        "operational sequence: what the model sees, what code processes, "
                        "and when the process stops. This page does not duplicate those "
                        "workflow-specific statements."
                    ),
                    (
                        "Never put passwords, API keys, authentication cookies, access "
                        "tokens, or session material in prompts or files the selected AI "
                        "workspace can read."
                    ),
                ],
            },
            {
                "id": "connected-sources",
                "title": "Connectors and sends use their own destination.",
                "paragraphs": [
                    (
                        "A connected app, public search, portal, or send action is used only "
                        "when that route is part of the selected work. The destination's "
                        "terms and controls apply separately."
                    ),
                    (
                        "Using an external destination does not make Mparanza the recipient. "
                        "The workflow or point-of-use notice identifies a Mparanza-hosted "
                        "route when one is involved."
                    ),
                ],
            },
            {
                "id": "hosted-features",
                "title": "Mparanza-hosted services are a separate boundary.",
                "paragraphs": [
                    (
                        "When a function uses a Mparanza-hosted service, the content needed "
                        "for that service reaches Mparanza-controlled systems. Hosted "
                        "interviews, voice capture, and retail data are examples."
                    ),
                    (
                        "The notice shown where that service is used states what reaches it "
                        "and the applicable access, retention, and deletion arrangement."
                    ),
                ],
            },
        ],
        "resources": {
            "title": "Verify the position.",
            "intro": "You do not have to rely on the claim alone.",
            "links_label": "Data-handling references",
            "links": [
                {"label": "Inspect the source", "href": _SOURCE_URL, "external": True},
                {
                    "label": "Read the Zero Retention Policy",
                    "href": "/zero-retention",
                    "external": False,
                },
                {
                    "label": "Read the GDPR text (Article 5)",
                    "href": _GDPR_URL,
                    "external": True,
                },
                {
                    "label": "Read the EDPB opinion on AI models and anonymity",
                    "href": _EDPB_AI_OPINION_URL,
                    "external": True,
                },
                {
                    "label": "Review OpenAI's Codex data controls",
                    "href": _OPENAI_CODEX_DATA_URL,
                    "external": True,
                },
                {
                    "label": "See how ChatGPT data analysis runs code",
                    "href": _OPENAI_CHATGPT_ANALYSIS_URL,
                    "external": True,
                },
                {
                    "label": "Review Anthropic's data handling and retention guidance",
                    "href": _ANTHROPIC_DATA_URL,
                    "external": True,
                },
            ],
        },
        "closing": "One global boundary. Process details stay with the process.",
    },
    "it": {
        "meta_description": (
            "Come i plugin di Mparanza LLC distinguono elaborazione locale, dati "
            "inviati al modello, destinazioni esterne e funzioni sul server."
        ),
        "skip_label": "Vai al contenuto principale",
        "home_label": "Torna a Mparanza",
        "language_selector_label": "Selettore della lingua",
        "eyebrow": "Sicurezza, privacy e dati",
        "title": "Come vengono gestiti i dati.",
        "summary": (
            "I nostri plugin combinano operazioni locali e trattamento del modello. "
            "Ogni processo dichiara che cosa resta locale, che cosa arriva al modello "
            "e che cosa viene escluso."
        ),
        "video": {
            "eyebrow": "Vera + Clara · Video",
            "title": "Come Vera e Clara gestiscono i dati.",
            "description": (
                "Guarda la differenza tra operazioni locali, trattamento del modello e "
                "funzioni che utilizzano il server di Mparanza LLC."
            ),
            "youtube_id": "q3nS9YBaEP8",
            "watch_label": "Guarda su YouTube",
        },
        "boundary": {
            "title": "Operazioni locali e trattamento del modello.",
            "intro": (
                "Il plugin esegue localmente e in modo deterministico ordinamenti, "
                "calcoli, riconciliazioni, filtri e aggregazioni. Il modello riceve i "
                "dati necessari al singolo processo."
            ),
            "local_label": "Elaborazione locale",
            "local_detail": (
                "Ordinamenti · calcoli · riconciliazioni · filtri · aggregazioni"
            ),
            "account_label": "Trattamento del modello",
            "account_detail": "Dati necessari al singolo processo",
            "exclusion": (
                "Ogni processo dichiara che cosa viene elaborato localmente, che cosa "
                "arriva al modello e che cosa resta escluso."
            ),
        },
        "sections": [
            {
                "id": "local-execution",
                "title": "Anonimizzazione e finalità del processo.",
                "paragraphs": [
                    (
                        "Anonimizzare può rendere più difficile proprio l'analisi che il "
                        "modello deve svolgere."
                    ),
                    (
                        "Per questo i nostri plugin, in generale, non anonimizzano i dati; "
                        "lo fanno solo quando ciò non incide sul processo."
                    ),
                ],
            },
            {
                "id": "workflow-boundaries",
                "title": "Dati personali e DPA.",
                "paragraphs": [
                    (
                        "I dati vengono filtrati e aggregati localmente quando il processo "
                        "lo consente, ma alcuni dati personali possono comunque essere "
                        "trattati dal modello."
                    ),
                    (
                        "Se si caricano dati personali, è necessario avere un DPA con il "
                        "provider del modello."
                    ),
                ],
            },
            {
                "id": "connected-sources",
                "title": "Destinazioni esterne.",
                "paragraphs": [
                    (
                        "Se un processo usa un'app collegata, una ricerca pubblica, un "
                        "portale o un invio, i dati necessari raggiungono anche quella "
                        "destinazione. Si applicano le condizioni e i controlli del relativo "
                        "servizio."
                    ),
                    (
                        "La pagina del singolo processo indica se viene utilizzata una "
                        "destinazione esterna."
                    ),
                ],
            },
            {
                "id": "hosted-features",
                "title": "Server di Mparanza LLC.",
                "paragraphs": [
                    (
                        "Il normale funzionamento dei plugin non invia né conserva sul "
                        "server di Mparanza LLC i dati del cliente o del lavoro. Per il "
                        "normale funzionamento dei plugin non è quindi necessario un DPA "
                        "con Mparanza LLC."
                    ),
                    (
                        "Alcune elaborazioni particolari, richieste espressamente, possono "
                        "utilizzare il server di Mparanza LLC. La documentazione della "
                        "funzione indica quali dati vengono inviati e come sono trattati."
                    ),
                ],
            },
        ],
        "resources": {
            "title": "Verifica questa posizione.",
            "intro": "Non devi basarti soltanto su questa dichiarazione.",
            "links_label": "Riferimenti sul trattamento dei dati",
            "links": [
                {"label": "Esamina il codice", "href": _SOURCE_URL, "external": True},
                {
                    "label": "Leggi la Zero Retention Policy",
                    "href": "/zero-retention",
                    "external": False,
                },
                {
                    "label": "Leggi il GDPR (articoli 5 e 28)",
                    "href": _GDPR_URL,
                    "external": True,
                },
                {
                    "label": "Consulta il parere EDPB su modelli di IA e anonimato",
                    "href": _EDPB_AI_OPINION_URL,
                    "external": True,
                },
                {
                    "label": "Consulta i controlli dati Codex di OpenAI",
                    "href": _OPENAI_CODEX_DATA_URL,
                    "external": True,
                },
                {
                    "label": "Scopri come ChatGPT esegue l'analisi dati",
                    "href": _OPENAI_CHATGPT_ANALYSIS_URL,
                    "external": True,
                },
                {
                    "label": "Consulta le indicazioni Anthropic su dati e conservazione",
                    "href": _ANTHROPIC_DATA_URL,
                    "external": True,
                },
            ],
        },
        "closing": (
            "Ogni processo spiega quali dati restano locali, quali arrivano al modello "
            "e quali raggiungono altre destinazioni."
        ),
    },
    "fr": {
        "meta_description": (
            "Comment les plugins Mparanza utilisent l'environnement d'IA choisi, le "
            "traitement local, les services hébergés et les destinations externes."
        ),
        "skip_label": "Aller au contenu principal",
        "home_label": "Retourner à Mparanza",
        "language_selector_label": "Sélecteur de langue",
        "eyebrow": "Sécurité, confidentialité et données",
        "title": "Comment vos données sont traitées.",
        "summary": (
            "Vera, Clara et Lucia travaillent dans l'environnement d'IA choisi par "
            "l'utilisateur. Les services hébergés par Mparanza et les autres destinations "
            "externes sont distincts."
        ),
        "video": {
            "eyebrow": "Vera + Clara · Vidéo",
            "title": "Comment Vera et Clara traitent les données.",
            "description": (
                "Voyez la différence entre la préparation locale, le traitement du modèle "
                "dans l'environnement choisi et un service hébergé par Mparanza."
            ),
            "youtube_id": "gIpiAURzyjA",
            "watch_label": "Voir sur YouTube",
        },
        "boundary": {
            "title": "L'environnement d'IA choisi est le périmètre principal.",
            "intro": (
                "Les données nécessaires au travail peuvent entrer dans le contexte du "
                "modèle du compte OpenAI ChatGPT ou Codex, ou Anthropic Claude ou Cowork, "
                "choisi par l'utilisateur. Mparanza n'est pas un destinataire distinct du "
                "travail ordinaire des plugins."
            ),
            "local_label": "Votre ordinateur",
            "local_detail": "Fichiers locaux · Python local · livrables locaux",
            "account_label": "Votre environnement d'IA choisi",
            "account_detail": "OpenAI ChatGPT ou Codex · Anthropic Claude ou Cowork",
            "exclusion": "Le travail ordinaire des plugins n'envoie à Mparanza aucun contenu client ou professionnel.",
        },
        "sections": [
            {
                "id": "local-execution",
                "title": "La préparation locale est utile, mais n'anonymise pas automatiquement.",
                "paragraphs": [
                    (
                        "Python peut localement trier, calculer, rapprocher, filtrer, "
                        "agréger et créer des livrables. Un workflow peut l'utiliser avant "
                        "une étape du modèle lorsque cela améliore le travail."
                    ),
                    (
                        "Les plugins n'anonymisent ni ne pseudonymisent automatiquement les "
                        "données. Les noms, documents, textes originaux et faits du dossier "
                        "restent présents lorsqu'ils servent la finalité professionnelle."
                    ),
                ],
            },
            {
                "id": "workflow-boundaries",
                "title": "Le périmètre détaillé appartient au workflow.",
                "paragraphs": [
                    (
                        "Chaque workflow peut utiliser les données différemment. Sa page "
                        "explique la séquence opérationnelle : ce que voit le modèle, ce "
                        "que traite le code et quand le processus s'arrête. Cette page ne "
                        "duplique pas ces déclarations spécifiques."
                    ),
                    (
                        "Ne placez jamais de mots de passe, clés API, cookies "
                        "d'authentification, jetons d'accès ou données de session dans "
                        "des prompts ou fichiers que l'environnement d'IA choisi peut lire."
                    ),
                ],
            },
            {
                "id": "connected-sources",
                "title": "Les connecteurs et les envois utilisent leur propre destination.",
                "paragraphs": [
                    (
                        "Une application connectée, une recherche publique, un portail ou "
                        "un envoi n'est utilisé que lorsque cette voie fait partie du travail "
                        "choisi. Les conditions et contrôles de la destination s'appliquent "
                        "séparément."
                    ),
                    (
                        "L'utilisation d'une destination externe ne fait pas de Mparanza le "
                        "destinataire. Le workflow ou l'avis affiché au moment de l'usage "
                        "identifie une voie hébergée par Mparanza lorsqu'elle intervient."
                    ),
                ],
            },
            {
                "id": "hosted-features",
                "title": "Les services hébergés par Mparanza ont un périmètre distinct.",
                "paragraphs": [
                    (
                        "Lorsqu'une fonction utilise un service hébergé par Mparanza, les "
                        "contenus nécessaires atteignent des systèmes contrôlés par "
                        "Mparanza. Les entretiens, la capture vocale et les données retail "
                        "hébergés en sont des exemples."
                    ),
                    (
                        "L'avis affiché là où le service est utilisé indique ce qui lui "
                        "parvient ainsi que les modalités applicables d'accès, de "
                        "conservation et de suppression."
                    ),
                ],
            },
        ],
        "resources": {
            "title": "Vérifier cette position.",
            "intro": "Vous n'avez pas à vous fier uniquement à cette affirmation.",
            "links_label": "Références sur le traitement des données",
            "links": [
                {"label": "Examiner le code", "href": _SOURCE_URL, "external": True},
                {
                    "label": "Lire la politique Zero Retention",
                    "href": "/zero-retention",
                    "external": False,
                },
                {
                    "label": "Lire le RGPD (article 5)",
                    "href": _GDPR_URL,
                    "external": True,
                },
                {
                    "label": "Lire l'avis de l'EDPB sur les modèles d'IA et l'anonymat",
                    "href": _EDPB_AI_OPINION_URL,
                    "external": True,
                },
                {
                    "label": "Consulter les contrôles de données Codex d'OpenAI",
                    "href": _OPENAI_CODEX_DATA_URL,
                    "external": True,
                },
                {
                    "label": "Voir comment ChatGPT exécute l'analyse de données",
                    "href": _OPENAI_CHATGPT_ANALYSIS_URL,
                    "external": True,
                },
                {
                    "label": "Consulter les règles Anthropic sur les données et la conservation",
                    "href": _ANTHROPIC_DATA_URL,
                    "external": True,
                },
            ],
        },
        "closing": "Un périmètre global. Les détails du processus restent avec le processus.",
    },
    "de": {
        "meta_description": (
            "Wie Mparanza-Plugins die gewählte KI-Arbeitsumgebung, lokale Verarbeitung, "
            "gehostete Dienste und externe Ziele nutzen."
        ),
        "skip_label": "Zum Hauptinhalt springen",
        "home_label": "Zurück zu Mparanza",
        "language_selector_label": "Sprachauswahl",
        "eyebrow": "Sicherheit, Datenschutz und Daten",
        "title": "So werden Ihre Daten verarbeitet.",
        "summary": (
            "Vera, Clara und Lucia arbeiten in der vom Nutzer gewählten "
            "KI-Arbeitsumgebung. Mparanza-gehostete Dienste und andere externe Ziele "
            "sind davon getrennt."
        ),
        "video": {
            "eyebrow": "Vera + Clara · Video",
            "title": "Wie Vera und Clara Daten verarbeiten.",
            "description": (
                "Sehen Sie den Unterschied zwischen lokaler Vorbereitung, "
                "Modellverarbeitung in der gewählten Umgebung und einem von Mparanza "
                "gehosteten Dienst."
            ),
            "youtube_id": "g5XV1cZoTaI",
            "watch_label": "Auf YouTube ansehen",
        },
        "boundary": {
            "title": "Die gewählte KI-Arbeitsumgebung ist die Hauptgrenze.",
            "intro": (
                "Für die Arbeit benötigte Daten können in den Modellkontext des gewählten "
                "OpenAI-ChatGPT- oder Codex-Kontos beziehungsweise Anthropic-Claude- oder "
                "Cowork-Kontos gelangen. Mparanza ist kein separater Empfänger der "
                "gewöhnlichen Plugin-Arbeit."
            ),
            "local_label": "Ihr Computer",
            "local_detail": "Lokale Dateien · lokales Python · lokale Ergebnisse",
            "account_label": "Ihre gewählte KI-Arbeitsumgebung",
            "account_detail": "OpenAI ChatGPT oder Codex · Anthropic Claude oder Cowork",
            "exclusion": "Gewöhnliche Plugin-Arbeit sendet keine Mandanten- oder Arbeitsinhalte an Mparanza.",
        },
        "sections": [
            {
                "id": "local-execution",
                "title": "Lokale Vorbereitung ist nützlich, aber keine automatische Anonymisierung.",
                "paragraphs": [
                    (
                        "Lokales Python kann sortieren, berechnen, abstimmen, filtern, "
                        "aggregieren und Ergebnisse erstellen. Ein Workflow kann dies vor "
                        "einem Modellschritt nutzen, wenn es die Arbeit verbessert."
                    ),
                    (
                        "Die Plugins anonymisieren oder pseudonymisieren Daten nicht "
                        "automatisch. Namen, Dokumente, Originalformulierungen und Fallfakten "
                        "bleiben erhalten, wenn sie dem beruflichen Zweck dienen."
                    ),
                ],
            },
            {
                "id": "workflow-boundaries",
                "title": "Die detaillierte Grenze gehört zum Workflow.",
                "paragraphs": [
                    (
                        "Jeder Workflow kann Daten anders nutzen. Seine eigene Seite erklärt "
                        "den Ablauf: was das Modell sieht, was der Code verarbeitet und wann "
                        "der Prozess stoppt. Diese Seite dupliziert diese spezifischen "
                        "Aussagen nicht."
                    ),
                    (
                        "Geben Sie niemals Passwörter, API-Schlüssel, Authentifizierungs-"
                        "Cookies, Zugriffstoken oder Sitzungsdaten in Prompts oder Dateien "
                        "ein, die die gewählte KI-Arbeitsumgebung lesen kann."
                    ),
                ],
            },
            {
                "id": "connected-sources",
                "title": "Connectoren und Sendefunktionen nutzen ihr eigenes Ziel.",
                "paragraphs": [
                    (
                        "Eine verbundene App, öffentliche Suche, ein Portal oder eine "
                        "Sendefunktion wird nur genutzt, wenn dieser Weg Teil der gewählten "
                        "Arbeit ist. Bedingungen und Kontrollen des Ziels gelten separat."
                    ),
                    (
                        "Die Nutzung eines externen Ziels macht Mparanza nicht zum Empfänger. "
                        "Der Workflow oder der Hinweis am Nutzungsort kennzeichnet einen von "
                        "Mparanza gehosteten Weg, wenn er beteiligt ist."
                    ),
                ],
            },
            {
                "id": "hosted-features",
                "title": "Mparanza-gehostete Dienste haben eine separate Grenze.",
                "paragraphs": [
                    (
                        "Wenn eine Funktion einen Mparanza-gehosteten Dienst nutzt, erreichen "
                        "die erforderlichen Inhalte von Mparanza kontrollierte Systeme. "
                        "Gehostete Interviews, Spracherfassung und Retail-Daten sind Beispiele."
                    ),
                    (
                        "Der Hinweis dort, wo der Dienst genutzt wird, nennt die übermittelten "
                        "Inhalte und die geltenden Zugriffs-, Aufbewahrungs- und Löschregeln."
                    ),
                ],
            },
        ],
        "resources": {
            "title": "Diese Position überprüfen.",
            "intro": "Sie müssen sich nicht allein auf diese Aussage verlassen.",
            "links_label": "Quellen zur Datenverarbeitung",
            "links": [
                {"label": "Quellcode prüfen", "href": _SOURCE_URL, "external": True},
                {
                    "label": "Zero-Retention-Richtlinie lesen",
                    "href": "/zero-retention",
                    "external": False,
                },
                {
                    "label": "DSGVO lesen (Artikel 5)",
                    "href": _GDPR_URL,
                    "external": True,
                },
                {
                    "label": "EDSA-Stellungnahme zu KI-Modellen und Anonymität lesen",
                    "href": _EDPB_AI_OPINION_URL,
                    "external": True,
                },
                {
                    "label": "OpenAI-Datenkontrollen für Codex prüfen",
                    "href": _OPENAI_CODEX_DATA_URL,
                    "external": True,
                },
                {
                    "label": "Nachlesen, wie ChatGPT Datenanalysen ausführt",
                    "href": _OPENAI_CHATGPT_ANALYSIS_URL,
                    "external": True,
                },
                {
                    "label": "Anthropic-Hinweise zu Datenverarbeitung und Aufbewahrung prüfen",
                    "href": _ANTHROPIC_DATA_URL,
                    "external": True,
                },
            ],
        },
        "closing": "Eine globale Grenze. Prozessdetails bleiben beim Prozess.",
    },
    "es": {
        "meta_description": (
            "Cómo usan los plugins de Mparanza el entorno de IA elegido, el tratamiento "
            "local, los servicios alojados y los destinos externos."
        ),
        "skip_label": "Ir al contenido principal",
        "home_label": "Volver a Mparanza",
        "language_selector_label": "Selector de idioma",
        "eyebrow": "Seguridad, privacidad y datos",
        "title": "Cómo se tratan tus datos.",
        "summary": (
            "Vera, Clara y Lucia trabajan en el entorno de IA que elija el usuario. "
            "Los servicios alojados por Mparanza y los demás destinos externos están "
            "separados."
        ),
        "video": {
            "eyebrow": "Vera + Clara · Vídeo",
            "title": "Cómo tratan los datos Vera y Clara.",
            "description": (
                "Descubre la diferencia entre la preparación local, el tratamiento del "
                "modelo en el entorno elegido y un servicio alojado por Mparanza."
            ),
            "youtube_id": "LAimCM-F994",
            "watch_label": "Ver en YouTube",
        },
        "boundary": {
            "title": "El entorno de IA elegido es el límite principal.",
            "intro": (
                "Los datos necesarios para el trabajo pueden entrar en el contexto del "
                "modelo de la cuenta de OpenAI ChatGPT o Codex, o de Anthropic Claude o "
                "Cowork, que elija el usuario. Mparanza no es un destinatario separado del "
                "trabajo ordinario de los plugins."
            ),
            "local_label": "Tu ordenador",
            "local_detail": "Archivos locales · Python local · resultados locales",
            "account_label": "Tu entorno de IA elegido",
            "account_detail": "OpenAI ChatGPT o Codex · Anthropic Claude o Cowork",
            "exclusion": "El trabajo ordinario de los plugins no envía contenido de clientes ni del trabajo a Mparanza.",
        },
        "sections": [
            {
                "id": "local-execution",
                "title": "La preparación local es útil, pero no anonimiza automáticamente.",
                "paragraphs": [
                    (
                        "Python en local puede ordenar, calcular, conciliar, filtrar, agregar "
                        "y crear resultados. Un flujo puede usarlo antes de un paso del "
                        "modelo cuando mejora el trabajo."
                    ),
                    (
                        "Los plugins no anonimizan ni seudonimizan los datos automáticamente. "
                        "Los nombres, documentos, textos originales y hechos del caso se "
                        "mantienen cuando sirven para la finalidad profesional."
                    ),
                ],
            },
            {
                "id": "workflow-boundaries",
                "title": "El límite detallado pertenece al flujo de trabajo.",
                "paragraphs": [
                    (
                        "Cada flujo puede usar los datos de manera distinta. Su propia página "
                        "explica la secuencia operativa: qué ve el modelo, qué procesa el "
                        "código y cuándo se detiene el proceso. Esta página no duplica esas "
                        "declaraciones específicas."
                    ),
                    (
                        "Nunca incluyas contraseñas, claves de API, cookies de autenticación, "
                        "tokens de acceso ni datos de sesión en prompts o archivos que el "
                        "entorno de IA elegido pueda leer."
                    ),
                ],
            },
            {
                "id": "connected-sources",
                "title": "Los conectores y envíos usan su propio destino.",
                "paragraphs": [
                    (
                        "Una aplicación conectada, una búsqueda pública, un portal o un envío "
                        "solo se usa cuando esa vía forma parte del trabajo elegido. Las "
                        "condiciones y controles del destino se aplican por separado."
                    ),
                    (
                        "Usar un destino externo no convierte a Mparanza en destinatario. "
                        "El flujo o el aviso mostrado en el momento de uso identifica una "
                        "vía alojada por Mparanza cuando interviene."
                    ),
                ],
            },
            {
                "id": "hosted-features",
                "title": "Los servicios alojados por Mparanza tienen un límite separado.",
                "paragraphs": [
                    (
                        "Cuando una función usa un servicio alojado por Mparanza, el contenido "
                        "necesario llega a sistemas controlados por Mparanza. Las entrevistas, "
                        "la captura de voz y los datos retail alojados son algunos ejemplos."
                    ),
                    (
                        "El aviso mostrado donde se usa el servicio indica qué contenido le "
                        "llega y las condiciones aplicables de acceso, conservación y eliminación."
                    ),
                ],
            },
        ],
        "resources": {
            "title": "Comprueba esta posición.",
            "intro": "No tienes que confiar únicamente en esta afirmación.",
            "links_label": "Referencias sobre el tratamiento de datos",
            "links": [
                {
                    "label": "Examinar el código fuente",
                    "href": _SOURCE_URL,
                    "external": True,
                },
                {
                    "label": "Leer la Política de retención cero",
                    "href": "/zero-retention",
                    "external": False,
                },
                {
                    "label": "Leer el RGPD (artículo 5)",
                    "href": _GDPR_URL,
                    "external": True,
                },
                {
                    "label": "Leer el dictamen del CEPD sobre modelos de IA y anonimato",
                    "href": _EDPB_AI_OPINION_URL,
                    "external": True,
                },
                {
                    "label": "Revisar los controles de datos de Codex de OpenAI",
                    "href": _OPENAI_CODEX_DATA_URL,
                    "external": True,
                },
                {
                    "label": "Ver cómo el análisis de datos de ChatGPT ejecuta código",
                    "href": _OPENAI_CHATGPT_ANALYSIS_URL,
                    "external": True,
                },
                {
                    "label": "Consultar las indicaciones de Anthropic sobre datos y conservación",
                    "href": _ANTHROPIC_DATA_URL,
                    "external": True,
                },
            ],
        },
        "closing": "Un límite global. Los detalles del proceso permanecen con el proceso.",
    },
}


def get_data_handling_content(lang: str) -> dict[str, Any]:
    """Return independent localized content for the public data-handling page."""

    content = _DATA_HANDLING_CONTENT.get(lang) or _DATA_HANDLING_CONTENT["en"]
    return deepcopy(content)
