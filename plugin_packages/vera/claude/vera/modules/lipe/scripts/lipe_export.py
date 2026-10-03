"""Export an unsigned IVP18 after re-verifying exact-version professional approval.

No signature is added to the XML and no return is transmitted. The filename
registry prevents local reuse; external filename use and importer qualification
must still be established by the studio.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from lipe_approval import current_bindings, verify_review
from lipe_authorization import (
    load_authority,
    load_export_registry,
    read_evidence,
    request_bytes,
)
from lipe_core import ContractError, digest, read_json
from lipe_xml import AMOUNTS, _serialize
from lipe_xml_compare import compare_ivp, comparison_markdown, read_ivp

__all__ = ["export_xml", "compare_files", "main"]

REGISTRY_ID = 0x4C495045


def _write(path: Path, raw: bytes) -> None:
    with path.open("xb") as handle:
        path.chmod(0o600)
        handle.write(raw)


def _separate(output: Path, source: Path) -> None:
    if output.resolve().is_relative_to(
        source.resolve()
    ) or source.resolve().is_relative_to(output.resolve()):
        raise ContractError(
            "Export folders must be separate from the evidence they preserve"
        )


def _reserve(registry: Path, filename: str, record: dict, policy: dict) -> None:
    """Reserve once in a single SQLite transaction; failed writes never reuse a name."""
    if registry.is_symlink() or (registry.exists() and not registry.is_file()):
        raise ContractError("Select the firm's regular export registry file")
    try:
        with registry.open("xb"):
            registry.chmod(0o600)
    except FileExistsError:
        pass
    connection = sqlite3.connect(registry, timeout=10)
    try:
        connection.execute("BEGIN IMMEDIATE")
        identity = connection.execute("PRAGMA application_id").fetchone()[0]
        if (
            identity == 0
            and not connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ):
            connection.execute("PRAGMA application_id=1279873093")
            connection.execute("CREATE TABLE registry (identity TEXT NOT NULL)")
            connection.execute(
                "CREATE TABLE exports (filename TEXT PRIMARY KEY, record TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO registry VALUES (?)",
                (
                    json.dumps(
                        {key: policy[key] for key in ("studio_id", "data_origin")},
                        sort_keys=True,
                    ),
                ),
            )
        elif identity != REGISTRY_ID:
            raise ContractError("The selected database is not a LIPE export registry")
        expected = {key: policy[key] for key in ("studio_id", "data_origin")}
        identities = connection.execute("SELECT identity FROM registry").fetchall()
        if len(identities) != 1 or json.loads(identities[0][0]) != expected:
            raise ContractError(
                "Export registry belongs to a different studio or data origin"
            )
        if connection.execute(
            "SELECT 1 FROM exports WHERE filename=?", (filename,)
        ).fetchone():
            raise ContractError(
                "This intermediary filename was already reserved; choose an unused progressive"
            )
        connection.execute(
            "INSERT INTO exports VALUES (?, ?)",
            (
                filename,
                request_bytes(
                    {
                        "status": "RESERVED",
                        **{
                            key: record[key]
                            for key in (
                                "filename",
                                "created_at",
                                "scope",
                                "xml_sha256",
                                "approved_request_sha256",
                            )
                        },
                    }
                ).decode("utf-8"),
            ),
        )
        connection.commit()
    finally:
        connection.close()


def _roundtrip(raw: bytes, case: dict, result: dict, front: dict) -> dict:
    """Read the written XML back and compare every amount, period and front field."""
    parsed = read_ivp(raw)
    if parsed["frontpage"] != front or parsed["signature_present"]:
        raise ContractError(
            "Serialized front page or unsigned status differs from approval"
        )
    expected_header = {"CodiceFornitura": "IVP18"}
    if "CFDichiarante" in front:
        expected_header.update(
            CodiceFiscaleDichiarante=front["CFDichiarante"],
            CodiceCarica=front["CodiceCaricaDichiarante"],
        )
    if parsed["header"] != expected_header or parsed["communication_id"] != "00001":
        raise ContractError(
            "Serialized header differs from the approved import profile"
        )
    if len(parsed["modules"]) != len(result["modules"]):
        raise ContractError("Serialized module count differs from approval")
    kind = "Mese" if case["regime"] == "MONTHLY" else "Trimestre"
    for index, (written, module) in enumerate(
        zip(parsed["modules"], result["modules"], strict=True), 1
    ):
        expected_amounts = {
            key: value if value is not None else "0.00"
            for key, value in module["rows"].items()
        }
        expected_fields = {"NumeroModulo": str(index), kind: str(module["xml_period"])}
        expected_fields.update(
            {
                tag: module["rows"][key].replace(".", ",")
                for key, tag in AMOUNTS
                if module["rows"][key] not in (None, "0.00")
            }
        )
        if module["rows"]["vp13"] not in (None, "0.00"):
            expected_fields["Metodo"] = str(module["vp13_method"])
        if (
            written["amounts"] != expected_amounts
            or written["fields"] != expected_fields
        ):
            raise ContractError(
                "Serialized VP values, omissions or period differ from approval"
            )
    return {
        "schema_validation": "PASS",
        "frontpage_and_header": "PASS",
        "periods_and_all_vp_values": "PASS",
        "zero_omission": "PASS",
        "unsigned": True,
    }


def export_xml(
    case: dict,
    front: dict,
    draft_folder: Path,
    source_root: Path,
    approval_folder: Path,
    output: Path,
    *,
    authority: dict,
    registry: Path,
    progressive: int,
    at: datetime,
    catalog_path: Path | None = None,
    model_data_report: Path | None = None,
    run_id: str | None = None,
) -> Path:
    """Reverify original approval evidence, reserve a filename and preserve unsigned XML."""
    if type(progressive) is not int or not 1 <= progressive <= 99999:
        raise ContractError("The import progressive must be an integer from 1 to 99999")
    if output.exists():
        raise FileExistsError(output)
    _separate(output, draft_folder)
    _separate(output, approval_folder)
    if registry.resolve().is_relative_to(output.resolve()):
        raise ContractError(
            "The shared filename registry cannot be stored inside this export"
        )
    if approval_folder.is_symlink() or not approval_folder.is_dir():
        raise ContractError("Select the preserved original approval folder")
    options = {
        "at": at,
        "catalog_path": catalog_path,
        "model_data_report": model_data_report,
        "run_id": run_id,
    }
    verified = verify_review(
        case,
        front,
        draft_folder,
        source_root,
        approval_folder / "request.json",
        signature=approval_folder / "decision.p7s",
        mandate=approval_folder / "mandate.json",
        mandate_signature=approval_folder / "mandate.p7s",
        authority=authority,
        **options,
    )
    snapshot = verified["snapshot"]
    fields = snapshot["frontpage_validation"]["fields"]
    if "CFIntermediario" not in fields:
        raise ContractError(
            "The reviewed intermediary fiscal code is required for this import profile"
        )
    raw = _serialize(case, snapshot["result"], fields)
    roundtrip = _roundtrip(raw, case, snapshot["result"], fields)
    pdf = read_evidence(draft_folder / "summary.pdf")
    if hashlib.sha256(pdf).hexdigest() != snapshot["artifacts"]["summary.pdf"]:
        raise ContractError("The approved PDF changed during export")
    latest = current_bindings(case, front, draft_folder, source_root, **options)
    if latest["bindings"] != snapshot["bindings"]:
        raise ContractError("Reviewed data changed during XML serialization")
    filename = f"IT{fields['CFIntermediario']}_LI_{progressive:05d}.xml"
    receipt = {
        "schema_version": "lipe.xml-export.v1",
        "status": "APPROVED_VERSION_XML_UNSIGNED",
        "created_at": at.astimezone(timezone.utc).isoformat(),
        "scope": verified["request"]["scope"],
        "filename": filename,
        "xml_sha256": hashlib.sha256(raw).hexdigest(),
        "approved_request_sha256": verified["proof"]["input_sha256"]["request"],
        "bindings": snapshot["bindings"],
        "roundtrip": roundtrip,
        "artifacts": {
            "approved-summary.pdf": hashlib.sha256(pdf).hexdigest(),
            **{
                "approval/" + name: hashlib.sha256(value).hexdigest()
                for name, value in verified["files"].items()
            },
        },
        "filename_uniqueness": "RESERVED_IN_CONFIGURED_REGISTRY_ONLY",
        "external_filename_history": "NOT_VERIFIED",
        "professional_and_importer_acceptance": "NOT_ESTABLISHED",
        "filing_status": "NOT_SIGNED_OR_TRANSMITTED",
        "network_calls": False,
    }
    _reserve(registry, filename, receipt, authority["policy"])
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    (output / "approval").mkdir(mode=0o700)
    for name, value in verified["files"].items():
        _write(output / "approval" / name, value)
    _write(output / filename, raw)
    _write(output / "approved-summary.pdf", pdf)
    _write(output / "export.json", request_bytes(receipt))
    _write(
        output / "export.md",
        (
            "# LIPE — XML della versione approvata\n\n"
            f"File: `{filename}`\n\nSHA-256: `{receipt['xml_sha256']}`\n\n"
            "XML non firmato e non trasmesso, destinato all'importazione nel gestionale. La firma CMS verificata approva la versione dei dati e non firma questa dichiarazione.\n\n"
            "Frontespizio, periodi e tutti gli importi sono stati riletti dall'XML e confrontati con il risultato approvato. Gli elementi importo a zero sono omessi. La sintesi PDF conservata è quella vincolata dalla richiesta firmata.\n\n"
            "Il progressivo è riservato nel registro dello studio. LIPE non conosce i nomi usati esternamente o in altri registri: il professionista ne verifica l'unicità prima dell'uso. Una prenotazione rimane consumata anche se una scrittura successiva fallisce.\n\n"
            "La validazione XSD e l'approvazione della versione non attestano la qualificazione professionale del software, l'importazione nel gestionale o l'accettazione dell'Agenzia. Queste prove restano pendenti. Non inviare una dichiarazione per eseguire un test.\n\n"
            "## Quali dati arrivano al modello\n\n"
            "Se aperti dall'host, XML, frontespizio, identificativi di contribuente e intermediario, importi VP, PDF, richiesta firmata, mandato e verifiche dei certificati possono entrare nel modello scelto. Il codice locale non chiama modelli o reti. Registrare le letture effettive nel report della sessione.\n"
        ).encode("utf-8"),
    )
    return output


def compare_files(case: dict, reference: Path, supplied: Path, output: Path) -> Path:
    """Preserve a comparison of supplied documents without authenticating their origin."""
    from lipe_core import validate

    validate(case)
    first, second = read_evidence(reference), read_evidence(supplied)
    try:
        report = compare_ivp(first, second)
    except ContractError as exc:
        report = {
            "schema_version": "lipe.xml-comparison.v1",
            "status": "BLOCKED",
            "diagnostics": [str(exc)],
            "reference_sha256": hashlib.sha256(first).hexdigest(),
            "supplied_sha256": hashlib.sha256(second).hexdigest(),
            "amounts_match": None,
            "reference_authorization": "NOT_ESTABLISHED_BY_COMPARISON",
            "signature_authenticity": "NOT_TESTED",
            "filing_acceptance": "NOT_ESTABLISHED",
            "network_calls": False,
        }
    report.update(
        scope={
            key: case[key]
            for key in (
                "pipeline",
                "client_id",
                "engagement_id",
                "data_origin",
                "tax_year",
                "quarter",
            )
        },
        case_association="OPERATOR_SELECTION_NOT_ESTABLISHED_BY_COMPARISON",
        source_names={"reference": reference.name, "supplied": supplied.name},
        case_hash=digest(case),
    )
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    _write(output / "reference.original", first)
    _write(output / "supplied.original", second)
    _write(output / "comparison.json", request_bytes(report))
    _write(output / "comparison.md", comparison_markdown(report).encode("utf-8"))
    return output


def main(argv: list[str] | None = None) -> int:
    """Export an approved case or compare two supplied XML documents in its run."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export")
    comparison = sub.add_parser("compare")
    for command in (export, comparison):
        command.add_argument("--case", type=Path, required=True)
        command.add_argument("--client-engagement", type=Path)
        command.add_argument("--output", type=Path, required=True)
    for name in ("frontpage", "draft", "approval"):
        export.add_argument("--" + name, type=Path, required=True)
    export.add_argument("--source-root", type=Path)
    export.add_argument("--catalog", type=Path)
    export.add_argument("--progressive", type=int, required=True)
    comparison.add_argument("--reference", type=Path, required=True)
    comparison.add_argument("--supplied", type=Path, required=True)
    args = parser.parse_args(argv)
    case = read_json(args.case)
    source_root, archive_output, disclosure, run_id = None, None, None, None
    if case.get("data_origin") != "SYNTHETIC":
        from lipe import _archive

        source_root, archive_output = _archive(case, args.case, args.client_engagement)
        if not args.output.resolve().is_relative_to(archive_output.resolve()):
            raise ContractError(
                "Real export and comparison belong in the selected Archive output"
            )
    if args.command == "compare":
        folder = compare_files(case, args.reference, args.supplied, args.output)
        report = read_json(folder / "comparison.json")
        logging.info("LIPE XML comparison (filing acceptance NOT VERIFIED): %s", folder)
        return 0 if report["status"] == "FIELDS_MATCH" else 2
    front = read_json(args.frontpage)
    if archive_output is not None:
        extra = [
            args.frontpage,
            *[source_root / item["path"] for item in front["sources"]],
        ]
        source_root, archive_output = _archive(
            case, args.case, args.client_engagement, extra
        )
        if any(
            not path.resolve().is_relative_to(archive_output.resolve())
            for path in (args.draft, args.approval)
        ):
            raise ContractError(
                "Real draft and approval belong to the selected Archive run"
            )
        disclosure, run_id = (
            archive_output / "model_data_report.json",
            read_json(args.client_engagement)["run_id"],
        )
    else:
        source_root = args.source_root
    if source_root is None:
        raise ContractError("Synthetic export requires an explicit source root")
    excluded = [
        source_root.parent if case["data_origin"] == "REAL" else source_root,
        args.draft,
        args.approval,
        args.output,
    ]
    authority = load_authority(excluded_roots=excluded)
    registry = load_export_registry(excluded_roots=excluded)
    folder = export_xml(
        case,
        front,
        args.draft,
        source_root,
        args.approval,
        args.output,
        authority=authority,
        registry=registry,
        progressive=args.progressive,
        at=datetime.now(timezone.utc),
        catalog_path=args.catalog,
        model_data_report=disclosure,
        run_id=run_id,
    )
    logging.info("LIPE approved-version XML (UNSIGNED, NOT TRANSMITTED): %s", folder)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
