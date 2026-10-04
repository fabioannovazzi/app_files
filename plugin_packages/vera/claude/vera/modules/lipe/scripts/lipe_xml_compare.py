"""Compare exact IVP18 fields and Decimal amounts; do not infer filing validity.

The official schema supplies the mechanical shape. Matching fields do not
authenticate either document or establish the meaning of a changed tax flag.
"""

from __future__ import annotations

import hashlib
import html
from decimal import Decimal
from typing import Any

from lipe_core import ContractError
from lipe_xml import AMOUNTS, NS, load_official_schema, parse_xml
from lxml import etree

__all__ = ["read_ivp", "compare_ivp", "comparison_markdown"]


def _fields(element: Any) -> dict[str, str]:
    return {
        etree.QName(child).localname: child.text or ""
        for child in element
        if isinstance(child.tag, str)
    }


def read_ivp(raw: bytes) -> dict:
    """Read one unambiguous, schema-valid communication using direct children only."""
    root = parse_xml(raw)
    schema = load_official_schema()
    if not schema.validate(root):
        raise ContractError(
            "IVP18 XSD validation failed: " + str(schema.error_log)[:2000]
        )
    signatures = len(list(root.iter("{http://www.w3.org/2000/09/xmldsig#}Signature")))
    if (
        len(list(root.iter(f"{{{NS}}}Fornitura"))) != 1
        or len(list(root.iter(f"{{{NS}}}Comunicazione"))) != 1
        or signatures > 1
    ):
        raise ContractError("Ambiguous nested IVP18 communication or signature")
    communication = root.find(f"{{{NS}}}Comunicazione")
    modules = []
    periods = set()
    for index, node in enumerate(
        communication.findall(f"{{{NS}}}DatiContabili/{{{NS}}}Modulo"), 1
    ):
        fields = _fields(node)
        if ("Mese" in fields) == ("Trimestre" in fields):
            raise ContractError(
                "Each supplied module needs exactly one month or quarter"
            )
        kind = "Mese" if "Mese" in fields else "Trimestre"
        period = (kind, int(fields[kind]))
        if period in periods or int(fields["NumeroModulo"]) != index:
            raise ContractError("Duplicate periods or inconsistent module numbering")
        periods.add(period)
        amounts = {}
        for key, tag in AMOUNTS:
            value = Decimal(fields.get(tag, "0,00").replace(",", "."))
            amounts[key] = format(value if value else Decimal(0), ".2f")
        modules.append(
            {
                "period_kind": kind,
                "period": period[1],
                "fields": fields,
                "amounts": amounts,
            }
        )
    return {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "schema_validation": "PASS",
        "header": _fields(root.find(f"{{{NS}}}Intestazione")),
        "frontpage": _fields(communication.find(f"{{{NS}}}Frontespizio")),
        "communication_id": communication.get("identificativo"),
        "modules": modules,
        "signature_present": signatures == 1,
        "signature_authenticity": "NOT_TESTED",
        "filing_acceptance": "NOT_ESTABLISHED",
    }


def _differences(before: dict, after: dict, location: str) -> list[dict]:
    return [
        {
            "location": location,
            "field": key,
            "reference": before.get(key),
            "supplied": after.get(key),
        }
        for key in sorted(set(before) | set(after))
        if before.get(key) != after.get(key)
    ]


def compare_ivp(reference: bytes, supplied: bytes) -> dict:
    """Compare one supplied XML to one reference; neither is authenticated here."""
    expected, actual = read_ivp(reference), read_ivp(supplied)
    report: dict = {
        "schema_version": "lipe.xml-comparison.v1",
        "reference_sha256": expected["sha256"],
        "supplied_sha256": actual["sha256"],
        "bytes_equal": reference == supplied,
        "schema_validation": {"reference": "PASS", "supplied": "PASS"},
        "reference_authorization": "NOT_ESTABLISHED_BY_COMPARISON",
        "signature_authenticity": "NOT_TESTED",
        "filing_acceptance": "NOT_ESTABLISHED",
        "amounts_match": None,
        "amount_differences": [],
        "other_field_differences": [],
        "amount_representation_differences": [],
        "network_calls": False,
    }
    identities = ("CodiceFiscale", "PartitaIVA", "AnnoImposta")
    identity_differences = _differences(
        {key: expected["frontpage"][key] for key in identities},
        {key: actual["frontpage"][key] for key in identities},
        "Frontespizio",
    )
    if identity_differences:
        report.update(
            status="DIFFERENT_TAXPAYER_OR_YEAR",
            other_field_differences=identity_differences,
        )
        return report
    before = {
        (item["period_kind"], item["period"]): item for item in expected["modules"]
    }
    after = {(item["period_kind"], item["period"]): item for item in actual["modules"]}
    if set(before) != set(after):
        report.update(
            status="DIFFERENT_PERIODS",
            other_field_differences=[
                {
                    "location": "DatiContabili",
                    "field": "periods",
                    "reference": sorted(before),
                    "supplied": sorted(after),
                }
            ],
        )
        return report
    other = _differences(expected["header"], actual["header"], "Intestazione")
    other += _differences(expected["frontpage"], actual["frontpage"], "Frontespizio")
    other += _differences(
        {key: expected[key] for key in ("communication_id", "signature_present")},
        {key: actual[key] for key in ("communication_id", "signature_present")},
        "Fornitura",
    )
    amount_tags = {name for _, name in AMOUNTS}
    amounts, representations = [], []
    for period, original in before.items():
        changed = after[period]
        location = f"{period[0]} {period[1]}"
        amounts += _differences(original["amounts"], changed["amounts"], location)
        other += _differences(
            {
                key: value
                for key, value in original["fields"].items()
                if key not in amount_tags
            },
            {
                key: value
                for key, value in changed["fields"].items()
                if key not in amount_tags
            },
            location,
        )
        for key, tag in AMOUNTS:
            if original["amounts"][key] == changed["amounts"][key] and original[
                "fields"
            ].get(tag) != changed["fields"].get(tag):
                representations.append(
                    {
                        "location": location,
                        "field": tag,
                        "reference": original["fields"].get(tag),
                        "supplied": changed["fields"].get(tag),
                    }
                )
    report.update(
        status=(
            "AMOUNTS_DIFFER"
            if amounts
            else (
                "AMOUNTS_MATCH_REVIEW_OTHER_FIELDS"
                if other
                else (
                    "AMOUNTS_MATCH_REPRESENTATION_DIFFERS"
                    if representations
                    else "FIELDS_MATCH"
                )
            )
        ),
        amounts_match=not amounts,
        amount_differences=amounts,
        other_field_differences=other,
        amount_representation_differences=representations,
    )
    return report


def _text(value: object) -> str:
    if value is None:
        return "Assente"
    text = html.escape(str(value), quote=False).replace("\r", " ").replace("\n", " ↵ ")
    for character in "\\`*_{}[]()#+-.!|":
        text = text.replace(character, "\\" + character)
    return text


def comparison_markdown(report: dict) -> str:
    """Show every mechanical difference without deciding whether a change is acceptable."""
    statuses = {
        "BLOCKED": "Lettura bloccata: almeno un file non è confrontabile.",
        "DIFFERENT_TAXPAYER_OR_YEAR": "Contribuente o anno diversi: importi non confrontati.",
        "DIFFERENT_PERIODS": "Periodi diversi: importi non confrontati.",
        "AMOUNTS_DIFFER": "Gli importi VP differiscono.",
        "AMOUNTS_MATCH_REVIEW_OTHER_FIELDS": "Gli importi VP coincidono; altri campi sono diversi e richiedono revisione.",
        "AMOUNTS_MATCH_REPRESENTATION_DIFFERS": "Gli importi VP coincidono; la rappresentazione degli importi è diversa.",
        "FIELDS_MATCH": "I campi confrontati coincidono.",
    }
    lines = [
        "# LIPE — confronto XML",
        "",
        statuses[report["status"]],
        "",
        "Il confronto non autentica l'approvazione del riferimento, la firma dei documenti o l'accettazione dell'invio. L'associazione al fascicolo è scelta dall'operatore e va verificata.",
        "",
        f"Riferimento SHA-256: `{report['reference_sha256']}`",
        f"File fornito SHA-256: `{report['supplied_sha256']}`",
        "",
    ]
    if "source_names" in report:
        lines += [
            f"Riferimento: {_text(report['source_names']['reference'])}",
            f"File fornito: {_text(report['source_names']['supplied'])}",
            "",
        ]
    for heading, key in (
        ("Differenze negli importi", "amount_differences"),
        ("Altri campi da rivedere", "other_field_differences"),
        ("Differenze nella rappresentazione", "amount_representation_differences"),
    ):
        differences = report.get(key, [])
        if differences:
            lines += [
                f"## {heading}",
                "",
                "| Posizione | Campo | Riferimento | File fornito |",
                "|---|---|---|---|",
            ]
            lines.extend(
                "| "
                + " | ".join(
                    _text(item[field])
                    for field in ("location", "field", "reference", "supplied")
                )
                + " |"
                for item in differences
            )
            lines.append("")
    if report.get("diagnostics"):
        lines += [
            "## Motivo del blocco",
            "",
            *["- " + _text(item) for item in report["diagnostics"]],
            "",
        ]
    lines += [
        "Le cifre sono confrontate al centesimo per periodo, non sommando l'intera comunicazione. L'assenza di un elemento importo è confrontata numericamente con zero, ma viene registrata come differenza di rappresentazione. Questo non decide se lo zero esplicito sia ammesso dal software di controllo.",
        "",
        "Date d'impegno, rappresentanti, intermediari, firme dichiarate, metodi, flag e altri campi modificati restano visibili. La sola coincidenza degli importi non approva queste modifiche. Le firme XML, se presenti, non sono verificate; contenitori .p7m o ZIP non vengono aperti da questo passaggio.",
        "",
        "## Quali dati arrivano al modello",
        "",
        "Se l'host apre i file, il modello può leggere i frontespizi e tutti i dati contabili dei due XML, nomi dei file, identificativi e differenze. I byte originali restano conservati separatamente. Il confronto locale non usa rete o modelli; il report della sessione deve registrare le letture effettive.",
        "",
    ]
    return "\n".join(lines)
