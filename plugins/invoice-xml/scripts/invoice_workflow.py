"""Persist drafts and export only their exact, source-bound reviewed version."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import logging
import re
import stat
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from invoice_checks import check_invoice
from invoice_schema import InvoiceSchema, flatten_fields

__all__ = ["digest", "export_invoice", "prepare_draft", "main"]

ROOT = Path(__file__).resolve().parents[1]
DECISIONS = (
    "source_grouping",
    "source_completeness",
    "parties",
    "document_type",
    "tax_treatment",
    "numbering_and_date",
    "routing",
    "duplicate_and_issue_status",
)
FOREIGN_DECISIONS = (
    "operation_facts",
    "date_basis",
    "original_invoice_reference",
    "currency_conversion",
)
MAX_INPUT_BYTES = 50 * 1024 * 1024


def digest(value: Any) -> str:
    """Bind a review to exact data, evidence, decisions and unresolved questions."""
    return hashlib.sha256(_json(value)).hexdigest()


def _json(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2)
        + "\n"
    ).encode()


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} needs nonempty text")
    return value


def _regular(path: Path, limit: int = MAX_INPUT_BYTES) -> bytes:
    before = path.lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or before.st_size > limit
    ):
        raise ValueError("Expected a bounded, single-link regular file")
    payload = path.read_bytes()
    after = path.lstat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise ValueError("File changed while reading")
    return payload


def _within(root: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError("Source path must be relative to the bound input root")
    candidate = root
    for part in path.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise ValueError("Symlink source or output path is not allowed")
    if not candidate.resolve().is_relative_to(root.resolve()):
        raise ValueError("Path escapes the selected run")
    return candidate


def _sources(proposal: dict[str, Any], input_root: Path) -> dict[str, dict[str, Any]]:
    sources: dict[str, dict[str, Any]] = {}
    if not isinstance(proposal["sources"], list) or not proposal["sources"]:
        raise ValueError("At least one source is required")
    for source in proposal["sources"]:
        source_id = _text(source["id"], "source ID")
        if source_id in sources:
            raise ValueError("Duplicate source ID")
        if source["role"] not in {
            "invoice",
            "party_profile",
            "professional_confirmation",
            "context",
        }:
            raise ValueError("Unknown source role")
        _text(source["title"], "source title")
        _text(source["evidence_group"], "source evidence group")
        path = _within(input_root, source["path"])
        if hashlib.sha256(_regular(path)).hexdigest() != source["sha256"]:
            raise ValueError("Source changed; refresh evidence and professional review")
        sources[source_id] = source
    if not any(
        source["role"] in {"invoice", "professional_confirmation"}
        for source in sources.values()
    ):
        raise ValueError("Context images alone cannot establish an invoice")
    return sources


def _references(value: Any, sources: dict[str, Any]) -> None:
    if not isinstance(value, list) or not value:
        raise ValueError("An evidence item needs source references")
    for reference in value:
        if reference["source_id"] not in sources:
            raise ValueError("Unknown evidence source")
        _text(reference["locator"], "page, region or confirmation locator")


def _assess(
    proposal: dict[str, Any], input_root: Path, schema: InvoiceSchema
) -> tuple[dict[str, Any], bytes | None]:
    if proposal["schema_version"] != 1:
        raise ValueError("Expected invoice proposal schema version 1")
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,59}", proposal["draft_id"]):
        raise ValueError("Invalid draft ID")
    sources = _sources(proposal, input_root)
    fields = flatten_fields(proposal["invoice"])
    if not isinstance(proposal["questions"], list):
        raise ValueError("Questions must be a list")
    issues = [
        _text(question, "unresolved question") for question in proposal["questions"]
    ]
    evidence = proposal["field_evidence"]
    if not isinstance(evidence, dict):
        raise ValueError("Field evidence must be a pointer-indexed object")
    if set(evidence) - set(fields):
        raise ValueError("Evidence refers to fields absent from the current draft")
    for pointer, value in fields.items():
        if value is None or not value.strip():
            issues.append(f"Missing or unreadable value: {pointer}")
            continue
        if pointer not in evidence:
            issues.append(f"Missing field evidence: {pointer}")
            continue
        basis = evidence[pointer]
        if basis["kind"] not in {"source", "confirmed", "calculated"}:
            raise ValueError("Unknown field evidence kind")
        _references(basis["references"], sources)
        _text(basis["basis"], "field evidence basis")
        if basis["kind"] == "calculated":
            operands = basis["operands"]
            if (
                not isinstance(operands, list)
                or not operands
                or any(item not in fields or item == pointer for item in operands)
            ):
                raise ValueError("Calculated field needs other exact field pointers")
        if basis.get("uncertain", False) is not False:
            issues.append(f"Uncertain field: {pointer}")
    decisions = proposal["decisions"]
    required = DECISIONS + (
        FOREIGN_DECISIONS if proposal["route"] == "foreign_integration" else ()
    )
    for name in required:
        if name not in decisions:
            issues.append(f"Missing professional decision: {name}")
            continue
        _text(decisions[name]["assessment"], f"decision {name}")
        _references(decisions[name]["references"], sources)
    xml = None
    schema_errors: list[str] = []
    mechanical_errors: list[str] = []
    try:
        xml = schema.serialize(proposal["invoice"])
        schema_errors = schema.errors(xml)
    except ValueError as exc:
        schema_errors = [str(exc)]
    if not schema_errors:
        mechanical_errors = check_invoice(proposal["invoice"], proposal["route"])
    issues += schema_errors + mechanical_errors
    report = {
        "schema_version": 1,
        "proposal_sha256": digest(proposal),
        "status": "blocked" if issues else "awaiting_professional_review",
        "schema_valid": not schema_errors,
        "mechanical_checks_passed": not schema_errors and not mechanical_errors,
        "issues": issues,
        "schema_errors": schema_errors,
        "mechanical_errors": mechanical_errors,
        "schema_bundle": schema.receipt,
        "source_file_count": len(sources),
        "field_count": len(fields),
        "sdi_acceptance": "not_tested",
        "limitations": [
            "Local review declarations do not authenticate the reviewer.",
            "XSD and bounded arithmetic checks do not establish tax correctness, registry existence or SdI acceptance.",
            "Prior issuance or export outside the reviewed evidence set cannot be checked automatically.",
        ],
    }
    return report, xml


def _preview(proposal: dict[str, Any], report: dict[str, Any]) -> str:
    escape = html.escape
    fields = flatten_fields(proposal["invoice"])
    rows = []
    for pointer, value in fields.items():
        basis = proposal["field_evidence"].get(pointer, {})
        refs = "; ".join(
            f"{ref['source_id']} · {ref['locator']}"
            for ref in basis.get("references", [])
        )
        rows.append(
            f"<tr><th scope='row'>{escape(pointer.split('/')[-1])}<small>{escape(pointer)}</small></th><td>{escape(value or 'Da completare')}</td><td>{escape(str(basis.get('basis', 'Evidenza mancante')))}<small>{escape(refs)}</small></td></tr>"
        )
    questions = "".join(f"<li>{escape(issue)}</li>" for issue in report["issues"])
    decisions = "".join(
        f"<dt>{escape(name.replace('_', ' '))}</dt><dd>{escape(value['assessment'])}</dd>"
        for name, value in proposal["decisions"].items()
    )
    invoice = proposal["invoice"]
    header = invoice.get("FatturaElettronicaHeader", {})

    def party(role: str) -> str:
        data = header.get(role, {}).get("DatiAnagrafici", {})
        names = data.get("Anagrafica", {})
        name = (
            names.get("Denominazione")
            or " ".join(
                str(names.get(key) or "") for key in ("Nome", "Cognome")
            ).strip()
        )
        return escape(name or "Da completare")

    body_views = []
    bodies = invoice.get("FatturaElettronicaBody", [])
    bodies = bodies if isinstance(bodies, list) else [bodies]
    for body in bodies:
        general = body.get("DatiGenerali", {}).get("DatiGeneraliDocumento", {})
        detail = body.get("DatiBeniServizi", {}).get("DettaglioLinee", [])
        detail = detail if isinstance(detail, list) else [detail]
        line_rows = "".join(
            "<tr>"
            + "".join(
                f"<td>{escape(str(line.get(key) or 'Da completare'))}</td>"
                for key in (
                    "Descrizione",
                    "Quantita",
                    "PrezzoUnitario",
                    "PrezzoTotale",
                    "AliquotaIVA",
                )
            )
            + "</tr>"
            for line in detail
        )
        body_views.append(
            f"<section><h2>Fattura {escape(str(general.get('Numero') or 'Da completare'))}</h2>"
            f"<p>Data: {escape(str(general.get('Data') or 'Da completare'))} · Tipo: {escape(str(general.get('TipoDocumento') or 'Da rivedere'))}</p>"
            f"<p><strong>Fornitore:</strong> {party('CedentePrestatore')}<br><strong>Cliente:</strong> {party('CessionarioCommittente')}</p>"
            "<table><thead><tr><th>Descrizione</th><th>Quantità</th><th>Prezzo unitario</th><th>Importo</th><th>IVA %</th></tr></thead>"
            f"<tbody>{line_rows}</tbody></table><p><strong>Totale documento: {escape(str(general.get('ImportoTotaleDocumento') or 'Da completare'))} {escape(str(general.get('Divisa') or ''))}</strong></p></section>"
        )
    return f"""<!doctype html><html lang="it"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>Revisione fattura XML · Vera</title><style>
body{{font-family:'Instrument Sans',Arial,sans-serif;color:#17202d;background:white;margin:0}}main{{max-width:1120px;margin:48px auto;padding:0 24px}}header{{border-bottom:2px solid #002060;padding-bottom:24px}}h1{{font-size:32px;color:#002060}}p,li,dd{{line-height:1.6}}table{{border-collapse:collapse;width:100%;table-layout:fixed}}th,td{{border-bottom:1px solid #dbe0e7;text-align:left;padding:14px 12px;vertical-align:top;overflow-wrap:anywhere}}th{{font-weight:500}}small{{display:block;font-size:12px;font-weight:400;color:#596572;margin-top:8px;overflow-wrap:anywhere}}dt{{font-weight:bold;margin-top:20px}}dd{{margin:6px 0}}.status{{color:#002060;font-weight:bold}}@media print{{main{{margin:0}}tr{{break-inside:avoid}}}}
</style><main><header><p>VERA · PREPARAZIONE FATTURE XML</p><h1>Revisione della fattura</h1><p class="status">{'Dati da completare o correggere' if report['issues'] else 'In attesa di revisione professionale'}</p><p>Controlla i valori e le fonti. Comunica a Vera le correzioni; ogni modifica richiede una nuova revisione. Questa anteprima non è una fattura emessa.</p></header>
<section><h2>Punti da risolvere</h2>{'<ul>'+questions+'</ul>' if questions else '<p>Nessun blocco individuato dai controlli locali. Restano da approvare dati e decisioni professionali.</p>'}</section>
{''.join(body_views)}
<section><details><summary>Esamina tutti i campi e le relative fonti</summary><table><thead><tr><th>Campo</th><th>Valore proposto</th><th>Fonte e interpretazione</th></tr></thead><tbody>{''.join(rows)}</tbody></table></details></section>
<section><h2>Decisioni da rivedere</h2><dl>{decisions}</dl></section>
<footer><p>Esportazione XML senza firma o trasmissione al Sistema di Interscambio. Validazione dello schema e controlli aritmetici locali non attestano la correttezza fiscale.</p><small>Versione della proposta: {report['proposal_sha256']}</small></footer></main></html>"""


def _write_new(path: Path, payload: bytes) -> None:
    """Never replace another artifact; identical retries are idempotent."""
    if path.exists() or path.is_symlink():
        if _regular(path) != payload:
            raise ValueError("Existing artifact differs; use a new revision")
        return
    with path.open("xb") as stream:
        stream.write(payload)
    path.chmod(0o600)


def prepare_draft(
    proposal: dict[str, Any], *, input_root: Path, output_dir: Path
) -> Path:
    """Persist a complete or partial proposal without creating invoice XML."""
    schema = InvoiceSchema()
    report, _ = _assess(proposal, input_root, schema)
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    if output_dir.is_symlink():
        raise ValueError("Output directory cannot be a symlink")
    revision = _within(output_dir, f"draft-{digest(proposal)}")
    revision.mkdir(exist_ok=True, mode=0o700)
    _write_new(revision / "proposal.json", _json(proposal))
    _write_new(revision / "validation.json", _json(report))
    _write_new(revision / "preview.html", _preview(proposal, report).encode())
    review_request = {
        "schema_version": 1,
        "proposal_sha256": digest(proposal),
        "status": "awaiting_professional_review",
        "reviewer": None,
        "reviewed_at": None,
        "approval_basis": None,
        "scope": "Prepare and export these exact fields; no issue, signature or SdI transmission.",
    }
    _write_new(revision / "review_request.json", _json(review_request))
    return revision


def export_invoice(
    revision: Path, review: dict[str, Any], *, input_root: Path
) -> dict[str, Any]:
    """Revalidate source bytes and exact professional review before file export."""
    if revision.is_symlink():
        raise ValueError("Revision cannot be a symlink")
    proposal = json.loads(_regular(revision / "proposal.json", 5 * 1024 * 1024))
    if revision.name != f"draft-{digest(proposal)}":
        raise ValueError("Proposal changed after preparation")
    report, xml = _assess(proposal, input_root, InvoiceSchema())
    if report["issues"] or xml is None:
        raise ValueError("XML export blocked: " + "; ".join(report["issues"]))
    if (
        review["schema_version"] != 1
        or review["status"] != "approved_for_export"
        or review["proposal_sha256"] != digest(proposal)
    ):
        raise ValueError("Missing approval for the exact proposal")
    _text(review["reviewer"], "reviewer")
    _text(review["approval_basis"], "actual professional approval reference")
    reviewed_at = datetime.fromisoformat(
        _text(review["reviewed_at"], "review timestamp")
    )
    if reviewed_at.tzinfo is None:
        raise ValueError("Review timestamp needs a timezone")
    transmission = proposal["invoice"]["FatturaElettronicaHeader"]["DatiTrasmissione"]
    transmitter = transmission["IdTrasmittente"]
    filename = f"{transmitter['IdPaese']}{transmitter['IdCodice']}_{transmission['ProgressivoInvio']}.xml"
    if not re.fullmatch(r"[A-Z]{2}[A-Za-z0-9]{2,28}_[A-Za-z0-9]{1,5}\.xml", filename):
        raise ValueError(
            "Review a transmitter ID and 1–5 alphanumeric file-progressive characters for the export filename"
        )
    export_dir = _within(revision, "export")
    export_dir.mkdir(exist_ok=True, mode=0o700)
    final_report = dict(
        report,
        status="exported_for_operator",
        professional_review="approved_for_export",
        review_sha256=digest(review),
        xml_path=filename,
        xml_sha256=hashlib.sha256(xml).hexdigest(),
    )
    artifacts = {
        filename: xml,
        "review.json": _json(review),
        "export_report.json": _json(final_report),
    }
    # Preflight every existing artifact before any writes to avoid a mixed retry.
    for name, content in artifacts.items():
        path = export_dir / name
        if (path.exists() or path.is_symlink()) and _regular(path) != content:
            raise ValueError("Export already exists with different review or content")
    for name, content in artifacts.items():
        _write_new(export_dir / name, content)
    return final_report


def _context(path: Path, output: Path) -> dict[str, Any]:
    for vendor in (
        ROOT / "vendor" / "modules",
        ROOT.parent / "_shared" / "vendor" / "modules",
        ROOT.parent.parent / "vendor" / "modules",
    ):
        if (vendor / "vera_assurance").is_dir():
            sys.path.insert(0, str(vendor))
            break
    from vera_assurance import load_client_engagement_context_file

    return cast(
        dict[str, Any],
        load_client_engagement_context_file(
            path, expected_workflow_id="invoice-xml", output_dir=output
        ),
    )


def main(argv: list[str] | None = None) -> int:
    """Expose only managed draft preparation and approval-bound export."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "export"])
    parser.add_argument("--client-engagement", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--proposal", type=Path)
    parser.add_argument("--revision", type=Path)
    parser.add_argument("--review", type=Path)
    args = parser.parse_args(argv)
    context = _context(args.client_engagement, args.output)
    input_root = Path(context["input_dir"])
    if args.action == "prepare":
        if args.proposal is None or not args.proposal.resolve().is_relative_to(
            args.output.resolve()
        ):
            raise ValueError(
                "Save the model-authored proposal inside this managed output directory"
            )
        proposal = json.loads(_regular(args.proposal, 5 * 1024 * 1024))
        result = prepare_draft(proposal, input_root=input_root, output_dir=args.output)
        logging.info("Draft and review preview: %s", result)
    else:
        if args.revision is None or not args.revision.resolve().is_relative_to(
            args.output.resolve()
        ):
            raise ValueError("Select a prepared revision within this managed run")
        if args.review is None or not args.review.resolve().is_relative_to(
            args.output.resolve()
        ):
            raise ValueError(
                "Persist the exact professional approval inside this managed run"
            )
        export_report = export_invoice(
            args.revision, json.loads(_regular(args.review)), input_root=input_root
        )
        logging.info("XML exported for operator: %s", export_report["xml_path"])
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
