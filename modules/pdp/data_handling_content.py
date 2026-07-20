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
_SOURCE_URL = "https://github.com/fabioannovazzi/app_files"


_DATA_HANDLING_CONTENT: dict[str, dict[str, Any]] = {
    "en": {
        "meta_description": (
            "How Mparanza keeps local Codex work out of Mparanza systems, runs "
            "scripts on your machine, and approaches security, privacy, and GDPR."
        ),
        "skip_label": "Skip to main content",
        "home_label": "Return to Mparanza",
        "language_selector_label": "Language selector",
        "eyebrow": "Security, privacy and data",
        "title": "How your data is handled.",
        "summary": (
            "Mparanza is designed to stay out of the path of your work. The "
            "important question is not whether you trust a promise, but which "
            "systems actually receive your data."
        ),
        "boundary": {
            "title": "The local data boundary.",
            "intro": (
                "Vera and Clara add specialist methods to the Codex environment "
                "you already use. They do not add a Mparanza application server "
                "between your workspace and OpenAI."
            ),
            "local_label": "Your computer",
            "local_detail": "Codex workspace · local files · scripts and outputs",
            "account_label": "Your Codex / OpenAI account",
            "account_detail": "Model requests · account terms · data controls",
            "exclusion": "Mparanza does not receive the working content.",
        },
        "sections": [
            {
                "id": "local-execution",
                "title": "The scripts run on your machine.",
                "paragraphs": [
                    (
                        "Vera and Clara's tools execute from the Codex workspace on "
                        "your computer, using the local files, software, and "
                        "permissions you control."
                    ),
                    (
                        "This lets you analyze, filter, and aggregate data locally, "
                        "and limit what you send to the model to the information "
                        "needed for the request."
                    ),
                    (
                        "Unlike a conventional ChatGPT data-analysis workflow, where "
                        "uploaded files are made available to a provider-managed "
                        "Jupyter notebook, these scripts run where the files already live."
                    ),
                ],
            },
            {
                "id": "security",
                "title": "One fewer system to trust.",
                "paragraphs": [
                    (
                        "Model requests use your existing Codex/OpenAI account. "
                        "Mparanza is not the intermediary and cannot inspect prompts, "
                        "files, or outputs it does not receive."
                    ),
                    (
                        "The terms, data controls, and workspace policies attached "
                        "to your account continue to apply."
                    ),
                ],
            },
            {
                "id": "gdpr",
                "title": "GDPR follows the actual data flow.",
                "paragraphs": [
                    (
                        "A local-first architecture can reduce the number of recipients "
                        "and copies, but it does not by itself answer every GDPR "
                        "question. Local workflows do not add Mparanza as another "
                        "recipient of your working content."
                    ),
                    (
                        "Where Mparanza processes personal data, our policy explains "
                        "the scope, purpose, retention, and rights that apply."
                    ),
                ],
            },
            {
                "id": "hosted-features",
                "title": "Hosted features are explicit.",
                "paragraphs": [
                    (
                        "If you choose an optional Mparanza-hosted feature, the content "
                        "needed to provide it reaches systems controlled by Mparanza. "
                        "We identify that boundary and explain the applicable retention "
                        "and deletion rules in our policy."
                    ),
                    (
                        "Services you connect yourself remain governed by their own "
                        "permissions and terms."
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
        "closing": "Secure by design. Trust minimized, not merely promised.",
    },
    "it": {
        "meta_description": (
            "Come Mparanza mantiene il lavoro locale in Codex fuori dai propri "
            "sistemi, esegue gli script sul tuo computer e affronta sicurezza, "
            "privacy e GDPR."
        ),
        "skip_label": "Vai al contenuto principale",
        "home_label": "Torna a Mparanza",
        "language_selector_label": "Selettore della lingua",
        "eyebrow": "Sicurezza, privacy e dati",
        "title": "Come vengono gestiti i tuoi dati.",
        "summary": (
            "Mparanza nasce per restare fuori dal flusso del tuo lavoro. La "
            "domanda importante non è se ti fidi di una promessa, ma quali "
            "sistemi ricevono davvero i tuoi dati."
        ),
        "boundary": {
            "title": "Il confine dei dati locali.",
            "intro": (
                "Vera e Clara aggiungono metodi specialistici all'ambiente Codex "
                "che già usi. Non aggiungono un server applicativo Mparanza tra "
                "il tuo spazio di lavoro e OpenAI."
            ),
            "local_label": "Il tuo computer",
            "local_detail": "Ambiente Codex · file locali · script e risultati",
            "account_label": "Il tuo account Codex / OpenAI",
            "account_detail": "Richieste al modello · termini · controlli sui dati",
            "exclusion": "Mparanza non riceve i contenuti di lavoro.",
        },
        "sections": [
            {
                "id": "local-execution",
                "title": "Gli script vengono eseguiti sul tuo computer.",
                "paragraphs": [
                    (
                        "Gli strumenti di Vera e Clara vengono eseguiti dall'ambiente "
                        "Codex sul tuo computer, usando i file locali, il software e "
                        "le autorizzazioni che controlli."
                    ),
                    (
                        "Questo consente di analizzare, filtrare e aggregare i dati "
                        "localmente e di limitare ciò che viene inviato al modello alle "
                        "sole informazioni necessarie per la richiesta."
                    ),
                    (
                        "A differenza di un flusso convenzionale di analisi dati in "
                        "ChatGPT, in cui i file caricati vengono messi a disposizione "
                        "di un notebook Jupyter gestito dal fornitore, questi script "
                        "vengono eseguiti dove si trovano già i file."
                    ),
                ],
            },
            {
                "id": "security",
                "title": "Un sistema in meno di cui fidarsi.",
                "paragraphs": [
                    (
                        "Le richieste al modello usano il tuo account Codex/OpenAI. "
                        "Mparanza non fa da intermediario e non può esaminare prompt, "
                        "file o risultati che non riceve."
                    ),
                    (
                        "I termini, i controlli sui dati e le regole dello spazio di "
                        "lavoro associati al tuo account continuano ad applicarsi."
                    ),
                ],
            },
            {
                "id": "gdpr",
                "title": "Il GDPR segue il flusso reale dei dati.",
                "paragraphs": [
                    (
                        "Un'architettura local-first può ridurre il numero di "
                        "destinatari e di copie, ma da sola non risponde a ogni "
                        "questione GDPR. I flussi locali non aggiungono Mparanza come "
                        "ulteriore destinatario dei tuoi contenuti di lavoro."
                    ),
                    (
                        "Quando Mparanza tratta dati personali, la nostra informativa "
                        "spiega ambito, finalità, conservazione e diritti applicabili."
                    ),
                ],
            },
            {
                "id": "hosted-features",
                "title": "Le funzionalità ospitate sono esplicite.",
                "paragraphs": [
                    (
                        "Se scegli una funzionalità opzionale ospitata da Mparanza, i "
                        "contenuti necessari a fornirla arrivano su sistemi controllati "
                        "da Mparanza. Indichiamo chiaramente questo confine e spieghiamo "
                        "nella nostra informativa le regole applicabili di conservazione "
                        "e cancellazione."
                    ),
                    (
                        "I servizi che colleghi direttamente restano regolati dalle "
                        "rispettive autorizzazioni e condizioni."
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
        "closing": "Sicuri fin dalla progettazione. Meno fiducia richiesta, non una promessa in più.",
    },
    "fr": {
        "meta_description": (
            "Comment Mparanza maintient le travail Codex local hors de ses systèmes, "
            "exécute les scripts sur votre ordinateur et aborde la sécurité, la "
            "confidentialité et le RGPD."
        ),
        "skip_label": "Aller au contenu principal",
        "home_label": "Retourner à Mparanza",
        "language_selector_label": "Sélecteur de langue",
        "eyebrow": "Sécurité, confidentialité et données",
        "title": "Comment vos données sont traitées.",
        "summary": (
            "L'architecture de Mparanza est conçue pour ne pas s'interposer dans "
            "votre travail. La question importante n'est pas de savoir si vous "
            "faites confiance à une promesse, mais quels systèmes reçoivent "
            "réellement vos données."
        ),
        "boundary": {
            "title": "Le périmètre des données locales.",
            "intro": (
                "Vera et Clara ajoutent des méthodes spécialisées à l'environnement "
                "Codex que vous utilisez déjà. Elles n'ajoutent aucun serveur "
                "applicatif Mparanza entre votre espace de travail et OpenAI."
            ),
            "local_label": "Votre ordinateur",
            "local_detail": "Espace Codex · fichiers locaux · scripts et livrables",
            "account_label": "Votre compte Codex / OpenAI",
            "account_detail": "Requêtes au modèle · conditions · contrôles des données",
            "exclusion": "Mparanza ne reçoit pas les contenus de travail.",
        },
        "sections": [
            {
                "id": "local-execution",
                "title": "Les scripts s'exécutent sur votre ordinateur.",
                "paragraphs": [
                    (
                        "Les outils de Vera et Clara s'exécutent depuis l'espace Codex "
                        "sur votre ordinateur, en utilisant les fichiers locaux, les "
                        "logiciels et les autorisations que vous contrôlez."
                    ),
                    (
                        "Vous pouvez ainsi analyser, filtrer et agréger les données "
                        "localement, et limiter ce qui est envoyé au modèle aux seules "
                        "informations nécessaires à la requête."
                    ),
                    (
                        "Contrairement à un flux classique d'analyse de données dans "
                        "ChatGPT, où les fichiers téléversés sont mis à disposition "
                        "d'un notebook Jupyter géré par le fournisseur, ces scripts "
                        "s'exécutent là où les fichiers se trouvent déjà."
                    ),
                ],
            },
            {
                "id": "security",
                "title": "Un système de moins auquel faire confiance.",
                "paragraphs": [
                    (
                        "Les requêtes au modèle utilisent votre compte Codex/OpenAI. "
                        "Mparanza ne sert pas d'intermédiaire et ne peut pas examiner "
                        "les prompts, fichiers ou livrables qu'elle ne reçoit pas."
                    ),
                    (
                        "Les conditions, contrôles des données et règles de l'espace "
                        "de travail liés à votre compte continuent de s'appliquer."
                    ),
                ],
            },
            {
                "id": "gdpr",
                "title": "Le RGPD suit le flux réel des données.",
                "paragraphs": [
                    (
                        "Une architecture privilégiant le traitement local peut réduire "
                        "le nombre de destinataires et de copies, mais elle ne répond "
                        "pas à elle seule à toutes les questions liées au RGPD. Les flux "
                        "locaux n'ajoutent pas Mparanza comme destinataire supplémentaire "
                        "de vos contenus de travail."
                    ),
                    (
                        "Lorsque Mparanza traite des données à caractère personnel, "
                        "notre politique précise le périmètre, les finalités, la durée "
                        "de conservation et les droits applicables."
                    ),
                ],
            },
            {
                "id": "hosted-features",
                "title": "Les fonctionnalités hébergées sont clairement signalées.",
                "paragraphs": [
                    (
                        "Si vous choisissez une fonctionnalité optionnelle hébergée par "
                        "Mparanza, les contenus nécessaires sont transmis à des systèmes "
                        "contrôlés par Mparanza. Nous signalons clairement ce changement "
                        "de périmètre et expliquons dans notre politique les règles de "
                        "conservation et de suppression applicables."
                    ),
                    (
                        "Les services que vous connectez vous-même restent régis par "
                        "leurs propres autorisations et conditions."
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
        "closing": "Sécurisés dès la conception. Moins de confiance à accorder, pas une promesse de plus.",
    },
    "de": {
        "meta_description": (
            "Wie Mparanza lokale Codex-Arbeit aus Mparanza-Systemen heraushält, "
            "Skripte auf Ihrem Computer ausführt und Sicherheit, Datenschutz und "
            "DSGVO behandelt."
        ),
        "skip_label": "Zum Hauptinhalt springen",
        "home_label": "Zurück zu Mparanza",
        "language_selector_label": "Sprachauswahl",
        "eyebrow": "Sicherheit, Datenschutz und Daten",
        "title": "So werden Ihre Daten verarbeitet.",
        "summary": (
            "Mparanza ist darauf ausgelegt, nicht Teil des Datenwegs Ihrer Arbeit "
            "zu sein. Entscheidend ist nicht, ob Sie einem Versprechen vertrauen, "
            "sondern welche Systeme Ihre Daten tatsächlich erhalten."
        ),
        "boundary": {
            "title": "Die lokale Datengrenze.",
            "intro": (
                "Vera und Clara ergänzen Ihre bestehende Codex-Umgebung um "
                "fachliche Methoden. Sie schalten keinen Mparanza-Anwendungsserver "
                "zwischen Ihren Arbeitsbereich und OpenAI."
            ),
            "local_label": "Ihr Computer",
            "local_detail": "Codex-Arbeitsbereich · lokale Dateien · Skripte und Ergebnisse",
            "account_label": "Ihr Codex-/OpenAI-Konto",
            "account_detail": "Modellanfragen · Bedingungen · Datenkontrollen",
            "exclusion": "Mparanza erhält die Arbeitsinhalte nicht.",
        },
        "sections": [
            {
                "id": "local-execution",
                "title": "Die Skripte laufen auf Ihrem Computer.",
                "paragraphs": [
                    (
                        "Die Werkzeuge von Vera und Clara werden aus dem Codex-"
                        "Arbeitsbereich auf Ihrem Computer ausgeführt und verwenden "
                        "die lokalen Dateien, Programme und Berechtigungen, die Sie "
                        "kontrollieren."
                    ),
                    (
                        "So können Sie Daten lokal analysieren, filtern und aggregieren "
                        "und nur die für die jeweilige Anfrage erforderlichen "
                        "Informationen an das Modell senden."
                    ),
                    (
                        "Anders als bei einem herkömmlichen Datenanalyse-Ablauf in "
                        "ChatGPT, bei dem hochgeladene Dateien in einem vom Anbieter "
                        "verwalteten Jupyter-Notebook bereitgestellt werden, laufen "
                        "diese Skripte dort, wo sich die Dateien bereits befinden."
                    ),
                ],
            },
            {
                "id": "security",
                "title": "Ein System weniger, dem Sie vertrauen müssen.",
                "paragraphs": [
                    (
                        "Modellanfragen verwenden Ihr Codex-/OpenAI-Konto. Mparanza "
                        "ist nicht zwischengeschaltet und kann Prompts, Dateien oder "
                        "Ergebnisse, die Mparanza nicht erhält, nicht einsehen."
                    ),
                    (
                        "Die Bedingungen, Datenkontrollen und Arbeitsbereichsregeln "
                        "Ihres Kontos gelten weiterhin."
                    ),
                ],
            },
            {
                "id": "gdpr",
                "title": "Die DSGVO folgt dem tatsächlichen Datenfluss.",
                "paragraphs": [
                    (
                        "Eine Local-first-Architektur kann die Zahl der Empfänger und "
                        "Kopien verringern, beantwortet für sich allein jedoch nicht "
                        "jede DSGVO-Frage. Lokale Arbeitsabläufe machen Mparanza nicht "
                        "zu einem weiteren Empfänger Ihrer Arbeitsinhalte."
                    ),
                    (
                        "Wenn Mparanza personenbezogene Daten verarbeitet, erläutert "
                        "unsere Richtlinie Umfang, Zweck, Aufbewahrung und geltende Rechte."
                    ),
                ],
            },
            {
                "id": "hosted-features",
                "title": "Gehostete Funktionen werden klar ausgewiesen.",
                "paragraphs": [
                    (
                        "Wenn Sie eine optionale, von Mparanza gehostete Funktion "
                        "wählen, gelangen die dafür erforderlichen Inhalte auf von "
                        "Mparanza kontrollierte Systeme. Wir weisen klar auf diese "
                        "Datengrenze hin und erläutern die geltenden Aufbewahrungs- "
                        "und Löschregeln in unserer Richtlinie."
                    ),
                    (
                        "Dienste, die Sie selbst verbinden, unterliegen weiterhin "
                        "ihren eigenen Berechtigungen und Bedingungen."
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
        "closing": "Sicher konzipiert. Weniger notwendiges Vertrauen statt eines weiteren Versprechens.",
    },
}


def get_data_handling_content(lang: str) -> dict[str, Any]:
    """Return independent localized content for the public data-handling page."""

    content = _DATA_HANDLING_CONTENT.get(lang) or _DATA_HANDLING_CONTENT["en"]
    return deepcopy(content)
