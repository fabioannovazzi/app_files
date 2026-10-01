# Einen synthetischen Umwandlungsfall bearbeiten

Erklärung und kurze Übung dauern ungefähr 5–8 Minuten. Verarbeitung und Ihre Fragen können die Sitzung verlängern.

Sprechen Sie im Lehrchat mit der Standardstimme von Codex. Im Arbeitschat im Fenster daneben führt die Funktion den Fall mit den vorbereiteten Dateien aus und zeigt die tatsächlichen Ergebnisse. Die Erklärung folgt diesen Ergebnissen: Sie können unterbrechen, Fragen stellen und das Tempo ändern.

Vermitteln Sie mit dem vorbereiteten Material eine vollständige erste Anwendung. Wählen Sie bei der Einführung 3–4 passende Funktionen; beginnen Sie später mit dem heutigen Arbeitswunsch. Passen Sie Tempo und Erklärungen an. Erstellen Sie bei Bedarf eigene Beispiele mit demselben Workflow und geprüften Eingaben. Lesen Sie execution-request.json, verwenden Sie den echten zugeordneten lokalen Fall und erklären Sie die überprüften Ergebnisse des Arbeitschats. Erfinden Sie weder Ergebnisse noch Nutzerantworten oder Verständnisbestätigungen. Das Öffnen des Materials schließt keine Lektion ab.

## 1. Wann sie hilft · 45 s

Verbinden Sie die Funktion mit einer konkreten beruflichen Aufgabe.

Ein synthetisches Dossier erstellen und prüfen, Belege verfolgen und Entscheidungen nach geänderten Verbindlichkeiten neu prüfen.

Die erfundene Officina Selce SNC erwägt eine SRL. Zwei Gesellschafter haben unterschiedliche Kapital-, Stimm- und Gewinnrechte. Die Bewertung kommt nach der Gläubigerliste.

Italienischer Prototyp mit erfundenen Daten in Codex Desktop und lokalem Work, soweit unterstützt. Cowork bietet diesen Kurs nicht. Das native Dossier bleibt italienisch. Keine rechtliche oder steuerliche Qualifizierung, authentifizierte Unterschrift, Studio-Archive-Integration oder Einreichung.

## 2. Dateien und Anfrage · 60 s

Öffnen Sie die Dateien im Arbeitsfenster und zeigen Sie die passende Anfrage.

Öffnen Sie files/input/case.json, participants.json und creditors.json. valuation.json folgt im zweiten Schritt, valuation-update.json bei der letzten Änderung. Null bedeutet unbekannt, nicht null Euro oder Zustimmung; Zahlenzeichenfolgen sind exakt. Keine echten Mandanten.

Vera, führe mich durch den synthetischen Fall Officina Selce: importiere zuerst Auftrag, Gesellschafter und Gläubiger, zeige die fehlenden Kapitalbelege und erfasse dann die Bewertung. Schlage beleggebundene Schlussfolgerungen vor, zeige die zu prüfenden Entscheidungen und exportiere ohne externe Aktionen.

## 3. Den Ablauf ausführen · 105 s

Erklären Sie den laufenden Schritt und warten Sie auf sein tatsächliches Ergebnis.

Im Arbeitschat liest Vera das installierte Verfahren und erstellt einen neuen lokalen synthetischen Ordner. Importieren Sie die ersten drei Dateien als Belege. Schlagen Sie getrennte Zweige für Kapital, Gläubigererfassung und Steuern vor. Kapital hängt von der noch fehlenden Bewertung ab; die Erfassung kann weitergehen, während Haftungsbefreiung und Widerspruch getrennte offene Fragen bleiben. Exportieren Sie diese Version.

Importieren Sie valuation.json. Das Modell schlägt Berechnungen, Rechte und Schlussfolgerungen mit genauen Belegabhängigkeiten und prüfbaren Gründen vor. Prüfen Sie Kapitaldeckung und Verteilung; unterscheiden Sie Kapital/Stimmen/Gewinn sowie Buch-/Schätz-/Steuerwert. Erfinden Sie keine Rechtsquellen: Steuerfragen und fehlende Empfangsnachweise bleiben offen. Zeigen Sie Vorschlag, Digest und Dossier vor der Prüfung.

Erfassen Sie nur tatsächlich geäußerte Entscheidungen des Teilnehmers mit Prüfer, Grund und Digest; kennzeichnen Sie Simulationen. Bewahren Sie den Export auf. Importieren Sie valuation-update.json unter derselben Bewertungs-ID: Kapital wird stale, unabhängige Erfassung bleibt aktuell. Neue Dokumente ändern alte Berechnungen nicht: korrigieren Sie Zahlen und Aussagen, reichen Sie erneut zur Prüfung ein und erfragen Sie eine neue Entscheidung. Öffnen Sie dossier.md, case.json, manifest.json und history/.

Während der Lektion führt der Arbeitschat die Funktion aus und erstellt das Ergebnis. Ist ein Schritt nicht verfügbar, erklären Sie, was fehlt, und lassen Sie die Lektion unvollständig.

## 4. Das Ergebnis verwenden · 75 s

Öffnen Sie das gerade erstellte Dokument und zeigen Sie den Einstieg.

Versioniertes Markdown- und JSON-Dossier mit Belegen, Abhängigkeiten, Beträgen, Rechten, Blockaden, offenen Fragen und Entscheidungen; Hash-Manifest.

Frühere Exporte und verkettete Historie sowie lesbarer lokaler Bericht zu Modelldaten. Vorbereitete Dateien sind keine Ausführungsergebnisse.

Verfolgen Sie eine Aussage zu evidence/<hash> und zum Originalbeleg. Prüfen Sie exakte Beträge und getrennte Rechte. Ein Rechenüberschuss ist keine ausschüttbare Rücklage. Ein unbekannter Empfangsnachweis belegt weder Haftungsbefreiung noch Widerspruchsausgang. Der Prüfvermerk authentifiziert keinen Prüfer und erlaubt höchstens synthetische Vorbereitung.

## 5. Gemeinsam prüfen · 45 s

Führen Sie diese Prüfungen an den angegebenen Stellen durch.

Benennen Sie vor der Bewertung den blockierten und den weiterarbeitenden Zweig; finden Sie fehlenden Empfangsnachweis und Steuerbasis.

Prüfen Sie vor der Entscheidung Beleg und drei Rechteanteile je Gesellschafter. Zeigen Sie nach der Änderung stale und eine erhaltene unabhängige Entscheidung.

Diese Pausen helfen beim Erlernen der Funktion. Sie sind kein Quiz über technische Einzelheiten.

## 6. Selbst ausprobieren · 60 s

Lassen Sie den Nutzer die Anfrage formulieren und begleiten Sie seinen Versuch.

Erstellen Sie mit files/practice/ einen zweiten Fall und bewahren Sie die Demo. Verwenden Sie Aktiva 640000 und Verbindlichkeiten 270000; wiederholen Sie Import, Vorschlag und Prüfung. Importieren Sie dann valuation-update.json mit Verbindlichkeiten 305000 unter derselben ID. Finden Sie stale-Zweige, korrigieren Sie Deckung und Aussagen, fordern Sie neue Prüfung an und exportieren Sie ohne Steuerfragen zu schließen oder Empfangsnachweise zu erfinden.

Prüfen Sie in der Demo Nettovermögen 450000, Rechenüberschuss 350000 und Kapitalbeträge 60000/40000; bei Verbindlichkeiten 310000 nach Neubewertung 390000/290000. In der Übung: 370000/270000, danach 335000/235000. Finden Sie Stimmen 1/2–1/2, Gewinn 7/10–3/10, frühere Entscheidung in history, Steuerblockade und Export-Hashes. Dies sind Prüfkriterien, keine bereits ausgeführten Ergebnisse.

Nur mit synthetischen Daten, neuem Ordner und tatsächlich installierter Vera-Skill wiederholen. Ein beaufsichtigter professioneller Pilot benötigt noch Qualifizierung und Abnahme. Erklärung und Kurzversuch: 5–8 Minuten; vollständige Prüfung und Übung können länger dauern. Profil, Fortschritt und Dateien bleiben lokal; ausgewählte Dokumente können vom nativen Modell gelesen werden, Verarbeitung ist nicht ausschließlich lokal.

Das Material enthält fiktive Dateien und einen vorbereiteten Ablauf. Ergebnisse der Demonstration und Übung entstehen durch neue Ausführungen der aktuellen Funktion.

Bibliothek, Profil und Lernfortschritt bleiben auf Ihrem Computer und werden nicht an Mparanza gesendet. Sprache und im Chat gelesene Inhalte verarbeitet Ihr OpenAI-Konto: Lokale Speicherung bedeutet keine Offline-Inferenz.
