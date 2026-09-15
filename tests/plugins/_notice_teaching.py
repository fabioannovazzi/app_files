"""Source-bound model text for fictional native notice regression runs.

These test interpretations exercise the skill's ordinary Codex review-note
stage. They are not shipped in teaching kits or replayed as learner results.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["write_notice_review"]

COPY = {
    "it": (
        "Prima lettura della comunicazione",
        "Caso interamente fittizio, da rivedere nello studio. La comunicazione chiede la dichiarazione del periodo d’imposta 2025 e le relative quietanze F24. Non quantifica un debito e non impartisce istruzioni di pagamento.",
        "Destinatario: Marco Prova. Mittente rappresentato: Agenzia delle Entrate, Ufficio Esempio. Riferimento: DEMO-NOTICE-01.",
        "Date e stato dei documenti",
        "La lettera è datata 02/04/2026 e indica il 30/04/2026 per fornire i documenti. Sono date riportate nella trascrizione: natura dell’atto, ricezione e termine applicabile restano da verificare sul documento integrale e sulle prove disponibili.",
        "Non sono forniti prova di ricezione, copia della dichiarazione o quietanze F24. La richiesta riguarda documenti da acquisire, non un pagamento da eseguire.",
        "Nel messaggio del 06/04/2026 il cliente dice di aver trovato la comunicazione il 3 aprile e recuperato la dichiarazione, ma non le quietanze F24. È una dichiarazione del cliente, non una ricevuta di notifica. La dichiarazione non è allegata e non risulta ricevuta dallo studio.",
        "Prossimo passo",
        "Acquisire comunicazione integrale e prova di ricezione; ottenere la dichiarazione e le quietanze richieste. Far verificare allo studio provenienza, natura della comunicazione e data applicabile prima di decidere la risposta. Nessuna risposta è stata predisposta o inviata.",
        "Fonti e file di supporto",
    ),
    "en": (
        "Initial reading of the notice",
        "Entirely fictional case for the practice to review. The notice requests the return for tax year 2025 and the corresponding F24 payment receipts. It does not quantify a debt or give payment instructions.",
        "Recipient: Marco Prova. Represented sender: Agenzia delle Entrate, Ufficio Esempio. Reference: DEMO-NOTICE-01.",
        "Dates and document status",
        "The letter is dated 02/04/2026 and states 30/04/2026 for supplying documents. These are dates in the transcription: the notice’s nature, receipt and applicable deadline require checking against the complete document and available evidence.",
        "No evidence of receipt, copy of the return or F24 receipts is supplied. This is a request to obtain documents, not an instruction to make a payment.",
        "In the message of 06/04/2026, the client says he found the notice on 3 April and recovered the return, but not the F24 receipts. This is the client’s statement, not evidence of service. The return is not attached and has not been received by the practice.",
        "Next step",
        "Obtain the complete notice and evidence of receipt, then the requested return and payment receipts. Have the practice check provenance, the notice’s nature and the applicable date before deciding the response. No response has been prepared or sent.",
        "Sources and supporting files",
    ),
    "fr": (
        "Première lecture de la communication",
        "Cas entièrement fictif à revoir au cabinet. La communication demande la déclaration de l’année fiscale 2025 et les justificatifs F24 correspondants. Elle ne chiffre aucune dette et ne donne aucune instruction de paiement.",
        "Destinataire : Marco Prova. Expéditeur représenté : Agenzia delle Entrate, Ufficio Esempio. Référence : DEMO-NOTICE-01.",
        "Dates et état des documents",
        "La lettre est datée du 02/04/2026 et indique le 30/04/2026 pour fournir les documents. Ce sont les dates de la transcription : nature de l’acte, réception et délai applicable restent à vérifier sur le document intégral et les preuves disponibles.",
        "Aucune preuve de réception, copie de la déclaration ou justificatif F24 n’est fourni. Il faut réunir des documents ; aucun paiement n’est demandé.",
        "Dans son message du 06/04/2026, le client dit avoir trouvé la communication le 3 avril et récupéré la déclaration, mais pas les justificatifs F24. Il s’agit de sa déclaration, pas d’une preuve de notification. La déclaration n’est pas jointe et n’a pas été reçue par le cabinet.",
        "Prochaine étape",
        "Obtenir la communication intégrale et la preuve de réception, puis la déclaration et les justificatifs demandés. Faire vérifier au cabinet la provenance, la nature de la communication et la date applicable avant de décider de la réponse. Aucune réponse n’a été préparée ou envoyée.",
        "Sources et fichiers de support",
    ),
    "de": (
        "Erste Durchsicht der Mitteilung",
        "Vollständig fiktiver Fall zur Prüfung durch die Kanzlei. Die Mitteilung verlangt die Erklärung für das Steuerjahr 2025 und die zugehörigen F24-Zahlungsbelege. Sie beziffert keine Schuld und enthält keine Zahlungsanweisung.",
        "Empfänger: Marco Prova. Im Fall dargestellter Absender: Agenzia delle Entrate, Ufficio Esempio. Referenz: DEMO-NOTICE-01.",
        "Daten und Stand der Unterlagen",
        "Das Schreiben ist auf den 02/04/2026 datiert und nennt den 30/04/2026 für die Vorlage der Unterlagen. Dies sind Angaben der Abschrift: Art des Schreibens, Zugang und maßgebliche Frist müssen anhand des vollständigen Dokuments und verfügbarer Nachweise geprüft werden.",
        "Zugangsnachweis, Erklärungskopie und F24-Belege liegen nicht vor. Unterlagen sind zu beschaffen; eine Zahlung wird nicht verlangt.",
        "In seiner Nachricht vom 06/04/2026 erklärt der Mandant, er habe die Mitteilung am 3. April gefunden und die Erklärung, jedoch nicht die F24-Belege beschafft. Dies ist seine Aussage, kein Zustellnachweis. Die Erklärung ist nicht beigefügt und bei der Kanzlei nicht eingegangen.",
        "Nächster Schritt",
        "Vollständige Mitteilung und Zugangsnachweis sowie Erklärung und angeforderte Belege beschaffen. Die Kanzlei soll Herkunft, Art der Mitteilung und maßgebliches Datum prüfen, bevor sie über die Antwort entscheidet. Es wurde keine Antwort erstellt oder versandt.",
        "Quellen und unterstützende Dateien",
    ),
    "es": (
        "Primera lectura de la comunicación",
        "Caso totalmente ficticio para revisión del despacho. La comunicación pide la declaración del ejercicio fiscal 2025 y los justificantes F24 correspondientes. No cuantifica una deuda ni da instrucciones de pago.",
        "Destinatario: Marco Prova. Remitente representado: Agenzia delle Entrate, Ufficio Esempio. Referencia: DEMO-NOTICE-01.",
        "Fechas y estado de los documentos",
        "La carta está fechada el 02/04/2026 e indica el 30/04/2026 para aportar documentos. Son fechas de la transcripción: deben comprobarse la naturaleza del acto, su recepción y el plazo aplicable con el documento completo y las pruebas disponibles.",
        "No se aportan prueba de recepción, copia de la declaración ni justificantes F24. Se trata de obtener documentos, no de efectuar un pago.",
        "En su mensaje del 06/04/2026, el cliente dice que encontró la comunicación el 3 de abril y recuperó la declaración, pero no los justificantes F24. Es su declaración, no una prueba de notificación. La declaración no está adjunta y el despacho no la ha recibido.",
        "Siguiente paso",
        "Obtener la comunicación completa y la prueba de recepción, además de la declaración y los justificantes solicitados. El despacho debe comprobar procedencia, naturaleza de la comunicación y fecha aplicable antes de decidir la respuesta. No se ha preparado ni enviado ninguna respuesta.",
        "Fuentes y archivos de apoyo",
    ),
}


def write_notice_review(
    output: Path, source_paths: list[Path], language: str, phase: str
) -> Path:
    """Save the bounded interpretation after the actual extraction has run."""
    words = COPY[language]
    text = (
        f"# {words[0]} — DEMO-NOTICE-01\n\n{words[1]}\n\n{words[2]}\n\n"
        f"## {words[3]}\n\n{words[4]}\n\n{words[6] if phase == 'practice' else words[5]}\n\n"
        f"## {words[7]}\n\n{words[8]}\n\n## {words[9]}\n\n"
    )
    text += "\n".join(f"- [{path.name}]({path})" for path in source_paths)
    text += "\n- [deadlines_and_amounts.csv](avviso/deadlines_and_amounts.csv)\n"
    path = output / "codex_run_review.md"
    path.write_text(text, encoding="utf-8")
    return path
