"""Fixed, source-backed invoice interpretation for fictional regression cases.

This is test data, not a production extractor or a prepared lesson result.
Live teaching uses the native model and the user's actual revision approval.
"""

from __future__ import annotations

from typing import Any

__all__ = ["proposal"]


def proposal(source: dict[str, str], phase: str, language: str) -> dict[str, Any]:
    """Return the explicit fixture interpretation of the supplied data sheet."""
    practice = phase == "practice"
    header = {
        "DatiTrasmissione": {
            "IdTrasmittente": {"IdPaese": "IT", "IdCodice": "01234567897"},
            "ProgressivoInvio": "DID02" if practice else "DID01",
            "FormatoTrasmissione": "FPR12",
            "CodiceDestinatario": "0000000",
        },
        "CedentePrestatore": {
            "DatiAnagrafici": {
                "IdFiscaleIVA": {"IdPaese": "IT", "IdCodice": "01234567897"},
                "Anagrafica": {
                    "Denominazione": "Officina Arco Srl - SOLO ESERCITAZIONE"
                },
                "RegimeFiscale": "RF01",
            },
            "Sede": {
                "Indirizzo": "Via Esempio 1",
                "CAP": "00100",
                "Comune": "Roma",
                "Nazione": "IT",
            },
        },
        "CessionarioCommittente": {
            "DatiAnagrafici": {
                "IdFiscaleIVA": {"IdPaese": "IT", "IdCodice": "09876543217"},
                "Anagrafica": {
                    "Denominazione": "Studio Esempio Srl - SOLO ESERCITAZIONE"
                },
            },
            "Sede": {
                "Indirizzo": "Via Prova 2",
                "CAP": "20100",
                "Comune": "Milano",
                "Nazione": "IT",
            },
        },
    }
    body = {
        "DatiGenerali": {
            "DatiGeneraliDocumento": {
                "TipoDocumento": "TD01",
                "Divisa": "EUR",
                "Data": "2026-09-15" if practice else "2026-09-14",
                "Numero": "DID-002" if practice else "DID-001",
                "ImportoTotaleDocumento": "244.00" if practice else "122.00",
            }
        },
        "DatiBeniServizi": {
            "DettaglioLinee": [
                {
                    "NumeroLinea": "1",
                    "Descrizione": (
                        "Manutenzione biciclette - prestazione fittizia"
                        if practice
                        else "Manutenzione bicicletta - prestazione fittizia"
                    ),
                    "Quantita": "2.00" if practice else "1.00",
                    "PrezzoUnitario": "100.00",
                    "PrezzoTotale": "200.00" if practice else "100.00",
                    "AliquotaIVA": "22.00",
                }
            ],
            "DatiRiepilogo": [
                {
                    "AliquotaIVA": "22.00",
                    "ImponibileImporto": "200.00" if practice else "100.00",
                    "Imposta": "44.00" if practice else "22.00",
                }
            ],
        },
    }
    invoice = {
        "FatturaElettronicaHeader": header,
        "FatturaElettronicaBody": [body],
    }
    # Use native field enumeration; the meanings below are authored fixture data.
    from invoice_schema import flatten_fields

    evidence_basis = {
        "it": "Valore esplicito nella scheda fittizia dell’esercizio",
        "en": "Explicit value in the fictional teaching data sheet",
        "fr": "Valeur explicite dans la fiche fictive de l’exercice",
        "de": "Ausdrücklicher Wert im fiktiven Übungsdatenblatt",
        "es": "Valor explícito en la ficha ficticia del ejercicio",
    }[language]
    evidence = {}
    for pointer in flatten_fields(invoice):
        section = "DATI DELLA BOZZA"
        if "/CedentePrestatore/" in pointer:
            section = "FORNITORE FITTIZIO"
        elif "/CessionarioCommittente/" in pointer:
            section = "CLIENTE FITTIZIO"
        elif "/DatiTrasmissione/" in pointer:
            section = "DATI DI PREPARAZIONE DEL FILE"
        evidence[pointer] = {
            "kind": "source",
            "basis": evidence_basis,
            "references": [{"source_id": source["id"], "locator": section}],
        }
    decisions = {
        "source_grouping": "One complete text data sheet describes one fictional invoice.",
        "source_completeness": "All ordinary fields used by this fixture are stated in the selected sheet; no PDF or native-vision extraction is claimed.",
        "parties": "The separately labelled fictional supplier and customer retain their stated roles and identifiers. No real identity has been verified.",
        "document_type": "The sheet explicitly specifies domestic ordinary TD01 for this fictional case.",
        "tax_treatment": "RF01, EUR and 22 percent VAT are explicit exercise assumptions, not a professional determination or a rule inferred from the service.",
        "numbering_and_date": "Use the number and date printed in this sheet; the model does not allocate an invoice sequence.",
        "routing": "Use the sheet's stated FPR12, technical progress number and recipient code; do not transmit.",
        "duplicate_and_issue_status": "The fictional scenario explicitly says new draft with no earlier issue or export. No real SdI status has been queried.",
    }
    translated_decisions = {
        "it": [
            "Una scheda completa descrive una sola fattura fittizia.",
            "I campi utilizzati sono tutti nella scheda; non è stata eseguita un’estrazione da PDF o fotografie.",
            "Fornitore e cliente mantengono ruoli e identificativi indicati. Nessuna identità reale è stata verificata.",
            "La scheda indica espressamente una fattura italiana ordinaria TD01.",
            "RF01, EUR e IVA al 22% sono ipotesi esplicite dell’esercizio, da rivedere; non sono un giudizio professionale.",
            "Numero e data provengono dalla scheda. Vera non assegna una numerazione.",
            "Formato FPR12, progressivo e codice destinatario provengono dalla scheda. Nessuna trasmissione.",
            "Il caso fittizio dichiara una nuova bozza senza emissioni o esportazioni precedenti. Non è stato interrogato SdI.",
        ],
        "fr": [
            "Une fiche complète décrit une seule facture fictive.",
            "Tous les champs utilisés figurent dans la fiche ; aucune extraction de PDF ou photo n’est revendiquée.",
            "Fournisseur et client conservent leurs rôles et identifiants indiqués. Aucune identité réelle n’a été vérifiée.",
            "La fiche indique explicitement une facture italienne ordinaire TD01.",
            "RF01, EUR et TVA à 22 % sont des hypothèses explicites de l’exercice à revoir, pas un jugement professionnel.",
            "Numéro et date proviennent de la fiche. Vera n’attribue pas de numérotation.",
            "FPR12, numéro technique et code destinataire proviennent de la fiche. Aucune transmission.",
            "Le cas fictif déclare un nouveau brouillon sans émission ni export antérieur. SdI n’a pas été interrogé.",
        ],
        "de": [
            "Ein vollständiges Datenblatt beschreibt genau eine fiktive Rechnung.",
            "Alle verwendeten Felder stehen im Blatt; eine PDF- oder Fotoauswertung wird nicht behauptet.",
            "Lieferant und Kunde behalten die angegebenen Rollen und Kennungen. Keine echte Identität wurde geprüft.",
            "Das Blatt nennt ausdrücklich eine gewöhnliche italienische TD01-Rechnung.",
            "RF01, EUR und 22 Prozent Umsatzsteuer sind ausdrückliche Übungsannahmen zur Prüfung, kein fachliches Urteil.",
            "Nummer und Datum stammen aus dem Blatt. Vera vergibt keine Rechnungsnummer.",
            "FPR12, technische Laufnummer und Empfängercode stammen aus dem Blatt. Keine Übermittlung.",
            "Der fiktive Fall nennt einen neuen Entwurf ohne frühere Ausstellung oder Export. SdI wurde nicht abgefragt.",
        ],
        "es": [
            "Una ficha completa describe una sola factura ficticia.",
            "Todos los campos utilizados están en la ficha; no se afirma haber extraído PDF ni fotografías.",
            "Proveedor y cliente conservan funciones e identificadores indicados. No se ha verificado ninguna identidad real.",
            "La ficha indica expresamente una factura italiana ordinaria TD01.",
            "RF01, EUR e IVA del 22 % son hipótesis explícitas del ejercicio para revisar, no un juicio profesional.",
            "Número y fecha proceden de la ficha. Vera no asigna una numeración.",
            "FPR12, número técnico y código destinatario proceden de la ficha. No se transmite nada.",
            "El caso ficticio declara un nuevo borrador sin emisión ni exportación previa. No se ha consultado SdI.",
        ],
    }
    if language != "en":
        decisions = dict(zip(decisions, translated_decisions[language], strict=True))
    return {
        "schema_version": 2,
        "draft_id": f"teaching-{phase}",
        "route": "domestic",
        "transmission_mode": "supplier_direct",
        "invoice": invoice,
        "sources": [source],
        "field_evidence": evidence,
        "decisions": {
            key: {
                "assessment": value,
                "references": [
                    {"source_id": source["id"], "locator": "Complete fictional sheet"}
                ],
            }
            for key, value in decisions.items()
        },
        "questions": [],
    }
