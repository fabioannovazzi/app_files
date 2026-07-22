"""Locale dictionaries for generic audit reconciliation.

The reconciliation engine uses stable internal codes. Locale packs only provide
the words needed to recognize source-document vocabulary and render outputs.
They must not introduce customer-specific logic.
"""

from __future__ import annotations

import re
from typing import Any

SUPPORTED_LANGUAGES = ("it", "en", "fr", "de", "es")
DEFAULT_LANGUAGE = "it"


BASE_OUTPUT_LABELS = {
    "metadata_field": "Field",
    "metadata_value": "Value",
    "conclusion": "Conclusion",
    "summary": "Summary",
    "assumptions": "Assumptions",
    "next_steps": "Next Steps",
    "fallback_narrative": "The detailed row-level reconciliation is contained in the Excel workpaper.",
    "excel_authority": "The Excel workbook is the authoritative row-level audit workpaper.",
}


LANGUAGE_PACKS: dict[str, dict[str, Any]] = {
    "it": {
        "output_labels": {
            "metadata_field": "Campo",
            "metadata_value": "Valore",
            "conclusion": "Conclusioni",
            "summary": "Sintesi",
            "assumptions": "Assunzioni",
            "next_steps": "Prossimi passi",
            "fallback_narrative": "Il dettaglio riga per riga della riconciliazione è contenuto nel file Excel.",
            "excel_authority": "Il file Excel è il workpaper auditabile di dettaglio riga per riga.",
        },
        "role_keywords": {
            "bank_statement": ("estratto conto", "conto corrente", "banca"),
            "factoring_statement": (
                "factoring",
                "factor",
                "anticipo",
                "anticipi",
                "cessione",
                "pro soluto",
            ),
            "payment_order": ("distinta", "ordine pagamento"),
            "journal": ("giornale", "libro giornale"),
            "ledger": ("mastrino", "partitario", "interrogazione conto", "sottoconto"),
            "open_items": (
                "partite aperte",
                "all.a",
                "scheda clienti",
                "scheda cliente",
                "scheda fornitori",
                "scheda fornitore",
            ),
        },
        "side_keywords": {
            "customer": ("cliente", "clienti"),
            "supplier": ("fornitore", "fornitori"),
        },
        "evidence_keywords": {
            "invoice": ("fattura", "fatture"),
            "closure": (
                "incassata",
                "incassato",
                "pagata",
                "pagato",
                "chiusa",
                "chiuso",
                "chius",
            ),
            "compensation": ("compens", "giroconto"),
            "netting": ("netting",),
            "factoring": (
                "factoring",
                "factor",
                "pro soluto",
                "pro-soluto",
                "cession",
                "cessione cred",
                "cess. cred",
                "anticipo",
                "anticip",
            ),
            "bank": (
                "bank",
                "banca",
                "estratto conto",
                "bonifico",
                "sepa",
                "wire",
                "payment",
                "pagamento",
                "incasso",
            ),
            "batch": ("distinta",),
        },
        "payment_order_terms": {
            "header": ("distinta",),
            "date_prefix": ("del",),
            "total": ("totale distinta",),
            "value_date": ("valuta",),
            "invoice": ("fattura",),
        },
        "next_steps": {
            "probable_payment": "Verificare le righe con pagamento probabile: esiste un movimento bancario probabile, ma va confermata l'allocazione riga/documento prima di trattarlo come chiusura definitiva.",
            "needs_evidence": "Acquisire le evidenze indicate nelle righe che richiedono documentazione aggiuntiva.",
            "unresolved": "Mappare manualmente le righe non risolte ai documenti sorgente o richiedere dettaglio contabile aggiuntivo.",
            "complete": "Conservare Excel e fonti come workpaper auditabile.",
        },
        "missing_evidence": {
            "probable_bank_payment_candidate": "Esiste un pagamento bancario probabile collegato alla riga; verificare distinta, descrizione bancaria o dettaglio allocazione prima di trattarlo come chiusura definitiva.",
            "payment_order_only": "La distinta è solo evidenza ponte; acquisire estratto conto, contabile bancaria o estratto del factor/operatore collegato al lotto.",
            "payment_order_amount_mismatch": "La distinta esiste, ma l'importo allocato non coincide con la riga All.A; acquisire dettaglio allocazione o conferma di saldo parziale.",
            "factoring_bridge_only": "La scrittura factor/operatore è solo evidenza ponte; acquisire estratto conto bancario o estratto operatore collegato a fattura o lotto.",
            "unallocated_external_bank_requires_allocation": "Esiste un movimento bancario, ma non è allocato alla specifica fattura/partita; acquisire dettaglio allocazione, avviso di pagamento o breakdown del lotto.",
            "internal_closure_without_external": "Esiste una chiusura interna; acquisire evidenza esterna bancaria, factor/operatore o compensazione documentata collegata alla riga.",
            "internal_booking_open_support": "La posizione aperta è supportata da registrazione/saldo interno; per superarla serve evidenza esterna specifica di chiusura.",
            "grouped_open_amount_internal_booking_support": "La posizione aperta è supportata da una registrazione interna aggregata che coincide con la somma delle righe All.A dello stesso documento; per superarla serve evidenza esterna specifica di chiusura.",
            "internal_accounting_only": "Esiste una scrittura interna di mastro/giornale; acquisire evidenza esterna bancaria, factor/operatore o compensazione documentata.",
            "compensation_needs_external_support": "La compensazione è indicata, ma la regola configurata richiede supporto bancario/esterno.",
            "default": "Acquisire evidenza specifica per documento: movimento bancario, estratto factor/operatore, compensazione documentata o dettaglio mastro.",
        },
    },
    "en": {
        "output_labels": BASE_OUTPUT_LABELS,
        "role_keywords": {
            "bank_statement": ("bank statement", "statement", "bank account", "bank"),
            "factoring_statement": (
                "factoring",
                "factor",
                "advance",
                "assignment of receivables",
                "without recourse",
            ),
            "payment_order": ("payment order", "payment batch", "remittance order"),
            "journal": ("journal", "general journal"),
            "ledger": ("ledger", "account ledger", "subledger", "account card"),
            "open_items": (
                "open items",
                "open-item",
                "customer statement",
                "supplier statement",
                "customer ledger",
                "supplier ledger",
            ),
        },
        "side_keywords": {
            "customer": ("customer", "client", "receivable"),
            "supplier": ("supplier", "vendor", "payable"),
        },
        "evidence_keywords": {
            "invoice": ("invoice", "invoices"),
            "closure": ("paid", "collected", "settled", "closed", "cleared"),
            "compensation": ("compensation", "set-off", "setoff"),
            "netting": ("netting",),
            "factoring": (
                "factoring",
                "factor",
                "without recourse",
                "assignment",
                "receivable assignment",
                "advance",
            ),
            "bank": (
                "bank",
                "bank statement",
                "wire",
                "sepa",
                "transfer",
                "payment",
                "receipt",
                "collection",
            ),
            "batch": ("batch", "payment batch", "remittance"),
        },
        "payment_order_terms": {
            "header": ("payment order", "payment batch", "remittance order"),
            "date_prefix": ("date", "dated"),
            "total": ("total payment order", "total batch", "batch total"),
            "value_date": ("value date",),
            "invoice": ("invoice",),
        },
        "next_steps": {
            "probable_payment": "Review rows classified as probable_payment: a likely bank movement exists, but row/document allocation must be confirmed before treating it as definitively closed.",
            "needs_evidence": "Obtain the evidence requested on rows classified as needs_evidence.",
            "unresolved": "Manually map unresolved rows to source documents or request additional ledger detail.",
            "complete": "Retain the Excel workbook and source documents as the audit workpaper.",
        },
        "missing_evidence": {
            "probable_bank_payment_candidate": "A probable bank payment is linked to this row; verify the payment batch, bank description, or allocation detail before treating it as definitively closed.",
            "payment_order_only": "Payment order is bridge evidence only; obtain bank statement, bank receipt, or factoring/operator statement tied to the batch.",
            "payment_order_amount_mismatch": "Payment order exists, but its allocated amount does not match the open-item row; obtain allocation detail or confirm partial settlement.",
            "factoring_bridge_only": "Factoring/operator entry is bridge evidence only; obtain bank statement or operator statement tied to the invoice or batch.",
            "unallocated_external_bank_requires_allocation": "A bank movement exists but is not allocated to the specific invoice/open item; obtain allocation detail, remittance advice, or batch breakdown.",
            "internal_closure_without_external": "Internal closure exists; obtain external bank, factoring/operator, or documented compensation evidence tied to the row.",
            "internal_booking_open_support": "Open-item position is supported by internal booking/open balance; to overturn it, obtain row-specific external closing evidence.",
            "grouped_open_amount_internal_booking_support": "Open-item position is supported by an aggregate internal booking that matches the sum of same-document open-item rows; to overturn it, obtain row-specific external closing evidence.",
            "internal_accounting_only": "Internal ledger/journal entry exists; obtain external bank, factoring/operator, or documented compensation evidence.",
            "compensation_needs_external_support": "Compensation/set-off is indicated but the configured rule requires bank/external support.",
            "default": "Obtain document-specific evidence: bank movement, factoring/operator statement, documented compensation, or source ledger detail.",
        },
    },
    "fr": {
        "output_labels": {
            "metadata_field": "Champ",
            "metadata_value": "Valeur",
            "conclusion": "Conclusions",
            "summary": "Synthèse",
            "assumptions": "Hypothèses",
            "next_steps": "Prochaines étapes",
            "fallback_narrative": "Le détail ligne par ligne de la réconciliation est contenu dans le fichier Excel.",
            "excel_authority": "Le classeur Excel constitue le workpaper audit fiable au niveau ligne.",
        },
        "role_keywords": {
            "bank_statement": (
                "relevé bancaire",
                "releve bancaire",
                "extrait de compte",
                "banque",
            ),
            "factoring_statement": (
                "affacturage",
                "factor",
                "avance",
                "cession de créance",
                "cession de creance",
                "sans recours",
            ),
            "payment_order": ("ordre de paiement", "lot de paiement", "remise"),
            "journal": ("journal", "livre journal"),
            "ledger": ("grand livre", "auxiliaire", "compte auxiliaire", "ledger"),
            "open_items": (
                "postes ouverts",
                "parties ouvertes",
                "compte client",
                "compte fournisseur",
            ),
        },
        "side_keywords": {
            "customer": ("client", "clients", "créance", "creance"),
            "supplier": ("fournisseur", "fournisseurs", "dette"),
        },
        "evidence_keywords": {
            "invoice": ("facture", "factures"),
            "closure": (
                "payée",
                "payee",
                "payé",
                "paye",
                "encaissée",
                "encaissee",
                "réglée",
                "reglee",
                "soldée",
                "soldee",
            ),
            "compensation": ("compensation",),
            "netting": ("netting",),
            "factoring": (
                "affacturage",
                "factor",
                "sans recours",
                "cession",
                "cession de créance",
                "cession de creance",
                "avance",
            ),
            "bank": (
                "banque",
                "relevé bancaire",
                "releve bancaire",
                "extrait de compte",
                "virement",
                "sepa",
                "paiement",
                "encaissement",
            ),
            "batch": ("lot", "remise"),
        },
        "payment_order_terms": {
            "header": ("ordre de paiement", "lot de paiement", "remise"),
            "date_prefix": ("du", "date"),
            "total": ("total ordre", "total remise", "total lot"),
            "value_date": ("date de valeur", "valeur"),
            "invoice": ("facture",),
        },
        "next_steps": {
            "needs_evidence": "Obtenir les éléments probants indiqués sur les lignes classées needs_evidence.",
            "unresolved": "Rattacher manuellement les lignes unresolved aux documents source ou demander un détail comptable complémentaire.",
            "complete": "Conserver le classeur Excel et les sources comme workpaper audit.",
        },
        "missing_evidence": {},
    },
    "de": {
        "output_labels": {
            "metadata_field": "Feld",
            "metadata_value": "Wert",
            "conclusion": "Ergebnisse",
            "summary": "Zusammenfassung",
            "assumptions": "Annahmen",
            "next_steps": "Nächste Schritte",
            "fallback_narrative": "Die zeilenweise Abstimmung ist in der Excel-Arbeitsmappe enthalten.",
            "excel_authority": "Die Excel-Arbeitsmappe ist das maßgebliche zeilenweise Audit-Workpaper.",
        },
        "role_keywords": {
            "bank_statement": ("kontoauszug", "bankauszug", "bankkonto", "bank"),
            "factoring_statement": (
                "factoring",
                "factor",
                "vorschuss",
                "abtretung",
                "forderungsabtretung",
                "ohne regress",
            ),
            "payment_order": (
                "zahlungsauftrag",
                "zahlungslauf",
                "sammelzahlung",
                "remittance",
            ),
            "journal": ("journal", "hauptjournal", "buchungsjournal"),
            "ledger": (
                "hauptbuch",
                "konto",
                "kontoblatt",
                "debitorenkonto",
                "kreditorenkonto",
                "ledger",
            ),
            "open_items": (
                "offene posten",
                "offener posten",
                "op-liste",
                "debitoren",
                "kreditoren",
            ),
        },
        "side_keywords": {
            "customer": ("kunde", "kunden", "debitor", "debitoren", "forderung"),
            "supplier": (
                "lieferant",
                "lieferanten",
                "kreditor",
                "kreditoren",
                "verbindlichkeit",
            ),
        },
        "evidence_keywords": {
            "invoice": ("rechnung", "rechnungen"),
            "closure": (
                "bezahlt",
                "gezahlt",
                "beglichen",
                "ausgeglichen",
                "geschlossen",
                "eingegangen",
                "vereinnahmt",
            ),
            "compensation": ("kompensation", "verrechnung", "aufrechnung"),
            "netting": ("netting",),
            "factoring": (
                "factoring",
                "factor",
                "ohne regress",
                "abtretung",
                "forderungsabtretung",
                "vorschuss",
            ),
            "bank": (
                "bank",
                "kontoauszug",
                "bankauszug",
                "überweisung",
                "ueberweisung",
                "sepa",
                "zahlung",
                "eingang",
                "einzug",
            ),
            "batch": ("zahlungslauf", "sammelzahlung", "batch"),
        },
        "payment_order_terms": {
            "header": ("zahlungsauftrag", "zahlungslauf", "sammelzahlung"),
            "date_prefix": ("vom", "datum"),
            "total": ("summe zahlungsauftrag", "summe zahlungslauf", "gesamtbetrag"),
            "value_date": ("valuta", "wertstellung"),
            "invoice": ("rechnung",),
        },
        "next_steps": {
            "needs_evidence": "Die in needs_evidence klassifizierten Zeilen mit den angeforderten Nachweisen belegen.",
            "unresolved": "Unresolved-Zeilen manuell den Quelldokumenten zuordnen oder zusätzliche Buchhaltungsdetails anfordern.",
            "complete": "Excel-Arbeitsmappe und Quelldokumente als Audit-Workpaper aufbewahren.",
        },
        "missing_evidence": {
            "payment_order_only": "Der Zahlungsauftrag ist nur ein Brückennachweis; Bankauszug, Bankbeleg oder Factor-/Operator-Auszug zum Zahlungslauf beschaffen.",
            "payment_order_amount_mismatch": "Der Zahlungsauftrag liegt vor, aber der zugeordnete Betrag stimmt nicht mit der offenen Position überein; Zuordnungsdetail oder Teilzahlung bestätigen.",
            "factoring_bridge_only": "Die Factor-/Operator-Buchung ist nur ein Brückennachweis; Bankauszug oder Operator-Auszug zur Rechnung oder zum Zahlungslauf beschaffen.",
            "unallocated_external_bank_requires_allocation": "Eine Bankbewegung liegt vor, ist aber nicht der konkreten Rechnung/offenen Position zugeordnet; Zuordnungsdetail, Zahlungsavis oder Aufschlüsselung des Zahlungslaufs beschaffen.",
            "internal_closure_without_external": "Eine interne Ausgleichsbuchung liegt vor; externen Bank-, Factor-/Operator- oder dokumentierten Verrechnungsnachweis zur Zeile beschaffen.",
            "internal_booking_open_support": "Die offene Position wird durch interne Buchung/offenen Saldo gestützt; zur Widerlegung ist zeilenspezifischer externer Ausgleichsnachweis erforderlich.",
            "grouped_open_amount_internal_booking_support": "Die offene Position wird durch eine aggregierte interne Buchung gestützt, die der Summe der offenen Positionen desselben Dokuments entspricht; zur Widerlegung ist zeilenspezifischer externer Ausgleichsnachweis erforderlich.",
            "internal_accounting_only": "Es liegt nur eine interne Hauptbuch-/Journalbuchung vor; externen Bank-, Factor-/Operator- oder dokumentierten Verrechnungsnachweis beschaffen.",
            "compensation_needs_external_support": "Eine Verrechnung ist erkennbar, aber die konfigurierte Regel verlangt Bank-/externen Nachweis.",
            "default": "Dokumentspezifischen Nachweis beschaffen: Bankbewegung, Factor-/Operator-Auszug, dokumentierte Verrechnung oder Quelldetail aus dem Hauptbuch.",
        },
    },
    "es": {
        "output_labels": {
            "metadata_field": "Campo",
            "metadata_value": "Valor",
            "conclusion": "Conclusiones",
            "summary": "Resumen",
            "assumptions": "Supuestos",
            "next_steps": "Próximos pasos",
            "fallback_narrative": "El detalle línea por línea de la conciliación se encuentra en el archivo Excel.",
            "excel_authority": "El libro Excel es el papel de trabajo de auditoría de referencia a nivel de línea.",
        },
        "role_keywords": {
            "bank_statement": (
                "extracto bancario",
                "estado de cuenta",
                "cuenta bancaria",
                "banco",
            ),
            "factoring_statement": (
                "factoring",
                "factor",
                "anticipo",
                "cesión de créditos",
                "cesion de creditos",
                "sin recurso",
            ),
            "payment_order": (
                "orden de pago",
                "lote de pagos",
                "remesa de pagos",
            ),
            "journal": ("diario", "libro diario"),
            "ledger": (
                "libro mayor",
                "mayor contable",
                "auxiliar",
                "ficha de cuenta",
            ),
            "open_items": (
                "partidas abiertas",
                "partida abierta",
                "estado de cliente",
                "estado de proveedor",
                "mayor de clientes",
                "mayor de proveedores",
            ),
        },
        "side_keywords": {
            "customer": ("cliente", "clientes", "cuenta por cobrar"),
            "supplier": ("proveedor", "proveedores", "cuenta por pagar"),
        },
        "evidence_keywords": {
            "invoice": ("factura", "facturas"),
            "closure": (
                "pagada",
                "pagado",
                "cobrada",
                "cobrado",
                "liquidada",
                "liquidado",
                "cerrada",
                "cerrado",
                "compensada",
                "compensado",
            ),
            "compensation": ("compensación", "compensacion"),
            "netting": ("netting", "compensación de saldos"),
            "factoring": (
                "factoring",
                "factor",
                "sin recurso",
                "cesión",
                "cesion",
                "cesión de créditos",
                "cesion de creditos",
                "anticipo",
            ),
            "bank": (
                "banco",
                "extracto bancario",
                "estado de cuenta",
                "transferencia",
                "sepa",
                "pago",
                "cobro",
                "ingreso",
            ),
            "batch": ("lote", "remesa", "lote de pagos"),
        },
        "payment_order_terms": {
            "header": ("orden de pago", "lote de pagos", "remesa de pagos"),
            "date_prefix": ("del", "fecha"),
            "total": ("total orden de pago", "total remesa", "total lote"),
            "value_date": ("fecha valor", "valor"),
            "invoice": ("factura",),
        },
        "next_steps": {
            "probable_payment": "Revisar las líneas clasificadas como probable_payment: existe un movimiento bancario probable, pero debe confirmarse la asignación a la línea o documento antes de tratarlo como cierre definitivo.",
            "needs_evidence": "Obtener las evidencias indicadas en las líneas clasificadas como needs_evidence.",
            "unresolved": "Asignar manualmente las líneas unresolved a los documentos fuente o solicitar detalle contable adicional.",
            "complete": "Conservar el libro Excel y los documentos fuente como papel de trabajo de auditoría.",
        },
        "missing_evidence": {
            "probable_bank_payment_candidate": "Hay un pago bancario probable vinculado a esta línea; verifique el lote de pagos, la descripción bancaria o el detalle de asignación antes de tratarlo como cierre definitivo.",
            "payment_order_only": "La orden de pago solo constituye evidencia puente; obtenga el extracto bancario, el justificante bancario o el extracto del factor u operador vinculado al lote.",
            "payment_order_amount_mismatch": "Existe una orden de pago, pero el importe asignado no coincide con la partida abierta; obtenga el detalle de asignación o confirme la liquidación parcial.",
            "factoring_bridge_only": "El asiento del factor u operador solo constituye evidencia puente; obtenga el extracto bancario o del operador vinculado a la factura o al lote.",
            "unallocated_external_bank_requires_allocation": "Existe un movimiento bancario, pero no está asignado a la factura o partida abierta concreta; obtenga el detalle de asignación, el aviso de pago o el desglose del lote.",
            "internal_closure_without_external": "Existe un cierre interno; obtenga evidencia externa bancaria, del factor u operador, o de una compensación documentada vinculada a la línea.",
            "internal_booking_open_support": "La posición abierta está respaldada por un asiento o saldo interno; para rebatirla se necesita evidencia externa de cierre específica de la línea.",
            "grouped_open_amount_internal_booking_support": "La posición abierta está respaldada por un asiento interno agregado que coincide con la suma de las partidas abiertas del mismo documento; para rebatirla se necesita evidencia externa de cierre específica de la línea.",
            "internal_accounting_only": "Solo existe un asiento interno de mayor o diario; obtenga evidencia externa bancaria, del factor u operador, o de una compensación documentada.",
            "compensation_needs_external_support": "Se indica una compensación, pero la regla configurada exige soporte bancario o externo.",
            "default": "Obtenga evidencia específica del documento: movimiento bancario, extracto del factor u operador, compensación documentada o detalle del libro mayor fuente.",
        },
    },
}


def normalize_language(language: object | None, default: str = DEFAULT_LANGUAGE) -> str:
    text = str(language or default).strip().lower().replace("_", "-")
    code = text.split("-", 1)[0]
    return code if code in SUPPORTED_LANGUAGES else default


def language_candidates(language: object | None = None) -> tuple[str, ...]:
    text = str(language or "").strip().lower().replace("_", "-")
    if not text or text == "auto":
        return SUPPORTED_LANGUAGES
    return (normalize_language(text),)


def configured_language(
    assumptions: dict[str, Any] | None = None, *, purpose: str = "document"
) -> str:
    active = assumptions or {}
    if purpose == "report":
        return normalize_language(
            active.get("report_language") or active.get("language") or DEFAULT_LANGUAGE
        )
    doc_language = active.get("document_language")
    if doc_language and str(doc_language).lower() != "auto":
        return normalize_language(doc_language)
    return normalize_language(
        active.get("report_language") or active.get("language") or DEFAULT_LANGUAGE
    )


def language_pack(language: object | None = None) -> dict[str, Any]:
    code = normalize_language(language)
    pack = LANGUAGE_PACKS[code]
    if code in {"fr"}:
        merged = dict(pack)
        missing = dict(LANGUAGE_PACKS["en"]["missing_evidence"])
        missing.update(pack.get("missing_evidence") or {})
        merged["missing_evidence"] = missing
        return merged
    return pack


def output_labels(language: object | None = None) -> dict[str, str]:
    labels = dict(BASE_OUTPUT_LABELS)
    labels.update(language_pack(language).get("output_labels") or {})
    return labels


def missing_evidence_messages(language: object | None = None) -> dict[str, str]:
    return dict(
        language_pack(language).get("missing_evidence")
        or LANGUAGE_PACKS["en"]["missing_evidence"]
    )


def keyword_tuple(
    language: object | None,
    section: str,
    key: str,
    extra: list[str] | tuple[str, ...] | None = None,
) -> tuple[str, ...]:
    pack = language_pack(language)
    values = tuple(
        str(value).lower() for value in (pack.get(section, {}).get(key) or ())
    )
    if extra:
        values += tuple(str(value).lower() for value in extra if str(value).strip())
    return values


def any_keyword_in(text: object, keywords: list[str] | tuple[str, ...]) -> bool:
    value = re.sub(r"[_/-]+", " ", str(text or "").lower())
    return any(
        (normalized := re.sub(r"[_/-]+", " ", str(keyword).lower()).strip())
        and normalized in value
        for keyword in keywords
    )
