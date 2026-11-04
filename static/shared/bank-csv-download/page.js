Object.assign(window.MPARANZA_FUNCTION_PAGES, {
  "bank-csv-download": {
    "product": "Vera",
    "defaultLanguage": "it",
    "copy": {
      "it": {
        "name": "Download CSV bancari",
        "summary": "Scarica i CSV originali dei movimenti dal portale bancario tramite computer use e 1Password.",
        "useWhen": "Quando occorrono movimenti bancari per aggiornare la contabilità.",
        "input": "Banca e portale, cliente/conto, periodo e accesso legittimo dell’operatore.",
        "work": "Il modello scelto nella chat naviga il portale, imposta i filtri e verifica i file scaricati.",
        "output": "CSV originali e rapporto con conto, periodo, verifiche e parti mancanti.",
        "responsibilityIntro": "Richiede computer use, accesso ai file locali e un browser utilizzabile. I portali bancari restano da collaudare.",
        "productRole": "Guida navigazione ed esportazione; distingue download riuscito e verifica della copertura.",
        "professionalRole": "Sblocca 1Password, completa MFA e valuta l’utilizzo contabile dei movimenti.",
        "prompt": "scarica i CSV della banca per il conto e il periodo indicati.",
        "modelDataStatus": "relevant"
      },
      "en": {
        "name": "Bank CSV download",
        "summary": "Downloads original transaction CSVs from the bank portal using computer use and 1Password.",
        "useWhen": "When bank movements are needed to update accounting.",
        "input": "Bank and portal, client/account, period and the operator’s legitimate access.",
        "work": "The selected chat model navigates the portal, sets filters and checks downloaded files.",
        "output": "Original CSVs and a report covering account, period, checks and missing parts.",
        "responsibilityIntro": "Requires computer use, local file access and a usable browser. Authenticated bank acceptance remains outstanding.",
        "productRole": "Guides navigation and export; distinguishes successful download from coverage verification.",
        "professionalRole": "Unlock 1Password, complete MFA and assess accounting use of the movements.",
        "prompt": "download the bank CSVs for the specified account and period.",
        "modelDataStatus": "relevant"
      },
      "fr": {
        "name": "Téléchargement CSV bancaires",
        "summary": "Télécharge les CSV originaux des opérations depuis le portail bancaire avec computer use et 1Password.",
        "useWhen": "Pour obtenir les opérations nécessaires à la comptabilité.",
        "input": "Banque et portail, client/compte, période et accès légitime de l’opérateur.",
        "work": "Le modèle choisi dans le chat parcourt le portail, règle les filtres et vérifie les fichiers téléchargés.",
        "output": "CSV originaux et rapport indiquant compte, période, contrôles et éléments manquants.",
        "responsibilityIntro": "Nécessite computer use, accès aux fichiers locaux et navigateur utilisable. Les essais bancaires authentifiés restent à effectuer.",
        "productRole": "Guide navigation et export ; distingue téléchargement et vérification de couverture.",
        "professionalRole": "Déverrouille 1Password, termine la MFA et évalue l’utilisation comptable des opérations.",
        "prompt": "télécharge les CSV bancaires pour le compte et la période indiqués.",
        "modelDataStatus": "relevant"
      },
      "de": {
        "name": "Bank-CSV herunterladen",
        "summary": "Lädt Original-CSV-Dateien der Kontobewegungen über Computer use und 1Password aus dem Bankportal herunter.",
        "useWhen": "Wenn Kontobewegungen für die Buchhaltung benötigt werden.",
        "input": "Bank und Portal, Mandant/Konto, Zeitraum und rechtmäßiger Zugang des Bedieners.",
        "work": "Das im Chat gewählte Modell navigiert im Portal, setzt Filter und prüft heruntergeladene Dateien.",
        "output": "Original-CSV-Dateien und Bericht über Konto, Zeitraum, Prüfungen und fehlende Teile.",
        "responsibilityIntro": "Erfordert Computer use, lokale Dateirechte und einen nutzbaren Browser. Authentifizierte Banktests stehen noch aus.",
        "productRole": "Führt Navigation und Export aus; trennt Download-Erfolg von Abdeckungsprüfung.",
        "professionalRole": "Entsperrt 1Password, erledigt MFA und beurteilt die buchhalterische Verwendung.",
        "prompt": "lade die Bank-CSV-Dateien für das angegebene Konto und den Zeitraum herunter.",
        "modelDataStatus": "relevant"
      },
      "es": {
        "name": "Descarga CSV bancarios",
        "summary": "Descarga los CSV originales de movimientos del portal bancario con computer use y 1Password.",
        "useWhen": "Cuando se necesitan movimientos bancarios para actualizar la contabilidad.",
        "input": "Banco y portal, cliente/cuenta, período y acceso legítimo del operador.",
        "work": "El modelo elegido en el chat navega por el portal, aplica filtros y verifica los archivos descargados.",
        "output": "CSV originales e informe con cuenta, período, comprobaciones y partes pendientes.",
        "responsibilityIntro": "Requiere computer use, acceso a archivos locales y navegador utilizable. Las pruebas bancarias autenticadas siguen pendientes.",
        "productRole": "Guía navegación y exportación; distingue descarga correcta de cobertura comprobada.",
        "professionalRole": "Desbloquea 1Password, completa MFA y evalúa el uso contable de los movimientos.",
        "prompt": "descarga los CSV bancarios para la cuenta y el período indicados.",
        "modelDataStatus": "relevant"
      }
    }
  }
});
