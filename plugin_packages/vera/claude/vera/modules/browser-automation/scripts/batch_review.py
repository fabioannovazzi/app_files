#!/usr/bin/env python3
"""Save and render model-authored batch decisions for later human review.

Code checks shape, immutable history and escaping, never accounting judgment.
This local report neither executes actions nor attests to their correctness.
"""

from __future__ import annotations

import argparse
import copy
import html
import json
import logging
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from capability_pipeline import canonical_json_bytes, sha256_payload

__all__ = [
    "validate_review",
    "read_review",
    "save_review",
    "record_review",
    "render_review",
    "main",
]
LOGGER = logging.getLogger(__name__)
SCHEMA = "browser-batch-review/v1"
STATUSES = {
    "pending": "Da elaborare",
    "completed": "Completata",
    "set_aside": "Da decidere",
    "failed": "Non riuscita",
    "unverified": "Esito da verificare",
}
ORDER = {"unverified": 0, "failed": 1, "set_aside": 2, "pending": 3, "completed": 4}
DECISIONS = {"checked": "Controllata", "correction_requested": "Correzione richiesta"}
ENTRY_TEXT = {"id", "document", "action", "reason", "outcome"}
ENTRY_KEYS = ENTRY_TEXT | {
    "status",
    "proposed",
    "actual",
    "evidence",
    "question",
    "posting_reference",
    "correction_of",
}


def _text(value: Any, *, empty: bool = False) -> bool:
    return (
        isinstance(value, str)
        and len(value) <= 10000
        and (empty or bool(value.strip()))
    )


def validate_review(payload: Any) -> None:
    """Validate declarations; a completed label still needs model evidence review."""
    if not isinstance(payload, dict) or set(payload) != {
        "schema_version",
        "batch_id",
        "title",
        "scope",
        "status",
        "expected_items",
        "entries",
        "reviews",
    }:
        raise ValueError("invalid batch review fields")
    if payload["schema_version"] != SCHEMA or not all(
        _text(payload[k]) for k in ("batch_id", "title", "scope")
    ):
        raise ValueError("batch identity and scope are required")
    if payload["status"] not in {"running", "paused", "finished"}:
        raise ValueError("invalid batch status")
    total = payload["expected_items"]
    if total is not None and (type(total) is not int or total < 0):
        raise ValueError("expected_items must be a nonnegative count or null")
    entries = payload["entries"]
    if not isinstance(entries, list) or len(entries) > 10000:
        raise ValueError("entries must be a bounded array")
    ids: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != ENTRY_KEYS:
            raise ValueError("invalid entry fields")
        if not all(_text(entry[k]) for k in ENTRY_TEXT) or entry["id"] in ids:
            raise ValueError(
                "entry identity, action, reason and outcome are required and ids unique"
            )
        ids.add(entry["id"])
        if entry["status"] not in STATUSES:
            raise ValueError("invalid entry status")
        for key in ("question", "posting_reference", "correction_of"):
            if not _text(entry[key], empty=True):
                raise ValueError("invalid optional entry text")
        for key in ("proposed", "actual", "evidence"):
            fields = entry[key]
            if not isinstance(fields, list) or len(fields) > 500:
                raise ValueError("details must be bounded arrays")
            if any(
                not isinstance(f, dict)
                or set(f) != {"label", "value", "source"}
                or not all(_text(v) for v in f.values())
                for f in fields
            ):
                raise ValueError("each detail requires label, value and source")
        if entry["status"] == "completed" and (
            not entry["actual"] or not entry["evidence"] or entry["question"]
        ):
            raise ValueError(
                "completion requires actual result and evidence with no open question"
            )
        if (
            entry["status"] in {"set_aside", "failed", "unverified"}
            and not entry["question"]
        ):
            raise ValueError("exception requires a concrete question or next action")
    if any(
        e["correction_of"]
        and (e["correction_of"] not in ids or e["correction_of"] == e["id"])
        for e in entries
    ):
        raise ValueError("correction must reference another existing entry")
    originals = sum(not e["correction_of"] for e in entries)
    if total is not None and originals > total:
        raise ValueError("recorded items exceed declared batch scope")
    if payload["status"] == "finished" and (
        any(e["status"] == "pending" for e in entries)
        or total is None
        or originals != total
    ):
        raise ValueError("finish requires accounted scope and no pending entries")
    reviews = payload["reviews"]
    if not isinstance(reviews, list):
        raise ValueError("reviews must be an array")
    for review in reviews:
        if (
            not isinstance(review, dict)
            or set(review) != {"entry_id", "decision", "note", "at"}
            or review["entry_id"] not in ids
            or review["decision"] not in DECISIONS
            or not all(_text(review[k]) for k in ("note", "at"))
        ):
            raise ValueError("invalid human review event")


def read_review(directory: Path) -> dict[str, Any]:
    """Verify every saved revision and return the latest snapshot."""
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("review directory must be a real directory")
    previous = None
    latest: dict[str, Any] = {}
    for number, path in enumerate(sorted(directory.glob("review-*.json")), 1):
        if path.is_symlink() or path.name != f"review-{number:04d}.json":
            raise ValueError("invalid review sequence")
        record = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(record, dict) or set(record) != {
            "revision",
            "previous_sha256",
            "saved_at",
            "payload",
            "sha256",
        }:
            raise ValueError("invalid review record")
        unsigned = {k: v for k, v in record.items() if k != "sha256"}
        if (
            record["revision"] != number
            or record["previous_sha256"] != previous
            or record["sha256"] != sha256_payload(unsigned)
        ):
            raise ValueError("invalid review history")
        validate_review(record["payload"])
        previous, latest = record["sha256"], record
    if not latest:
        raise ValueError("no saved batch review")
    return latest


def _check_update(old: dict[str, Any], new: dict[str, Any]) -> None:
    for key in ("batch_id", "title", "scope"):
        if old[key] != new[key]:
            raise ValueError("cannot replace batch identity or scope")
    current = {e["id"]: e for e in new["entries"]}
    for entry in old["entries"]:
        updated = current.get(entry["id"])
        if updated is None or any(
            updated[k] != entry[k] for k in ("document", "correction_of")
        ):
            raise ValueError("cannot remove or replace a recorded item")
        if entry["status"] == "completed" and updated != entry:
            raise ValueError("preserve completed entry; append a linked correction")
    if new["reviews"][: len(old["reviews"])] != old["reviews"]:
        raise ValueError("human review history is append-only")


def _write_new(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)


def save_review(
    directory: Path, payload: dict[str, Any], *, expected_revision: int
) -> Path:
    """Append a private snapshot; stale/concurrent writers cannot overwrite it."""
    validate_review(payload)
    if type(expected_revision) is not int or not 0 <= expected_revision < 9999:
        raise ValueError("invalid expected revision")
    previous = None
    if expected_revision == 0:
        directory.mkdir(mode=0o700)
    else:
        old = read_review(directory)
        if old["revision"] != expected_revision:
            raise ValueError("stale review; resume latest revision")
        _check_update(old["payload"], payload)
        previous = old["sha256"]
    record = {
        "revision": expected_revision + 1,
        "previous_sha256": previous,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }
    record["sha256"] = sha256_payload(record)
    _write_new(
        directory / f'review-{record["revision"]:04d}.json',
        canonical_json_bytes(record),
    )
    return render_review(directory)


def record_review(
    directory: Path, *, entry_id: str, decision: str, note: str, expected_revision: int
) -> Path:
    """Record an operator's explicit review; never alter an accounting entry."""
    old = read_review(directory)
    payload = copy.deepcopy(old["payload"])
    payload["reviews"].append(
        {
            "entry_id": entry_id,
            "decision": decision,
            "note": note,
            "at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return save_review(directory, payload, expected_revision=expected_revision)


def render_review(directory: Path) -> Path:
    """Render escaped, offline, read-only HTML from the latest verified JSON."""
    record = read_review(directory)
    p = record["payload"]
    esc = html.escape
    reviews = {r["entry_id"]: r for r in p["reviews"]}
    counts = Counter(e["status"] for e in p["entries"])
    rows = []
    for entry in sorted(
        p["entries"],
        key=lambda e: (
            (
                0
                if reviews.get(e["id"], {}).get("decision") == "correction_requested"
                else 1
            ),
            ORDER[e["status"]],
        ),
    ):
        review = reviews.get(entry["id"])
        review_label = DECISIONS[review["decision"]] if review else "Da controllare"
        detail = ""
        for key, label in (
            ("proposed", "Trattamento proposto"),
            ("actual", "Risultato effettivo"),
            ("evidence", "Evidenze e dati della fattura"),
        ):
            fields = "".join(
                f'<tr><th>{esc(f["label"])}</th><td>{esc(f["value"])}</td><td>{esc(f["source"])}</td></tr>'
                for f in entry[key]
            )
            detail += (
                f"<h3>{label}</h3><table><thead><tr><th>Campo</th><th>Valore</th><th>Fonte</th></tr></thead><tbody>{fields}</tbody></table>"
                if fields
                else f"<h3>{label}</h3><p>Non disponibile.</p>"
            )
        history = "".join(
            f'<li>{esc(r["at"])} — {DECISIONS[r["decision"]]}: {esc(r["note"])}</li>'
            for r in p["reviews"]
            if r["entry_id"] == entry["id"]
        )
        rows.append(
            f"""<article data-status="{entry['status']}"><details><summary><span>{esc(entry['document'])}</span><span>{STATUSES[entry['status']]} · {review_label}</span></summary>
<p><strong>Azione:</strong> {esc(entry['action'])}</p><p><strong>Perché:</strong> {esc(entry['reason'])}</p><p><strong>Esito:</strong> {esc(entry['outcome'])}</p>
<p><strong>Da risolvere:</strong> {esc(entry['question']) or 'Nessuna domanda aperta.'}</p>{detail}
<p><strong>Riferimento registrazione:</strong> {esc(entry['posting_reference']) or 'Non disponibile.'}</p>
<p><strong>ID voce:</strong> {esc(entry['id'])}</p><p><strong>Correzione di:</strong> {esc(entry['correction_of']) or '—'}</p><h3>Controlli del professionista</h3><ul>{history or '<li>Nessun controllo registrato.</li>'}</ul>
</details></article>"""
        )
    totals = " · ".join(f"{label}: {counts[key]}" for key, label in STATUSES.items())
    state = {
        "running": "In corso",
        "paused": "Interrotto — revisione parziale",
        "finished": "Elaborazione terminata",
    }[p["status"]]
    expected = (
        str(p["expected_items"])
        if p["expected_items"] is not None
        else "non ancora definito"
    )
    document = f"""<!doctype html><html lang="it"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>{esc(p['title'])} — Vera</title><style>body{{font-family:'Instrument Sans',system-ui,sans-serif;color:#162333;background:white;max-width:1050px;margin:40px auto;padding:0 24px;line-height:1.55}}h1{{color:#002060;margin-bottom:8px}}header{{border-bottom:2px solid #002060;padding-bottom:22px}}small{{color:#586574}}article{{border-bottom:1px solid #ccd3dc}}summary{{display:flex;justify-content:space-between;gap:20px;cursor:pointer;padding:20px 0;color:#002060;font-weight:600}}details[open]{{padding-bottom:20px}}h3{{font-size:1rem;margin-top:22px}}table{{border-collapse:collapse;width:100%;table-layout:fixed}}td,th{{text-align:left;vertical-align:top;border-bottom:1px solid #e1e5eb;padding:8px;overflow-wrap:anywhere}}p,li{{overflow-wrap:anywhere;white-space:pre-wrap}}nav{{display:flex;gap:14px;margin:24px 0;flex-wrap:wrap}}input,select{{font:inherit;padding:8px;border:1px solid #8995a5;border-radius:3px;max-width:100%}}@media(max-width:600px){{summary{{flex-direction:column;gap:4px}}body{{padding:0 16px}}}}@media print{{nav{{display:none}}body{{margin:0;max-width:none}}}}</style>
<header><small>VERA · REVISIONE DEL LOTTO</small><h1>{esc(p['title'])}</h1><p>{esc(p['scope'])}</p><p><strong>{state}</strong> · Fatture previste: {expected}</p><p>{totals}</p><small>Salvato {esc(record['saved_at'])} · Revisione {record['revision']}. Esiti riportati da Vera sulla base delle evidenze indicate.</small></header>
<p>Le eccezioni sono mostrate per prime. Apri una voce per confrontare proposta, risultato e fonti. Per registrare un controllo o richiedere una correzione, indica a Vera l’ID della voce e la tua decisione. Il controllo non modifica una registrazione contabile; un’eventuale rettifica sarà una voce separata.</p>
<nav><label>Cerca <input id="search" type="search"></label><label>Mostra <select id="status"><option value="">Tutte le voci</option>{''.join(f'<option value="{k}">{v}</option>' for k,v in STATUSES.items())}</select></label></nav><main>{''.join(rows) or '<p>Nessuna fattura acquisita. Questo registro non dimostra un’elaborazione.</p>'}</main>
<script>const filter=()=>{{const q=document.querySelector('#search').value.toLocaleLowerCase();const s=document.querySelector('#status').value;document.querySelectorAll('article').forEach(e=>e.hidden=!!((s&&e.dataset.status!==s)||!e.textContent.toLocaleLowerCase().includes(q)));}};document.querySelector('#search').addEventListener('input',filter);document.querySelector('#status').addEventListener('change',filter);window.addEventListener('beforeprint',()=>document.querySelectorAll('details').forEach(e=>e.open=true));</script></html>"""
    path = directory / f'review-{record["revision"]:04d}.html'
    if path.exists():
        if path.is_symlink() or path.read_text(encoding="utf-8") != document:
            raise ValueError(
                "saved HTML differs; retain it and inspect the discrepancy"
            )
    else:
        _write_new(path, document.encode("utf-8"))
    return path


def main(argv: list[str] | None = None) -> int:
    """Save, reopen or record a human check on one explicitly selected batch."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("save", "resume", "review"))
    parser.add_argument("directory", type=Path)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--expected-revision", type=int, default=0)
    parser.add_argument("--entry")
    parser.add_argument("--decision", choices=tuple(DECISIONS))
    parser.add_argument("--note")
    args = parser.parse_args(argv)
    try:
        if args.command == "save":
            if args.input is None:
                parser.error("save requires --input")
            path = save_review(
                args.directory,
                json.loads(args.input.read_text(encoding="utf-8")),
                expected_revision=args.expected_revision,
            )
        elif args.command == "review":
            if not all((args.entry, args.decision, args.note)):
                parser.error("review requires --entry, --decision and --note")
            path = record_review(
                args.directory,
                entry_id=args.entry,
                decision=args.decision,
                note=args.note,
                expected_revision=args.expected_revision,
            )
        else:
            path = render_review(args.directory)
        LOGGER.info("%s", path)
    except (ValueError, OSError) as exc:
        LOGGER.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
