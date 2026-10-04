"""Preserve and inspect a supplied LIPE receipt without asserting its authenticity.

Fixed parsing is justified by the official XML contract and exact byte/name
comparison. Neither a declared ES01 nor a matching filename proves a filing.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import logging
from pathlib import Path

from lipe_core import ROOT, ContractError, digest, engine_hash, read_json, validate
from lipe_xml import load_official_schema, parse_xml

__all__ = ["inspect_receipt", "preserve_receipt", "main"]

RECEIPT_NS = "http://ivaservizi.agenziaentrate.gov.it/docs/xsd/file/v2.0"
SIGNATURE_NS = "http://www.w3.org/2000/09/xmldsig#"
OUTCOMES = {
    "ES01": "File validato",
    "ES02": "File validato con segnalazione",
    "ES03": "File scartato",
}
MAX_INPUT_BYTES = 16 * 1024 * 1024


def inspect_receipt(raw: bytes) -> dict:
    """Read only direct schema-valid receipt fields; never verify an XML signature."""
    schema = load_official_schema("RECEIPT")
    report: dict = {
        "inspection_status": "BLOCKED",
        "schema_validation": "NOT_PASSED",
        "declared": None,
        "diagnostics": [],
        "signature": {
            "schema_presence": "NOT_ESTABLISHED",
            "xades_profile": "NOT_TESTED",
            "cryptographic_integrity": "NOT_TESTED",
            "signer_trust_and_revocation": "NOT_TESTED",
        },
        "filing_acceptance": "NOT_ESTABLISHED",
        "network_calls": False,
    }
    try:
        root = parse_xml(raw)
    except ContractError as exc:
        report["diagnostics"].append(str(exc))
        return report
    if not schema.validate(root):
        report["diagnostics"] = [
            str(item)[:1000] for item in list(schema.error_log)[:20]
        ]
        return report
    report["schema_validation"] = "PASS"
    # The signature schema permits arbitrary Object contents. Do not accept an
    # additional nested receipt/signature as an alternative interpretation.
    if (
        len(list(root.iter(f"{{{RECEIPT_NS}}}EsitoFile"))) != 1
        or len(list(root.iter(f"{{{SIGNATURE_NS}}}Signature"))) != 1
    ):
        report["diagnostics"].append("Ambiguous nested receipt or signature")
        return report
    if root.findtext("TipoFile") != "LI":
        report["diagnostics"].append("This is not a TipoFile LI receipt")
        return report
    report["signature"]["schema_presence"] = "PASS_STRUCTURE_ONLY"
    report["inspection_status"] = "STRUCTURALLY_VALID_UNAUTHENTICATED"
    declared = {
        name: root.findtext(name)
        for name in (
            "TipoFile",
            "IDFile",
            "NomeFile",
            "DataOraRicezione",
            "Esito",
            "MessageID",
            "PECMessageID",
            "Note",
        )
    }
    archive = root.find("RifArchivio")
    declared["RifArchivio"] = (
        None
        if archive is None
        else {name: archive.findtext(name) for name in ("IDArchivio", "NomeArchivio")}
    )
    declared["ListaErrori"] = [
        {name: error.findtext(name) for name in ("Codice", "Descrizione")}
        for error in root.findall("ListaErrori/Errore")
    ]
    declared["EsitoDescription"] = OUTCOMES[declared["Esito"]]
    report["declared"] = declared
    return report


def _read(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ContractError("Select a regular, non-symlink receipt or submitted file")
    with path.open("rb") as handle:
        raw = handle.read(MAX_INPUT_BYTES + 1)
    if not raw or len(raw) > MAX_INPUT_BYTES:
        raise ContractError("Supplied evidence is empty or exceeds the 16 MiB limit")
    return raw


def _identity(path: Path, raw: bytes, saved_as: str) -> dict:
    return {
        "original_name": path.name,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "saved_as": saved_as,
    }


def _text(value: object) -> str:
    text = html.escape(str(value), quote=False).replace("\r", " ").replace("\n", " ↵ ")
    for char in "\\`*_{}[]()#+-.!|":
        text = text.replace(char, "\\" + char)
    return text


def _markdown(report: dict) -> str:
    lines = [
        "# LIPE — esame della ricevuta fornita",
        "",
        "**Autenticità della ricevuta e accettazione dell'invio non accertate.**",
        "",
        "Il controllo legge la struttura XML e i valori dichiarati. Non verifica la firma XAdES, la fiducia nel firmatario, la revoca o lo stato presso l'Agenzia delle Entrate. Non effettua invii o richieste di rete.",
        "",
        f"Origine del fascicolo: {_text(report['scope']['data_origin'])}. Il collegamento a cliente e periodo è quello scelto dall'operatore: la ricevuta non contiene questi dati.",
        "",
        f"File originale: {_text(report['receipt']['original_name'])}",
        f"SHA-256: `{report['receipt']['sha256']}`",
        "",
    ]
    declared = report["declared"]
    if declared is None:
        lines += ["## Lettura bloccata", ""]
        lines.extend(f"- {_text(item)}" for item in report["diagnostics"])
    else:
        lines += [
            "## Dati dichiarati nel file",
            "",
            f"**{declared['Esito']}: {declared['EsitoDescription']}.** Questo è il testo dell'esito, non un'accettazione verificata da LIPE.",
            "",
            "| Campo | Valore dichiarato |",
            "|---|---|",
        ]
        lines.extend(
            f"| {name} | {_text(declared[name]) if declared[name] is not None else 'Non presente'} |"
            for name in (
                "IDFile",
                "NomeFile",
                "DataOraRicezione",
                "MessageID",
                "PECMessageID",
                "Note",
            )
        )
        if declared["RifArchivio"] is not None:
            lines += ["", "Archivio dichiarato:", ""]
            lines.extend(
                f"- {name}: {_text(value)}"
                for name, value in declared["RifArchivio"].items()
            )
        lines += ["", "## Errori o segnalazioni dichiarati", ""]
        lines.extend(
            f"- {_text(item['Codice'])}: {_text(item['Descrizione'])}"
            for item in declared["ListaErrori"]
        )
        if not declared["ListaErrori"]:
            lines.append(
                "Nessuna lista presente nel file. L'esito dichiarato sopra resta distinto."
            )
    lines += ["", "## Confronto con il file fornito come trasmesso", ""]
    association = report["submitted_file_association"]
    lines.append(
        {
            "NOT_CHECKED_NO_SUBMITTED_FILE": "File non fornito: confronto del nome non eseguito.",
            "NOT_CHECKED_BLOCKED_RECEIPT": "Ricevuta bloccata: confronto del nome non eseguito.",
            "FILENAME_MATCH_ONLY": "Il nome dichiarato nella ricevuta coincide esattamente con quello del file fornito.",
            "FILENAME_MISMATCH": "**I nomi non coincidono. Il collegamento richiede verifica; non è stabilito.**",
        }[association["filename_check"]]
    )
    if report["submitted_file"] is not None:
        lines += [
            "",
            f"File fornito: {_text(report['submitted_file']['original_name'])}",
            f"SHA-256: `{report['submitted_file']['sha256']}`",
        ]
    lines += [
        "",
        "La coincidenza del nome non lega crittograficamente la ricevuta ai byte del file. Il file fornito è conservato come evidenza opaca: importi VP, frontespizio ed eventuale firma non sono controllati in questo passaggio. Non rinominare un file per ottenere una coincidenza.",
        "",
        "## Verifica professionale ancora necessaria",
        "",
        "Controllare nel canale ufficiale l'origine della ricevuta, il collegamento al file effettivamente trasmesso e al cliente/periodo, lo stato e le segnalazioni. Conservare la prova della verifica. Un file scartato non diventa valido perché la sua ricevuta rispetta lo schema.",
        "",
        "## Quali dati arrivano al modello",
        "",
        "L'assistente può leggere il file ricevuto, identificativi e nomi dei file, date, messaggi, note ed errori e il file fornito come trasmesso, che può contenere frontespizio e righi VP. Questo helper locale non chiama modelli o reti. Aggiornare il report della sessione con le letture effettive; non dedurre che i dati siano rimasti fuori dal modello.",
        "",
    ]
    return "\n".join(lines)


def preserve_receipt(
    case: dict, receipt: Path, output: Path, *, submitted_file: Path | None = None
) -> Path:
    """Snapshot originals and persist even an invalid receipt in a new case folder."""
    validate(case)
    raw = _read(receipt)
    submitted = None if submitted_file is None else _read(submitted_file)
    report = inspect_receipt(raw)
    report.update(
        {
            "schema_version": "lipe.receipt-inspection.v1",
            "scope": {
                key: case[key]
                for key in (
                    "pipeline",
                    "client_id",
                    "engagement_id",
                    "tax_year",
                    "quarter",
                    "data_origin",
                )
            },
            "case_hash": digest(case),
            "engine_hash": engine_hash(),
            "xsd_manifest_hash": hashlib.sha256(
                (ROOT / "references/xsd/manifest.json").read_bytes()
            ).hexdigest(),
            "receipt": _identity(receipt, raw, "receipt.original"),
            "submitted_file": None,
            "case_association": "OPERATOR_SELECTION_NOT_ESTABLISHED_BY_RECEIPT",
        }
    )
    filename_check = "NOT_CHECKED_NO_SUBMITTED_FILE"
    if submitted is not None and submitted_file is not None:
        report["submitted_file"] = _identity(
            submitted_file, submitted, "submitted-file.original"
        )
        filename_check = (
            "NOT_CHECKED_BLOCKED_RECEIPT"
            if report["declared"] is None
            else (
                "FILENAME_MATCH_ONLY"
                if report["declared"]["NomeFile"] == submitted_file.name
                else "FILENAME_MISMATCH"
            )
        )
    report["submitted_file_association"] = {
        "filename_check": filename_check,
        "content_binding": "NOT_ESTABLISHED",
        "vp_and_frontpage_comparison": "NOT_TESTED",
        "submitted_file_signature": "NOT_TESTED",
    }
    report["report_hash"] = digest(report)
    files = {
        "receipt.original": raw,
        "receipt-inspection.json": (
            json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8"),
        "receipt-inspection.md": _markdown(report).encode("utf-8"),
    }
    if submitted is not None:
        files["submitted-file.original"] = submitted
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    for name, payload in files.items():
        with (output / name).open("xb") as handle:
            (output / name).chmod(0o600)
            handle.write(payload)
    return output


def main(argv: list[str] | None = None) -> int:
    """Attach a supplied receipt to an existing Archive run without sending it."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--submitted-file", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--client-engagement", type=Path)
    args = parser.parse_args(argv)
    case = read_json(args.case)
    if case.get("data_origin") != "SYNTHETIC":
        from lipe import _archive

        _, archive_output = _archive(case, args.case, args.client_engagement)
        if not args.output.resolve().is_relative_to(archive_output.resolve()):
            raise ContractError(
                "Real receipt evidence belongs in the selected Archive output"
            )
    folder = preserve_receipt(
        case, args.receipt, args.output, submitted_file=args.submitted_file
    )
    report = read_json(folder / "receipt-inspection.json")
    logging.info("LIPE receipt inspection (authenticity NOT VERIFIED): %s", folder)
    return (
        2
        if (
            report["inspection_status"] == "BLOCKED"
            or report["submitted_file_association"]["filename_check"]
            == "FILENAME_MISMATCH"
        )
        else 0
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
