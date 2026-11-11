"""Source-bound proposed postings, human corrections and positional IMPPN export.

Fixed positions, cents and conservation are mechanical contracts. Account and
invoice choices remain explicit agent proposals or recorded reviewer decisions.
This adapter does not claim a bank-reconciliation engine assurance result.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

__all__ = ["prepare", "projection", "save_decision", "export_reviewed", "revision"]
CASE = "posting_proposals.json"
STATE = "posting_decisions.json"
# These are display filters over retained proposal labels, not confidence scores
# or a new semantic classifier. Empty original lines are mechanically observable.
PROPOSAL_TYPES = {
    "NO_PROPOSAL": "Nessun abbinamento proposto",
    "INVOICE": "Riferimenti fattura presenti · da verificare",
    "BANK_FEES": "Oneri bancari",
    "AMOUNT_PARTY": "Importo e controparte · da verificare",
    "ACCOUNT": "Solo conto proposto",
    "HISTORICAL": "Riparto da registrazioni esistenti",
    "DOCUMENT": "Conto individuato · documento da definire",
    "ADVANCE": "Acconto o riparto da rivedere",
    "MISSING": "Documento mancante",
    "OTHER": "Altre proposte da verificare",
}
PROPOSAL_LABELS = {
    "Proposta fattura": "INVOICE",
    "Proposta oneri banca": "BANK_FEES",
    "Proposta importo e controparte": "AMOUNT_PARTY",
    "Proposta solo conto": "ACCOUNT",
    "Proposta riparto da partitari": "HISTORICAL",
    "Conto individuato, documento da definire": "DOCUMENT",
    "Acconto / riparto da rivedere": "ADVANCE",
    "Documento mancante": "MISSING",
}


def proposal_type(item: dict) -> str:
    """Project saved labels verbatim; do not infer accounting reliability."""
    if not item["proposed_lines"]:
        return "NO_PROPOSAL"
    return PROPOSAL_LABELS.get(item.get("proposal_status"), "OTHER")


def fingerprint(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def read(path: Path) -> dict[str, Any]:
    if (
        path.is_symlink()
        or path.stat().st_nlink != 1
        or path.stat().st_size > 8_000_000
    ):
        raise ValueError("Invalid posting review file")
    return json.loads(path.read_bytes())


def write(path: Path, value: Any) -> None:
    temporary = path.with_suffix(".tmp")
    if temporary.exists():
        raise ValueError("Interrupted posting write requires recovery")
    with temporary.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2))
    temporary.replace(path)


def cents(value: Any) -> int:
    if isinstance(value, (float, bool)):
        raise ValueError("Use an exact decimal amount")
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number * 100 != (number * 100).to_integral_value():
            raise ValueError("Amounts require exact cents")
        return int(number * 100)
    except InvalidOperation as error:
        raise ValueError("Invalid amount") from error


def lines_checked(item: dict, lines: list[dict], confirmed: bool) -> list[dict]:
    if not isinstance(lines, list) or not 1 <= len(lines) <= 79:
        raise ValueError("Supply between 1 and 79 counterpart lines")
    total = cents(item["bank"]["amount"])
    checked = []
    for line in lines:
        account = str(line["account"]).replace("/", "")
        amount = cents(line["amount"])
        side = line["side"]
        if (
            not re.fullmatch(r"\d{7}", account)
            or account == "0000000"
            or side not in {"D", "A"}
            or amount <= 0
            or amount >= 10**11
        ):
            raise ValueError("Invalid account, side or positive amount")
        total += amount if side == "D" else -amount
        partita = str(line.get("partita", "")).strip()
        year = str(line.get("year", "")).strip()
        section = str(line.get("section", "")).strip()
        if partita or year or section:
            if (
                not confirmed
                or not re.fullmatch(r"\d{1,6}", partita)
                or not re.fullmatch(r"\d{4}", year)
                or not re.fullmatch(r"\d{1,2}", section)
            ):
                raise ValueError(
                    "Confirm the actual partita, year and section, or clear all three"
                )
        checked.append(
            {
                "account": account,
                "amount": f"{Decimal(amount)/100:.2f}",
                "side": side,
                "partita": partita,
                "year": year,
                "section": section,
            }
        )
    if total:
        raise ValueError("Dare and Avere do not balance against the bank movement")
    return checked


def load(directory: Path) -> tuple[dict, dict]:
    case = read(directory / CASE)
    if case["schema"] != "vera.posting_proposals.v1":
        raise ValueError("Unsupported posting proposal schema")
    if fingerprint(case["batch"]) != case["batch_sha256"]:
        raise ValueError("The original proposals changed")
    state = read(directory / STATE)
    if state["batch_sha256"] != case["batch_sha256"]:
        raise ValueError("Decisions belong to another proposal batch")
    return case, state


def revision(directory: Path) -> str:
    case, state = load(directory)
    return fingerprint([case, state])


def prepare(directory: Path, batch: dict, *, run_id: str, source_sha256: str) -> dict:
    items = batch["items"]
    ids = [row["id"] for row in items]
    if not 1 <= len(items) <= 5000 or len(ids) != len(set(ids)):
        raise ValueError("Posting movements must have unique IDs")
    if not re.fullmatch(r"\d{1,5}", str(batch["company"])) or not re.fullmatch(
        r"\d{7}", batch["bank_account"]
    ):
        raise ValueError("Invalid company or bank account")
    for item in items:
        date.fromisoformat(item["bank"]["date"])
        if not cents(item["bank"]["amount"]):
            raise ValueError("Zero bank movement")
    case = {
        "schema": "vera.posting_proposals.v1",
        "run_id": run_id,
        "source_sha256": source_sha256,
        "batch_sha256": fingerprint(batch),
        "batch": batch,
    }
    if (directory / CASE).exists():
        old, _ = load(directory)
        if old != case:
            raise ValueError("This run already owns another posting batch")
        return {"status": "existing", "count": len(items)}
    if (directory / STATE).exists():
        raise ValueError("Orphaned decisions require recovery")
    write(directory / CASE, case)
    write(
        directory / STATE,
        {
            "schema": "vera.posting_decisions.v1",
            "batch_sha256": case["batch_sha256"],
            "decisions": {},
            "history": [],
        },
    )
    return {"status": "prepared", "count": len(items)}


def projection(directory: Path, args: dict) -> dict:
    case, state = load(directory)
    items = []
    for source in case["batch"]["items"]:
        row = copy.deepcopy(source)
        decision = state["decisions"].get(row["id"])
        row["status"] = decision["status"] if decision else "pending"
        row["decision"] = decision
        row["proposal_type"] = proposal_type(source)
        row["proposal_type_label"] = PROPOSAL_TYPES[row["proposal_type"]]
        items.append(row)
    all_items = items
    view = args.get("view", "REVIEW")
    filters = [{"view": "REVIEW", "label": "Tutti i movimenti", "count": len(items)}]
    for key, label in PROPOSAL_TYPES.items():
        count = sum(row["proposal_type"] == key for row in items)
        if count:
            filters.append({"view": "POSTING_" + key, "label": label, "count": count})
    if view != "REVIEW":
        key = view.removeprefix("POSTING_")
        if not view.startswith("POSTING_") or key not in PROPOSAL_TYPES:
            raise ValueError("Unknown posting proposal filter")
        items = [row for row in items if row["proposal_type"] == key]
    offset = args.get("offset", 0)
    selected = next((x for x in items if x["id"] == args.get("item_id")), None)
    if selected is None and not args.get("item_id"):
        selected = items[offset] if offset < len(items) else None
    counts = {
        key: sum(x["status"] == key for x in all_items)
        for key in ["pending", "accepted", "rejected"]
    }
    return {
        "items": items[offset : offset + 30],
        "selection": selected,
        "total": len(items),
        "data": {
            "counts": counts,
            "population_total": len(all_items),
            "saved_count": sum(row["decision"] is not None for row in all_items),
            "filters": filters,
            "company": case["batch"]["company"],
            "bank_account": case["batch"]["bank_account"],
            "notice": case["batch"]["notice"],
            "export": state.get("last_export"),
        },
    }


def save_decision(directory: Path, item_id: str, review: dict, *, actor: str) -> dict:
    case, state = load(directory)
    item = next((row for row in case["batch"]["items"] if row["id"] == item_id), None)
    if item is None:
        raise ValueError("Unknown bank movement")
    status = review["status"]
    if status not in {"pending", "accepted", "rejected"}:
        raise ValueError("Unknown posting decision")
    lines = review.get("lines", [])
    if (
        not isinstance(lines, list)
        or len(lines) > 79
        or any(
            not isinstance(row, dict)
            or any(
                not isinstance(value, str) or len(value) > 300 for value in row.values()
            )
            for row in lines
        )
    ):
        raise ValueError("Invalid posting draft lines")
    confirmed = review.get("partita_confirmed") is True
    if status == "accepted":
        lines = lines_checked(item, lines, confirmed)
    note = str(review.get("note", ""))
    if len(note) > 4000 or len(json.dumps(lines)) > 100_000:
        raise ValueError("Posting correction is oversized")
    decision = {
        "status": status,
        "lines": lines,
        "partita_confirmed": confirmed,
        "note": note,
        "actor": actor,
        "attribution": "configured operator; no authenticated professional identity claim",
        "at": datetime.now(timezone.utc).isoformat(),
    }
    state["history"].append(
        {
            "item_id": item_id,
            "before": state["decisions"].get(item_id),
            "after": decision,
        }
    )
    state["decisions"][item_id] = decision
    state.pop("last_export", None)
    write(directory / STATE, state)
    return {"saved": True, "status": status}


def record(batch: dict, item: dict, lines: list[dict]) -> bytes:
    raw = list(" " * 6999)

    def put(position: int, width: int, value: str, numeric: bool = False) -> None:
        if len(value) > width:
            raise ValueError("IMPPN field exceeds its documented width")
        raw[position - 1 : position - 1 + width] = (
            value.rjust(width, "0") if numeric else value.ljust(width)
        )

    put(1, 5, str(batch["company"]), True)
    put(6, 1, "3")
    put(7, 1, "0")
    put(268, 3, "027")
    put(271, 15, "VERA REVISIONE")
    put(286, 18, item["id"][:18])
    put(372, 8, date.fromisoformat(item["bank"]["date"]).strftime("%d%m%Y"))
    put(6814, 20, ("VERA-" + item["id"])[:20])
    money = cents(item["bank"]["amount"])
    all_lines = [
        {
            "account": batch["bank_account"],
            "amount": f"{Decimal(abs(money))/100:.2f}",
            "side": "D" if money > 0 else "A",
        },
        *lines,
    ]
    for index, line in enumerate(all_lines):
        pos = 973 + 64 * index
        put(pos, 7, line["account"].replace("/", ""), True)
        put(pos + 7, 1, line["side"])
        put(pos + 8, 12, str(cents(line["amount"])).zfill(11) + "+")
        if line.get("partita"):
            put(pos + 38, 6, line["partita"], True)
            put(pos + 44, 4, line["year"], True)
            put(6291 + 2 * index, 2, line["section"], True)
    if not any(row.get("partita") for row in lines):
        put(6964, 1, "N")
    return "".join(raw).encode("cp1252", errors="strict") + b"\r\n"


def export_reviewed(directory: Path) -> dict:
    case, state = load(directory)
    rows, excluded = [], []
    for item in case["batch"]["items"]:
        decision = state["decisions"].get(item["id"])
        if decision is None or decision["status"] != "accepted":
            excluded.append(
                {
                    "id": item["id"],
                    "status": decision["status"] if decision else "pending",
                }
            )
            continue
        lines = lines_checked(item, decision["lines"], decision["partita_confirmed"])
        rows.append(record(case["batch"], item, lines))
    if not rows:
        raise ValueError(
            "No accepted entries to export: accetta e salva almeno un movimento"
        )
    decisions_sha256 = fingerprint(state["decisions"])
    filename = "TRAF2000_REVISIONE_" + decisions_sha256[:16] + ".txt"
    target = directory / filename
    payload = b"".join(rows)
    if target.exists() and target.read_bytes() != payload:
        raise ValueError("Existing export bytes changed")
    if not target.exists():
        with target.open("xb") as stream:
            stream.write(payload)
    receipt = {
        "file": filename,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "records": len(rows),
        "excluded": excluded,
        "decisions_sha256": decisions_sha256,
        "import_tested": False,
    }
    write(directory / (filename + ".json"), receipt)
    state["last_export"] = receipt
    write(directory / STATE, state)
    return {"saved": True, "status": "exported", **receipt}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-engagement", required=True)
    parser.add_argument("--batch-input-id", required=True)
    args = parser.parse_args()
    import sys

    root = Path(__file__).resolve().parents[1]
    archive = root / "modules/studio-archive/scripts"
    if not archive.is_dir():
        archive = root.parent / "studio-archive/scripts"
    sys.path.insert(0, str(archive))
    import archive_core  # Initializes the maintained source/installed assurance environment.
    from vera_assurance import load_client_engagement_context_file

    context = load_client_engagement_context_file(
        Path(args.client_engagement), expected_workflow_id="journal-bank-reconciliation"
    )
    binding = next(
        row
        for row in context["input_bindings"]
        if row["binding_id"] == args.batch_input_id
    )
    source = Path(binding["path"])
    batch = read(source)
    result = prepare(
        Path(context["output_dir"]),
        batch,
        run_id=context["run_id"],
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    )
    import logging

    logging.basicConfig(level=logging.INFO)
    logging.info(json.dumps(result))


if __name__ == "__main__":
    main()
