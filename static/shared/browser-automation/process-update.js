(() => {
  const browserSessionCopy = {
    it: [
      "Prima di una pausa per accesso o altro intervento dell'operatore, Vera conserva la scheda del processo per il turno successivo. Distingue scheda persa, elenco vuoto e browser non disponibile. Lo scaricatore delle singole fatture Agenzia conserva gli avanzamenti e verifica il totale atteso; resta un prototipo finché non viene verificato sul sito reale.",
      "La diagnosi restituisce categorie, conteggi, esiti della conservazione della scheda e hash degli errori. Solo gli identificativi temporanei delle schede sulle origini autorizzate possono essere usati per la ripresa; URL completi e titoli non entrano nel report. Per lo scaricatore Agenzia il modello usa periodo, direzione e conteggi osservati e riceve avanzamento e stato del prototipo. Percorsi dei file e hash delle pagine di dettaglio restano nei report locali; i contenuti delle fatture non vengono restituiti. Le prove simulate sono identificate e non valgono come validazione sul sito reale."
    ],
    en: [
      "Before pausing for login or another operator step, Vera preserves the process tab for the next turn. It distinguishes a missing tab, an empty list and an unavailable browser. The individual Agenzia invoice downloader retains progress and checks the expected total; it remains a prototype until verified on the real site.",
      "Diagnosis returns categories, counts, tab-retention outcomes and error hashes. Only temporary tab identifiers on authorized origins may be used to resume; full URLs and titles are excluded from the report. For Agenzia downloads the model uses the period, direction and observed counts and receives progress and prototype status. File paths and detail-page hashes remain in local reports; invoice contents are not returned. Simulated tests are identified and cannot count as real-site validation."
    ],
    fr: [
      "Avant une pause pour connexion ou intervention de l'opérateur, Vera conserve l'onglet du processus pour le tour suivant. Elle distingue onglet absent, liste vide et navigateur indisponible. Le téléchargement individuel des factures Agenzia conserve la progression et vérifie le total attendu ; il reste un prototype jusqu'à sa vérification sur le site réel.",
      "Le diagnostic renvoie catégories, nombres, résultat de conservation de l'onglet et empreintes des erreurs. Seuls les identifiants temporaires d'onglets sur les origines autorisées peuvent servir à reprendre ; URL complètes et titres sont exclus du rapport. Pour Agenzia, le modèle utilise période, sens et nombres observés et reçoit progression et état du prototype. Chemins des fichiers et empreintes des pages de détail restent dans les rapports locaux ; le contenu des factures n'est pas renvoyé. Les tests simulés sont identifiés et ne constituent pas une validation sur le site réel."
    ],
    de: [
      "Vor einer Pause für Anmeldung oder einen Bedienerschritt bewahrt Vera den Prozess-Tab für den nächsten Gesprächsschritt auf. Sie unterscheidet fehlenden Tab, leere Liste und nicht verfügbaren Browser. Der Einzeldownload von Agenzia-Rechnungen speichert den Fortschritt und prüft die erwartete Gesamtzahl; bis zur Prüfung auf der echten Website bleibt er ein Prototyp.",
      "Die Diagnose liefert Kategorien, Anzahlen, Ergebnisse der Tab-Aufbewahrung und Fehler-Hashes. Nur temporäre Tab-Kennungen zugelassener Ursprünge dürfen zur Fortsetzung dienen; vollständige URLs und Titel fehlen im Bericht. Für Agenzia verwendet das Modell Zeitraum, Richtung und beobachtete Anzahlen und erhält Fortschritt und Prototypstatus. Dateipfade und Hashes der Detailseiten bleiben in lokalen Berichten; Rechnungsinhalte werden nicht zurückgegeben. Simulierte Tests werden gekennzeichnet und gelten nicht als Validierung auf der echten Website."
    ],
    es: [
      "Antes de pausar para iniciar sesión u otro paso del operador, Vera conserva la pestaña del proceso para el siguiente turno. Distingue pestaña ausente, lista vacía y navegador no disponible. La descarga individual de facturas Agenzia conserva el progreso y comprueba el total esperado; sigue siendo un prototipo hasta verificarse en el sitio real.",
      "El diagnóstico devuelve categorías, recuentos, resultado de conservación de la pestaña y hashes de errores. Solo pueden usarse identificadores temporales de pestañas en orígenes autorizados para retomar; URL completas y títulos quedan fuera del informe. Para Agenzia el modelo usa periodo, dirección y recuentos observados y recibe progreso y estado del prototipo. Rutas de archivos y hashes de páginas de detalle permanecen en informes locales; no se devuelve el contenido de las facturas. Las pruebas simuladas se identifican y no cuentan como validación en el sitio real."
    ]
  };
  Object.entries(browserSessionCopy).forEach(([language, text]) => {
    const page = window.MPARANZA_FUNCTION_PAGES["browser-automation"].copy[language];
    page.work += " " + text[0];
    page.modelData += "\n\n" + text[1];
  });
})();
