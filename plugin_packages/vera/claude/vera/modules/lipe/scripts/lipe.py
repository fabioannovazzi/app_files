"""Run LIPE locally; preserve reviewed inputs, blockers and inspectable outputs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import sys
from pathlib import Path

from lipe_core import ROOT, ContractError, calculate, digest, read_json

__all__ = ["extract", "save_result", "main"]


def _write_json(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as handle:
        path.chmod(0o600)
        handle.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def extract(source: Path, output: Path) -> Path:
    """Snapshot source bytes and page text; no semantic extraction or OCR claim."""
    payload = source.read_bytes()
    source_hash = hashlib.sha256(payload).hexdigest()
    folder = output / ("source-" + source_hash)
    folder.mkdir(parents=True, mode=0o700, exist_ok=False)
    original = folder / ("original" + source.suffix.lower())
    with original.open("xb") as handle:
        original.chmod(0o600)
        handle.write(payload)
    if source.suffix.lower() == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(original)
        if reader.is_encrypted:
            _write_json(
                folder / "extraction.json",
                {"status": "BLOCKED_ENCRYPTED", "sha256": source_hash},
            )
            return folder
        pages = [page.extract_text() or "" for page in reader.pages]
    elif source.suffix.lower() in {".txt", ".csv", ".md"}:
        pages = [payload.decode("utf-8-sig")]
    else:
        _write_json(
            folder / "extraction.json",
            {"status": "NEEDS_REVIEWED_READABLE_DERIVATIVE", "sha256": source_hash},
        )
        return folder
    records = []
    for index, text in enumerate(pages, 1):
        path = folder / f"page-{index:04d}.txt"
        with path.open("x", encoding="utf-8") as handle:
            path.chmod(0o600)
            handle.write(text)
        records.append(
            {
                "page": index,
                "path": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "characters": len(text),
                "status": (
                    "TEXT_REQUIRES_VISUAL_REVIEW"
                    if text.strip()
                    else "NEEDS_OCR_OR_READABLE_SOURCE"
                ),
            }
        )
    _write_json(
        folder / "extraction.json",
        {
            "status": "REVIEW_REQUIRED",
            "source_sha256": source_hash,
            "original": original.name,
            "pages": records,
            "limitations": "Text extraction is not verified table recognition. Review the PDF visually; no OCR is run.",
        },
    )
    return folder


def save_result(case: dict, result: dict, output: Path) -> Path:
    """Persist each revision exclusively, including a blocked result."""
    folder = output / ("lipe-" + result["result_hash"])
    folder.mkdir(parents=True, mode=0o700, exist_ok=False)
    _write_json(folder / "case.json", case)
    _write_json(folder / "result.json", result)
    with (folder / "vp.csv").open("x", encoding="utf-8", newline="") as handle:
        fields = [
            "period",
            "vp2",
            "vp3",
            "vp4",
            "vp5",
            "vp6_debit",
            "vp6_credit",
            "vp7",
            "vp8",
            "vp9",
            "vp10",
            "vp11",
            "vp12",
            "vp13",
            "vp14_debit",
            "vp14_credit",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for module in result["modules"]:
            writer.writerow({"period": module["period"], **module["rows"]})
    lines = [
        "# LIPE — bozza per revisione",
        "",
        (
            "**DATI SINTETICI — esempio non utilizzabile per dichiarazioni.**"
            if case.get("data_origin") == "SYNTHETIC"
            else "Origine dichiarata: documenti reali; verificare il fascicolo collegato."
        ),
        "",
        "Stato: "
        + {
            "DRAFT_FOR_REVIEW": "bozza da rivedere",
            "BLOCKED": "calcolo bloccato: conferme o dati mancanti",
            "BLOCKED_INVALID_INPUT": "calcolo bloccato: dati non validi",
        }[result["status"]],
        "",
        f"Anno d'imposta: {case.get('tax_year', 'non disponibile')} · Trimestre: {case.get('quarter', 'non disponibile')}",
        "",
        "Qualificazione: pilota; validazione professionale e importazione nei gestionali non eseguite.",
        "",
        f"Impronta del risultato: `{result['result_hash']}`",
        "",
    ]
    if result["blockers"]:
        lines += [
            "## Dati da completare",
            "",
            *[f"- {item}" for item in result["blockers"]],
            "",
        ]
    for module in result["modules"]:
        period_label = "Mese" if case["regime"] == "MONTHLY" else "Trimestre"
        lines += [
            f"## {period_label} {module['period']}",
            "",
            "| Rigo | Euro |",
            "|---|---:|",
        ]
        lines += [
            f"| {key.upper().replace('_DEBIT', ' a debito').replace('_CREDIT', ' a credito')} | "
            + (
                "Non compilato"
                if module["rows"][key] is None
                else module["rows"][key].replace(".", ",")
            )
            + " |"
            for key in fields[1:]
        ]
        payment_label = {
            "NOT_VERIFIED": "non verificati: evidenza mancante",
            "NOT_COMPARABLE_ANNUAL_SETTLEMENT": "non confrontabili: liquidazione annuale",
            "DEFERRED": "debito riportato al periodo successivo",
            "MATCH": "importi dichiarati coincidenti con il dovuto calcolato",
            "DIFFERENCE_TO_REVIEW": "differenza da esaminare",
        }[module["payment_status"]]
        lines += ["", f"Versamenti: {payment_label}", ""]
    lines += [
        "## Evidenze e decisioni",
        "",
        "[Composizione per riga e riferimenti alle fonti](result.json) · "
        "[Dati e decisioni registrate](case.json) · [Tabella VP](vp.csv)",
        "",
    ]
    lines += ["## Scarti da esaminare", ""]
    lines += [
        f"- {item['code']} — periodo {item['period']}: {item['meaning']}"
        for item in result["findings"]
    ] or [
        "Nessuno scarto meccanico rilevato. Questo non prova completezza o correttezza fiscale."
    ]
    lines += [
        "",
        "## Responsabilità e limiti",
        "",
        "Le conferme registrate sono attribuite al revisore dichiarato; non ne autenticano l'identità. I calcoli non certificano la natura IVA, la completezza dei registri o la spettanza della detrazione. XML reale, firma e trasmissione non disponibili.",
        "",
        "## Quali dati arrivano al modello",
        "",
        "L'assistente può leggere registri, pagine, nomi, codici fiscali, importi, mappature, decisioni e risultati per la revisione. Gli script locali non chiamano modelli o reti. Ciò non misura quanto il modello dell'host ha già letto. Il report della sessione deve registrare l'esposizione effettiva; nessuna anonimizzazione automatica è dichiarata.",
        "",
    ]
    (folder / "workpaper.md").write_text("\n".join(lines), encoding="utf-8")
    _write_json(
        folder / "local_processing_receipt.json",
        {
            "pipeline": "LIPE",
            "input_hash": result["input_hash"],
            "result_hash": result["result_hash"],
            "network_calls_by_this_helper": False,
            "model_context_extent": "NOT_MEASURABLE_BY_LOCAL_HELPER",
            "model_data_report_status": "HOST_MUST_RECORD_ACTUAL_PHASES",
        },
    )
    (folder / "review-request.md").write_text(
        "# Bozza richiesta di revisione — non inviata\n\nVerificare fonti e copertura di tutti i sezionali, classificazioni, periodi IVA, detraibilità, saldi iniziali, rettifiche e versamenti. Esaminare gli scarti nel workpaper e ricondurre ogni correzione alla fonte. Nessun importo è approvato da questa bozza.\n",
        encoding="utf-8",
    )
    for path in folder.iterdir():
        path.chmod(0o600)
    return folder


def _archive(
    case: dict, case_path: Path, context_path: Path | None
) -> tuple[Path, Path]:
    if context_path is None:
        raise ContractError(
            "Real LIPE cases require a Studio Archive client engagement"
        )
    for vendor in (
        ROOT / "vendor/modules",
        ROOT.parent.parent / "vendor/modules",
        ROOT.parent / "_shared/vendor/modules",
    ):
        if (vendor / "vera_assurance").is_dir():
            sys.path.insert(0, str(vendor))
            break
    from vera_assurance import load_client_engagement_context_file

    context = load_client_engagement_context_file(
        context_path, expected_workflow_id="lipe", input_paths=[case_path]
    )
    if context["schema_version"] != "vera.client_workflow_context.v2" or (
        case["client_id"],
        case["engagement_id"],
    ) != (context["client_id"], context["engagement_id"]):
        raise ContractError("Case and portable archive identity differ")
    root = Path(context["run_root"]) / "inputs"
    paths = [(root / item["path"]).resolve() for item in case["sources"]]
    if any(not path.is_relative_to(root.resolve()) for path in paths):
        raise ContractError("Source escapes archive inputs")
    load_client_engagement_context_file(
        context_path, expected_workflow_id="lipe", input_paths=paths
    )
    return root, Path(context["output_dir"])


def main(argv: list[str] | None = None) -> int:
    """Run a local pipeline stage; validation failures exit nonzero and persist."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    extraction = sub.add_parser("extract")
    extraction.add_argument("--source", type=Path, required=True)
    extraction.add_argument("--output", type=Path, required=True)
    for name in ("calculate", "xml-test"):
        command = sub.add_parser(name)
        command.add_argument("--case", type=Path, required=True)
        command.add_argument("--source-root", type=Path)
        command.add_argument("--output", type=Path)
        command.add_argument("--client-engagement", type=Path)
    args = parser.parse_args(argv)
    if args.command == "extract":
        logging.info("Extraction: %s", extract(args.source, args.output))
        return 0
    case = read_json(args.case)
    source_root, output = args.source_root, args.output
    if case.get("data_origin") != "SYNTHETIC":
        source_root, output = _archive(case, args.case, args.client_engagement)
    if source_root is None or output is None:
        raise ContractError("Source root and output required for synthetic runs")
    if args.command == "xml-test":
        from lipe_xml import build_test_xml

        payload = build_test_xml(case, source_root)
        output.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = output / (
            "SYNTHETIC_NOT_FOR_FILING-" + hashlib.sha256(payload).hexdigest() + ".xml"
        )
        with path.open("xb") as handle:
            path.chmod(0o600)
            handle.write(payload)
        logging.info("XSD-validated synthetic test XML: %s", path)
        return 0
    try:
        result = calculate(case, source_root)
    except (ContractError, OSError, UnicodeError) as exc:
        result = {
            "status": "BLOCKED_INVALID_INPUT",
            "input_hash": digest(case),
            "blockers": [str(exc)],
            "modules": [],
            "findings": [],
            "composition": [],
        }
        result["result_hash"] = digest(result)
    folder = save_result(case, result, output)
    logging.info("LIPE %s: %s", result["status"], folder)
    return 2 if result["status"].startswith("BLOCKED") else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
