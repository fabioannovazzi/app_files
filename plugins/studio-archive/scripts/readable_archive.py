"""Rebuild portable human navigation without changing the authoritative ledger."""

from __future__ import annotations

import html
import os
import re
import tempfile
import unicodedata
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.parse import quote

__all__ = ["refresh_readable_archive"]

_MARKER = "<!-- vera-readable-archive:v1 -->"
_NAMES = {
    "journal-bank-reconciliation": "Riconciliazione bancaria",
    "journal-sampling": "Campionamento giornale",
    "client-file-preparation": "Controllo documenti e fatture XML",
    "financial-analysis": "Analisi finanziaria",
    "treasury-forecast": "Previsione di tesoreria",
}
_STATES = {
    "prepared": "Preparata: esecuzione non iniziata",
    "running": "In lavorazione: risultati non ancora finalizzati",
    "ready_for_review": "Risultati finalizzati: da rivedere",
    "completed": "Esecuzione conclusa",
    "failed": "Esecuzione fallita: risultati non disponibili",
    "cancelled": "Esecuzione annullata: risultati non disponibili",
}
_STYLE = """body{font:16px system-ui,sans-serif;color:#18304e;background:#f6f8fc;
max-width:1100px;margin:40px auto;padding:0 24px}h1,h2{color:#09285e}
a{color:#075cbd}section{background:white;border:1px solid #d9e2ee;
border-radius:8px;padding:20px;margin:18px 0}table{width:100%;border-collapse:collapse}
td,th{text-align:left;padding:9px;border-bottom:1px solid #d9e2ee;vertical-align:top;
overflow-wrap:anywhere}code{overflow-wrap:anywhere}small{color:#52667e}
li{margin:8px 0}.warning{background:#fff4de;padding:14px;border-radius:6px}"""


def _slug(value: str, maximum: int = 32) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "-", normalized).strip("-.")[:maximum] or "Pratica"


def _link(page: Path, target: Path, label: str) -> str:
    relative = os.path.relpath(target, page.parent).replace(os.sep, "/")
    return f'<a href="{quote(relative, safe="/")}">{html.escape(label)}</a>'


def _page(title: str, body: str) -> str:
    return (
        f'{_MARKER}\n<!doctype html><html lang="it"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{html.escape(title)}</title><style>{_STYLE}</style>"
        f"<h1>{html.escape(title)}</h1>{body}</html>"
    )


def _write(page: Path, content: str, ledger: ModuleType) -> None:
    """Atomically replace only ordinary generated navigation pages."""
    ledger._ordinary_directory(page.parent, label="readable archive directory")
    if page.exists() or page.is_symlink():
        ledger._ordinary_file(page, label="readable archive page")
        if not page.read_text(encoding="utf-8").startswith(_MARKER):
            raise ledger.LedgerError(
                "Readable archive would overwrite an unowned file."
            )
        if page.read_text(encoding="utf-8") == content:
            return
    descriptor, temporary = tempfile.mkstemp(prefix=".view-", dir=page.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        # Stage beside the target, including when the client is on another drive.
        os.replace(temporary, page)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _directory(path: Path, ledger: ModuleType) -> None:
    ledger._ordinary_directory(path, label="readable archive directory", create=True)


def _input_table(page: Path, rows: list[dict[str, Any]], root: Path) -> str:
    body = "<table><tr><th>Documento</th><th>Ruolo</th><th>Riferimento</th></tr>"
    for row in rows:
        target = root / row["relative_path"]
        body += (
            "<tr><td>"
            + _link(page, target, row["original_name"])
            + f"</td><td>{html.escape(row['role'])}</td>"
            + f"<td><code>{html.escape(row['input_id'])}</code></td></tr>"
        )
    return body + "</table>"


def _run_page(
    page: Path,
    loaded: dict[str, Any],
    engagement_page: Path,
    ledger: ModuleType,
) -> str:
    run = loaded["run"]
    title = _NAMES.get(run["workflow_id"], run["label"])
    body = _link(page, engagement_page, "Torna alla pratica")
    body += (
        f"<p>{html.escape(run['label'])}</p><p>{html.escape(run['purpose'])}</p>"
        f"<p><strong>{_STATES[run['status']]}</strong> · "
        f"Creata: {html.escape(run['created_at'])} · "
        f"Aggiornata: {html.escape(run['updated_at'])}</p>"
        '<p class="warning">Lo stato dell’esecuzione non equivale ad approvazione '
        "professionale. Consultare anche gli stati di revisione nei risultati.</p>"
        f"<p>ID completo: <code>{run['run_id']}</code> · "
        f"Workflow: <code>{html.escape(run['workflow_id'])}</code> · "
        f"Versione componente: {html.escape(run['workflow_version'])}</p>"
        "<section><h2>Documenti utilizzati in questa esecuzione</h2><ul>"
    )
    for row in loaded["context"]["input_bindings"]:
        body += "<li>" + _link(page, Path(row["path"]), Path(row["path"]).name)
        body += f" — <code>{html.escape(row['binding_id'])}</code></li>"
    body += "</ul></section><section><h2>Risultati e versioni conservate</h2>"
    if run["status"] in {"ready_for_review", "completed"}:
        try:
            manifest = ledger.validate_run_artifacts(
                Path(loaded["context"]["studio_client_folder"]["client_root"]),
                run["engagement_id"],
                run["run_id"],
            )
        except ledger.LedgerError as exc:
            body += (
                f'<p class="warning">Verifica non superata: {html.escape(str(exc))}</p>'
            )
        else:
            body += "<p>Integrità dei file verificata contro il manifesto.</p>"
            body += "<table><tr><th>File esatto</th><th>Scopo</th><th>Destinazione</th></tr>"
            for item in manifest["artifacts"]:
                body += (
                    "<tr><td>"
                    + _link(
                        page,
                        Path(loaded["output_dir"]) / item["path"],
                        item["path"],
                    )
                    + f"</td><td>{html.escape(item['purpose'])}</td>"
                )
                body += f"<td>{html.escape(item['audience'])}</td></tr>"
            body += "</table>"
    else:
        body += "<p>Nessun risultato finalizzato disponibile per questa esecuzione.</p>"
    if run["failure"]:
        body += f"<p>Motivo: {html.escape(run['failure']['reason'])}</p>"
    body += "</section><details><summary>Registrazioni tecniche e tracciabilità</summary><ul>"
    names = ["run.json", "context.json", "input_manifest.json"]
    if run["status"] in {"ready_for_review", "completed"}:
        names.append("artifact_manifest.json")
    for name in names:
        body += "<li>" + _link(page, Path(loaded["run_root"]) / name, name) + "</li>"
    return _page(title, body + "</ul></details>")


def refresh_readable_archive(root: Path, ledger: ModuleType) -> dict[str, Any]:
    """Render a relocatable view from verified records, keeping exact IDs and bytes."""
    root = ledger._ordinary_directory(root, label="client folder")
    client = ledger.load_client_manifest(root)
    vera = root / "Vera"
    view = vera / "Pratiche"
    _directory(view, ledger)
    # Reuse the platform process-lock implementation with a separate client lock.
    lock_path = vera / ".readable-archive.lock"
    with ledger._engagement_thread_lock(lock_path):
        descriptor = ledger._open_engagement_lock(lock_path)
        try:
            ledger._acquire_process_lock(descriptor)
            index = vera / "APRI ARCHIVIO.html"
            body = (
                f"<p>Cliente: <strong>{html.escape(root.name)}</strong></p>"
                f"<p>ID stabile: <code>{client['client_id']}</code></p>"
                "<p>Aprire una pratica per trovare documenti acquisiti, attività, risultati "
                "e versioni. Queste pagine sono ricostruibili dal ledger tecnico: "
                "non sostituiscono documenti, ricevute o revisioni.</p><section><h2>Pratiche</h2><ul>"
            )
            engagements = ledger.list_engagements(root, client["client_id"])
            run_count = 0
            for engagement in engagements:
                eid = engagement["engagement_id"]
                directory = view / (
                    engagement["created_at"][:10]
                    + "--"
                    + _slug(engagement["label"])
                    + "--"
                    + eid
                )
                _directory(directory, ledger)
                page = directory / "Indice.html"
                body += "<li>" + _link(index, page, engagement["label"])
                body += (
                    f" — {engagement['created_at'][:10]} — {engagement['status']}</li>"
                )
                detail = _link(page, index, "Torna al cliente")
                detail += (
                    f"<p>Cliente: {html.escape(root.name)}</p>"
                    f"<p>Pratica: {html.escape(engagement['label'])}</p>"
                    f"<p>Stato: {engagement['status']} · ID: <code>{eid}</code></p>"
                    "<section><h2>Documenti acquisiti nella pratica</h2>"
                )
                detail += _input_table(page, list(ledger.list_inputs(root, eid)), root)
                detail += "</section><section><h2>Attività ed esecuzioni</h2><ul>"
                for loaded in ledger.list_runs(root, eid):
                    run = loaded["run"]
                    title = _NAMES.get(run["workflow_id"], run["label"])
                    run_dir = directory / (_slug(title) + "--" + run["run_id"])
                    _directory(run_dir, ledger)
                    run_page = run_dir / "Indice.html"
                    _write(run_page, _run_page(run_page, loaded, page, ledger), ledger)
                    detail += "<li>" + _link(page, run_page, title)
                    detail += (
                        f" — {run['created_at'][:10]} — {_STATES[run['status']]}"
                        f" — <code>{run['run_id']}</code></li>"
                    )
                    run_count += 1
                detail += (
                    "</ul></section><details><summary>Ledger della pratica</summary>"
                )
                detail += _link(
                    page,
                    vera / "engagements" / eid / "engagement.json",
                    "engagement.json",
                )
                _write(page, _page(engagement["label"], detail + "</details>"), ledger)
            body += (
                "</ul></section><details><summary>Come leggere la struttura tecnica</summary>"
                "<p>engagements contiene le pratiche identificate da eng_…; inputs contiene "
                "le copie immutabili importate; runs contiene tutte le esecuzioni run_…. "
                "Ogni esecuzione conserva i propri inputs, outputs, stati e manifesti. "
                "Le versioni rimangono nei risultati e sono elencate senza eliminarne nessuna.</p>"
            )
            body += _link(index, vera / "client.json", "Identità tecnica del cliente")
            _write(
                index,
                _page("Archivio Vera — " + root.name, body + "</details>"),
                ledger,
            )
            return {
                "status": "ready",
                "index_path": str(index),
                "engagement_count": len(engagements),
                "run_count": run_count,
            }
        finally:
            os.close(descriptor)
