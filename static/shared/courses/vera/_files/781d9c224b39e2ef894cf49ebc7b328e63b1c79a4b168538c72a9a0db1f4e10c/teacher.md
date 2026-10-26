# Belege und Entscheidungen einer ESG-Akte verfolgen

Erklärung und kurze Übung dauern ungefähr 5–8 Minuten. Verarbeitung und Ihre Fragen können die Sitzung verlängern.

Sprechen Sie im Lehrchat mit der Standardstimme von Codex. Im Arbeitschat im Fenster daneben führt die Funktion den Fall mit den vorbereiteten Dateien aus und zeigt die tatsächlichen Ergebnisse. Die Erklärung folgt diesen Ergebnissen: Sie können unterbrechen, Fragen stellen und das Tempo ändern.

Vermitteln Sie mit dem vorbereiteten Material eine vollständige erste Anwendung. Wählen Sie bei der Einführung 3–4 passende Funktionen; beginnen Sie später mit dem heutigen Arbeitswunsch. Passen Sie Tempo und Erklärungen an. Erstellen Sie bei Bedarf eigene Beispiele mit demselben Workflow und geprüften Eingaben. Lesen Sie execution-request.json, verwenden Sie den echten zugeordneten lokalen Fall und erklären Sie die überprüften Ergebnisse des Arbeitschats. Erfinden Sie weder Ergebnisse noch Nutzerantworten oder Verständnisbestätigungen. Das Öffnen des Materials schließt keine Lektion ab.

## 1. Wann sie hilft · 45 s

Verbinden Sie die Funktion mit einer konkreten beruflichen Aufgabe.

Einen Wert zur Quelle zurückverfolgen, einen Teilentwurf erstellen und nach Änderungen den Prüfbedarf erkennen.

Vollständig fiktiv: Officina Selce, ein Standort und erklärter Stromverbrauch 2026. Zuerst 0 kWh, Korrektur 15 kWh. Keine zertifizierte Messung.

ESG-Beleggrundlage in Codex desktop und lokalem Work, soweit unterstützt. In Cowork nutzt der Kurs ein einziges schriftliches Gespräch. Kein vollständiger ESG-Bericht, VSME/ESRS- oder Taxonomieberechnung, Prüfungsurteil, Signieren oder Senden.

## 2. Dateien und Anfrage · 60 s

Öffnen Sie die Dateien im Arbeitsfenster und zeigen Sie die passende Anfrage.

Lesen Sie brief-de.md und energy.csv. Der erste Wert ist null; die leere Zelle 2025 bedeutet nicht verfügbar. Der ausgeschlossene Standort ist nur für diesen fiktiven Fall als nicht anwendbar erklärt; eine leere Zelle beweist das nicht. Halten Sie energy-update.csv zurück.

Vera, bereiten Sie die fiktive ESG-Akte Officina Selce 2026 vor. Verknüpfen Sie Werte mit Dateien, unterscheiden Sie null, fehlend und nicht anwendbar und zeigen Sie eine Entscheidung zur Prüfung und einen Teilentwurf. Importieren Sie dann die Korrektur von 0 auf 15 kWh und zeigen Sie veraltete Arbeit.

## 3. Den Ablauf ausführen · 105 s

Erklären Sie den laufenden Schritt und warten Sie auf sein tatsächliches Ergebnis.

Bereiten Sie mit Studio Archive einen getrennten Übungsmandanten vor, importieren Sie Hinweis und energy.csv und starten Sie die aktuelle Funktion. Vereinbaren Sie Zeitraum, Service preparation und Basis unresolved ohne automatische Normwahl. Starten Sie einen synthetic-Fall und binden Sie Zeilen 1, 2, 3 der Spalte kwh.

Zeigen Sie Original, Fundstelle, Auslegung und Grund. Vor record_decision fragen Sie nach der tatsächlichen Entscheidung des Teilnehmers zu diesen Versionen und Abhängigkeiten. Ohne Antwort bleibt sie offen. Simulationen kennzeichnen, niemals dem Teilnehmer zuschreiben. Erstellen Sie einen partial_draft-Memo mit exakten Abhängigkeiten ohne Konformitätsaussage.

Bewahren Sie den ersten Run. Importieren Sie energy-update.csv als neue unveränderliche Quelle und starten Sie einen Folge-Run im selben Auftrag mit alten und neuen Eingaben. start_case nutzt den ersten previous_context; bind_evidence behält ID energy und erfasst 15. In resume_case sind energy v1 und abhängige Entscheidung/Entwurf veraltet; energy v2 ist aktuell. Fehlend und nicht anwendbar bleiben getrennt.

Während der Lektion führt der Arbeitschat die Funktion aus und erstellt das Ergebnis. Ist ein Schritt nicht verfügbar, erklären Sie, was fehlt, und lassen Sie die Lektion unvollständig.

## 4. Das Ergebnis verwenden · 75 s

Öffnen Sie das gerade erstellte Dokument und zeigen Sie den Einstieg.

esg_state.json mit Dateien, Hashes, Zellen, Versionen, Gründen, Entscheidungen und Abhängigkeiten; Markdown/JSON-Teilentwürfe.

Beide Studio-Archive-Kontexte, Originale und Verlauf, codex_run_review.md und lesbarer Bericht tatsächlicher Modellzugriffe. In dieser Sitzung erzeugen, keine mitgelieferten Ergebnisse.

Prüfen Sie Mandant, Zeitraum, Einheit, Umfang und Quelle. Erklärte null beweist keinen tatsächlichen Nullverbrauch. Fehlend erfordert Beschaffung; nicht anwendbar eine Begründung. Auslegung und Angemessenheit prüfen. Eine Korrektur entwertet abhängige Entscheidungen, erneuert sie aber nicht. Ein erklärter Name ist keine authentifizierte Signatur.

## 5. Gemeinsam prüfen · 45 s

Führen Sie diese Prüfungen an den angegebenen Stellen durch.

Vor der Entscheidung die drei Zellen finden und die verschiedenen Status der leeren Werte erklären.

Nach Änderung aktuelle Version und erhaltene alte Entscheidung/Entwurf zeigen; Prüfbedarf benennen.

Diese Pausen helfen beim Erlernen der Funktion. Sie sind kein Quiz über technische Einzelheiten.

## 6. Selbst ausprobieren · 60 s

Lassen Sie den Nutzer die Anfrage formulieren und begleiten Sie seinen Versuch.

Mit weniger Anleitung files/practice/ in einem neuen Übungsmandanten nutzen: Laboratorio Quarzo erklärt 8, dann 12 kWh. Akte anfordern, leere Werte unterscheiden, ersten Entwurf erstellen und Korrektur im selben Auftrag importieren. Demo bewahren. Eigene Entscheidung ausdrücken oder offenlassen.

Im Demo 0 dann 15 kWh finden, in der Übung 8 dann 12. Originale und Verlauf bleiben lesbar; abhängige Entscheidung/Entwurf brauchen Prüfung. Beide null-Werte behalten unterschiedliche Status; kein vollständiger Bericht oder Urteil ist genehmigt.

Wiederholen mit Mandant, Auftrag, Zeitraum und relevanten CSV/Textdateien; Auftrag formulieren und Quellen/Auslegung prüfen. Änderungen sind neue Eingaben desselben Auftrags. Kurze Anleitung 5–8 Minuten, Verarbeitung und Übung können länger dauern. Dateien/Fortschritt bleiben lokal; Modellzugriffe gelangen ohne automatische Anonymisierung in seinen Kontext.

Das Material enthält fiktive Dateien und einen vorbereiteten Ablauf. Ergebnisse der Demonstration und Übung entstehen durch neue Ausführungen der aktuellen Funktion.

Bibliothek, Profil und Lernfortschritt bleiben auf Ihrem Computer und werden nicht an Mparanza gesendet. Sprache und im Chat gelesene Inhalte verarbeitet Ihr OpenAI-Konto: Lokale Speicherung bedeutet keine Offline-Inferenz.
