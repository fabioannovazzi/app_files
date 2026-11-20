"""Source-bound balance mapping and exact cutoff arithmetic; no matching decisions."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

__all__ = ["read_balance_evidence", "build_balance_bridge"]


def read_balance_evidence(
    path: Path | None,
    roots: Mapping[str, Path],
    rows: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, Any]:
    """Replay reviewed PDF balance/date quotes against the actual input bytes.

    Mapping a quoted number to a closing balance remains an explicit agent or
    professional decision, just like input column mapping. Never guess from
    the final transaction date or an arbitrary excluded monetary column.
    """
    if path is None:
        return {
            "missing": [
                "Saldo banca datato e saldo partitario alla stessa data: mappatura delle fonti assente."
            ]
        }
    import pdfplumber
    from vera_assurance import parse_localized_decimal

    data = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(data, dict)
        or data.get("schema_version") != "journal_bank.balance_evidence.v1"
    ):
        raise ValueError("Unknown balance evidence schema")
    result: dict[str, Any] = {
        "missing": [],
        "mapping_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    for side in ("bank", "journal"):
        item = data.get(side)
        if not item:
            result["missing"].append(
                f"{side}: saldo di chiusura datato e fonte mancanti."
            )
            continue
        fields = (
            "role",
            "reviewed_by",
            "source_file",
            "source_sha256",
            "quote",
            "amount_text",
            "date_text",
            "date_format",
            "currency",
            "entity_ref",
        )
        if not isinstance(item, dict) or any(
            not isinstance(item.get(k), str) or not item[k] for k in fields
        ):
            raise ValueError("Balance mapping needs nonempty source fields")
        if type(item.get("page")) is not int or type(item.get("cash_sign")) is not int:
            raise ValueError("Balance page and cash sign must be integers")
        if item.get("role") != "closing_balance" or item.get("reviewed_by") not in {
            "agent",
            "professional",
        }:
            raise ValueError("Balance role needs an attributed source mapping")
        # Only the original input population may supply a balance, not arbitrary files.
        files = {str(r["source_file"]) for r in rows[side]}
        if (
            item["source_file"] not in files
            or Path(item["source_file"]).name != item["source_file"]
        ):
            raise ValueError("Balance source is outside this population")
        root = roots["source_" + side]
        source = root if root.is_file() else root / item["source_file"]
        if (
            source.suffix.lower() != ".pdf"
            or hashlib.sha256(source.read_bytes()).hexdigest() != item["source_sha256"]
        ):
            raise ValueError("Balance PDF changed or is unsupported")
        with pdfplumber.open(source) as pdf:
            page = int(item["page"])
            if not 1 <= page <= len(pdf.pages):
                raise ValueError("Balance page is outside the source")
            text = " ".join((pdf.pages[page - 1].extract_text() or "").split())
        quote = " ".join(item["quote"].split())
        if (
            not quote
            or quote not in text
            or not re.search(
                r"(?<![\d.,])" + re.escape(item["amount_text"]) + r"(?![\d.,])", quote
            )
            or item["date_text"] not in quote
        ):
            raise ValueError("Balance amount/date quote does not replay")
        if item["date_format"] not in {
            "%Y-%m-%d",
            "%d/%m/%Y",
            "%d/%m/%y",
            "%d.%m.%Y",
            "%d.%m.%y",
        }:
            raise ValueError("Balance date convention is unsupported")
        as_of = (
            datetime.strptime(item["date_text"], item["date_format"]).date().isoformat()
        )
        amount = parse_localized_decimal(item["amount_text"])
        if item.get("cash_sign") not in (-1, 1) or amount is None:
            raise ValueError("Balance cash sign is missing")
        amount *= item["cash_sign"]
        if not amount.is_finite() or amount != amount.quantize(Decimal(".01")):
            raise ValueError("Balance must use exact cents")
        result[side] = {
            "date": as_of,
            "amount": str(amount),
            "currency": item["currency"],
            "entity_ref": item["entity_ref"],
            "evidence": dict(item),
        }
    return result


def build_balance_bridge(
    bank: Sequence[Mapping[str, Any]],
    journal: Sequence[Mapping[str, Any]],
    relations: Sequence[Mapping[str, Any]],
    evidence: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    """Bridge cash balances without closing any open item or reusing an allocation."""
    from bank_first import _money, cents

    missing = list(evidence.get("missing", []))
    snapshots = {s: evidence.get(s) for s in ("bank", "journal")}
    for side, snapshot in snapshots.items():
        if not snapshot:
            missing.append(f"{side}: saldo di chiusura datato mancante.")
    cutoff = snapshots["bank"]["date"] if snapshots["bank"] else None
    if cutoff:
        date.fromisoformat(cutoff)
    if snapshots["journal"] and snapshots["journal"]["date"] != cutoff:
        missing.append(
            "Saldo partitario alla data di chiusura dell'estratto conto mancante."
        )
    comparable_scope = True
    for field in ("currency", "entity_ref"):
        values = {
            r.get(field) or policy.get("default_" + field) for r in [*bank, *journal]
        }
        values.update(s[field] for s in snapshots.values() if s)
        if len(values) != 1 or not all(values):
            comparable_scope = False
            missing.append(f"Perimetro comparabile non accertato: {field}.")
    if policy.get("direction_policy", "same_sign") != "same_sign":
        comparable_scope = False
        missing.append(
            "Saldi e movimenti con la stessa convenzione di segno di cassa non accertati."
        )
    output: dict[str, Any] = {
        "cutoff": cutoff,
        "missing": list(dict.fromkeys(missing)),
        "status": "unavailable" if missing else "available",
        "balance_evidence": dict(evidence),
        "subsequent_journal_ids": [],
    }
    if comparable_scope:
        for side, snapshot in snapshots.items():
            if snapshot and snapshot["date"] == cutoff:
                output[side + "_closing"] = _money(cents(snapshot["amount"]))
    if not cutoff:
        return output
    records = {
        "bank": {r["transaction_id"]: r for r in bank},
        "journal": {r["transaction_id"]: r for r in journal},
    }
    before = {
        side: {i for i, r in items.items() if r["transaction_date"] <= cutoff}
        for side, items in records.items()
    }
    subsequent = [r for r in journal if r["transaction_date"] > cutoff]
    output.update(
        subsequent_journal_ids=[r["transaction_id"] for r in subsequent],
        subsequent_journal_net=_money(
            sum(cents(r["amount_signed"]) for r in subsequent)
        ),
    )
    closed: dict[str, set[str]] = {"bank": set(), "journal": set()}
    differences = 0
    for group in relations:
        # A cross-cutoff link is subsequent evidence, not a cutoff posting.
        ids = {s: set(group[s + "_ids"]) for s in records}
        supported = (
            group.get("allocation_state") == "reserved"
            and group.get("bank_resolution", {}).get("status") == "resolved"
        )
        if supported and all(ids[s] and ids[s] <= before[s] for s in records):
            if any(ids[s] & closed[s] for s in records):
                raise ValueError("Balance bridge cannot reuse source rows")
            for side in records:
                closed[side].update(ids[side])
            differences += sum(
                cents(records["bank"][i]["amount_signed"]) for i in ids["bank"]
            ) - sum(
                cents(records["journal"][i]["amount_signed"]) for i in ids["journal"]
            )
    nets = {}
    for side in records:
        opened = [i for i in records[side] if i in before[side] - closed[side]]
        nets[side] = sum(cents(records[side][i]["amount_signed"]) for i in opened)
        output[side + "_open_ids"] = opened
        output[side + "_open_net"] = _money(nets[side])
    output["supported_difference"] = _money(differences)
    if not missing:
        b, j = (cents(snapshots[s]["amount"]) for s in ("bank", "journal"))
        output.update(
            bank_closing=_money(b),
            journal_closing=_money(j),
            balance_gap=_money(b - j),
            explained_difference=_money(nets["bank"] - nets["journal"] + differences),
            unexplained_difference=_money(
                b - j - nets["bank"] + nets["journal"] - differences
            ),
        )
    return output
