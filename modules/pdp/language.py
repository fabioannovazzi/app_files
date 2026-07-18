from __future__ import annotations

import ipaddress
from typing import Any, Dict, List, Optional
from urllib.error import URLError
from urllib.request import urlopen

from fastapi import Request

LANGUAGE_LABELS: Dict[str, str] = {
    "en": "English",
    "it": "Italiano",
    "fr": "Français",
    "de": "Deutsch",
}
LANDING_LANGUAGE_LABELS: Dict[str, str] = {
    "en": "En",
    "it": "It",
    "fr": "Fr",
    "de": "De",
}
LANGUAGE_ORDER: List[str] = ["en", "it", "fr", "de"]
SUPPORTED_LANGUAGES = set(LANGUAGE_LABELS.keys())

PAGE_LABELS = {
    "/check/page": {
        "en": "Check entries",
        "it": "Verifica registrazioni contabili",
        "fr": "Contrôler les écritures",
        "de": "Buchungen prüfen",
    },
    "/presentations/page": {
        "en": "Presentations",
        "it": "Presentazioni",
        "fr": "Présentations",
        "de": "Präsentationen",
    },
    "/review/reports/page": {
        "en": "Retailer signals",
        "it": "Segnali dei retailer",
        "fr": "Signaux retailers",
        "de": "Retailer-Signale",
    },
    "/review/brand-reports/page": {
        "en": "Brand fit",
        "it": "Fit del brand",
        "fr": "Fit de marque",
        "de": "Marken-Fit",
    },
    "/review/product-hypotheses/page": {
        "en": "Product hints",
        "it": "Spunti prodotto",
        "fr": "Pistes produit",
        "de": "Produkt-Hinweise",
    },
    "/auth/page": {
        "en": "Sign in",
        "it": "Accedi",
        "fr": "Se connecter",
        "de": "Anmelden",
    },
    "/slides/page": {
        "en": "Slide editor",
        "it": "Editor diapositive",
        "fr": "Éditeur de diapositives",
        "de": "Folieneditor",
    },
    "/review/page": {
        "en": "Catalog",
        "it": "Catalogo",
        "fr": "Catalogue",
        "de": "Katalog",
    },
    "/review/react": {
        "en": "Catalog",
        "it": "Catalogo",
        "fr": "Catalogue",
        "de": "Katalog",
    },
    "/review/coverage/page": {
        "en": "Attribute coverage",
        "it": "Copertura attributi",
        "fr": "Couverture des attributs",
        "de": "Attributabdeckung",
    },
    "/review/explicit-rules/page": {
        "en": "Explicit attributes",
        "it": "Dichiarazioni PDP",
        "fr": "Déclarations PDP",
        "de": "PDP-Angaben",
    },
    "/review/issues/page": {
        "en": "Attribute issues",
        "it": "Problemi attributi",
        "fr": "Problèmes d’attributs",
        "de": "Attributprobleme",
    },
}

PAGE_COPY: Dict[str, Dict[str, Any]] = {
    "landing": {
        "thesis_alt": {
            "en": "Power is nothing without control.",
            "it": "La potenza è nulla senza controllo.",
            "fr": "La puissance n'est rien sans le contrôle.",
            "de": "Leistung ist nichts ohne Kontrolle.",
        },
        "primary_navigation_label": {
            "en": "Primary navigation",
            "it": "Navigazione principale",
            "fr": "Navigation principale",
            "de": "Hauptnavigation",
        },
        "language_selector_label": {
            "en": "Language selector",
            "it": "Selezione della lingua",
            "fr": "Sélecteur de langue",
            "de": "Sprachauswahl",
        },
        "sign_out_button": {
            "en": "Sign out",
            "it": "Esci",
            "fr": "Se déconnecter",
            "de": "Abmelden",
        },
        "magic_link_placeholder": {
            "en": "name@example.com",
            "it": "nome@example.com",
            "fr": "nom@example.com",
            "de": "name@example.com",
        },
        "magic_link_email_label": {
            "en": "Email",
            "it": "Email",
            "fr": "Adresse e-mail",
            "de": "E-Mail-Adresse",
        },
        "magic_link_button": {
            "en": "Send link",
            "it": "Invia link",
            "fr": "Envoyer le lien",
            "de": "Link senden",
        },
        "magic_link_helper": {
            "en": "Use your email to receive a sign-in link.",
            "it": "Usa la tua email per ricevere un link di accesso.",
            "fr": "Utilisez votre adresse e-mail pour recevoir un lien de connexion.",
            "de": "Verwenden Sie Ihre E-Mail-Adresse, um einen Anmeldelink zu erhalten.",
        },
        "magic_link_tooltip": {
            "en": "Enter your email and we will send a one-time sign-in link.",
            "it": "Inserisci la tua email: ti invieremo un link di accesso monouso.",
            "fr": "Saisissez votre adresse e-mail : nous vous enverrons un lien de connexion à usage unique.",
            "de": "Geben Sie Ihre E-Mail-Adresse ein: Wir senden Ihnen einen einmaligen Anmeldelink.",
        },
        "magic_link_invalid_email": {
            "en": "Enter a valid email address.",
            "it": "Inserisci un indirizzo email valido.",
            "fr": "Saisissez une adresse e-mail valide.",
            "de": "Geben Sie eine gültige E-Mail-Adresse ein.",
        },
        "magic_link_sending": {
            "en": "Sending link...",
            "it": "Invio del link...",
            "fr": "Envoi du lien...",
            "de": "Link wird gesendet...",
        },
        "magic_link_sent": {
            "en": "Check your inbox for the sign-in link. It stays valid for 15 minutes. If you don't see it, check Spam or Junk.",
            "it": "Controlla la posta: il link di accesso resta valido per 15 minuti. Se non lo vedi, controlla anche Spam o Posta indesiderata.",
            "fr": "Consultez votre boîte de réception : le lien de connexion reste valable 15 minutes. Si vous ne le voyez pas, vérifiez aussi les courriers indésirables.",
            "de": "Prüfen Sie Ihren Posteingang: Der Anmeldelink bleibt 15 Minuten gültig. Wenn Sie ihn nicht sehen, prüfen Sie auch den Spam- oder Junk-Ordner.",
        },
        "magic_link_error_generic": {
            "en": "Unable to send link. Try again.",
            "it": "Impossibile inviare il link. Riprova.",
            "fr": "Impossible d'envoyer le lien. Réessayez.",
            "de": "Link konnte nicht gesendet werden. Bitte versuchen Sie es erneut.",
        },
    },
    "auth_login": {
        "description": {
            "en": "Use Google sign-in or request a magic link to access the requested workspace.",
            "it": "Usa Google Sign-In oppure richiedi un magic link per accedere all'area richiesta.",
            "fr": "Utilisez Google Sign-In ou demandez un lien magique pour accéder à l'espace demandé.",
            "de": "Verwenden Sie Google Sign-In oder fordern Sie einen Magic Link an, um auf den angeforderten Arbeitsbereich zuzugreifen.",
        },
        "helper": {
            "en": "Your session cookie will be stored securely in the browser.",
            "it": "Il cookie di sessione verrà salvato in modo sicuro nel browser.",
            "fr": "Votre cookie de session sera stocké de manière sécurisée dans le navigateur.",
            "de": "Ihr Sitzungs-Cookie wird sicher im Browser gespeichert.",
        },
        "magic_link_placeholder": {
            "en": "name@example.com",
            "it": "nome@example.com",
            "fr": "nom@example.com",
            "de": "name@example.com",
        },
        "magic_link_email_label": {
            "en": "Email",
            "it": "Email",
            "fr": "Adresse e-mail",
            "de": "E-Mail-Adresse",
        },
        "magic_link_button": {
            "en": "Send link",
            "it": "Invia link",
            "fr": "Envoyer le lien",
            "de": "Link senden",
        },
        "magic_link_helper": {
            "en": "Use your email to receive a sign-in link.",
            "it": "Usa la tua email per ricevere un link di accesso.",
            "fr": "Utilisez votre adresse e-mail pour recevoir un lien de connexion.",
            "de": "Verwenden Sie Ihre E-Mail-Adresse, um einen Anmeldelink zu erhalten.",
        },
        "magic_link_tooltip": {
            "en": "Enter your email and we will send a one-time sign-in link.",
            "it": "Inserisci la tua email: ti invieremo un link di accesso monouso.",
            "fr": "Saisissez votre adresse e-mail : nous vous enverrons un lien de connexion à usage unique.",
            "de": "Geben Sie Ihre E-Mail-Adresse ein: Wir senden Ihnen einen einmaligen Anmeldelink.",
        },
        "magic_link_invalid_email": {
            "en": "Enter a valid email address.",
            "it": "Inserisci un indirizzo email valido.",
            "fr": "Saisissez une adresse e-mail valide.",
            "de": "Geben Sie eine gültige E-Mail-Adresse ein.",
        },
        "magic_link_sending": {
            "en": "Sending link...",
            "it": "Invio del link...",
            "fr": "Envoi du lien...",
            "de": "Link wird gesendet...",
        },
        "magic_link_sent": {
            "en": "Check your inbox for the sign-in link. It stays valid for 15 minutes. If you don't see it, check Spam or Junk.",
            "it": "Controlla la posta: il link di accesso resta valido per 15 minuti. Se non lo vedi, controlla anche Spam o Posta indesiderata.",
            "fr": "Consultez votre boîte de réception : le lien de connexion reste valable 15 minutes. Si vous ne le voyez pas, vérifiez aussi les courriers indésirables.",
            "de": "Prüfen Sie Ihren Posteingang: Der Anmeldelink bleibt 15 Minuten gültig. Wenn Sie ihn nicht sehen, prüfen Sie auch den Spam- oder Junk-Ordner.",
        },
        "magic_link_error_generic": {
            "en": "Unable to send link. Try again.",
            "it": "Impossibile inviare il link. Riprova.",
            "fr": "Impossible d'envoyer le lien. Réessayez.",
            "de": "Link konnte nicht gesendet werden. Bitte versuchen Sie es erneut.",
        },
        "disabled": {
            "en": "Authentication is currently disabled.",
            "it": "L'autenticazione è attualmente disattivata.",
            "fr": "L'authentification est actuellement désactivée.",
            "de": "Die Authentifizierung ist derzeit deaktiviert.",
        },
        "redirect_notice": {
            "en": "Sign in to continue to the requested page.",
            "it": "Accedi per continuare alla pagina richiesta.",
            "fr": "Connectez-vous pour continuer vers la page demandée.",
            "de": "Melden Sie sich an, um zur angeforderten Seite fortzufahren.",
        },
        "home_link_aria": {
            "en": "Return to the home page",
            "it": "Torna alla home page",
            "fr": "Retourner à la page d'accueil",
            "de": "Zur Startseite zurückkehren",
        },
    },
    "slides_editor": {
        "home_link_aria": {
            "en": "Return to the home page",
            "it": "Torna alla home page",
            "fr": "Retourner à la page d'accueil",
            "de": "Zur Startseite zurückkehren",
        },
        "labels": {
            "upload_deck": {
                "en": "Upload HTML deck",
                "it": "Carica deck HTML",
                "fr": "Importer un deck HTML",
                "de": "HTML-Deck hochladen",
            },
            "upload_zip_deck": {
                "en": "Upload zip deck",
                "it": "Carica deck zip",
                "fr": "Importer un deck zip",
                "de": "Zip-Deck hochladen",
            },
            "upload_pdf_deck": {
                "en": "Upload PDF deck",
                "it": "Carica deck PDF",
                "fr": "Importer un deck PDF",
                "de": "PDF-Deck hochladen",
            },
            "upload_zip_package": {
                "en": "Upload ZIP",
                "it": "Carica ZIP",
                "fr": "Importer ZIP",
                "de": "ZIP hochladen",
            },
            "replace_zip_package": {
                "en": "Replace ZIP",
                "it": "Sostituisci ZIP",
                "fr": "Remplacer ZIP",
                "de": "ZIP ersetzen",
            },
            "run_chart_remap": {
                "en": "Run chart remap",
                "it": "Esegui remap grafici",
                "fr": "Lancer le remap des graphiques",
                "de": "Chart-Remap starten",
            },
            "prompt_style_label": {
                "en": "Deck template",
                "it": "Template del deck",
                "fr": "Modèle de deck",
                "de": "Deck-Vorlage",
            },
            "upload_action": {
                "en": "Upload",
                "it": "Carica",
                "fr": "Importer",
                "de": "Hochladen",
            },
            "select_file": {
                "en": "Select file",
                "it": "Seleziona file",
                "fr": "Sélectionner un fichier",
                "de": "Datei auswählen",
            },
            "cancel_action": {
                "en": "Cancel",
                "it": "Annulla",
                "fr": "Annuler",
                "de": "Abbrechen",
            },
            "session_pdf_decks": {
                "en": "Session PDF decks",
                "it": "Deck PDF della sessione",
                "fr": "Decks PDF de session",
                "de": "PDF-Decks der Sitzung",
            },
            "brief_zip_loaded": {
                "en": "Brief ZIP loaded",
                "it": "ZIP brief caricato",
                "fr": "ZIP brief chargé",
                "de": "Brief-ZIP geladen",
            },
            "brief_zip_not_loaded": {
                "en": "Brief ZIP not loaded yet.",
                "it": "ZIP brief non ancora caricato.",
                "fr": "ZIP brief pas encore chargé.",
                "de": "Brief-ZIP noch nicht geladen.",
            },
            "chart_remap_job_status": {
                "en": "Chart remap job status",
                "it": "Stato job remap grafici",
                "fr": "Statut du job de remap des graphiques",
                "de": "Status des Chart-Remap-Jobs",
            },
            "chart_remap_step": {
                "en": "Chart remap step",
                "it": "Fase remap grafici",
                "fr": "Étape du remap des graphiques",
                "de": "Chart-Remap-Schritt",
            },
            "download_unmatched_pngs": {
                "en": "Download unmatched PNGs",
                "it": "Scarica PNG non associati",
                "fr": "Télécharger les PNG non associés",
                "de": "Nicht zugeordnete PNGs herunterladen",
            },
            "output_deck_label": {
                "en": "Output",
                "it": "Output",
                "fr": "Sortie",
                "de": "Ausgabe",
            },
            "status_pending": {
                "en": "Pending",
                "it": "In attesa",
                "fr": "En attente",
                "de": "Ausstehend",
            },
            "status_running": {
                "en": "Running",
                "it": "In esecuzione",
                "fr": "En cours",
                "de": "Läuft",
            },
            "status_completed": {
                "en": "Completed",
                "it": "Completato",
                "fr": "Terminé",
                "de": "Abgeschlossen",
            },
            "status_failed": {
                "en": "Failed",
                "it": "Fallito",
                "fr": "Échoué",
                "de": "Fehlgeschlagen",
            },
            "status_cancelled": {
                "en": "Cancelled",
                "it": "Annullato",
                "fr": "Annulé",
                "de": "Abgebrochen",
            },
            "remap_stage_queued": {
                "en": "Queued",
                "it": "In coda",
                "fr": "En file d'attente",
                "de": "In Warteschlange",
            },
            "remap_stage_reading_package": {
                "en": "Loading ZIP",
                "it": "Caricamento ZIP",
                "fr": "Chargement ZIP",
                "de": "ZIP wird geladen",
            },
            "remap_stage_reading_ocr": {
                "en": "Reading OCR",
                "it": "Lettura OCR",
                "fr": "Lecture OCR",
                "de": "OCR wird gelesen",
            },
            "remap_stage_layout_analysis": {
                "en": "Layout analysis",
                "it": "Analisi layout",
                "fr": "Analyse de mise en page",
                "de": "Layout-Analyse",
            },
            "remap_stage_chart_understanding": {
                "en": "Chart understanding",
                "it": "Comprensione grafici",
                "fr": "Compréhension des graphiques",
                "de": "Chart-Verständnis",
            },
            "remap_stage_validation": {
                "en": "Validating masks",
                "it": "Validazione maschere",
                "fr": "Validation des masques",
                "de": "Masken werden validiert",
            },
            "remap_stage_repair": {
                "en": "Repairing masks",
                "it": "Correzione maschere",
                "fr": "Correction des masques",
                "de": "Masken werden korrigiert",
            },
            "remap_stage_notifying": {
                "en": "Sending completion email",
                "it": "Invio email di completamento",
                "fr": "Envoi de l'e-mail de fin",
                "de": "Abschluss-E-Mail wird gesendet",
            },
            "remap_stage_matching_slides": {
                "en": "Matching charts to slides",
                "it": "Abbinamento grafici alle slide",
                "fr": "Association des graphiques aux slides",
                "de": "Charts werden Folien zugeordnet",
            },
            "remap_stage_patching_slides": {
                "en": "Applying white masks",
                "it": "Applicazione maschere bianche",
                "fr": "Application des masques blancs",
                "de": "Weiße Masken werden angewendet",
            },
            "remap_stage_substituting_slides": {
                "en": "Inserting charts",
                "it": "Inserimento grafici",
                "fr": "Insertion des graphiques",
                "de": "Charts werden eingefügt",
            },
            "remap_stage_qa_patching": {
                "en": "Verifying masks",
                "it": "Verifica maschere",
                "fr": "Vérification des masques",
                "de": "Masken werden geprüft",
            },
            "remap_stage_qa_substitution": {
                "en": "Verifying inserted charts",
                "it": "Verifica grafici inseriti",
                "fr": "Vérification des graphiques insérés",
                "de": "Eingefügte Charts werden geprüft",
            },
            "notebook_remap_queued": {
                "en": "Notebook chart remap queued.",
                "it": "Remap grafici Notebook in coda.",
                "fr": "Remap des graphiques Notebook mis en file d'attente.",
                "de": "Notebook-Chart-Remap in Warteschlange.",
            },
            "remap_requires_pdf_first": {
                "en": "Upload at least one PDF deck first.",
                "it": "Carica prima almeno un deck PDF.",
                "fr": "Importez d'abord au moins un deck PDF.",
                "de": "Laden Sie zuerst mindestens ein PDF-Deck hoch.",
            },
            "remap_requires_zip_first": {
                "en": "Upload the brief package ZIP first.",
                "it": "Carica prima lo ZIP del brief package.",
                "fr": "Importez d'abord le ZIP du brief package.",
                "de": "Laden Sie zuerst das Brief-Paket-ZIP hoch.",
            },
            "remap_upload_pdf_before_zip": {
                "en": "Upload at least one PDF deck before uploading the ZIP package.",
                "it": "Carica almeno un deck PDF prima di caricare il pacchetto ZIP.",
                "fr": "Importez au moins un deck PDF avant de charger le package ZIP.",
                "de": "Laden Sie mindestens ein PDF-Deck hoch, bevor Sie das ZIP-Paket hochladen.",
            },
            "remap_select_zip_package": {
                "en": "Select a .zip brief package.",
                "it": "Seleziona un brief package .zip.",
                "fr": "Sélectionnez un brief package .zip.",
                "de": "Wählen Sie ein .zip-Brief-Paket aus.",
            },
            "remap_brief_zip_required": {
                "en": "Brief package must be a .zip file.",
                "it": "Il brief package deve essere un file .zip.",
                "fr": "Le brief package doit être un fichier .zip.",
                "de": "Das Brief-Paket muss eine .zip-Datei sein.",
            },
            "concat_decks": {
                "en": "Combine decks",
                "it": "Unisci deck",
                "fr": "Fusionner des decks",
                "de": "Decks zusammenführen",
            },
            "concat_dialog_title": {
                "en": "Combine decks",
                "it": "Unisci deck",
                "fr": "Fusionner des decks",
                "de": "Decks zusammenführen",
            },
            "concat_deck_name": {
                "en": "New deck name",
                "it": "Nome del nuovo deck",
                "fr": "Nom du nouveau deck",
                "de": "Name des neuen Decks",
            },
            "concat_helper": {
                "en": "Select one or more decks to append in order.",
                "it": "Seleziona uno o più deck da concatenare nell'ordine desiderato.",
                "fr": "Sélectionnez un ou plusieurs decks à ajouter dans l'ordre souhaité.",
                "de": "Wählen Sie ein oder mehrere Decks aus, die in Reihenfolge angehängt werden sollen.",
            },
            "concat_confirm": {
                "en": "Create deck",
                "it": "Crea deck",
                "fr": "Créer un deck",
                "de": "Deck erstellen",
            },
            "deck_select_label": {
                "en": "Select deck",
                "it": "Seleziona deck",
                "fr": "Sélectionner un deck",
                "de": "Deck auswählen",
            },
            "deck_placeholder": {
                "en": "Select deck",
                "it": "Seleziona deck",
                "fr": "Sélectionner un deck",
                "de": "Deck auswählen",
            },
            "add_slide": {
                "en": "Add slide",
                "it": "Aggiungi slide",
                "fr": "Ajouter une diapositive",
                "de": "Folie hinzufügen",
            },
            "add_intro_slides": {
                "en": "Add title + disclaimer",
                "it": "Aggiungi titolo + disclaimer",
                "fr": "Ajouter titre + avertissement",
                "de": "Titel + Hinweis hinzufügen",
            },
            "delete_slide": {
                "en": "Delete slide",
                "it": "Elimina slide",
                "fr": "Supprimer la diapositive",
                "de": "Folie löschen",
            },
            "import_slide": {
                "en": "Insert from deck",
                "it": "Inserisci da deck",
                "fr": "Insérer depuis un deck",
                "de": "Aus Deck einfügen",
            },
            "save_deck": {
                "en": "Save deck",
                "it": "Salva deck",
                "fr": "Enregistrer le deck",
                "de": "Deck speichern",
            },
            "print_deck": {
                "en": "Export PDF",
                "it": "Esporta PDF",
                "fr": "Exporter en PDF",
                "de": "PDF exportieren",
            },
            "export_pptx": {
                "en": "Export PPTX",
                "it": "Esporta PPTX",
                "fr": "Exporter en PPTX",
                "de": "PPTX exportieren",
            },
            "list_view": {
                "en": "List view",
                "it": "Vista elenco",
                "fr": "Vue liste",
                "de": "Listenansicht",
            },
            "loading_status": {
                "en": "Loading…",
                "it": "Caricamento…",
                "fr": "Chargement…",
                "de": "Wird geladen…",
            },
            "unsaved_changes": {
                "en": "Unsaved changes",
                "it": "Modifiche non salvate",
                "fr": "Modifications non enregistrées",
                "de": "Ungespeicherte Änderungen",
            },
            "storyboard_view": {
                "en": "Storyboard",
                "it": "Storyboard",
                "fr": "Storyboard",
                "de": "Storyboard",
            },
            "storyboard_card_size": {
                "en": "Card size",
                "it": "Dimensione schede",
                "fr": "Taille des cartes",
                "de": "Kartengröße",
            },
            "storyboard_mark_as_header": {
                "en": "Mark as section header",
                "it": "Segna come intestazione sezione",
                "fr": "Marquer comme en-tête de section",
                "de": "Als Abschnittskopf markieren",
            },
            "storyboard_empty_slide": {
                "en": "(empty slide)",
                "it": "(slide vuota)",
                "fr": "(diapositive vide)",
                "de": "(leere Folie)",
            },
            "storyboard_active_hint": {
                "en": "Storyboard is active. Use the grid to select and reorder slides.",
                "it": "Storyboard attivo. Usa la griglia per selezionare e riordinare le slide.",
                "fr": "Le storyboard est actif. Utilisez la grille pour sélectionner et réorganiser les diapositives.",
                "de": "Storyboard ist aktiv. Verwenden Sie das Raster, um Folien auszuwählen und neu anzuordnen.",
            },
            "add_section": {
                "en": "Add section",
                "it": "Aggiungi sezione",
                "fr": "Ajouter une section",
                "de": "Abschnitt hinzufügen",
            },
            "sections_heading": {
                "en": "Sections",
                "it": "Sezioni",
                "fr": "Sections",
                "de": "Abschnitte",
            },
            "section_fallback_title": {
                "en": "Section {index}",
                "it": "Sezione {index}",
                "fr": "Section {index}",
                "de": "Abschnitt {index}",
            },
            "section_header_prefix": {
                "en": "Header",
                "it": "Intestazione",
                "fr": "En-tête",
                "de": "Kopf",
            },
            "section_id_label": {
                "en": "ID",
                "it": "ID",
                "fr": "ID",
                "de": "ID",
            },
            "section_title_label": {
                "en": "Title",
                "it": "Titolo",
                "fr": "Titre",
                "de": "Titel",
            },
            "section_starts_at": {
                "en": "Starts at",
                "it": "Inizia da",
                "fr": "Commence à",
                "de": "Beginnt bei",
            },
            "section_remove": {
                "en": "Remove",
                "it": "Rimuovi",
                "fr": "Supprimer",
                "de": "Entfernen",
            },
            "section_insert_header": {
                "en": "Insert header",
                "it": "Inserisci intestazione",
                "fr": "Insérer l'en-tête",
                "de": "Kopf einfügen",
            },
            "section_use_selection_as_header": {
                "en": "Use selection as header",
                "it": "Usa la selezione come intestazione",
                "fr": "Utiliser la sélection comme en-tête",
                "de": "Auswahl als Kopf verwenden",
            },
            "section_add_subsection": {
                "en": "Add subsection",
                "it": "Aggiungi sottosezione",
                "fr": "Ajouter une sous-section",
                "de": "Unterabschnitt hinzufügen",
            },
            "section_no_subsections": {
                "en": "No subsections yet.",
                "it": "Nessuna sottosezione ancora.",
                "fr": "Aucune sous-section pour le moment.",
                "de": "Noch keine Unterabschnitte.",
            },
            "slides_heading": {
                "en": "Slides",
                "it": "Slide",
                "fr": "Diapositives",
                "de": "Folien",
            },
            "preview_label": {
                "en": "Slide preview",
                "it": "Anteprima slide",
                "fr": "Aperçu de la diapositive",
                "de": "Folienvorschau",
            },
            "title_label": {
                "en": "Title HTML",
                "it": "HTML titolo",
                "fr": "HTML du titre",
                "de": "Titel-HTML",
            },
            "body_label": {
                "en": "Body HTML",
                "it": "HTML corpo",
                "fr": "HTML du contenu",
                "de": "Inhalts-HTML",
            },
            "notes_label": {
                "en": "Notes",
                "it": "Note",
                "fr": "Notes",
                "de": "Notizen",
            },
            "notes_placeholder": {
                "en": "Add a note or link (plain text). Links stay clickable in exports.",
                "it": "Aggiungi una nota o un link (testo semplice). I link restano cliccabili negli export.",
                "fr": "Ajoutez une note ou un lien (texte brut). Les liens restent cliquables dans les exports.",
                "de": "Fügen Sie eine Notiz oder einen Link hinzu (reiner Text). Links bleiben in Exporten anklickbar.",
            },
            "import_dialog_title": {
                "en": "Insert slide from another deck",
                "it": "Inserisci slide da un altro deck",
                "fr": "Insérer une diapositive d'un autre deck",
                "de": "Folie aus einem anderen Deck einfügen",
            },
            "import_dialog_close": {
                "en": "Close",
                "it": "Chiudi",
                "fr": "Fermer",
                "de": "Schließen",
            },
            "import_deck_label": {
                "en": "Deck",
                "it": "Deck",
                "fr": "Deck",
                "de": "Deck",
            },
            "import_deck_placeholder": {
                "en": "Select a deck",
                "it": "Seleziona un deck",
                "fr": "Sélectionner un deck",
                "de": "Deck auswählen",
            },
        },
        "tooltips": {
            "upload_deck": {
                "en": "Upload entire HTML slide folder.",
                "it": "Carica l'intera cartella di slide HTML.",
                "fr": "Importez tout le dossier de diapositives HTML.",
                "de": "Laden Sie den gesamten HTML-Folienordner hoch.",
            },
            "upload_zip_deck": {
                "en": "Upload a packaged .zip export of a slide deck.",
                "it": "Carica un export .zip compresso del deck.",
                "fr": "Importez un deck empaqueté en .zip.",
                "de": "Laden Sie ein gepacktes .zip-Deck hoch.",
            },
            "upload_pdf_deck": {
                "en": "Upload a PDF deck to convert into slides.",
                "it": "Carica un deck PDF da convertire in slide.",
                "fr": "Importez un deck PDF pour le convertir en diapositives.",
                "de": "Laden Sie ein PDF-Deck hoch, um es in Folien zu konvertieren.",
            },
            "list_view": {
                "en": "Display slides as a list.",
                "it": "Mostra le slide in elenco.",
                "fr": "Afficher les diapositives sous forme de liste.",
                "de": "Folien als Liste anzeigen.",
            },
            "storyboard_view": {
                "en": "Display slides in a storyboard grid.",
                "it": "Mostra le slide in una griglia storyboard.",
                "fr": "Afficher les diapositives sous forme de storyboard.",
                "de": "Folien in einem Storyboard-Raster anzeigen.",
            },
            "concat_decks": {
                "en": "Append multiple decks into a single new deck.",
                "it": "Unisci più deck in un nuovo deck unico.",
                "fr": "Fusionnez plusieurs decks dans un nouveau deck.",
                "de": "Führen Sie mehrere Decks in einem neuen Deck zusammen.",
            },
            "print_deck": {
                "en": "Download a PDF snapshot of the current deck.",
                "it": "Scarica un PDF del deck corrente.",
                "fr": "Téléchargez un PDF du deck courant.",
                "de": "Laden Sie eine PDF-Version des aktuellen Decks herunter.",
            },
            "export_pptx": {
                "en": "Download a PPTX snapshot of the current deck.",
                "it": "Scarica un PPTX del deck corrente.",
                "fr": "Téléchargez un PPTX du deck courant.",
                "de": "Laden Sie eine PPTX-Version des aktuellen Decks herunter.",
            },
            "add_slide": {
                "en": "Create a new slide immediately after the selected slide.",
                "it": "Crea una nuova slide subito dopo quella selezionata.",
                "fr": "Créez une nouvelle diapositive juste après la sélection.",
                "de": "Erstellen Sie direkt nach der ausgewählten Folie eine neue Folie.",
            },
            "add_intro_slides": {
                "en": "Insert a title slide and a disclaimer slide at the beginning of the deck.",
                "it": "Inserisci una slide titolo e una slide disclaimer all'inizio del deck.",
                "fr": "Insérez une diapositive de titre et une diapositive d'avertissement au début du deck.",
                "de": "Fügen Sie am Anfang des Decks eine Titelfolie und eine Hinweisfolie ein.",
            },
            "delete_slide": {
                "en": "Remove the currently selected slide from this deck.",
                "it": "Rimuovi la slide selezionata da questo deck.",
                "fr": "Retirez la diapositive sélectionnée de ce deck.",
                "de": "Entfernen Sie die ausgewählte Folie aus diesem Deck.",
            },
            "import_slide": {
                "en": "Insert a slide from another deck after the current selection.",
                "it": "Inserisci una slide da un altro deck dopo la selezione corrente.",
                "fr": "Insérez une diapositive provenant d'un autre deck après la sélection.",
                "de": "Fügen Sie nach der aktuellen Auswahl eine Folie aus einem anderen Deck ein.",
            },
            "save_deck": {
                "en": "Save every change made to the current deck.",
                "it": "Salva tutte le modifiche applicate al deck corrente.",
                "fr": "Enregistrez toutes les modifications apportées au deck en cours.",
                "de": "Speichern Sie alle Änderungen am aktuellen Deck.",
            },
            "add_section": {
                "en": "Group related slides into navigation sections.",
                "it": "Raggruppa le slide correlate in sezioni di navigazione.",
                "fr": "Regroupez les diapositives liées en sections de navigation.",
                "de": "Fassen Sie verwandte Folien in Navigationsabschnitten zusammen.",
            },
            "insert_header": {
                "en": "Insert a section-header slide before the first slide in this group.",
                "it": "Inserisci una slide di intestazione di sezione prima della prima slide del gruppo.",
                "fr": "Insérez une diapositive d'en-tête de section avant la première diapositive du groupe.",
                "de": "Fügen Sie eine Abschnittsüberschrift-Folie vor der ersten Folie dieser Gruppe ein.",
            },
            "use_selection_as_header": {
                "en": "Convert the selected slide into a section header for this group.",
                "it": "Trasforma la slide selezionata in intestazione di sezione per questo gruppo.",
                "fr": "Convertissez la diapositive sélectionnée en en-tête de section pour ce groupe.",
                "de": "Wandeln Sie die ausgewählte Folie in eine Abschnittsüberschrift für diese Gruppe um.",
            },
            "add_subsection": {
                "en": "Create a subsection that links to a specific slide inside this section.",
                "it": "Crea una sottosezione che rimanda a una slide specifica all'interno della sezione.",
                "fr": "Créez une sous-section qui pointe vers une diapositive précise de la section.",
                "de": "Erstellen Sie eine Untersektion, die auf eine bestimmte Folie innerhalb dieses Abschnitts verweist.",
            },
        },
    },
    "check_entries": {
        "page_help": {
            "en": "Upload the journal, map the key columns, attach the supporting PDFs, run the automated checks, and download the flagged entries plus the Excel summary.",
            "it": "Carica il giornale, mappa le colonne chiave, allega i PDF di supporto, esegui i controlli automatici e scarica le registrazioni segnalate insieme al riepilogo Excel.",
            "fr": "Importez le journal, cartographiez les colonnes clés, joignez les PDF justificatifs, lancez les contrôles automatiques puis téléchargez les écritures signalées et le résumé Excel.",
            "de": "Laden Sie das Journal hoch, ordnen Sie die wichtigsten Spalten zu, hängen Sie die Nachweis-PDFs an, starten Sie die automatischen Prüfungen und laden Sie die markierten Buchungen sowie das Excel-Resümee herunter.",
        },
        "panels": {
            "upload": {
                "title": {
                    "en": "Upload sample file",
                    "it": "Carica campionatura",
                    "fr": "Importer le fichier d'échantillon",
                    "de": "Stichprobendatei hochladen",
                },
                "subtitle": {
                    "en": "Upload the ledger extract to analyse.",
                    "it": "Carica l'estratto contabile da analizzare.",
                    "fr": "Importez l'extrait du grand livre à analyser.",
                    "de": "Laden Sie den auszuwertenden Kontoauszug hoch.",
                },
            },
            "mapping": {
                "title": {
                    "en": "Column mapping",
                    "it": "Mappatura colonne",
                    "fr": "Cartographie des colonnes",
                    "de": "Spaltenzuordnung",
                },
                "subtitle": {
                    "en": "Confirm which columns correspond to the required fields.",
                    "it": "Conferma quali colonne corrispondono ai campi richiesti.",
                    "fr": "Confirmez quelles colonnes correspondent aux champs requis.",
                    "de": "Bestätigen Sie, welche Spalten den benötigten Feldern entsprechen.",
                },
            },
            "pdf": {
                "title": {
                    "en": "Upload PDFs",
                    "it": "Carica PDF",
                    "fr": "Importer les PDF",
                    "de": "PDFs hochladen",
                },
                "subtitle": {
                    "en": "Attach the supporting documents to match against.",
                    "it": "Allega i documenti di supporto da confrontare.",
                    "fr": "Joignez les justificatifs à rapprocher.",
                    "de": "Fügen Sie die Nachweise zum Abgleich hinzu.",
                },
            },
            "parameters": {
                "title": {
                    "en": "Configure checks",
                    "it": "Configura i controlli",
                    "fr": "Configurer les contrôles",
                    "de": "Prüfungen konfigurieren",
                },
                "subtitle": {
                    "en": "Adjust tolerances and beneficiary comparison settings.",
                    "it": "Imposta le tolleranze e i controlli sui beneficiari.",
                    "fr": "Ajustez les tolérances et les options de comparaison des bénéficiaires.",
                    "de": "Passen Sie Toleranzen und Begünstigtenabgleich an.",
                },
            },
            "results": {
                "title": {
                    "en": "Results",
                    "it": "Risultati",
                    "fr": "Résultats",
                    "de": "Ergebnisse",
                },
                "subtitle": {
                    "en": "Review mismatches, download reports, and apply overrides.",
                    "it": "Rivedi le discrepanze, scarica i report e applica le correzioni.",
                    "fr": "Examinez les écarts, téléchargez les rapports et appliquez les corrections.",
                    "de": "Prüfen Sie Abweichungen, laden Sie Berichte herunter und nehmen Sie Korrekturen vor.",
                },
            },
        },
        "labels": {
            "select_journal": {
                "en": "Select journal file",
                "it": "Seleziona file giornale",
                "fr": "Sélectionner le fichier journal",
                "de": "Journaldatei auswählen",
            },
            "no_file": {
                "en": "No file selected",
                "it": "Nessun file selezionato",
                "fr": "Aucun fichier sélectionné",
                "de": "Keine Datei ausgewählt",
            },
            "select_pdfs": {
                "en": "Select PDF files",
                "it": "Seleziona PDF",
                "fr": "Sélectionner les PDF",
                "de": "PDF-Dateien auswählen",
            },
            "no_files": {
                "en": "No files selected",
                "it": "Nessun file selezionato",
                "fr": "Aucun fichier sélectionné",
                "de": "Keine Dateien ausgewählt",
            },
            "files_selected": {
                "en": "{count} files selected",
                "it": "{count} file selezionati",
                "fr": "{count} fichiers sélectionnés",
                "de": "{count} Dateien ausgewählt",
            },
            "contact_email": {
                "en": "Contact email (optional)",
                "it": "Email di contatto (opzionale)",
                "fr": "Email de contact (optionnel)",
                "de": "Kontakt‑E-Mail (optional)",
            },
            "contact_email_placeholder": {
                "en": "name@example.com",
                "it": "nome@example.com",
                "fr": "nom@example.com",
                "de": "name@example.com",
            },
            "contact_email_help": {
                "en": "Automatic check can take from a few minutes to a few hours. We’ll email you when validation finishes.",
                "it": "Il controllo automatico può richiedere da pochi minuti a qualche ora. Ti invieremo un’email quando la validazione termina.",
                "fr": "La vérification automatique peut prendre de quelques minutes à plusieurs heures. Nous vous enverrons un e-mail une fois la validation terminée.",
                "de": "Die automatische Prüfung kann einige Minuten bis zu mehrere Stunden dauern. Wir senden Ihnen eine E‑Mail, sobald die Validierung abgeschlossen ist.",
            },
            "run_job_id": {
                "en": "Job ID",
                "it": "ID job",
                "fr": "ID du job",
                "de": "Job-ID",
            },
            "run_job_link": {
                "en": "Status link",
                "it": "Link stato",
                "fr": "Lien de statut",
                "de": "Status-Link",
            },
            "mapping_fields": {
                "movement_number": {
                    "en": "Movement number",
                    "it": "Numero movimento",
                    "fr": "Numéro d'écriture",
                    "de": "Buchungsnummer",
                },
                "amount": {
                    "en": "Amount",
                    "it": "Importo",
                    "fr": "Montant",
                    "de": "Betrag",
                },
                "debit_amount": {
                    "en": "Debit amount",
                    "it": "Importo dare",
                    "fr": "Montant débit",
                    "de": "Sollbetrag",
                },
                "credit_amount": {
                    "en": "Credit amount",
                    "it": "Importo avere",
                    "fr": "Montant crédit",
                    "de": "Habenbetrag",
                },
                "date": {
                    "en": "Date",
                    "it": "Data",
                    "fr": "Date",
                    "de": "Datum",
                },
                "account": {
                    "en": "Account",
                    "it": "Conto",
                    "fr": "Compte",
                    "de": "Konto",
                },
                "account_desc": {
                    "en": "Account description",
                    "it": "Descrizione conto",
                    "fr": "Description du compte",
                    "de": "Kontobeschreibung",
                },
                "line_desc": {
                    "en": "Line description",
                    "it": "Descrizione riga",
                    "fr": "Description de ligne",
                    "de": "Postenbeschreibung",
                },
                "beneficiary": {
                    "en": "Beneficiary",
                    "it": "Beneficiario",
                    "fr": "Bénéficiaire",
                    "de": "Begünstigter",
                },
            },
            "ocr_language": {
                "en": "OCR language",
                "it": "Lingua OCR",
                "fr": "Langue OCR",
                "de": "OCR-Sprache",
            },
            "amount_tolerance": {
                "en": "Amount tolerance",
                "it": "Tolleranza importi",
                "fr": "Tolérance sur le montant",
                "de": "Betragstoleranz",
            },
            "date_window": {
                "en": "Date window (days)",
                "it": "Intervallo date (giorni)",
                "fr": "Fenêtre de dates (jours)",
                "de": "Datumsfenster (Tage)",
            },
            "timing_diff": {
                "en": "Timing difference (days)",
                "it": "Differenza temporale (giorni)",
                "fr": "Décalage temporel (jours)",
                "de": "Zeitdifferenz (Tage)",
            },
            "beneficiary_check": {
                "en": "Beneficiary check",
                "it": "Controllo beneficiario",
                "fr": "Contrôle bénéficiaire",
                "de": "Begünstigtenprüfung",
            },
            "beneficiary_similarity": {
                "en": "Beneficiary similarity (%)",
                "it": "Somiglianza beneficiario (%)",
                "fr": "Similarité bénéficiaire (%)",
                "de": "Begünstigten-Ähnlichkeit (%)",
            },
            "include_debug": {
                "en": "Include debug columns in excel",
                "it": "Includi colonne di debug in excel",
                "fr": "Inclure les colonnes de debug dans excel",
                "de": "Debug-Spalten in excel einschließen",
            },
            "mismatches_title": {
                "en": "Mismatches",
                "it": "Differenze",
                "fr": "Écarts",
                "de": "Abweichungen",
            },
            "download_pdf": {
                "en": "Download PDF",
                "it": "Scarica PDF",
                "fr": "Télécharger le PDF",
                "de": "PDF herunterladen",
            },
            "movement_title": {
                "en": "Movement {movement}",
                "it": "Movimento {movement}",
                "fr": "Écriture {movement}",
                "de": "Buchung {movement}",
            },
            "mismatch_option": {
                "en": "Mismatch",
                "it": "Differenza",
                "fr": "Écart",
                "de": "Abweichung",
            },
            "ok_option": {
                "en": "OK",
                "it": "OK",
                "fr": "OK",
                "de": "OK",
            },
            "override_placeholder": {
                "en": "Reason for override (optional)",
                "it": "Motivo della correzione (opzionale)",
                "fr": "Motif de la correction (optionnel)",
                "de": "Begründung für die Anpassung (optional)",
            },
        },
        "buttons": {
            "upload_file": {
                "en": "Upload file",
                "it": "Carica file",
                "fr": "Importer le fichier",
                "de": "Datei hochladen",
            },
            "auto_map": {
                "en": "Auto-map columns",
                "it": "Mappa colonne automaticamente",
                "fr": "Cartographier automatiquement",
                "de": "Spalten automatisch zuordnen",
            },
            "save_mapping": {
                "en": "Save mapping",
                "it": "Salva mappatura",
                "fr": "Enregistrer la cartographie",
                "de": "Zuordnung speichern",
            },
            "upload_pdfs": {
                "en": "Upload PDFs",
                "it": "Carica PDF",
                "fr": "Importer les PDF",
                "de": "PDFs hochladen",
            },
            "run_checks": {
                "en": "Run automatic check",
                "it": "Avvia controllo automatico",
                "fr": "Lancer la vérification automatique",
                "de": "Automatische Prüfung starten",
            },
            "cancel_job": {
                "en": "Cancel check",
                "it": "Annulla controllo",
                "fr": "Annuler la vérification",
                "de": "Prüfung abbrechen",
            },
            "copy_job_link": {
                "en": "Copy link",
                "it": "Copia link",
                "fr": "Copier le lien",
                "de": "Link kopieren",
            },
            "download_excel": {
                "en": "Download Excel",
                "it": "Scarica Excel",
                "fr": "Télécharger Excel",
                "de": "Excel herunterladen",
            },
            "download_summary": {
                "en": "Download summary",
                "it": "Scarica riepilogo",
                "fr": "Télécharger le résumé",
                "de": "Zusammenfassung herunterladen",
            },
            "apply_review": {
                "en": "Apply review",
                "it": "Applica revisione",
                "fr": "Appliquer la revue",
                "de": "Prüfung anwenden",
            },
        },
        "options": {
            "beneficiary_modes": {
                "compare": {
                    "en": "Compare",
                    "it": "Confronta",
                    "fr": "Comparer",
                    "de": "Vergleichen",
                },
                "extract_only": {
                    "en": "Extract only",
                    "it": "Solo estrazione",
                    "fr": "Extraction seule",
                    "de": "Nur Extrahieren",
                },
                "off": {"en": "Off", "it": "Disattivo", "fr": "Désactivé", "de": "Aus"},
            },
        },
        "messages": {
            "select_file_first": {
                "en": "Select a file first.",
                "it": "Seleziona prima un file.",
                "fr": "Sélectionnez d'abord un fichier.",
                "de": "Wählen Sie zuerst eine Datei aus.",
            },
            "upload_status": {
                "en": "Loaded {rows} rows from {filename}.",
                "it": "Caricate {rows} righe da {filename}.",
                "fr": "{rows} lignes importées depuis {filename}.",
                "de": "{rows} Zeilen aus {filename} geladen.",
            },
            "upload_first": {
                "en": "Upload the journal first.",
                "it": "Carica prima il giornale.",
                "fr": "Importez d'abord le journal.",
                "de": "Laden Sie zuerst das Journal hoch.",
            },
            "auto_mapping_ok": {
                "en": "Column mapping suggested automatically.",
                "it": "Mappatura colonne suggerita automaticamente.",
                "fr": "Cartographie proposée automatiquement.",
                "de": "Spalten automatisch vorgeschlagen.",
            },
            "mapping_saved": {
                "en": "Mapping saved.",
                "it": "Mappatura salvata.",
                "fr": "Cartographie enregistrée.",
                "de": "Zuordnung gespeichert.",
            },
            "run_checks_needed": {
                "en": "Submit the mapping and PDFs before running.",
                "it": "Invia la mappatura e i PDF prima di avviare.",
                "fr": "Validez la cartographie et les PDFs avant de lancer.",
                "de": "Zuordnung und PDFs vor dem Start übermitteln.",
            },
            "run_checks_init": {
                "en": "Running checks…",
                "it": "Esecuzione controlli…",
                "fr": "Vérifications en cours…",
                "de": "Prüfung läuft…",
            },
            "run_checks_done": {
                "en": "Checks completed.",
                "it": "Controlli completati.",
                "fr": "Vérifications terminées.",
                "de": "Prüfungen abgeschlossen.",
            },
            "run_checks_pdfs": {
                "en": "Upload supporting PDF files before running.",
                "it": "Carica i PDF di supporto prima di avviare.",
                "fr": "Importez les PDF justificatifs avant de lancer la vérification.",
                "de": "Laden Sie die unterstützenden PDFs hoch, bevor Sie starten.",
            },
            "run_checks_failed": {
                "en": "Automatic check failed. Please try again.",
                "it": "Il controllo automatico non è riuscito. Riprova.",
                "fr": "La vérification automatique a échoué. Veuillez réessayer.",
                "de": "Die automatische Prüfung ist fehlgeschlagen. Bitte erneut versuchen.",
            },
            "run_checks_timeout": {
                "en": "Automatic check is taking longer than expected. Please try again in a few minutes.",
                "it": "Il controllo automatico richiede più tempo del previsto. Riprova tra qualche minuto.",
                "fr": "La vérification automatique prend plus de temps que prévu. Réessayez dans quelques minutes.",
                "de": "Die automatische Prüfung dauert länger als erwartet. Bitte versuchen Sie es in ein paar Minuten erneut.",
            },
            "run_checks_batch_pending": {
                "en": "Submitted the automatic check as a batch run. This can take several hours; we’ll email you when it finishes.",
                "it": "Il controllo automatico è stato inviato come batch. L’elaborazione può richiedere alcune ore; ti avviseremo via email al termine.",
                "fr": "La vérification automatique a été envoyée en traitement batch. Cela peut prendre plusieurs heures ; nous vous préviendrons par email une fois terminée.",
                "de": "Die automatische Prüfung wurde als Batch gestartet. Dies kann mehrere Stunden dauern; wir informieren Sie per E‑Mail, sobald sie abgeschlossen ist.",
            },
            "run_checks_help": {
                "en": "Click to run checks. They can take from a few minutes to a few hours.",
                "it": "Clicca per eseguire i controlli. Possono durare da pochi minuti ad alcune ore.",
                "fr": "Cliquez pour lancer les vérifications. Elles peuvent durer de quelques minutes à plusieurs heures.",
                "de": "Klicken Sie, um die Prüfungen zu starten. Sie können wenige Minuten bis mehrere Stunden dauern.",
            },
            "run_checks_email_notice": {
                "en": "We’ll email {email} when the checks finish. Feel free to close this page.",
                "it": "Invieremo una mail a {email} quando i controlli saranno terminati. Puoi chiudere questa pagina.",
                "fr": "Nous vous enverrons un e-mail à {email} lorsque les vérifications seront terminées. Vous pouvez fermer cette page.",
                "de": "Wir senden eine E-Mail an {email}, sobald die Prüfungen abgeschlossen sind. Sie können diese Seite schließen.",
            },
            "run_checks_email_label": {
                "en": "your sign-in address",
                "it": "il tuo indirizzo di accesso",
                "fr": "votre adresse de connexion",
                "de": "Ihre Anmeldeadresse",
            },
            "run_checks_cancelled": {
                "en": "Automatic check was cancelled.",
                "it": "Il controllo automatico è stato annullato.",
                "fr": "La vérification automatique a été annulée.",
                "de": "Die automatische Prüfung wurde abgebrochen.",
            },
            "run_checks_leave_note": {
                "en": "You can close this page. Save the link above to resume or download results later.",
                "it": "Puoi chiudere questa pagina. Salva il link qui sopra per riprendere o scaricare i risultati più tardi.",
                "fr": "Vous pouvez fermer cette page. Enregistrez le lien ci-dessus pour reprendre ou télécharger les résultats plus tard.",
                "de": "Sie können diese Seite schließen. Speichern Sie den obigen Link, um später fortzufahren oder Ergebnisse herunterzuladen.",
            },
            "run_job_link_copied": {
                "en": "Job link copied.",
                "it": "Link del job copiato.",
                "fr": "Lien du job copié.",
                "de": "Job-Link kopiert.",
            },
            "pdf_download_failed": {
                "en": "PDF download failed",
                "it": "Download PDF non riuscito",
                "fr": "Échec du téléchargement PDF",
                "de": "PDF-Download fehlgeschlagen",
            },
            "download_failed": {
                "en": "Download failed",
                "it": "Download non riuscito",
                "fr": "Échec du téléchargement",
                "de": "Download fehlgeschlagen",
            },
            "review_first": {
                "en": "Run the checks first.",
                "it": "Esegui i controlli prima.",
                "fr": "Lancez d'abord les vérifications.",
                "de": "Führen Sie zuerst die Prüfungen durch.",
            },
            "select_pdfs_first": {
                "en": "Select one or more PDF files.",
                "it": "Seleziona uno o più PDF.",
                "fr": "Sélectionnez un ou plusieurs PDF.",
                "de": "Wählen Sie eine oder mehrere PDF-Dateien aus.",
            },
            "pdfs_attached": {
                "en": "Attached {count} PDF(s).",
                "it": "Allegati {count} PDF.",
                "fr": "{count} PDF joints.",
                "de": "{count} PDF(s) hinzugefügt.",
            },
        },
    },
    "product_attributes": {
        "page_help": {
            "en": "Select the retailer, brand, and category, toggle the attribute filters you care about, and review or download the resulting parents/variants to focus your attribute analysis.",
            "it": "Seleziona retailer, brand e categoria, attiva i filtri sugli attributi di interesse e analizza o scarica i prodotti/varianti risultanti per concentrare l’attività di revisione.",
            "fr": "Choisissez le distributeur, la marque et la catégorie, activez les filtres d’attributs pertinents, puis consultez ou exportez les produits/variantes obtenus pour orienter vos analyses.",
            "de": "Wählen Sie Händler, Marke und Kategorie, setzen Sie die gewünschten Attributfilter und prüfen bzw. exportieren Sie die resultierenden Produkte oder Varianten für die Analyse.",
        },
        "labels": {
            "source": {"en": "Source", "it": "Fonte", "fr": "Source", "de": "Quelle"},
            "brand": {"en": "Brand", "it": "Marca", "fr": "Marque", "de": "Marke"},
            "category": {
                "en": "Category",
                "it": "Categoria",
                "fr": "Catégorie",
                "de": "Kategorie",
            },
            "display_limit": {
                "en": "Displayed items",
                "it": "Elementi visualizzati",
                "fr": "Éléments affichés",
                "de": "Angezeigte Elemente",
            },
            "rolling_months": {
                "en": "Rolling months",
                "it": "Mesi scorrevoli",
                "fr": "Mois glissants",
                "de": "Laufende Monate",
            },
            "show_all": {
                "en": "Show all attributes",
                "it": "Mostra tutti gli attributi",
                "fr": "Afficher tous les attributs",
                "de": "Alle Attribute anzeigen",
            },
        },
        "record_types": {
            "parent": {
                "en": "Parents",
                "it": "Prodotti",
                "fr": "Produits",
                "de": "Produkte",
            },
            "variant": {
                "en": "Variants",
                "it": "Varianti",
                "fr": "Variantes",
                "de": "Varianten",
            },
        },
        "panels": {
            "attributes": {
                "title": {
                    "en": "Attribute filters",
                    "it": "Filtri attributi",
                    "fr": "Filtres d'attributs",
                    "de": "Attributfilter",
                },
                "subtitle_active": {
                    "en": "Select attribute values to refine the results.",
                    "it": "Seleziona i valori degli attributi per affinare i risultati.",
                    "fr": "Sélectionnez des valeurs d'attribut pour affiner les résultats.",
                    "de": "Wählen Sie Attributwerte, um die Ergebnisse zu verfeinern.",
                },
                "subtitle_wait": {
                    "en": "Attributes will appear when categories share common fields.",
                    "it": "Gli attributi appariranno quando le categorie condividono campi comuni.",
                    "fr": "Les attributs apparaîtront lorsque les catégories partageront des champs communs.",
                    "de": "Attribute werden angezeigt, wenn Kategorien gemeinsame Felder haben.",
                },
                "empty": {
                    "en": "The selected categories do not share any attributes.",
                    "it": "Le categorie selezionate non condividono attributi.",
                    "fr": "Les catégories sélectionnées ne partagent aucun attribut.",
                    "de": "Die ausgewählten Kategorien teilen keine Attribute.",
                },
            },
            "sales_dimensions": {
                "title": {
                    "en": "Attribute dimensions",
                    "it": "Dimensioni attributi",
                    "fr": "Dimensions d'attributs",
                    "de": "Attributdimensionen",
                },
                "subtitle": {
                    "en": "Choose one or more attributes to analyze sales by dimension.",
                    "it": "Scegli uno o più attributi per analizzare le vendite per dimensione.",
                    "fr": "Choisissez un ou plusieurs attributs pour analyser les ventes par dimension.",
                    "de": "Wählen Sie ein oder mehrere Attribute, um Verkäufe nach Dimension zu analysieren.",
                },
                "label": {
                    "en": "Select attributes",
                    "it": "Seleziona attributi",
                    "fr": "Sélectionner des attributs",
                    "de": "Attribute auswählen",
                },
            },
            "sales": {
                "summary": {
                    "en": "Sales: {sales} · Units: {units}",
                    "it": "Vendite: {sales} · Pezzi: {units}",
                    "fr": "Ventes : {sales} · Unités : {units}",
                    "de": "Umsatz: {sales} · Einheiten: {units}",
                },
                "empty": {
                    "en": "No sales data found for the current filters.",
                    "it": "Nessun dato di vendita per i filtri correnti.",
                    "fr": "Aucune donnée de vente pour les filtres actuels.",
                    "de": "Keine Verkaufsdaten für die aktuellen Filter.",
                },
            },
            "results": {
                "catalog_view": {
                    "en": "Catalog view",
                    "it": "Vista catalogo",
                    "fr": "Vue catalogue",
                    "de": "Katalogansicht",
                },
                "catalog_view_tooltip": {
                    "en": "See filtered products.",
                    "it": "Visualizza prodotti filtrati.",
                    "fr": "Voir les produits filtrés.",
                    "de": "Gefilterte Produkte anzeigen.",
                },
                "sales_view": {
                    "en": "Sales view",
                    "it": "Vista vendite",
                    "fr": "Vue ventes",
                    "de": "Verkaufsansicht",
                },
                "sales_view_tooltip": {
                    "en": "Analyze sales by attribute.",
                    "it": "Analizza vendite per attributo.",
                    "fr": "Analyser les ventes par attribut.",
                    "de": "Verkäufe nach Attribut analysieren.",
                },
                "toggle_show": {
                    "en": "Show data table",
                    "it": "Mostra tabella",
                    "fr": "Afficher le tableau",
                    "de": "Tabelle anzeigen",
                },
                "toggle_hide": {
                    "en": "Hide data table",
                    "it": "Nascondi tabella",
                    "fr": "Masquer le tableau",
                    "de": "Tabelle ausblenden",
                },
                "download_csv": {
                    "en": "Download CSV",
                    "it": "Scarica CSV",
                    "fr": "Télécharger le CSV",
                    "de": "CSV herunterladen",
                },
                "no_records": {
                    "en": "No records match the selected filters.",
                    "it": "Nessun record corrisponde ai filtri selezionati.",
                    "fr": "Aucun enregistrement ne correspond aux filtres sélectionnés.",
                    "de": "Keine Einträge entsprechen den ausgewählten Filtern.",
                },
            },
        },
        "pill": {
            "all_label": {"en": "All", "it": "Tutti", "fr": "Tout", "de": "Alle"},
            "no_options": {
                "en": "No options available",
                "it": "Nessuna opzione disponibile",
                "fr": "Aucune option disponible",
                "de": "Keine Optionen verfügbar",
            },
        },
        "statuses": {
            "loading_retailers": {
                "en": "Loading sources…",
                "it": "Caricamento fonti…",
                "fr": "Chargement des sources…",
                "de": "Quellen werden geladen…",
            },
            "loading_categories": {
                "en": "Loading categories…",
                "it": "Caricamento categorie…",
                "fr": "Chargement des catégories…",
                "de": "Kategorien werden geladen…",
            },
            "loading_brands": {
                "en": "Loading brands…",
                "it": "Caricamento brand…",
                "fr": "Chargement des marques…",
                "de": "Marken werden geladen…",
            },
            "loading_attributes": {
                "en": "Loading attribute filters…",
                "it": "Caricamento filtri attributi…",
                "fr": "Chargement des filtres d'attributs…",
                "de": "Attributfilter werden geladen…",
            },
            "loading_records": {
                "en": "Loading records…",
                "it": "Caricamento record…",
                "fr": "Chargement des enregistrements…",
                "de": "Datensätze werden geladen…",
            },
            "loading_sales": {
                "en": "Loading sales…",
                "it": "Caricamento vendite…",
                "fr": "Chargement des ventes…",
                "de": "Verkäufe werden geladen…",
            },
        },
        "records": {
            "summary_displaying": {
                "en": "Displaying {count} of {total} {label}.",
                "it": "Visualizzazione di {count} su {total} {label}.",
                "fr": "Affichage de {count} sur {total} {label}.",
                "de": "{count} von {total} {label} werden angezeigt.",
            },
            "summary_empty": {
                "en": "No matches yet.",
                "it": "Nessuna corrispondenza al momento.",
                "fr": "Aucune correspondance pour l'instant.",
                "de": "Noch keine Treffer.",
            },
            "parent_label": {
                "en": "products",
                "it": "prodotti",
                "fr": "produits",
                "de": "Produkte",
            },
            "variant_label": {
                "en": "variants",
                "it": "varianti",
                "fr": "variantes",
                "de": "Varianten",
            },
            "parent_filename": {
                "en": "parents",
                "it": "prodotti",
                "fr": "parents",
                "de": "produkte",
            },
            "variant_filename": {
                "en": "variants",
                "it": "varianti",
                "fr": "variantes",
                "de": "varianten",
            },
            "fallback_name": {
                "en": "Product",
                "it": "Prodotto",
                "fr": "Produit",
                "de": "Produkt",
            },
            "value_missing": {"en": "N/A", "it": "N/D", "fr": "N.D.", "de": "k. A."},
            "image_alt": {
                "en": "Product image",
                "it": "Immagine prodotto",
                "fr": "Image du produit",
                "de": "Produktbild",
            },
        },
        "images": {
            "placeholder": {
                "en": "Image unavailable",
                "it": "Immagine non disponibile",
                "fr": "Image indisponible",
                "de": "Kein Bild verfügbar",
            },
        },
        "errors": {
            "request_failed": {
                "en": "Request failed ({status})",
                "it": "Richiesta non riuscita ({status})",
                "fr": "Échec de la requête ({status})",
                "de": "Anfrage fehlgeschlagen ({status})",
            },
            "image_failed": {
                "en": "Image request failed ({status})",
                "it": "Richiesta immagine non riuscita ({status})",
                "fr": "Échec du chargement de l'image ({status})",
                "de": "Bildanforderung fehlgeschlagen ({status})",
            },
        },
    },
    "report_builder": {
        "page_help": {
            "en": "Upload the exported Excel workbook, confirm the detected report type, review the suggested section mapping, add any context, then build and download the DOCX file.",
            "it": "Carica il file Excel esportato, conferma il tipo di report rilevato, verifica le sezioni suggerite, aggiungi eventuale contesto e genera il DOCX finale.",
            "fr": "Importez le classeur Excel exporté, confirmez le type de rapport détecté, vérifiez la répartition des sections, ajoutez du contexte puis générez le fichier DOCX.",
            "de": "Laden Sie die exportierte Excel-Datei hoch, bestätigen Sie den erkannten Berichtstyp, prüfen Sie die vorgeschlagene Abschnittszuordnung, ergänzen Sie Kontext und erzeugen Sie anschließend das DOCX.",
        },
        "header_subtitle": {
            "en": "Upload the exported Excel workbooks, review the detected tables, provide optional context, and generate the DOCX report.",
            "it": "Carica i file Excel esportati, verifica le tabelle rilevate, aggiungi eventuale contesto e genera il report DOCX.",
            "fr": "Importez les classeurs Excel exportés, vérifiez les tableaux détectés, ajoutez du contexte facultatif et générez le rapport DOCX.",
            "de": "Laden Sie die exportierten Excel-Arbeitsmappen hoch, prüfen Sie die erkannten Tabellen, ergänzen Sie optional Kontext und erzeugen Sie den DOCX-Bericht.",
        },
        "panels": {
            "upload": {
                "title": {
                    "en": "Upload file",
                    "it": "Carica file",
                    "fr": "Importer un fichier",
                    "de": "Datei hochladen",
                },
                "subtitle": {
                    "en": "Upload an XLSX file. One table per sheet.",
                    "it": "Carica un file XLSX. Una tabella per foglio.",
                    "fr": "Importez un fichier XLSX. Un tableau par onglet.",
                    "de": "Laden Sie eine XLSX-Datei hoch. Eine Tabelle pro Blatt.",
                },
            },
            "detection": {
                "title": {
                    "en": "Report type",
                    "it": "Tipo report",
                    "fr": "Type de rapport",
                    "de": "Berichtstyp",
                },
                "subtitle": {
                    "en": "Review the automatic detection and adjust if needed.",
                    "it": "Verifica il rilevamento automatico e modificane il risultato se necessario.",
                    "fr": "Vérifiez la détection automatique et ajustez-la si besoin.",
                    "de": "Überprüfen Sie die automatische Erkennung und passen Sie sie bei Bedarf an.",
                },
            },
            "mapping": {
                "title": {
                    "en": "Map tables",
                    "it": "Mappa le tabelle",
                    "fr": "Cartographier les tableaux",
                    "de": "Tabellen zuordnen",
                },
                "subtitle": {
                    "en": "Assign each template section to the appropriate Excel sheet.",
                    "it": "Assegna ogni sezione del modello al foglio Excel appropriato.",
                    "fr": "Affectez chaque section du modèle à la feuille Excel appropriée.",
                    "de": "Ordnen Sie jeden Vorlagenabschnitt dem passenden Excel-Blatt zu.",
                },
            },
            "context": {
                "title": {
                    "en": "Context notes",
                    "it": "Note di contesto",
                    "fr": "Notes de contexte",
                    "de": "Kontextnotizen",
                },
                "subtitle": {
                    "en": "Add manual remarks or edit suggestions that will appear in the narrative.",
                    "it": "Aggiungi note manuali o suggerimenti che verranno riportati nel testo.",
                    "fr": "Ajoutez des remarques ou suggestions qui apparaîtront dans le rapport.",
                    "de": "Fügen Sie manuelle Hinweise oder Vorschläge für den Berichtstext hinzu.",
                },
            },
            "build": {
                "title": {
                    "en": "Build & download",
                    "it": "Genera e scarica",
                    "fr": "Générer et télécharger",
                    "de": "Erstellen & herunterladen",
                },
                "subtitle": {
                    "en": "Generate the DOCX report using the current mapping and context.",
                    "it": "Genera il report DOCX utilizzando la mappatura e il contesto correnti.",
                    "fr": "Générez le rapport DOCX à partir de la cartographie et du contexte actuels.",
                    "de": "Erstellen Sie den DOCX-Bericht mit der aktuellen Zuordnung und dem Kontext.",
                },
            },
        },
        "labels": {
            "ente": {
                "en": "Authority",
                "it": "Ente",
                "fr": "Collectivité",
                "de": "Behörde",
            },
            "ente_placeholder": {
                "en": "Comune di Example",
                "it": "Comune di Example",
                "fr": "Ville d’Exemple",
                "de": "Gemeinde Beispiel",
            },
            "year": {"en": "Year", "it": "Anno", "fr": "Année", "de": "Jahr"},
            "contact_email": {
                "en": "Contact email (optional)",
                "it": "Email di contatto (opzionale)",
                "fr": "Email de contact (optionnel)",
                "de": "Kontakt‑E-Mail (optional)",
            },
            "contact_email_placeholder": {
                "en": "name@example.com",
                "it": "nome@example.com",
                "fr": "nom@example.com",
                "de": "name@example.com",
            },
            "zip_package": {
                "en": "ZIP package",
                "it": "Pacchetto ZIP",
                "fr": "Paquet ZIP",
                "de": "ZIP-Paket",
            },
            "excel_workbook": {
                "en": "Excel file",
                "it": "File Excel",
                "fr": "Fichier Excel",
                "de": "Excel-Datei",
            },
            "select_zip": {
                "en": "Select ZIP file",
                "it": "Seleziona file ZIP",
                "fr": "Sélectionner le ZIP",
                "de": "ZIP-Datei auswählen",
            },
            "select_excel": {
                "en": "Select Excel (.xlsx) file",
                "it": "Seleziona file Excel (.xlsx)",
                "fr": "Sélectionner le fichier Excel (.xlsx)",
                "de": "Excel-Datei (.xlsx) auswählen",
            },
            "no_file": {
                "en": "No file selected",
                "it": "Nessun file selezionato",
                "fr": "Aucun fichier sélectionné",
                "de": "Keine Datei ausgewählt",
            },
            "upload_hint": {
                "en": "Upload an XLSX with the required tables (one table per sheet).",
                "it": "Carica un file XLSX con le tabelle richieste (una tabella per foglio).",
                "fr": "Importez un fichier XLSX avec les tableaux requis (un tableau par onglet).",
                "de": "Laden Sie eine XLSX-Datei mit den benötigten Tabellen hoch (eine Tabelle pro Blatt).",
            },
            "report_type": {
                "en": "Report type",
                "it": "Tipo di report",
                "fr": "Type de rapport",
                "de": "Berichtstyp",
            },
            "language_label": {
                "en": "Language",
                "it": "Lingua",
                "fr": "Langue",
                "de": "Sprache",
            },
            "detection_confidence": {
                "en": "Detection confidence",
                "it": "Attendibilità rilevazione",
                "fr": "Confiance de détection",
                "de": "Erkennungs­sicherheit",
            },
            "unassigned_option": {
                "en": "— empty —",
                "it": "— vuoto —",
                "fr": "— vide —",
                "de": "— leer —",
            },
            "context_empty": {
                "en": "No context notes yet. Add a manual note to capture additional background.",
                "it": "Nessuna nota di contesto. Aggiungi una nota manuale per inserire ulteriori dettagli.",
                "fr": "Aucune note de contexte pour le moment. Ajoutez une note manuelle pour compléter le rapport.",
                "de": "Noch keine Kontextnotizen. Fügen Sie manuell eine Notiz für zusätzliche Hinweise hinzu.",
            },
            "context_key": {
                "en": "Key",
                "it": "Chiave",
                "fr": "Clé",
                "de": "Schlüssel",
            },
            "context_value": {"en": "Note", "it": "Nota", "fr": "Note", "de": "Notiz"},
            "context_delete": {
                "en": "Remove",
                "it": "Rimuovi",
                "fr": "Supprimer",
                "de": "Entfernen",
            },
            "markdown_preview": {
                "en": "Markdown preview",
                "it": "Anteprima Markdown",
                "fr": "Aperçu Markdown",
                "de": "Markdown-Vorschau",
            },
            "analysis_preview": {
                "en": "Detected insights",
                "it": "Approfondimenti rilevati",
                "fr": "Insights détectés",
                "de": "Erkannte Erkenntnisse",
            },
        },
        "table_headers": {
            "section": {
                "en": "Section",
                "it": "Sezione",
                "fr": "Section",
                "de": "Abschnitt",
            },
            "assigned_file": {
                "en": "Assigned sheet",
                "it": "Foglio assegnato",
                "fr": "Feuille associée",
                "de": "Zugewiesenes Blatt",
            },
        },
        "buttons": {
            "upload_detect": {
                "en": "Upload & detect tables",
                "it": "Carica e rileva tabelle",
                "fr": "Importer & détecter",
                "de": "Hochladen & Tabellen erkennen",
            },
            "reset_workflow": {
                "en": "Start over",
                "it": "Ricominci",
                "fr": "Recommencer",
                "de": "Neu starten",
            },
            "auto_map_tables": {
                "en": "Auto-map tables",
                "it": "Mappa tabelle automaticamente",
                "fr": "Mapper les tableaux automatiquement",
                "de": "Tabellen automatisch zuordnen",
            },
            "save_mapping": {
                "en": "Save mapping",
                "it": "Salva mappatura",
                "fr": "Enregistrer la cartographie",
                "de": "Zuordnung speichern",
            },
            "add_context": {
                "en": "Add note",
                "it": "Aggiungi nota",
                "fr": "Ajouter une note",
                "de": "Notiz hinzufügen",
            },
            "build_report": {
                "en": "Build report",
                "it": "Genera report",
                "fr": "Générer le rapport",
                "de": "Bericht erstellen",
            },
            "download_docx": {
                "en": "Download",
                "it": "Scarica",
                "fr": "Télécharger",
                "de": "Herunterladen",
            },
        },
        "messages": {
            "confirm_new_session": {
                "en": "Uploading new data will start a new session. Continue?",
                "it": "Caricando nuovi dati verrà avviata una nuova sessione. Procedere?",
                "fr": "Importer de nouvelles données démarrera une nouvelle session. Continuer ?",
                "de": "Das Hochladen neuer Daten startet eine neue Sitzung. Fortfahren?",
            },
            "uploading": {
                "en": "Uploading…",
                "it": "Caricamento…",
                "fr": "Importation…",
                "de": "Wird hochgeladen…",
            },
            "processing_upload": {
                "en": "Processing file…",
                "it": "Elaborazione del file…",
                "fr": "Traitement du fichier…",
                "de": "Datei wird verarbeitet…",
            },
            "provide_ente_year": {
                "en": "Provide both ente and year.",
                "it": "Indica sia l'ente sia l'anno.",
                "fr": "Indiquez l'organisme et l'année.",
                "de": "Geben Sie Behörde und Jahr an.",
            },
            "both_files_error": {
                "en": "Upload either a ZIP file or an Excel workbook, not both.",
                "it": "Carica un file ZIP oppure un file Excel, non entrambi.",
                "fr": "Importez soit un ZIP soit un classeur Excel, pas les deux.",
                "de": "Laden Sie entweder ein ZIP oder ein Excel hoch, nicht beides.",
            },
            "select_file_error": {
                "en": "Select an XLSX file before uploading.",
                "it": "Seleziona un file XLSX prima di caricare.",
                "fr": "Sélectionnez un fichier XLSX avant d'importer.",
                "de": "Wählen Sie vor dem Hochladen eine XLSX-Datei aus.",
            },
            "invalid_excel": {
                "en": "Only .xlsx files are supported. Export or save your workbook as XLSX.",
                "it": "Sono supportati solo i file .xlsx. Esporta o salva il file come XLSX.",
                "fr": "Seuls les fichiers .xlsx sont acceptés. Exportez ou enregistrez votre classeur au format XLSX.",
                "de": "Es werden nur .xlsx-Dateien unterstützt. Exportieren oder speichern Sie die Arbeitsmappe als XLSX.",
            },
            "upload_success": {
                "en": "Uploaded {filename} successfully.",
                "it": "{filename} caricato correttamente.",
                "fr": "{filename} importé avec succès.",
                "de": "{filename} erfolgreich hochgeladen.",
            },
            "upload_failed": {
                "en": "Upload failed.",
                "it": "Caricamento non riuscito.",
                "fr": "Échec de l'import.",
                "de": "Upload fehlgeschlagen.",
            },
            "switching_report_type": {
                "en": "Switching report type…",
                "it": "Cambio tipo di report…",
                "fr": "Changement du type de rapport…",
                "de": "Berichtstyp wird gewechselt…",
            },
            "report_type_updated": {
                "en": "Report type updated.",
                "it": "Tipo di report aggiornato.",
                "fr": "Type de rapport mis à jour.",
                "de": "Berichtstyp aktualisiert.",
            },
            "report_type_failed": {
                "en": "Failed to switch report type.",
                "it": "Impossibile cambiare tipo di report.",
                "fr": "Échec du changement de type de rapport.",
                "de": "Berichtstyp konnte nicht geändert werden.",
            },
            "mapping_auto_running": {
                "en": "Running automatic mapping…",
                "it": "Esecuzione mappatura automatica…",
                "fr": "Cartographie automatique…",
                "de": "Automatische Zuordnung läuft…",
            },
            "mapping_auto_failed": {
                "en": "Automatic mapping failed.",
                "it": "Mappatura automatica non riuscita.",
                "fr": "Échec de la cartographie automatique.",
                "de": "Automatische Zuordnung fehlgeschlagen.",
            },
            "mapping_saving": {
                "en": "Saving table mapping…",
                "it": "Salvataggio mappatura tabelle…",
                "fr": "Enregistrement de la cartographie…",
                "de": "Tabellenzuordnung wird gespeichert…",
            },
            "mapping_saved": {
                "en": "Mapping updated.",
                "it": "Mappatura aggiornata.",
                "fr": "Cartographie mise à jour.",
                "de": "Zuordnung aktualisiert.",
            },
            "mapping_save_failed": {
                "en": "Failed to save mapping.",
                "it": "Impossibile salvare la mappatura.",
                "fr": "Échec de l'enregistrement de la cartographie.",
                "de": "Zuordnung konnte nicht gespeichert werden.",
            },
            "mapping_hint_auto": {
                "en": "Tables were automatically mapped based on file names.",
                "it": "Le tabelle sono state abbinate automaticamente in base ai nomi dei file.",
                "fr": "Les tableaux ont été associés automatiquement selon les noms de fichiers.",
                "de": "Tabellen wurden automatisch anhand der Dateinamen zugeordnet.",
            },
            "mapping_hint_manual": {
                "en": "Review and map the sections manually if needed.",
                "it": "Rivedi e abbina manualmente le sezioni se necessario.",
                "fr": "Vérifiez et affectez manuellement les sections si besoin.",
                "de": "Prüfen und ordnen Sie die Abschnitte bei Bedarf manuell zu.",
            },
            "mapping_hidden_empty": {
                "en": "Empty sheets are hidden from mapping.",
                "it": "I fogli vuoti vengono esclusi dalla mappatura.",
                "fr": "Les feuilles vides sont masquées dans le mapping.",
                "de": "Leere Blätter werden bei der Zuordnung ausgeblendet.",
            },
            "context_key_empty": {
                "en": "Context keys cannot be empty.",
                "it": "Le chiavi di contesto non possono essere vuote.",
                "fr": "Les clés de contexte ne peuvent pas être vides.",
                "de": "Kontextschlüssel dürfen nicht leer sein.",
            },
            "context_key_exists": {
                "en": "Context key already exists.",
                "it": "La chiave di contesto esiste già.",
                "fr": "Cette clé de contexte existe déjà.",
                "de": "Dieser Kontextschlüssel existiert bereits.",
            },
            "context_saving": {
                "en": "Saving context…",
                "it": "Salvataggio contesto…",
                "fr": "Enregistrement du contexte…",
                "de": "Kontext wird gespeichert…",
            },
            "context_saved": {
                "en": "Context saved.",
                "it": "Contesto salvato.",
                "fr": "Contexte enregistré.",
                "de": "Kontext gespeichert.",
            },
            "context_save_failed": {
                "en": "Failed to save context.",
                "it": "Impossibile salvare il contesto.",
                "fr": "Échec de l'enregistrement du contexte.",
                "de": "Kontext konnte nicht gespeichert werden.",
            },
            "building": {
                "en": "Building report…",
                "it": "Generazione report…",
                "fr": "Génération du rapport…",
                "de": "Bericht wird erstellt…",
            },
            "build_done": {
                "en": "Report generated.",
                "it": "Report generato.",
                "fr": "Rapport généré.",
                "de": "Bericht erstellt.",
            },
            "build_failed": {
                "en": "Failed to build report.",
                "it": "Impossibile generare il report.",
                "fr": "Échec de la génération du rapport.",
                "de": "Erstellung des Berichts fehlgeschlagen.",
            },
            "build_enqueued": {
                "en": "Build started. We'll email you a link when it's ready.",
                "it": "Generazione avviata. Ti invieremo un link via email quando sarà terminata.",
                "fr": "Génération lancée. Nous vous enverrons un lien par e-mail dès que prêt.",
                "de": "Erstellung gestartet. Wir senden dir einen Link per E-Mail, sobald alles bereit ist.",
            },
        },
    },
    "check_statements": {
        "page_help": {
            "en": "Upload the bank statements and ledger extracts, map the ledger columns, fine-tune tolerance and date windows, then run the reconciliation to review unmatched movements and download the reconciliation package.",
            "it": "Carica estratti conto e movimenti di prima nota, mappa le colonne del mastro, regola tolleranze e finestre temporali e avvia la riconciliazione per analizzare le differenze e scaricare il pacchetto di riconciliazione.",
            "fr": "Importez les relevés bancaires et extractions de grand livre, cartographiez les colonnes, ajustez tolérance et fenêtre de dates puis lancez la réconciliation pour examiner les écarts et télécharger le dossier de rapprochement.",
            "de": "Laden Sie Kontoauszüge und Hauptbuchauszüge hoch, ordnen Sie die Spalten zu, passen Sie Toleranzen und Datumsfenster an und starten Sie die Abstimmung, um Abweichungen zu prüfen und das Abstimmungspaket herunterzuladen.",
        },
        "panels": {
            "upload": {
                "title": {
                    "en": "Upload files",
                    "it": "Carica i file",
                    "fr": "Importer les fichiers",
                    "de": "Dateien hochladen",
                },
                "subtitle": {
                    "en": "Provide the bank statements, ledger extracts, and optionally a sample of movement numbers.",
                    "it": "Carica gli estratti conto bancari, gli estratti del mastro e facoltativamente un campione di protocolli.",
                    "fr": "Importez les relevés bancaires, les extraits du grand livre et, en option, un échantillon de numéros d'écriture.",
                    "de": "Laden Sie die Kontoauszüge, die Hauptbuchauszüge und optional eine Stichprobe der Buchungscodes hoch.",
                },
            },
            "mapping": {
                "title": {
                    "en": "Ledger mapping",
                    "it": "Mappatura del mastro",
                    "fr": "Cartographie du grand livre",
                    "de": "Konten-Mapping",
                },
                "subtitle": {
                    "en": "Confirm which ledger columns contain the account identifiers and descriptions.",
                    "it": "Indica quali colonne del mastro contengono i codici e le descrizioni dei conti.",
                    "fr": "Indiquez quelles colonnes du grand livre contiennent les identifiants et descriptions des comptes.",
                    "de": "Geben Sie an, welche Spalten die Kontokennungen und Beschreibungen enthalten.",
                },
            },
            "parameters": {
                "title": {
                    "en": "Parameters",
                    "it": "Parametri",
                    "fr": "Paramètres",
                    "de": "Parameter",
                },
                "subtitle": {
                    "en": "Adjust tolerance, date window, and choose the ledger account to reconcile.",
                    "it": "Imposta le tolleranze, la finestra temporale e scegli il conto da riconciliare.",
                    "fr": "Ajustez la tolérance, la fenêtre de dates et choisissez le compte à rapprocher.",
                    "de": "Passen Sie Toleranz, Datumsfenster und das zu prüfende Konto an.",
                },
            },
            "results": {
                "title": {
                    "en": "Results",
                    "it": "Risultati",
                    "fr": "Résultats",
                    "de": "Ergebnisse",
                },
                "subtitle": {
                    "en": "Review unmatched items, stage coverage, and download the reconciliation package.",
                    "it": "Analizza le partite scoperte, la copertura per stadio e scarica il pacchetto di riconciliazione.",
                    "fr": "Analysez les écarts, la couverture par étape et téléchargez le dossier de rapprochement.",
                    "de": "Prüfen Sie offene Positionen, die Abdeckung und laden Sie das Abstimmungspaket herunter.",
                },
            },
        },
        "labels": {
            "bank_files": {
                "en": "Bank statements",
                "it": "Estratti conto bancari",
                "fr": "Relevés bancaires",
                "de": "Kontoauszüge",
            },
            "ledger_files": {
                "en": "Ledger files",
                "it": "File di mastro",
                "fr": "Fichiers du grand livre",
                "de": "Hauptbuchdateien",
            },
            "sample_file": {
                "en": "Sample movements (optional)",
                "it": "Campione movimenti (opzionale)",
                "fr": "Échantillon d'écritures (optionnel)",
                "de": "Belegliste (optional)",
            },
            "select_bank": {
                "en": "Select bank files",
                "it": "Seleziona i file bancari",
                "fr": "Sélectionner les fichiers bancaires",
                "de": "Bankdateien auswählen",
            },
            "select_ledger": {
                "en": "Select ledger files",
                "it": "Seleziona i file di mastro",
                "fr": "Sélectionner les fichiers du grand livre",
                "de": "Hauptbuchdateien auswählen",
            },
            "select_sample": {
                "en": "Select sample file",
                "it": "Seleziona il file campione",
                "fr": "Sélectionner le fichier d'échantillon",
                "de": "Stichprobendatei auswählen",
            },
            "no_files": {
                "en": "No files selected",
                "it": "Nessun file selezionato",
                "fr": "Aucun fichier sélectionné",
                "de": "Keine Dateien ausgewählt",
            },
            "no_file": {
                "en": "No file selected",
                "it": "Nessun file selezionato",
                "fr": "Aucun fichier sélectionné",
                "de": "Keine Datei ausgewählt",
            },
            "files_selected": {
                "en": "{count} files selected",
                "it": "{count} file selezionati",
                "fr": "{count} fichiers sélectionnés",
                "de": "{count} Dateien ausgewählt",
            },
            "all_accounts": {
                "en": "All accounts",
                "it": "Tutti i conti",
                "fr": "Tous les comptes",
                "de": "Alle Konten",
            },
            "ledger_account": {
                "en": "Ledger account",
                "it": "Conto di mastro",
                "fr": "Compte du grand livre",
                "de": "Hauptbuchkonto",
            },
            "ledger_account_desc": {
                "en": "Ledger account description",
                "it": "Descrizione conto di mastro",
                "fr": "Description du compte",
                "de": "Kontobeschreibung",
            },
            "counter_account_desc": {
                "en": "Counter-account description",
                "it": "Descrizione contropartita",
                "fr": "Description du compte de contrepartie",
                "de": "Gegenkonto-Beschreibung",
            },
            "extra_desc": {
                "en": "Additional description",
                "it": "Descrizione aggiuntiva",
                "fr": "Description additionnelle",
                "de": "Zusätzliche Beschreibung",
            },
            "amount_tolerance": {
                "en": "Amount tolerance",
                "it": "Tolleranza importi",
                "fr": "Tolérance sur le montant",
                "de": "Betragstoleranz",
            },
            "date_window": {
                "en": "Date window (days)",
                "it": "Intervallo date (giorni)",
                "fr": "Fenêtre de dates (jours)",
                "de": "Datumsfenster (Tage)",
            },
            "account_select": {
                "en": "Ledger account",
                "it": "Conto da riconciliare",
                "fr": "Compte à rapprocher",
                "de": "Zu prüfendes Konto",
            },
            "download_excel": {
                "en": "Download Excel",
                "it": "Scarica Excel",
                "fr": "Télécharger Excel",
                "de": "Excel herunterladen",
            },
            "summary_stage": {
                "en": "Stage summary",
                "it": "Sintesi per stadio",
                "fr": "Synthèse par étape",
                "de": "Stufe zusammenfassung",
            },
            "summary_balanced": {
                "en": "Balanced clusters",
                "it": "Cluster bilanciati",
                "fr": "Clusters équilibrés",
                "de": "Ausgeglichene Cluster",
            },
            "summary_bank_buckets": {
                "en": "Bank buckets",
                "it": "Bucket banca",
                "fr": "Regroupements banque",
                "de": "Bank-Buckets",
            },
            "summary_ledger_buckets": {
                "en": "Ledger buckets",
                "it": "Bucket mastro",
                "fr": "Regroupements grand livre",
                "de": "Hauptbuch-Buckets",
            },
            "summary_unmatched_bank": {
                "en": "Unmatched bank entries (after filtering)",
                "it": "Banche non riconciliate (dopo i filtri)",
                "fr": "Lignes bancaires non rapprochées (après filtres)",
                "de": "Nicht abgeglichene Bankbuchungen (nach Filter)",
            },
            "summary_unmatched_ledger": {
                "en": "Unmatched ledger entries",
                "it": "Registrazioni di mastro non riconciliate",
                "fr": "Écritures du grand livre non rapprochées",
                "de": "Offene Hauptbuchbuchungen",
            },
            "summary_evidence": {
                "en": "Support examples",
                "it": "Esempi di supporti",
                "fr": "Exemples de justificatifs",
                "de": "Belegbeispiele",
            },
            "summary_labels": {
                "unmatched_bank_raw": {
                    "en": "Unmatched bank (raw)",
                    "it": "Banche non riconciliate (grezzo)",
                    "fr": "Écarts banque (brut)",
                    "de": "Nicht abgeglichene Bank (roh)",
                },
                "unmatched_bank_filtered": {
                    "en": "Unmatched bank (filtered)",
                    "it": "Banche non riconciliate (filtrato)",
                    "fr": "Écarts banque (filtré)",
                    "de": "Nicht abgeglichene Bank (gefiltert)",
                },
                "unmatched_bank_total": {
                    "en": "Unmatched bank total",
                    "it": "Totale banche non riconciliate",
                    "fr": "Total écarts banque",
                    "de": "Summe Bankabweichungen",
                },
                "unmatched_ledger": {
                    "en": "Unmatched ledger",
                    "it": "Mastro non riconciliato",
                    "fr": "Grand livre non rapproché",
                    "de": "Nicht abgeglichenes Hauptbuch",
                },
                "unmatched_ledger_total": {
                    "en": "Unmatched ledger total",
                    "it": "Totale mastro non riconciliato",
                    "fr": "Total grand livre non rapproché",
                    "de": "Summe offene Hauptbuchposten",
                },
                "bank_drop": {
                    "en": "Early non-transaction drop",
                    "it": "Esclusioni preliminari",
                    "fr": "Exclusions initiales",
                    "de": "Frühe Ausschlüsse",
                },
            },
            "sample_filter": {
                "title": {
                    "en": "Sample filter",
                    "it": "Filtro campione",
                    "fr": "Filtre échantillon",
                    "de": "Stichprobenfilter",
                },
                "default_message": {
                    "en": "Sample file processed.",
                    "it": "File campione elaborato.",
                    "fr": "Fichier échantillon traité.",
                    "de": "Stichprobendatei verarbeitet.",
                },
                "movements_detected": {
                    "en": "{count} movements detected",
                    "it": "{count} movimenti rilevati",
                    "fr": "{count} écritures détectées",
                    "de": "{count} Buchungen erkannt",
                },
                "matched_template": {
                    "en": "Matched {matched} movements out of {total}.",
                    "it": "Abbinate {matched} registrazioni su {total}.",
                    "fr": "{matched} écritures rapprochées sur {total}.",
                    "de": "{matched} von {total} Buchungen abgeglichen.",
                },
            },
        },
        "buttons": {
            "upload": {
                "en": "Upload files",
                "it": "Carica file",
                "fr": "Importer les fichiers",
                "de": "Dateien hochladen",
            },
            "save_mapping": {
                "en": "Save mapping",
                "it": "Salva mappatura",
                "fr": "Enregistrer la cartographie",
                "de": "Zuordnung speichern",
            },
            "run": {
                "en": "Run reconciliation",
                "it": "Avvia riconciliazione",
                "fr": "Lancer le rapprochement",
                "de": "Abgleich starten",
            },
            "download_excel": {
                "en": "Download Excel",
                "it": "Scarica Excel",
                "fr": "Télécharger Excel",
                "de": "Excel herunterladen",
            },
        },
        "messages": {
            "upload_requirement": {
                "en": "Upload at least one bank file and one ledger file.",
                "it": "Carica almeno un file bancario e uno di mastro.",
                "fr": "Importez au moins un fichier banque et un fichier grand livre.",
                "de": "Laden Sie mindestens eine Bankdatei und eine Hauptbuchdatei hoch.",
            },
            "files_uploaded": {
                "en": "Files uploaded successfully.",
                "it": "File caricati con successo.",
                "fr": "Fichiers importés avec succès.",
                "de": "Dateien erfolgreich hochgeladen.",
            },
            "upload_first": {
                "en": "Upload files first.",
                "it": "Carica prima i file.",
                "fr": "Importez d’abord les fichiers.",
                "de": "Zuerst Dateien hochladen.",
            },
            "mapping_saved": {
                "en": "Mapping saved.",
                "it": "Mappatura salvata.",
                "fr": "Cartographie enregistrée.",
                "de": "Zuordnung gespeichert.",
            },
            "reconciliation_done": {
                "en": "Reconciliation completed.",
                "it": "Riconciliazione completata.",
                "fr": "Rapprochement terminé.",
                "de": "Abgleich abgeschlossen.",
            },
            "run_before_download": {
                "en": "Run reconciliation before downloading.",
                "it": "Esegui la riconciliazione prima di scaricare.",
                "fr": "Lancez le rapprochement avant de télécharger.",
                "de": "Abgleich ausführen, bevor Sie herunterladen.",
            },
            "download_failed": {
                "en": "Download failed",
                "it": "Download non riuscito",
                "fr": "Échec du téléchargement",
                "de": "Download fehlgeschlagen",
            },
        },
    },
    "presentations": {
        "page_help": {
            "en": "View our shared presentations and PDF documents.",
            "it": "Consulta le nostre presentazioni e i documenti PDF condivisi.",
            "fr": "Consultez nos présentations et documents PDF partagés.",
            "de": "Sehen Sie sich unsere Präsentationen und PDF-Dokumente an.",
        },
        "form": {
            "title": {
                "en": "Enter project token",
                "it": "Inserisci il token del progetto",
                "fr": "Saisissez le jeton du projet",
                "de": "Projekt-Token eingeben",
            },
            "label": {
                "en": "Provide the token to continue.",
                "it": "Inserisci il token per continuare.",
                "fr": "Indiquez le jeton pour continuer.",
                "de": "Geben Sie das Token ein, um fortzufahren.",
            },
            "placeholder": {
                "en": "Project token",
                "it": "Token progetto",
                "fr": "Jeton du projet",
                "de": "Projekt-Token",
            },
            "button": {
                "en": "Continue",
                "it": "Continua",
                "fr": "Continuer",
                "de": "Weiter",
            },
            "toggle_show": {
                "en": "Show",
                "it": "Mostra",
                "fr": "Afficher",
                "de": "Anzeigen",
            },
            "toggle_hide": {
                "en": "Hide",
                "it": "Nascondi",
                "fr": "Masquer",
                "de": "Ausblenden",
            },
            "error": {
                "en": "Invalid token. Try again.",
                "it": "Token non valido. Riprova.",
                "fr": "Jeton invalide. Réessayez.",
                "de": "Ungültiges Token. Versuchen Sie es erneut.",
            },
        },
        "buttons": {
            "hand_bikes": {
                "en": "Hand bikes",
                "it": "Hand bikes",
                "fr": "Hand bikes",
                "de": "Hand bikes",
            },
            "combined_bikes": {
                "en": "e-Bike Opportunity",
                "it": "Opportunità e-Bike",
                "fr": "Opportunité e-Bike",
                "de": "E-Bike-Chance",
            },
            "setting_category_transformation": {
                "en": "setting category transformation",
                "it": "setting category transformation",
                "fr": "setting category transformation",
                "de": "setting category transformation",
            },
            "print_deck": {
                "en": "Print PDF",
                "it": "Stampa PDF",
                "fr": "Imprimer en PDF",
                "de": "PDF drucken",
            },
            "export_pptx": {
                "en": "Export PPTX",
                "it": "Esporta PPTX",
                "fr": "Exporter en PPTX",
                "de": "PPTX exportieren",
            },
        },
    },
    "launch_reports": {
        "page_help": {
            "en": "Browse retailer signals to see which attribute bundles appear to be winning, emerging, or overrepresented in the retailer environment.",
            "it": "Esplora i segnali dei retailer per vedere quali combinazioni di attributi sembrano vincenti, emergenti o sovrarappresentate nell'ambiente del retailer.",
            "fr": "Parcourez les signaux retailers pour voir quelles combinaisons d'attributs semblent gagnantes, émergentes ou surreprésentées dans l'environnement du retailer.",
            "de": "Durchsuchen Sie Retailer-Signale, um zu sehen, welche Attributbündel im Retailer-Umfeld als stark, aufkommend oder überrepräsentiert erscheinen.",
        },
        "validation_status_checked": {
            "en": "Automated check found no caution items.",
            "it": "Il controllo automatico non ha trovato elementi di cautela.",
            "fr": "Le contrôle automatique n'a trouvé aucun élément de prudence.",
            "de": "Die automatische Prüfung hat keine Vorsichtspunkte gefunden.",
        },
        "validation_status_noted": {
            "en": "Automated check found caution notes only.",
            "it": "Il controllo automatico ha trovato solo note di cautela.",
            "fr": "Le contrôle automatique n'a trouvé que des notes de prudence.",
            "de": "Die automatische Prüfung hat nur Vorsichtshinweise gefunden.",
        },
        "validation_status_caution": {
            "en": "Automated check found items that need review.",
            "it": "Il controllo automatico ha trovato elementi da rivedere.",
            "fr": "Le contrôle automatique a trouvé des éléments à relire.",
            "de": "Die automatische Prüfung hat Punkte gefunden, die geprüft werden sollten.",
        },
        "validation_status_unknown": {
            "en": "Automated validation status is unknown; most report text units remain unresolved.",
            "it": "Lo stato della validazione automatica è sconosciuto; la maggior parte dei testi del report resta non risolta.",
            "fr": "Le statut de validation automatique est inconnu; la plupart des textes du rapport restent non résolus.",
            "de": "Der Status der automatischen Validierung ist unbekannt; die meisten Texte im Report bleiben ungelöst.",
        },
        "validation_status_unknown_short": {
            "en": "unknown",
            "it": "unknown",
            "fr": "unknown",
            "de": "unknown",
        },
        "validation_status_summary": {
            "en": "Automated package check does not apply to this summary report.",
            "it": "Il controllo automatico del pacchetto non si applica a questo report riepilogativo.",
            "fr": "Le contrôle automatique du package ne s'applique pas à ce rapport de synthèse.",
            "de": "Die automatische Paketprüfung gilt nicht für diesen Zusammenfassungsreport.",
        },
        "validation_status_pending": {
            "en": "Automated check is not available yet.",
            "it": "Il controllo automatico non è ancora disponibile.",
            "fr": "Le contrôle automatique n'est pas encore disponible.",
            "de": "Die automatische Prüfung ist noch nicht verfügbar.",
        },
    },
    "brand_reports": {
        "page_help": {
            "en": "Use brand fit reports to see which retailer signals the brand already covers, and where the brand may still have retailer-relevant product gaps.",
            "it": "Usa i report brand fit per vedere quali segnali del retailer il brand copre già e dove il brand può avere ancora gap di prodotto rilevanti per il retailer.",
            "fr": "Utilisez les rapports brand fit pour voir quels signaux retailer la marque couvre déjà et où la marque peut encore avoir des écarts produit pertinents pour le retailer.",
            "de": "Nutzen Sie brand-fit-Berichte, um zu sehen, welche Retailer-Signale die Marke bereits abdeckt und wo die Marke noch retailer-relevante Produktlücken haben kann.",
        },
    },
    "product_hypotheses": {
        "page_help": {
            "en": "Explore product hypotheses derived from retailer signals and brand fit.",
            "it": "Esplora ipotesi di prodotto derivate dai segnali dei retailer e dal brand fit.",
            "fr": "Explorez des hypothèses produit dérivées des signaux retailers et du brand fit.",
            "de": "Entdecken Sie Produkthypothesen, die aus Retailer-Signalen und brand fit abgeleitet werden.",
        },
    },
}


def resolve_language(request: Request) -> str:
    lang_param = request.query_params.get("lang")
    if lang_param in SUPPORTED_LANGUAGES:
        return lang_param

    cookie_lang = request.cookies.get("lang")
    if cookie_lang in SUPPORTED_LANGUAGES:
        return cookie_lang

    header_lang = request.headers.get("accept-language")
    if header_lang:
        for item in header_lang.split(","):
            code = item.split(";")[0].strip().lower()
            if not code:
                continue
            primary = code.split("-")[0]
            if primary in SUPPORTED_LANGUAGES:
                return primary
            if len(code) >= 2 and code[:2] in SUPPORTED_LANGUAGES:
                return code[:2]

    ip_address = _extract_client_ip(request)
    if ip_address:
        country_code = _lookup_country_code(ip_address)
        if country_code == "IT":
            return "it"
        if country_code == "FR":
            return "fr"
        if country_code == "DE":
            return "de"
    return "en"


def _extract_client_ip(request: Request) -> Optional[str]:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
        if ip:
            return ip
    if request.client and request.client.host:
        return request.client.host
    return None


def _lookup_country_code(ip_address: str) -> Optional[str]:
    if not ip_address:
        return None
    try:
        parsed = ipaddress.ip_address(ip_address)
        if parsed.is_private or parsed.is_loopback:
            return None
    except ValueError:
        return None

    endpoint = f"https://ipinfo.io/{ip_address}/country"
    try:
        with urlopen(endpoint, timeout=1.0) as response:
            if response.status == 200:
                code = response.read().decode("utf-8").strip().upper()
                if len(code) == 2 and code.isalpha():
                    return code
    except URLError:
        return None
    except Exception:
        return None
    return None


def get_navigation_label(lang: str, href: str) -> Optional[str]:
    labels = PAGE_LABELS.get(href)
    if not labels:
        return None
    return labels.get(lang) or labels.get("en")


def get_page_copy(page: str, lang: str) -> Dict[str, Any]:
    page_data = PAGE_COPY.get(page)
    if not page_data:
        return {}
    return _resolve_copy(page_data, lang)


def _resolve_copy(node: Any, lang: str) -> Any:
    if isinstance(node, dict):
        keys = set(node.keys())
        if keys and keys.issubset(SUPPORTED_LANGUAGES):
            return node.get(lang) or node.get("en") or next(iter(node.values()))
        return {key: _resolve_copy(value, lang) for key, value in node.items()}
    return node


__all__ = [
    "LANDING_LANGUAGE_LABELS",
    "LANGUAGE_LABELS",
    "LANGUAGE_ORDER",
    "SUPPORTED_LANGUAGES",
    "resolve_language",
    "get_navigation_label",
    "get_page_copy",
]
