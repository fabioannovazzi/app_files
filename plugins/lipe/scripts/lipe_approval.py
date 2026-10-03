"""Prepare and accept an externally signed review of exact LIPE artifacts.

This implements approval evidence, not the remaining filing qualification gate.
Real XML serialization, tax-return signing and transmission are separate stages.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from lipe_authorization import (
    load_authority,
    provider_hash,
    read_evidence,
    read_signed_json,
    request_bytes,
    validate_request,
    verify_approval,
)
from lipe_core import ROOT, ContractError, calculate, digest, read_json
from lipe_frontpage import validate_frontpage

__all__ = [
    "prepare_review",
    "accept_review",
    "verify_review",
    "current_bindings",
    "main",
]

ARTIFACTS = {
    "case.json",
    "result.json",
    "workpaper.md",
    "workpaper.xlsx",
    "summary.pdf",
    "vp.csv",
    "anomalies.json",
    "anomalies.md",
    "review-request.md",
    "local_processing_receipt.json",
}


def _hash(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ContractError("Review artifacts must be regular, non-symlink files")
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def _write(path: Path, raw: bytes) -> None:
    with path.open("xb") as handle:
        path.chmod(0o600)
        handle.write(raw)


def _scope(case: dict) -> dict:
    return {
        key: case[key]
        for key in (
            "pipeline",
            "client_id",
            "engagement_id",
            "tax_year",
            "quarter",
            "data_origin",
        )
    }


def _separate_output(draft: Path, output: Path) -> None:
    if output.resolve().is_relative_to(
        draft.resolve()
    ) or draft.resolve().is_relative_to(output.resolve()):
        raise ContractError("Keep approval packets separate from the draft they bind")


def _markdown(value: str) -> str:
    # File names are data, not Markdown instructions or additional table rows.
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("`", "&#96;")
        .replace("[", "&#91;")
        .replace("]", "&#93;")
        .replace("|", "&#124;")
        .replace("\r", " ")
        .replace("\n", " ")
    )


def _disclosure(path: Path | None, run_id: str | None) -> dict:
    """Bind the selected run's disclosure using the existing canonical validator."""
    if path is None or not run_id:
        raise ContractError("Real review requires the selected run's model-data report")
    candidates = (
        ROOT.parent / "studio-archive/vendor/modules/model_data_report.py",
        ROOT.parent / "vera/scripts/model_data_report.py",
    )
    helper = next((item for item in candidates if item.is_file()), None)
    if helper is None:
        raise ContractError("The installed Studio Archive report validator is required")
    helper_hash = _hash(helper)
    spec = importlib.util.spec_from_file_location(
        "_lipe_disclosure_" + helper_hash, helper
    )
    if spec is None or spec.loader is None:
        raise ContractError("Cannot load the installed report validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    report = read_json(path)
    try:
        module.validate_model_data_report(report, evidence_root=path.parent)
        rebuilt, markdown = module.build_model_data_report(
            {
                key: value
                for key, value in report.items()
                if key not in {"report_id", "evidence", "limitations"}
            },
            evidence_root=path.parent,
        )
    except module.ModelDataReportError as exc:
        raise ContractError(str(exc)) from exc
    if report["workflow_id"] != "lipe" or report["run_id"] != run_id:
        raise ContractError("Model-data report belongs to a different workflow run")
    readable = path.with_suffix(".md")
    if (
        rebuilt["evidence"] != report["evidence"]
        or readable.read_text(encoding="utf-8") != markdown
    ):
        raise ContractError(
            "Model-data report differs from its evidence or readable disclosure"
        )
    return {
        "run/model_data_report.json": _hash(path),
        "run/model_data_report.md": _hash(readable),
        "runtime/model_data_report.py": helper_hash,
    }


def current_bindings(
    case: dict,
    front: dict,
    draft_folder: Path,
    source_root: Path,
    *,
    at: datetime,
    catalog_path: Path | None = None,
    model_data_report: Path | None = None,
    run_id: str | None = None,
) -> dict:
    """Recalculate sources and bind all actual draft files before accepting review."""
    if at.tzinfo is None:
        raise ContractError("Review time requires a timezone")
    if draft_folder.is_symlink() or not draft_folder.is_dir():
        raise ContractError("Select the preserved LIPE draft directory")
    result = calculate(case, source_root, catalog_path)
    if result["status"] != "DRAFT_FOR_REVIEW":
        raise ContractError("Unresolved LIPE blockers prevent a final approval request")
    checked = validate_frontpage(
        front, case, source_root, on_date=at.astimezone(ZoneInfo("Europe/Rome")).date()
    )
    required = ARTIFACTS
    paths = {path.name: path for path in draft_folder.iterdir()}
    if not required.issubset(paths):
        raise ContractError(
            "The preserved draft is missing review artifacts or the real model-data report"
        )
    if (
        read_json(paths["case.json"]) != case
        or read_json(paths["result.json"]) != result
    ):
        raise ContractError(
            "Recalculation differs from the preserved draft; generate and review a new revision"
        )
    artifacts = {name: _hash(path) for name, path in sorted(paths.items())}
    if case["data_origin"] == "REAL":
        artifacts.update(_disclosure(model_data_report, run_id))
    sources = [
        {"role": role, **source}
        for role, value in (("CASE", case), ("FRONTPAGE", front))
        for source in value["sources"]
    ]
    bindings = {
        "case_hash": digest(case),
        "frontpage_hash": checked["frontpage_hash"],
        "result_hash": result["result_hash"],
        "engine_hash": result["engine_hash"],
        "rules_hash": result["rules_hash"],
        "catalog_review_hash": digest(result["catalog_review"]),
        "source_inventory_hash": digest(sources),
        "artifacts_hash": digest(artifacts),
        "xsd_manifest_hash": _hash(ROOT / "references/xsd/manifest.json"),
        "crypto_provider_hash": provider_hash(),
    }
    return {
        "bindings": bindings,
        "artifacts": artifacts,
        "sources": sources,
        "frontpage_validation": checked,
        "result": result,
    }


def prepare_review(
    case: dict,
    front: dict,
    draft_folder: Path,
    source_root: Path,
    output: Path,
    *,
    at: datetime,
    catalog_path: Path | None = None,
    model_data_report: Path | None = None,
    run_id: str | None = None,
) -> Path:
    """Write a readable review packet and exact request bytes; never create approval."""
    _separate_output(draft_folder, output)
    snapshot = current_bindings(
        case,
        front,
        draft_folder,
        source_root,
        at=at,
        catalog_path=catalog_path,
        model_data_report=model_data_report,
        run_id=run_id,
    )
    statement = read_json(ROOT / "schemas/approval-request.schema.json")["properties"][
        "statement"
    ]["const"]
    now = at.astimezone(timezone.utc)
    request = {
        "schema_version": "lipe.approval-request.v1",
        "request_id": str(uuid4()),
        "action": "APPROVE_LIPE_EXPORT",
        "scope": _scope(case),
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=24)).isoformat(),
        "statement": statement,
        "bindings": snapshot["bindings"],
    }
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    _write(output / "request.json", request_bytes(request))
    _write(output / "review-snapshot.json", request_bytes(snapshot))
    _write(output / "frontpage.json", request_bytes(front))
    lines = [
        "# LIPE — richiesta di approvazione della versione",
        "",
        statement,
        "",
        "La richiesta non è ancora approvata. Firma del file telematico e invio non sono eseguiti.",
        "",
        "Leggere i documenti della bozza e i relativi riferimenti alle fonti. Verificare frontespizio, righi VP, quadrature, anomalie e decisioni. La firma autentica questa dichiarazione e i suoi vincoli; non certifica completezza fiscale o accettazione del gestionale.",
        "",
        f"Origine dichiarata: {case['data_origin']} · anno {case['tax_year']} · trimestre {case['quarter']}",
        "",
        "## Frontespizio proposto",
        "",
        "| Campo | Valore |",
        "|---|---|",
    ]
    lines.extend(
        f"| {name} | {value} |"
        for name, value in snapshot["frontpage_validation"]["fields"].items()
    )
    lines.extend(
        [
            "",
            "I campi FirmaDichiarazione e FirmaIntermediario sono dichiarazioni proposte, non firme digitali sul file XML. Esistenza e corrispondenza in Anagrafe restano basate sulle prove e sulla revisione professionale registrate.",
            "",
            "## Righi VP",
            "",
            "| Periodo | VP2 | VP3 | VP4 | VP5 | VP14 debito | VP14 credito |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for module in snapshot["result"]["modules"]:
        values = [
            (
                "Non compilato"
                if module["rows"][key] is None
                else module["rows"][key].replace(".", ",")
            )
            for key in ("vp2", "vp3", "vp4", "vp5", "vp14_debit", "vp14_credit")
        ]
        lines.append("| " + " | ".join([str(module["period"]), *values]) + " |")
    lines.extend(
        [
            "",
            "## File della bozza vincolati",
            "",
            *[
                f"- {_markdown(name)} — SHA-256 `{fingerprint}`"
                for name, fingerprint in snapshot["artifacts"].items()
            ],
            "",
            "Firmare esternamente gli esatti byte di request.json con il certificato coperto dal mandato dello studio. Una modifica a dati, fonti, catalogo, motore o file richiede una nuova revisione. Non fornire chiavi private a LIPE.",
            "",
            "La qualifica produttiva e le prove professionali/importatore restano separate e pendenti. L'export richiede la riverifica della decisione firmata, del mandato e della versione corrente; questa richiesta da sola non genera un XML.",
            "",
        ]
    )
    _write(output / "review-request.md", "\n".join(lines).encode("utf-8"))
    return output


def verify_review(
    case: dict,
    front: dict,
    draft_folder: Path,
    source_root: Path,
    request_path: Path,
    *,
    signature: Path,
    mandate: Path,
    mandate_signature: Path,
    authority: dict,
    at: datetime,
    catalog_path: Path | None = None,
    model_data_report: Path | None = None,
    run_id: str | None = None,
) -> dict:
    """Reverify original signatures and current bindings without trusting a saved status."""
    snapshot = current_bindings(
        case,
        front,
        draft_folder,
        source_root,
        at=at,
        catalog_path=catalog_path,
        model_data_report=model_data_report,
        run_id=run_id,
    )
    request, raw_request = read_signed_json(request_path)
    validate_request(request)
    if raw_request != request_bytes(request):
        raise ContractError("Sign the exact canonical request prepared by LIPE")
    if request["scope"] != _scope(case) or request["bindings"] != snapshot["bindings"]:
        raise ContractError(
            "The signed request is stale or belongs to a different case"
        )
    context = case["catalog_context"]
    if context is not None and context["studio_id"] != authority["policy"]["studio_id"]:
        raise ContractError("Firm authority does not match the selected studio catalog")
    proof = verify_approval(
        request,
        signature=signature,
        mandate=mandate,
        mandate_signature=mandate_signature,
        at=at,
        **authority,
    )
    originals = {
        "request": raw_request,
        "signature": read_evidence(signature),
        "mandate": read_evidence(mandate),
        "mandate_signature": read_evidence(mandate_signature),
        "trusted_roots": read_evidence(authority["trusted_roots"]),
        "crls": read_evidence(authority["crls"]),
    }
    if any(
        hashlib.sha256(raw).hexdigest() != proof["input_sha256"][name]
        for name, raw in originals.items()
    ):
        raise ContractError("Approval evidence changed during verification")
    latest = current_bindings(
        case,
        front,
        draft_folder,
        source_root,
        at=at,
        catalog_path=catalog_path,
        model_data_report=model_data_report,
        run_id=run_id,
    )
    if latest["bindings"] != snapshot["bindings"]:
        raise ContractError("Reviewed data or artifacts changed during verification")
    names = {
        "request": "request.json",
        "signature": "decision.p7s",
        "mandate": "mandate.json",
        "mandate_signature": "mandate.p7s",
        "trusted_roots": "trusted-roots.pem",
        "crls": "crls.pem",
    }
    files = {names[name]: raw for name, raw in originals.items()}
    files["policy.json"] = request_bytes(authority["policy"])
    files["review-snapshot.json"] = request_bytes(snapshot)
    files["approval.json"] = request_bytes(proof)
    return {"request": request, "snapshot": snapshot, "proof": proof, "files": files}


def accept_review(
    case: dict,
    front: dict,
    draft_folder: Path,
    source_root: Path,
    request_path: Path,
    output: Path,
    *,
    signature: Path,
    mandate: Path,
    mandate_signature: Path,
    authority: dict,
    at: datetime,
    catalog_path: Path | None = None,
    model_data_report: Path | None = None,
    run_id: str | None = None,
) -> Path:
    """Recheck exact current bindings and retain externally signed approval evidence."""
    _separate_output(draft_folder, output)
    verified = verify_review(
        case,
        front,
        draft_folder,
        source_root,
        request_path,
        signature=signature,
        mandate=mandate,
        mandate_signature=mandate_signature,
        authority=authority,
        at=at,
        catalog_path=catalog_path,
        model_data_report=model_data_report,
        run_id=run_id,
    )
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    for name, raw in verified["files"].items():
        _write(output / name, raw)
    return output


def main(argv: list[str] | None = None) -> int:
    """Prepare or verify one selected review without requesting or using private keys."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    accept = sub.add_parser("accept")
    for command in (prepare, accept):
        command.add_argument("--case", type=Path, required=True)
        command.add_argument("--frontpage", type=Path, required=True)
        command.add_argument("--draft", type=Path, required=True)
        command.add_argument("--source-root", type=Path)
        command.add_argument("--client-engagement", type=Path)
        command.add_argument("--catalog", type=Path)
        command.add_argument("--output", type=Path, required=True)
    for name in ("request", "signature", "mandate", "mandate-signature"):
        accept.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args(argv)
    case, front = read_json(args.case), read_json(args.frontpage)
    source_root = args.source_root
    disclosure_path, run_id = None, None
    if case["data_origin"] != "SYNTHETIC":
        from lipe import _archive

        if args.client_engagement is None:
            raise ContractError(
                "Real approval requires the existing Studio Archive run"
            )
        context = read_json(args.client_engagement)
        root, _ = _archive(case, args.case, args.client_engagement)
        extra = [args.frontpage, *[root / item["path"] for item in front["sources"]]]
        source_root, archive_output = _archive(
            case, args.case, args.client_engagement, extra
        )
        disclosure_path, run_id = (
            archive_output / "model_data_report.json",
            context["run_id"],
        )
        if not args.draft.resolve().is_relative_to(
            archive_output.resolve()
        ) or not args.output.resolve().is_relative_to(archive_output.resolve()):
            raise ContractError(
                "Real review artifacts belong in the selected Archive output"
            )
    if source_root is None:
        raise ContractError("Synthetic approval needs its explicit source root")
    options = {
        "case": case,
        "front": front,
        "draft_folder": args.draft,
        "source_root": source_root,
        "output": args.output,
        "at": datetime.now(timezone.utc),
        "catalog_path": args.catalog,
        "model_data_report": disclosure_path,
        "run_id": run_id,
    }
    if args.command == "prepare":
        folder = prepare_review(**options)
    else:
        authority = load_authority(
            excluded_roots=[
                source_root.parent if case["data_origin"] == "REAL" else source_root,
                args.draft,
                args.output,
            ]
        )
        folder = accept_review(
            **options,
            request_path=args.request,
            signature=args.signature,
            mandate=args.mandate,
            mandate_signature=args.mandate_signature,
            authority=authority,
        )
    logging.info("LIPE review %s: %s", args.command, folder)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
