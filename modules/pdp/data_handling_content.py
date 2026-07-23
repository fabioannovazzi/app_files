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
_GDPR_URL = "https://eur-lex.europa.eu/eli/reg/2016/679/oj"
_EDPB_AI_OPINION_URL = (
    "https://www.edpb.europa.eu/documents/opinion-of-the-board-art-64/"
    "opinion-282024-on-certain-data-protection-aspects-related-to_en"
)
_SOURCE_URL = "https://github.com/fabioannovazzi/app_files"


_DATA_HANDLING_CONTENT: dict[str, dict[str, Any]] = {
    "en": {
        "meta_description": (
            "The two processing categories for Vera and Clara: work inside "
            "Codex and separate Mparanza-hosted services."
        ),
        "skip_label": "Skip to main content",
        "home_label": "Return to Mparanza",
        "language_selector_label": "Language selector",
        "eyebrow": "Security, privacy and data",
        "title": "How your data is handled.",
        "summary": (
            "Vera and Clara follow one policy. Plugin functions run inside "
            "Codex; Mparanza-hosted services form a separate processing boundary."
        ),
        "video": {
            "eyebrow": "Vera + Clara · Video",
            "title": "How Vera and Clara handle data.",
            "description": (
                "See what can stay on your computer, what may enter a language-model "
                "call through Codex, and when Mparanza becomes a separate processing "
                "boundary."
            ),
            "youtube_id": "HhmQgTEnl78",
            "watch_label": "Watch on YouTube",
        },
        "boundary": {
            "title": "When Vera and Clara work inside Codex.",
            "intro": (
                "Vera and Clara do not automatically anonymise data. They may use local "
                "Python to filter or aggregate information when useful. Data supplied "
                "to the model is processed through the user's existing ChatGPT plan. "
                "Workflows inside Codex do not send client files, prompts, or "
                "model-context content to Mparanza."
            ),
            "local_label": "Your computer",
            "local_detail": "Local files · local Python · local outputs",
            "account_label": "Your existing ChatGPT plan",
            "account_detail": "Model context · plan terms · data controls",
            "exclusion": "Workflows inside Codex send no client or work content to Mparanza.",
        },
        "sections": [
            {
                "id": "local-execution",
                "title": "Local processing is used when it helps the work.",
                "paragraphs": [
                    (
                        "Local Python can sort, calculate, reconcile, filter, aggregate, "
                        "and create outputs without first moving complete source files to "
                        "a separate Mparanza system."
                    ),
                    (
                        "This is not automatic anonymisation. When the professional task "
                        "requires names, documents, original language, or case facts, that "
                        "material may enter the model context."
                    ),
                ],
            },
            {
                "id": "security",
                "title": "Mapped once per workflow, not once per prompt.",
                "paragraphs": [
                    (
                        "Each workflow inside Codex is reviewed when it is added or changed. "
                        "The review records what normally stays local and what Codex may "
                        "read. It does not create a form, consent step, or record for each "
                        "prompt."
                    ),
                    (
                        "Never put passwords, API keys, authentication cookies, access "
                        "tokens, or session material in prompts or files Codex can read."
                    ),
                ],
            },
            {
                "id": "hosted-features",
                "title": "Mparanza-hosted services are a separate boundary.",
                "paragraphs": [
                    (
                        "When a Vera or Clara function uses a Mparanza-hosted service, the "
                        "content needed for that service reaches Mparanza-controlled "
                        "systems. Hosted interviews, Hosted Voice, and the retail-data "
                        "bridge are examples, not separate policies."
                    ),
                    (
                        "Each hosted service is documented once at service level: what may "
                        "be sent, who can access it, and its retention and deletion "
                        "arrangements. There is no prompt-by-prompt documentation."
                    ),
                    (
                        "A public search, connector, portal, or send action chosen by the "
                        "user follows that external service's terms. It is an external "
                        "destination, not a third Mparanza processing category."
                    ),
                    (
                        "The plugins also contact Mparanza to check for updates and the "
                        "status of previously submitted feedback. Those requests contain "
                        "no client or work content, although technical connection "
                        "records may still be logged. Feedback content is sent only through "
                        "the explicit submission workflow."
                    ),
                ],
            },
            {
                "id": "gdpr",
                "title": "One policy for Vera and Clara.",
                "paragraphs": [
                    (
                        "The distinction is architectural, not professional. A Vera "
                        "reconciliation and a Clara presentation both fall in the first "
                        "category when they run inside Codex."
                    ),
                    (
                        "Any Mparanza-hosted service used by either plugin falls in the "
                        "second category and is covered by its service-level description."
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
            ],
        },
        "closing": "One policy for Vera and Clara. No prompt-by-prompt paperwork.",
    },
    "it": {
        "meta_description": (
            "Le due categorie di trattamento per Vera e Clara: il lavoro svolto "
            "dentro Codex e i servizi hosted di Mparanza, che hanno un confine separato."
        ),
        "skip_label": "Vai al contenuto principale",
        "home_label": "Torna a Mparanza",
        "language_selector_label": "Selettore della lingua",
        "eyebrow": "Sicurezza, privacy e dati",
        "title": "Come vengono gestiti i tuoi dati.",
        "summary": (
            "Vera e Clara seguono la stessa regola. Le funzioni dei plugin vengono "
            "eseguite dentro Codex; i servizi hosted di Mparanza hanno un confine "
            "di trattamento separato."
        ),
        "video": {
            "eyebrow": "Vera + Clara · Video",
            "title": "Come Vera e Clara gestiscono i dati.",
            "description": (
                "Scopri che cosa può restare sul tuo computer, che cosa può entrare "
                "in una chiamata a un modello linguistico tramite Codex e quando "
                "Mparanza diventa un confine di trattamento separato."
            ),
            "youtube_id": "q3nS9YBaEP8",
            "watch_label": "Guarda su YouTube",
        },
        "boundary": {
            "title": "Quando Vera e Clara lavorano dentro Codex.",
            "intro": (
                "Vera e Clara non anonimizzano automaticamente i dati. Possono usare "
                "Python in locale per filtrare o aggregare le informazioni quando è "
                "utile. I dati forniti al modello vengono trattati attraverso il piano "
                "ChatGPT già utilizzato dall'utente. I workflow dentro Codex non inviano a "
                "Mparanza file dei clienti, prompt o contenuti del contesto del modello."
            ),
            "local_label": "Il tuo computer",
            "local_detail": "File locali · Python locale · risultati locali",
            "account_label": "Il tuo piano ChatGPT esistente",
            "account_detail": "Contesto del modello · termini · controlli sui dati",
            "exclusion": "I workflow dentro Codex non inviano a Mparanza contenuti del cliente o del lavoro.",
        },
        "sections": [
            {
                "id": "local-execution",
                "title": "L'elaborazione locale si usa quando aiuta il lavoro.",
                "paragraphs": [
                    (
                        "Python in locale può ordinare, calcolare, riconciliare, filtrare, "
                        "aggregare e creare risultati senza spostare prima i file sorgente "
                        "completi su un sistema separato di Mparanza."
                    ),
                    (
                        "Non è anonimizzazione automatica. Quando il lavoro professionale "
                        "richiede nomi, documenti, testo originale o fatti del caso, questi "
                        "contenuti possono entrare nel contesto del modello."
                    ),
                ],
            },
            {
                "id": "security",
                "title": "Una mappa per workflow, non una per prompt.",
                "paragraphs": [
                    (
                        "Ogni workflow dentro Codex viene riesaminato quando viene aggiunto o "
                        "modificato. La mappa registra che cosa resta normalmente locale e "
                        "che cosa può leggere Codex. Non crea un modulo, un consenso o una "
                        "registrazione per ogni prompt."
                    ),
                    (
                        "Non inserire mai password, chiavi API, cookie di autenticazione, "
                        "token di accesso o dati di sessione nei prompt o nei file che "
                        "Codex può leggere."
                    ),
                ],
            },
            {
                "id": "hosted-features",
                "title": "I servizi hosted di Mparanza hanno un confine separato.",
                "paragraphs": [
                    (
                        "Quando una funzione di Vera o Clara usa un servizio hosted di "
                        "Mparanza, i contenuti necessari raggiungono sistemi controllati "
                        "da Mparanza. Interviste hosted, Hosted Voice e il bridge dei dati "
                        "retail sono esempi, non regole diverse."
                    ),
                    (
                        "Ogni servizio hosted viene documentato una volta a livello di "
                        "servizio: che cosa può essere inviato, chi può accedervi e come "
                        "funzionano conservazione e cancellazione. Non esiste documentazione "
                        "prompt per prompt."
                    ),
                    (
                        "Una ricerca pubblica, un connector, un portale o un invio scelto "
                        "dall'utente segue le condizioni del servizio esterno. È una "
                        "destinazione esterna, non una terza categoria di trattamento Mparanza."
                    ),
                    (
                        "I plugin contattano inoltre Mparanza per verificare gli aggiornamenti "
                        "e lo stato dei feedback già inviati. Queste richieste non includono "
                        "contenuti del cliente o del lavoro, anche se possono essere registrati "
                        "dati tecnici di connessione. Il contenuto di un feedback viene "
                        "inviato soltanto tramite il flusso esplicito di trasmissione."
                    ),
                ],
            },
            {
                "id": "gdpr",
                "title": "Una sola regola per Vera e Clara.",
                "paragraphs": [
                    (
                        "La distinzione è architetturale, non professionale. Una "
                        "riconciliazione Vera e una presentazione Clara rientrano entrambe "
                        "nella prima categoria quando operano dentro Codex."
                    ),
                    (
                        "Qualsiasi servizio hosted di Mparanza usato da uno dei due plugin "
                        "rientra nella seconda categoria ed è coperto dalla propria "
                        "descrizione a livello di servizio."
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
                    "label": "Leggi il GDPR (articolo 5)",
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
            ],
        },
        "closing": "Una regola per Vera e Clara. Nessuna burocrazia prompt per prompt.",
    },
    "fr": {
        "meta_description": (
            "Les deux catégories de traitement de Vera et Clara : le travail effectué "
            "dans Codex et les services hébergés par Mparanza, qui ont un périmètre distinct."
        ),
        "skip_label": "Aller au contenu principal",
        "home_label": "Retourner à Mparanza",
        "language_selector_label": "Sélecteur de langue",
        "eyebrow": "Sécurité, confidentialité et données",
        "title": "Comment vos données sont traitées.",
        "summary": (
            "Vera et Clara suivent la même règle. Les fonctions des plugins s'exécutent "
            "dans Codex ; les services hébergés par Mparanza ont un périmètre "
            "de traitement distinct."
        ),
        "video": {
            "eyebrow": "Vera + Clara · Vidéo",
            "title": "Comment Vera et Clara traitent les données.",
            "description": (
                "Découvrez ce qui peut rester sur votre ordinateur, ce qui peut entrer "
                "dans un appel à un modèle de langage via Codex et quand Mparanza "
                "devient un périmètre de traitement distinct."
            ),
            "youtube_id": "gIpiAURzyjA",
            "watch_label": "Voir sur YouTube",
        },
        "boundary": {
            "title": "Quand Vera et Clara travaillent dans Codex.",
            "intro": (
                "Vera et Clara n'anonymisent pas automatiquement les données. Elles "
                "peuvent utiliser Python localement pour filtrer ou agréger des "
                "informations lorsque cela est utile. Les données fournies au modèle "
                "sont traitées dans le cadre de l'offre ChatGPT existante de l'utilisateur. "
                "Les workflows dans Codex n'envoient à Mparanza ni fichiers clients, "
                "ni prompts, ni contenu du contexte du modèle."
            ),
            "local_label": "Votre ordinateur",
            "local_detail": "Fichiers locaux · Python local · livrables locaux",
            "account_label": "Votre offre ChatGPT existante",
            "account_detail": "Contexte du modèle · conditions · contrôles des données",
            "exclusion": "Les workflows dans Codex n'envoient à Mparanza aucun contenu client ou de travail.",
        },
        "sections": [
            {
                "id": "local-execution",
                "title": "Le traitement local est utilisé lorsqu'il aide le travail.",
                "paragraphs": [
                    (
                        "Python peut localement trier, calculer, rapprocher, filtrer, "
                        "agréger et créer des livrables sans déplacer d'abord les fichiers "
                        "sources complets vers un système Mparanza distinct."
                    ),
                    (
                        "Il ne s'agit pas d'une anonymisation automatique. Lorsque le "
                        "travail professionnel exige des noms, des documents, le texte "
                        "original ou des faits propres au dossier, ces contenus peuvent "
                        "entrer dans le contexte du modèle."
                    ),
                ],
            },
            {
                "id": "security",
                "title": "Une cartographie par workflow, pas une par prompt.",
                "paragraphs": [
                    (
                        "Chaque workflow dans Codex est revu lorsqu'il est ajouté ou "
                        "modifié. La cartographie indique ce qui reste normalement local "
                        "et ce que Codex peut lire. Elle ne crée ni formulaire, ni étape "
                        "de consentement, ni enregistrement pour chaque prompt."
                    ),
                    (
                        "Ne placez jamais de mots de passe, clés API, cookies "
                        "d'authentification, jetons d'accès ou données de session dans "
                        "des prompts ou fichiers que Codex peut lire."
                    ),
                ],
            },
            {
                "id": "hosted-features",
                "title": "Les services hébergés par Mparanza ont un périmètre distinct.",
                "paragraphs": [
                    (
                        "Lorsqu'une fonction de Vera ou Clara utilise un service hébergé "
                        "par Mparanza, les contenus nécessaires atteignent des systèmes "
                        "contrôlés par Mparanza. Les entretiens hébergés, Hosted Voice et "
                        "la passerelle de données retail sont des exemples, pas des règles "
                        "différentes."
                    ),
                    (
                        "Chaque service hébergé est documenté une seule fois au niveau du "
                        "service : ce qui peut être transmis, qui peut y accéder, ainsi "
                        "que les modalités de conservation et de suppression. Il n'existe "
                        "aucune documentation prompt par prompt."
                    ),
                    (
                        "Une recherche publique, un connecteur, un portail ou un envoi "
                        "choisi par l'utilisateur relève des conditions du service externe. "
                        "C'est une destination externe, pas une troisième catégorie de "
                        "traitement Mparanza."
                    ),
                    (
                        "Les plugins contactent également Mparanza pour vérifier les mises à "
                        "jour et le statut des retours déjà transmis. Ces requêtes ne "
                        "contiennent aucun contenu client ou de travail, même si des données "
                        "techniques de connexion peuvent être journalisées. Le "
                        "contenu d'un retour n'est envoyé que par le workflow de transmission "
                        "explicite."
                    ),
                ],
            },
            {
                "id": "gdpr",
                "title": "Une seule règle pour Vera et Clara.",
                "paragraphs": [
                    (
                        "La distinction est architecturale, pas professionnelle. Un "
                        "rapprochement Vera et une présentation Clara relèvent tous deux "
                        "de la première catégorie lorsqu'ils s'exécutent dans Codex."
                    ),
                    (
                        "Tout service hébergé par Mparanza utilisé par l'un ou l'autre "
                        "plugin relève de la seconde catégorie et de sa description au "
                        "niveau du service."
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
            ],
        },
        "closing": "Une règle pour Vera et Clara. Aucune paperasse prompt par prompt.",
    },
    "de": {
        "meta_description": (
            "Die zwei Verarbeitungskategorien für Vera und Clara: Arbeit in "
            "Codex und Mparanza-gehostete Dienste mit eigener Grenze."
        ),
        "skip_label": "Zum Hauptinhalt springen",
        "home_label": "Zurück zu Mparanza",
        "language_selector_label": "Sprachauswahl",
        "eyebrow": "Sicherheit, Datenschutz und Daten",
        "title": "So werden Ihre Daten verarbeitet.",
        "summary": (
            "Für Vera und Clara gilt dieselbe Regel. Plugin-Funktionen laufen "
            "in Codex; Mparanza-gehostete Dienste haben eine separate Verarbeitungsgrenze."
        ),
        "video": {
            "eyebrow": "Vera + Clara · Video",
            "title": "Wie Vera und Clara Daten verarbeiten.",
            "description": (
                "Sehen Sie, was auf Ihrem Computer bleiben kann, was über Codex in "
                "eine Sprachmodell-Anfrage eingehen kann und wann Mparanza zu einer "
                "separaten Verarbeitungsgrenze wird."
            ),
            "youtube_id": "g5XV1cZoTaI",
            "watch_label": "Auf YouTube ansehen",
        },
        "boundary": {
            "title": "Wenn Vera und Clara in Codex arbeiten.",
            "intro": (
                "Vera und Clara anonymisieren Daten nicht automatisch. Sie können "
                "Python lokal einsetzen, um Informationen zu filtern oder zu aggregieren, "
                "wenn dies nützlich ist. Daten, die dem Modell bereitgestellt werden, "
                "werden im Rahmen des bestehenden ChatGPT-Tarifs des Nutzers verarbeitet. "
                "Workflows in Codex senden keine Mandantendateien, Prompts oder Inhalte "
                "des Modellkontexts an Mparanza."
            ),
            "local_label": "Ihr Computer",
            "local_detail": "Lokale Dateien · lokales Python · lokale Ergebnisse",
            "account_label": "Ihr bestehender ChatGPT-Tarif",
            "account_detail": "Modellkontext · Bedingungen · Datenkontrollen",
            "exclusion": "Workflows in Codex senden keine Mandanten- oder Arbeitsinhalte an Mparanza.",
        },
        "sections": [
            {
                "id": "local-execution",
                "title": "Lokale Verarbeitung wird eingesetzt, wenn sie der Arbeit hilft.",
                "paragraphs": [
                    (
                        "Lokales Python kann sortieren, berechnen, abstimmen, filtern, "
                        "aggregieren und Ergebnisse erstellen, ohne vollständige "
                        "Quelldateien zuerst auf ein separates Mparanza-System zu verschieben."
                    ),
                    (
                        "Das ist keine automatische Anonymisierung. Wenn die professionelle "
                        "Aufgabe Namen, Dokumente, Originalformulierungen oder Fallfakten "
                        "benötigt, können diese Inhalte in den Modellkontext gelangen."
                    ),
                ],
            },
            {
                "id": "security",
                "title": "Eine Zuordnung pro Workflow, nicht pro Prompt.",
                "paragraphs": [
                    (
                        "Jeder Workflow in Codex wird geprüft, wenn er hinzugefügt oder "
                        "geändert wird. Die Zuordnung hält fest, was normalerweise lokal "
                        "bleibt und was Codex lesen kann. Sie erzeugt kein Formular, keine "
                        "Einwilligungsstufe und keinen Nachweis für jeden Prompt."
                    ),
                    (
                        "Geben Sie niemals Passwörter, API-Schlüssel, Authentifizierungs-"
                        "Cookies, Zugriffstoken oder Sitzungsdaten in Prompts oder Dateien "
                        "ein, die Codex lesen kann."
                    ),
                ],
            },
            {
                "id": "hosted-features",
                "title": "Mparanza-gehostete Dienste haben eine separate Grenze.",
                "paragraphs": [
                    (
                        "Wenn eine Vera- oder Clara-Funktion einen Mparanza-gehosteten "
                        "Dienst nutzt, erreichen die erforderlichen Inhalte von Mparanza "
                        "kontrollierte Systeme. Gehostete Interviews, Hosted Voice und die "
                        "Retail-Daten-Bridge sind Beispiele, keine abweichenden Regeln."
                    ),
                    (
                        "Jeder gehostete Dienst wird einmal auf Dienstebene dokumentiert: "
                        "was übermittelt werden kann, wer darauf zugreifen kann und welche "
                        "Aufbewahrungs- und Löschregeln gelten. Es gibt keine Dokumentation "
                        "für jeden einzelnen Prompt."
                    ),
                    (
                        "Eine vom Nutzer gewählte öffentliche Suche, ein Connector, ein "
                        "Portal oder ein Versand unterliegt den Bedingungen des externen "
                        "Dienstes. Das ist ein externes Ziel, keine dritte Mparanza-"
                        "Verarbeitungskategorie."
                    ),
                    (
                        "Die Plugins kontaktieren Mparanza außerdem, um nach Updates und dem "
                        "Status bereits übermittelten Feedbacks zu sehen. Diese Anfragen "
                        "enthalten keine Mandanten- oder Arbeitsinhalte; technische "
                        "Verbindungsdaten können dennoch protokolliert werden. Feedback-Inhalte "
                        "werden nur über den ausdrücklichen Übermittlungsablauf gesendet."
                    ),
                ],
            },
            {
                "id": "gdpr",
                "title": "Eine Regel für Vera und Clara.",
                "paragraphs": [
                    (
                        "Die Unterscheidung ist architektonisch, nicht berufsbezogen. Eine "
                        "Vera-Abstimmung und eine Clara-Präsentation gehören beide zur "
                        "ersten Kategorie, wenn sie in Codex laufen."
                    ),
                    (
                        "Jeder von einem der beiden Plugins verwendete Mparanza-gehostete "
                        "Dienst gehört zur zweiten Kategorie und wird auf Dienstebene "
                        "beschrieben."
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
            ],
        },
        "closing": "Eine Regel für Vera und Clara. Kein Papierkram für jeden Prompt.",
    },
    "es": {
        "meta_description": (
            "Las dos categorías de tratamiento para Vera y Clara: el trabajo "
            "dentro de Codex y los servicios alojados por Mparanza, con un límite separado."
        ),
        "skip_label": "Ir al contenido principal",
        "home_label": "Volver a Mparanza",
        "language_selector_label": "Selector de idioma",
        "eyebrow": "Seguridad, privacidad y datos",
        "title": "Cómo se tratan tus datos.",
        "summary": (
            "Vera y Clara siguen una misma política. Las funciones de los plugins se "
            "ejecutan dentro de Codex; los servicios alojados por Mparanza "
            "constituyen un límite de tratamiento separado."
        ),
        "video": {
            "eyebrow": "Vera + Clara · Vídeo",
            "title": "Cómo tratan los datos Vera y Clara.",
            "description": (
                "Descubre qué puede permanecer en tu ordenador, qué puede entrar en "
                "una llamada a un modelo de lenguaje a través de Codex y cuándo "
                "Mparanza se convierte en un límite de tratamiento separado."
            ),
            "youtube_id": "LAimCM-F994",
            "watch_label": "Ver en YouTube",
        },
        "boundary": {
            "title": "Cuando Vera y Clara trabajan dentro de Codex.",
            "intro": (
                "Vera y Clara no anonimizan los datos automáticamente. Pueden usar Python "
                "en local para filtrar o agregar información cuando resulte útil. Los datos "
                "facilitados al modelo se tratan mediante el plan de ChatGPT que ya usa el "
                "usuario. Los flujos dentro de Codex no envían a Mparanza archivos de clientes, "
                "prompts ni contenido del contexto del modelo."
            ),
            "local_label": "Tu ordenador",
            "local_detail": "Archivos locales · Python local · resultados locales",
            "account_label": "Tu plan de ChatGPT actual",
            "account_detail": "Contexto del modelo · condiciones del plan · controles de datos",
            "exclusion": (
                "Los flujos dentro de Codex no envían contenido de clientes ni del trabajo "
                "a Mparanza."
            ),
        },
        "sections": [
            {
                "id": "local-execution",
                "title": "El tratamiento local se usa cuando ayuda al trabajo.",
                "paragraphs": [
                    (
                        "Python en local puede ordenar, calcular, conciliar, filtrar, agregar "
                        "y crear resultados sin trasladar antes los archivos fuente completos "
                        "a un sistema separado de Mparanza."
                    ),
                    (
                        "Esto no es anonimización automática. Cuando la tarea profesional "
                        "requiere nombres, documentos, el idioma original o hechos del caso, "
                        "ese material puede entrar en el contexto del modelo."
                    ),
                ],
            },
            {
                "id": "security",
                "title": "Un mapeo por flujo de trabajo, no por prompt.",
                "paragraphs": [
                    (
                        "Cada flujo dentro de Codex se revisa cuando se añade o modifica. La revisión "
                        "registra qué permanece normalmente en local y qué puede leer Codex. "
                        "No crea un formulario, un paso de consentimiento ni un registro para "
                        "cada prompt."
                    ),
                    (
                        "Nunca incluyas contraseñas, claves de API, cookies de autenticación, "
                        "tokens de acceso ni datos de sesión en prompts o archivos que Codex "
                        "pueda leer."
                    ),
                ],
            },
            {
                "id": "hosted-features",
                "title": "Los servicios alojados por Mparanza tienen un límite separado.",
                "paragraphs": [
                    (
                        "Cuando una función de Vera o Clara usa un servicio alojado por "
                        "Mparanza, el contenido necesario para ese servicio llega a sistemas "
                        "controlados por Mparanza. Las entrevistas alojadas, Hosted Voice y "
                        "el puente de datos de retailers son ejemplos, no políticas separadas."
                    ),
                    (
                        "Cada servicio alojado se documenta una vez a nivel de servicio: qué "
                        "se puede enviar, quién puede acceder y cuáles son las condiciones de "
                        "conservación y eliminación. No hay documentación para cada prompt."
                    ),
                    (
                        "Las búsquedas públicas, conectores, portales o acciones de envío que "
                        "elija el usuario se rigen por las condiciones de ese servicio externo. "
                        "Se trata de un destino externo, no de una tercera categoría de "
                        "tratamiento de Mparanza."
                    ),
                    (
                        "Los plugins también contactan con Mparanza para comprobar actualizaciones "
                        "y el estado de comentarios enviados anteriormente. Esas solicitudes no "
                        "contienen contenido de clientes ni del trabajo, aunque pueden registrarse "
                        "los datos técnicos de conexión. El contenido de los comentarios "
                        "solo se envía mediante el flujo de envío explícito."
                    ),
                ],
            },
            {
                "id": "gdpr",
                "title": "Una política para Vera y Clara.",
                "paragraphs": [
                    (
                        "La distinción es arquitectónica, no profesional. Una conciliación de "
                        "Vera y una presentación de Clara pertenecen a la primera categoría "
                        "cuando se ejecutan dentro de Codex."
                    ),
                    (
                        "Cualquier servicio alojado por Mparanza que use cualquiera de los dos "
                        "plugins pertenece a la segunda categoría y queda cubierto por su "
                        "descripción a nivel de servicio."
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
            ],
        },
        "closing": "Una política para Vera y Clara. Sin documentación para cada prompt.",
    },
}


def get_data_handling_content(lang: str) -> dict[str, Any]:
    """Return independent localized content for the public data-handling page."""

    content = _DATA_HANDLING_CONTENT.get(lang) or _DATA_HANDLING_CONTENT["en"]
    return deepcopy(content)
