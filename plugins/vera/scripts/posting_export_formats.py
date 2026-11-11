"""Versioned accounting export adapters over one reviewed journal contract.

Source reconciliation and human choices belong upstream. An adapter may only
encode their exact saved accounts, amounts and supplied external references.
New targets require a verified import profile and their own validation/encoder.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

__all__ = ["DEFAULT_FORMAT", "formats", "adapter", "reviewed_entry", "validate_entry"]
DEFAULT_FORMAT = "teamsystem_imppn_v1"


@dataclass(frozen=True)
class ExportAdapter:
    identifier: str
    label: str
    standard: str
    version: str | None
    status: str
    filename_prefix: str | None
    encode: Callable[[dict[str, Any]], bytes] | None
    requirements: str
    extension: str | None = None
    encoding: str | None = None


def _cents(value: Any) -> int:
    if isinstance(value, (bool, float)):
        raise ValueError("Exact decimal amounts required")
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number * 100 != (number * 100).to_integral_value():
            raise ValueError("Exact cents required")
        return int(number * 100)
    except InvalidOperation as error:
        raise ValueError("Invalid exact amount") from error


def validate_entry(entry: dict[str, Any]) -> None:
    if (
        entry.get("schema_version") != "vera.reviewed_journal_entry.v1"
        or entry.get("decision_status") != "accepted_saved"
    ):
        raise ValueError("Only accepted saved accounting entries are exportable")
    date.fromisoformat(entry["posting_date"])
    if (
        not entry.get("source_movement_id")
        or not isinstance(entry.get("lines"), list)
        or len(entry["lines"]) < 2
    ):
        raise ValueError("A source-bound balanced journal entry is required")
    balance = 0
    for line in entry["lines"]:
        if (
            not isinstance(line.get("account"), str)
            or not line["account"].strip()
            or line.get("side") not in {"D", "A"}
        ):
            raise ValueError("Saved account and debit/credit side required")
        amount = _cents(line["amount"])
        if amount <= 0:
            raise ValueError("Positive journal-line amounts required")
        balance += amount if line["side"] == "D" else -amount
    if balance:
        raise ValueError("Reviewed journal entry does not balance")


def reviewed_entry(
    batch: dict, item: dict, lines: list[dict], *, decision_status: str
) -> dict[str, Any]:
    """Project reviewed values without assigning unknown destination keys."""
    amount = _cents(item["bank"]["amount"])
    result = {
        "schema_version": "vera.reviewed_journal_entry.v1",
        "decision_status": decision_status,
        "source_movement_id": item["id"],
        "posting_date": item["bank"]["date"],
        "currency": batch.get("currency"),
        "company_identity": batch.get("company_identity"),
        "destination_context": copy.deepcopy(batch.get("destination_context", {})),
        "lines": [
            {
                "account": batch["bank_account"],
                "side": "D" if amount > 0 else "A",
                "amount": format(Decimal(abs(amount)) / 100, ".2f"),
                "role": "bank",
                "external_references": {},
            }
        ],
    }
    if batch.get("company") is not None:
        result["destination_context"]["teamsystem"] = {"company": str(batch["company"])}
    for source in lines:
        refs = {
            key: source[key]
            for key in ("partita", "year", "section")
            if source.get(key)
        }
        result["lines"].append(
            {
                "account": source["account"],
                "side": source["side"],
                "amount": source["amount"],
                "role": "counterpart",
                "external_references": {"teamsystem": refs} if refs else {},
            }
        )
    validate_entry(result)
    return copy.deepcopy(result)


def _teamsystem(entry: dict[str, Any]) -> bytes:
    validate_entry(entry)
    raw = list(" " * 6999)

    def put(position, width, value, numeric=False):
        if len(value) > width:
            raise ValueError("IMPPN field exceeds its documented width")
        raw[position - 1 : position - 1 + width] = (
            value.rjust(width, "0") if numeric else value.ljust(width)
        )

    company = entry["destination_context"]["teamsystem"]["company"]
    if not company.isascii() or not company.isdigit() or len(company) > 5:
        raise ValueError("Invalid TeamSystem company code")
    if len(entry["lines"]) > 80:
        raise ValueError("IMPPN supports at most 80 accounting lines")
    put(1, 5, company, True)
    put(6, 1, "3")
    put(7, 1, "0")
    put(268, 3, "027")
    put(271, 15, "VERA REVISIONE")
    put(286, 18, entry["source_movement_id"][:18])
    put(372, 8, date.fromisoformat(entry["posting_date"]).strftime("%d%m%Y"))
    put(6814, 20, ("VERA-" + entry["source_movement_id"])[:20])
    has_partita = False
    for index, line in enumerate(entry["lines"]):
        account = line["account"].replace("/", "")
        if len(account) != 7 or not account.isascii() or not account.isdigit():
            raise ValueError("TeamSystem requires its exact seven-digit account code")
        position = 973 + 64 * index
        put(position, 7, account, True)
        put(position + 7, 1, line["side"])
        put(position + 8, 12, str(_cents(line["amount"])).zfill(11) + "+")
        refs = line["external_references"].get("teamsystem", {})
        if refs:
            if set(refs) != {"partita", "year", "section"} or any(
                not str(value).isascii() or not str(value).isdigit()
                for value in refs.values()
            ):
                raise ValueError(
                    "IMPPN requires supplied partita, year and section together"
                )
            has_partita = True
            put(position + 38, 6, refs["partita"], True)
            put(position + 44, 4, refs["year"], True)
            put(6291 + 2 * index, 2, refs["section"], True)
    if not has_partita:
        put(6964, 1, "N")
    return "".join(raw).encode("cp1252", errors="strict") + b"\r\n"


_ADAPTERS = {
    DEFAULT_FORMAT: ExportAdapter(
        DEFAULT_FORMAT,
        "TXT TeamSystem",
        "IMPPN",
        "1",
        "available",
        "TRAF2000_REVISIONE_",
        _teamsystem,
        "Righe contabili accettate e salvate; codici TeamSystem verificati.",
        ".txt",
        "cp1252",
    ),
    "datev_koinos": ExportAdapter(
        "datev_koinos",
        "DATEV Koinos / DATEV Italia",
        "Profilo di importazione DATEV Koinos",
        None,
        "requires_verified_profile",
        None,
        None,
        "Acquisire tracciato e configurazione d'importazione dell'installazione destinataria; non usare il CSV EXTF tedesco.",
    ),
    "zucchetti": ExportAdapter(
        "zucchetti",
        "Zucchetti",
        "Profilo di importazione Zucchetti",
        None,
        "requires_verified_profile",
        None,
        None,
        "Identificare prodotto destinatario, versione e tracciato di importazione; acquisire una specifica o un file campione verificabile.",
    ),
}


def formats() -> list[dict[str, Any]]:
    return [
        {
            "id": item.identifier,
            "label": item.label,
            "standard": item.standard,
            "version": item.version,
            "status": item.status,
            "requirements": item.requirements,
            "extension": item.extension,
            "encoding": item.encoding,
        }
        for item in _ADAPTERS.values()
    ]


def adapter(identifier: str = DEFAULT_FORMAT) -> ExportAdapter:
    if identifier not in _ADAPTERS:
        raise ValueError("Formato di esportazione sconosciuto")
    selected = _ADAPTERS[identifier]
    if selected.status != "available" or selected.encode is None:
        raise ValueError(selected.label + ": " + selected.requirements)
    return selected
