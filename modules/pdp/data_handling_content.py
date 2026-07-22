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
            "How local Codex work, model requests, Mparanza-hosted features, and "
            "external services handle professional data."
        ),
        "skip_label": "Skip to main content",
        "home_label": "Return to Mparanza",
        "language_selector_label": "Language selector",
        "eyebrow": "Security, privacy and data",
        "title": "How your data is handled.",
        "summary": (
            "Real professional work may require Codex to read client data. Local "
            "execution tells you where scripts run; it does not make model-readable "
            "content anonymous."
        ),
        "boundary": {
            "title": "The local data boundary.",
            "intro": (
                "In a local workflow, scripts run on your computer. When Codex "
                "interprets content, the documents, passages, facts, or other content "
                "it reads enter the model context through your Codex/OpenAI account. "
                "They do not pass through Mparanza."
            ),
            "local_label": "Your computer",
            "local_detail": "Local files · local scripts · local outputs",
            "account_label": "Your Codex / OpenAI account",
            "account_detail": "Content Codex reads · account terms · data controls",
            "exclusion": "Local workflow: Mparanza is not a recipient.",
        },
        "sections": [
            {
                "id": "local-execution",
                "title": "Local processing is useful. It is not anonymization.",
                "paragraphs": [
                    (
                        "Vera and Clara's tools execute from the Codex workspace on "
                        "your computer. They can sort, calculate, reconcile, extract, "
                        "and create outputs where the files already live."
                    ),
                    (
                        "When Codex must interpret the work, it may read original "
                        "documents, images, text, data, or extracted facts through your "
                        "account. A file staying on your computer does not mean its "
                        "contents stay out of the model context."
                    ),
                ],
            },
            {
                "id": "security",
                "title": "Codex may read real client data.",
                "paragraphs": [
                    (
                        "Names, identity and ownership details, financial or tax facts, "
                        "correspondence, and supporting evidence may be needed for the "
                        "professional task. Vera and Clara do not automatically "
                        "anonymize case material or routinely remove names and personal "
                        "data."
                    ),
                    (
                        "Never put passwords, API keys, authentication cookies, access "
                        "tokens, or session material in prompts or files Codex can read."
                    ),
                ],
            },
            {
                "id": "hosted-features",
                "title": "Local, hosted, and external are different routes.",
                "paragraphs": [
                    (
                        "Local Vera and Clara workflows use your Codex/OpenAI account; "
                        "Mparanza is not the intermediary and does not receive the work."
                    ),
                    (
                        "If you choose a Mparanza-hosted feature, the content needed to "
                        "provide it reaches Mparanza systems under the stated retention "
                        "and deletion rules."
                    ),
                    (
                        "Public searches, portals, and external services receive the "
                        "queries, uploads, or submissions you send them and apply their "
                        "own permissions and terms."
                    ),
                ],
            },
            {
                "id": "gdpr",
                "title": "Compliance follows the actual data flow.",
                "paragraphs": [
                    (
                        "Local processing can reduce copies and systems involved. It "
                        "does not establish anonymity, a legal basis, or GDPR compliance. "
                        "GDPR data minimisation is purpose-based; it does not mean "
                        "automatically removing every identifier."
                    ),
                    (
                        "The firm chooses the Codex/OpenAI account used for professional "
                        "work and configures the data controls available for that plan. "
                        "Mparanza-hosted features and other external services are separate "
                        "routes, with their own recipients and terms."
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
        "closing": "Local processing changes the route, not the nature, of the data.",
    },
    "it": {
        "meta_description": (
            "Come il lavoro locale in Codex, le richieste al modello, le funzioni "
            "hosted di Mparanza e i servizi esterni trattano i dati professionali."
        ),
        "skip_label": "Vai al contenuto principale",
        "home_label": "Torna a Mparanza",
        "language_selector_label": "Selettore della lingua",
        "eyebrow": "Sicurezza, privacy e dati",
        "title": "Come vengono gestiti i tuoi dati.",
        "summary": (
            "Il lavoro professionale può richiedere a Codex di leggere dati dei "
            "clienti. L'esecuzione locale indica dove girano gli script; non rende "
            "anonimi i contenuti che Codex legge."
        ),
        "boundary": {
            "title": "Il confine dei dati locali.",
            "intro": (
                "In un flusso locale, gli script girano sul tuo computer. Quando Codex "
                "interpreta un contenuto, i documenti, i passaggi, i fatti o gli altri "
                "contenuti che legge entrano nel contesto del modello tramite il tuo "
                "account Codex/OpenAI. Non passano da Mparanza."
            ),
            "local_label": "Il tuo computer",
            "local_detail": "File locali · script locali · risultati locali",
            "account_label": "Il tuo account Codex / OpenAI",
            "account_detail": "Contenuti letti da Codex · termini · controlli sui dati",
            "exclusion": "Flusso locale: Mparanza non è destinataria dei dati.",
        },
        "sections": [
            {
                "id": "local-execution",
                "title": "L'elaborazione locale è utile. Non è anonimizzazione.",
                "paragraphs": [
                    (
                        "Gli strumenti di Vera e Clara girano dall'ambiente Codex sul "
                        "tuo computer. Possono ordinare, calcolare, riconciliare, estrarre "
                        "e creare risultati dove si trovano già i file."
                    ),
                    (
                        "Quando Codex deve interpretare il lavoro, può leggere documenti, "
                        "immagini, testi, dati originali o fatti estratti tramite il tuo "
                        "account. Che un file resti sul computer non significa che il "
                        "suo contenuto resti fuori dal contesto del modello."
                    ),
                ],
            },
            {
                "id": "security",
                "title": "Codex può leggere dati reali dei clienti.",
                "paragraphs": [
                    (
                        "Nomi, dati su identità e titolarità, fatti finanziari o fiscali, "
                        "corrispondenza e documenti di supporto possono servire al lavoro "
                        "professionale. Vera e Clara non anonimizzano automaticamente il "
                        "materiale del caso né rimuovono sistematicamente nomi e dati personali."
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
                "title": "Locale, hosted ed esterno sono percorsi diversi.",
                "paragraphs": [
                    (
                        "I flussi locali di Vera e Clara usano il tuo account Codex/OpenAI; "
                        "Mparanza non fa da intermediario e non riceve il lavoro."
                    ),
                    (
                        "Se scegli una funzione hosted da Mparanza, i contenuti necessari "
                        "a fornirla raggiungono i sistemi Mparanza secondo le regole "
                        "dichiarate di conservazione e cancellazione."
                    ),
                    (
                        "Ricerche pubbliche, portali e servizi esterni ricevono le query, "
                        "i file o gli invii che trasmetti e applicano autorizzazioni e "
                        "condizioni proprie."
                    ),
                ],
            },
            {
                "id": "gdpr",
                "title": "La conformità segue il flusso reale dei dati.",
                "paragraphs": [
                    (
                        "L'elaborazione locale può ridurre copie e sistemi coinvolti. Non "
                        "stabilisce anonimato, base giuridica o conformità al GDPR. La "
                        "minimizzazione prevista dal GDPR dipende dallo scopo; non "
                        "significa rimuovere automaticamente ogni identificativo."
                    ),
                    (
                        "Lo studio sceglie l'account Codex/OpenAI usato per il lavoro "
                        "professionale e configura i controlli disponibili per quel piano. "
                        "Le funzioni ospitate da Mparanza e gli altri servizi esterni sono "
                        "percorsi separati, con destinatari e condizioni propri."
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
        "closing": "L'elaborazione locale cambia il percorso, non la natura dei dati.",
    },
    "fr": {
        "meta_description": (
            "Comment le travail Codex local, les requêtes au modèle, les fonctions "
            "hébergées par Mparanza et les services externes traitent les données "
            "professionnelles."
        ),
        "skip_label": "Aller au contenu principal",
        "home_label": "Retourner à Mparanza",
        "language_selector_label": "Sélecteur de langue",
        "eyebrow": "Sécurité, confidentialité et données",
        "title": "Comment vos données sont traitées.",
        "summary": (
            "Le travail professionnel peut nécessiter que Codex lise des données clients. "
            "L'exécution locale indique où les scripts s'exécutent ; elle ne rend pas "
            "anonymes les contenus lus par Codex."
        ),
        "boundary": {
            "title": "Le périmètre des données locales.",
            "intro": (
                "Dans un flux local, les scripts s'exécutent sur votre ordinateur. "
                "Lorsque Codex interprète un contenu, les documents, passages, faits "
                "ou autres contenus qu'il lit entrent dans le contexte du modèle via "
                "votre compte Codex/OpenAI. Ils ne transitent pas par Mparanza."
            ),
            "local_label": "Votre ordinateur",
            "local_detail": "Fichiers locaux · scripts locaux · livrables locaux",
            "account_label": "Votre compte Codex / OpenAI",
            "account_detail": "Contenus lus par Codex · conditions · contrôles des données",
            "exclusion": "Flux local : Mparanza n'est pas destinataire des données.",
        },
        "sections": [
            {
                "id": "local-execution",
                "title": "Le traitement local est utile. Ce n'est pas une anonymisation.",
                "paragraphs": [
                    (
                        "Les outils de Vera et Clara s'exécutent depuis l'espace Codex "
                        "sur votre ordinateur. Ils peuvent trier, calculer, rapprocher, "
                        "extraire et produire des livrables là où se trouvent les fichiers."
                    ),
                    (
                        "Lorsque Codex doit interpréter le travail, il peut lire des "
                        "documents, images, textes, données d'origine ou faits extraits "
                        "via votre compte. Le fait qu'un fichier reste sur l'ordinateur "
                        "ne signifie pas que son contenu reste hors du contexte du modèle."
                    ),
                ],
            },
            {
                "id": "security",
                "title": "Codex peut lire de vraies données clients.",
                "paragraphs": [
                    (
                        "Noms, données d'identité et de détention, faits financiers ou "
                        "fiscaux, correspondance et justificatifs peuvent être nécessaires "
                        "au travail professionnel. Vera et Clara n'anonymisent pas "
                        "automatiquement les dossiers et ne suppriment pas "
                        "systématiquement les noms ou les données personnelles."
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
                "title": "Local, hébergé et externe sont des parcours distincts.",
                "paragraphs": [
                    (
                        "Les flux locaux de Vera et Clara utilisent votre compte "
                        "Codex/OpenAI ; Mparanza n'est pas l'intermédiaire et ne reçoit "
                        "pas le travail."
                    ),
                    (
                        "Si vous choisissez une fonction hébergée par Mparanza, les "
                        "contenus nécessaires atteignent les systèmes Mparanza selon les "
                        "règles de conservation et de suppression indiquées."
                    ),
                    (
                        "Les recherches publiques, portails et services externes reçoivent "
                        "les requêtes, fichiers ou soumissions que vous leur transmettez et "
                        "appliquent leurs propres autorisations et conditions."
                    ),
                ],
            },
            {
                "id": "gdpr",
                "title": "La conformité suit le flux réel des données.",
                "paragraphs": [
                    (
                        "Le traitement local peut réduire les copies et les systèmes "
                        "impliqués. Il n'établit ni anonymat, ni base juridique, ni "
                        "conformité au RGPD. La minimisation prévue par le RGPD dépend "
                        "de la finalité ; elle ne consiste pas à supprimer automatiquement "
                        "tout identifiant."
                    ),
                    (
                        "Le cabinet choisit le compte Codex/OpenAI utilisé pour le travail "
                        "professionnel et configure les contrôles disponibles pour cette "
                        "offre. Les fonctions hébergées par Mparanza et les autres services "
                        "externes sont des parcours distincts, avec leurs propres "
                        "destinataires et conditions."
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
        "closing": "Le traitement local change le parcours, pas la nature des données.",
    },
    "de": {
        "meta_description": (
            "Wie lokale Codex-Arbeit, Modellanfragen, von Mparanza gehostete "
            "Funktionen und externe Dienste professionelle Daten verarbeiten."
        ),
        "skip_label": "Zum Hauptinhalt springen",
        "home_label": "Zurück zu Mparanza",
        "language_selector_label": "Sprachauswahl",
        "eyebrow": "Sicherheit, Datenschutz und Daten",
        "title": "So werden Ihre Daten verarbeitet.",
        "summary": (
            "Professionelle Arbeit kann erfordern, dass Codex Mandantendaten liest. "
            "Lokale Ausführung beschreibt, wo Skripte laufen; sie macht Inhalte, die "
            "Codex liest, nicht anonym."
        ),
        "boundary": {
            "title": "Die lokale Datengrenze.",
            "intro": (
                "In einem lokalen Ablauf laufen Skripte auf Ihrem Computer. Wenn Codex "
                "Inhalte auswertet, gelangen die Dokumente, Passagen, Fakten oder "
                "anderen Inhalte, die Codex liest, über Ihr Codex-/OpenAI-Konto in den "
                "Modellkontext. Sie laufen nicht über Mparanza."
            ),
            "local_label": "Ihr Computer",
            "local_detail": "Lokale Dateien · lokale Skripte · lokale Ergebnisse",
            "account_label": "Ihr Codex-/OpenAI-Konto",
            "account_detail": "Von Codex gelesene Inhalte · Bedingungen · Datenkontrollen",
            "exclusion": "Lokaler Ablauf: Mparanza ist kein Datenempfänger.",
        },
        "sections": [
            {
                "id": "local-execution",
                "title": "Lokale Verarbeitung ist nützlich. Sie ist keine Anonymisierung.",
                "paragraphs": [
                    (
                        "Die Werkzeuge von Vera und Clara laufen aus dem Codex-"
                        "Arbeitsbereich auf Ihrem Computer. Sie können Dateien dort "
                        "sortieren, berechnen, abstimmen, extrahieren und Ergebnisse "
                        "erstellen, wo die Dateien bereits liegen."
                    ),
                    (
                        "Muss Codex die Arbeit auswerten, kann es Originaldokumente, "
                        "Bilder, Texte, Daten oder extrahierte Fakten über Ihr Konto "
                        "lesen. Dass eine Datei auf dem Computer bleibt, bedeutet nicht, "
                        "dass ihr Inhalt außerhalb des Modellkontexts bleibt."
                    ),
                ],
            },
            {
                "id": "security",
                "title": "Codex kann echte Mandantendaten lesen.",
                "paragraphs": [
                    (
                        "Namen, Identitäts- und Beteiligungsdaten, finanzielle oder "
                        "steuerliche Fakten, Korrespondenz und Nachweise können für die "
                        "professionelle Aufgabe erforderlich sein. Vera und Clara "
                        "anonymisieren Fallmaterial nicht automatisch und entfernen "
                        "Namen oder personenbezogene Daten nicht pauschal."
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
                "title": "Lokale, gehostete und externe Wege sind getrennt.",
                "paragraphs": [
                    (
                        "Lokale Vera- und Clara-Abläufe verwenden Ihr Codex-/OpenAI-"
                        "Konto; Mparanza ist nicht zwischengeschaltet und erhält die "
                        "Arbeit nicht."
                    ),
                    (
                        "Wählen Sie eine von Mparanza gehostete Funktion, erreichen die "
                        "dafür erforderlichen Inhalte Mparanza-Systeme nach den genannten "
                        "Aufbewahrungs- und Löschregeln."
                    ),
                    (
                        "Öffentliche Recherchen, Portale und externe Dienste erhalten "
                        "die Suchanfragen, Dateien oder Eingaben, die Sie senden, und "
                        "wenden ihre eigenen Berechtigungen und Bedingungen an."
                    ),
                ],
            },
            {
                "id": "gdpr",
                "title": "Compliance folgt dem tatsächlichen Datenfluss.",
                "paragraphs": [
                    (
                        "Lokale Verarbeitung kann Kopien und beteiligte Systeme "
                        "verringern. Sie begründet weder Anonymität noch Rechtsgrundlage "
                        "oder DSGVO-Konformität. Datenminimierung nach der DSGVO richtet "
                        "sich nach dem Zweck; sie bedeutet nicht, jede Kennung automatisch "
                        "zu entfernen."
                    ),
                    (
                        "Die Kanzlei wählt das Codex-/OpenAI-Konto für die berufliche Arbeit "
                        "und konfiguriert die für den Tarif verfügbaren Datenkontrollen. Von "
                        "Mparanza gehostete Funktionen und andere externe Dienste sind "
                        "getrennte Wege mit eigenen Empfängern und Bedingungen."
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
        "closing": "Lokale Verarbeitung ändert den Weg, nicht die Art der Daten.",
    },
}


def get_data_handling_content(lang: str) -> dict[str, Any]:
    """Return independent localized content for the public data-handling page."""

    content = _DATA_HANDLING_CONTENT.get(lang) or _DATA_HANDLING_CONTENT["en"]
    return deepcopy(content)
