"""Source-bound annual accounts adapter for reviewed Swiss CO statement mappings."""

from __future__ import annotations

import logging
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for vendor in (
    ROOT / "vendor/modules",
    ROOT.parent.parent / "vendor/modules",
    ROOT.parent / "_shared/vendor/modules",
):
    if (vendor / "vera_assurance").is_dir():
        sys.path.insert(0, str(vendor))
        break

from vera_assurance.jurisdiction import citations, run, seal, text, validate_envelope
from xbrl_case import normalize_decimal

__all__ = ["build_record", "render_memo"]

GROUPS = {"assets", "liabilities", "equity", "income", "expenses"}


def build_record(
    payload: dict[str, Any], *, input_root: Path, client_id: str, engagement_id: str
) -> dict[str, Any]:
    """Reconcile a complete reviewed trial balance without selecting Swiss rules."""
    payload = validate_envelope(payload, input_root)
    if payload["language"] not in {"fr", "en"}:
        raise ValueError("This presentation adapter supports fr and en")
    if payload.get("framework") != "CH-CO" or payload.get("currency") != "CHF":
        raise ValueError(
            "This adapter accepts Swiss CO accounts in CHF; no implicit FX"
        )
    text(payload.get("entity_name"), "entity name")
    text(payload.get("framework_assessment"), "entity-specific framework assessment")
    if payload.get("trial_balance_basis") != "debit_positive_before_result_transfer":
        raise ValueError(
            "Use a complete debit-positive trial balance before result transfer"
        )
    current_end = date.fromisoformat(payload["current_period_end"])
    prior_end = date.fromisoformat(payload["prior_period_end"])
    if current_end <= prior_end:
        raise ValueError("Current period must follow comparative period")
    source_ids = {s["id"] for s in payload["sources"]}
    accounts = payload.get("accounts")
    if not isinstance(accounts, list) or not accounts:
        raise ValueError("A complete source-bound trial balance is required")
    account_map = {}
    balances = {"current": Decimal(0), "prior": Decimal(0)}
    for account in accounts:
        identity = text(account.get("id"), "account ID")
        if identity in account_map:
            raise ValueError("Duplicate trial-balance account")
        text(account.get("label"), "account label")
        if account.get("currency") != "CHF":
            raise ValueError("Every trial-balance account must be explicitly in CHF")
        citations(account.get("citations"), source_ids)
        values = {period: normalize_decimal(account[period]) for period in balances}
        for period, value in values.items():
            balances[period] += value
        account_map[identity] = values
    if any(value != 0 for value in balances.values()):
        raise ValueError("The current and comparative trial balances must both balance")
    mapping = payload.get("statement_lines")
    if not isinstance(mapping, list) or not mapping:
        raise ValueError("Reviewed statement mappings are required")
    used: set[str] = set()
    line_ids: set[str] = set()
    totals = {group: {period: Decimal(0) for period in balances} for group in GROUPS}
    rendered_lines = []
    for line in mapping:
        identity = text(line.get("id"), "line ID")
        if identity in line_ids or line.get("group") not in GROUPS:
            raise ValueError("Duplicate statement line or invalid statement group")
        line_ids.add(identity)
        text(line.get("label"), "statement label")
        citations(line.get("citations"), source_ids)
        ids = line.get("account_ids")
        if not isinstance(ids, list) or not ids or len(set(ids)) != len(ids):
            raise ValueError("Statement line needs unique account IDs")
        if not set(ids) <= account_map.keys() or used.intersection(ids):
            raise ValueError("Unrecognized or multiply mapped trial-balance account")
        used.update(ids)
        sign = 1 if line["group"] in {"assets", "expenses"} else -1
        values = {
            period: sign * sum((account_map[i][period] for i in ids), Decimal(0))
            for period in balances
        }
        for period, value in values.items():
            totals[line["group"]][period] += value
        rendered_lines.append(
            {
                "id": identity,
                "label": line["label"],
                "group": line["group"],
                "account_ids": ids,
                **{p: format(v, "f") for p, v in values.items()},
            }
        )
    if used != account_map.keys():
        raise ValueError("Every trial-balance account must be mapped exactly once")
    disclosures = payload.get("disclosure_review")
    if not isinstance(disclosures, list) or not disclosures:
        raise ValueError(
            "Review applicable notes, prior-year comparability and additional requirements"
        )
    disclosure_ids: set[str] = set()
    for note in disclosures:
        identity = text(note.get("id"), "disclosure ID")
        if identity in disclosure_ids:
            raise ValueError("Duplicate disclosure ID")
        disclosure_ids.add(identity)
        for field in ("title", "requirement", "assessment"):
            text(note.get(field), field)
        if note.get("status") not in {"supported", "not_applicable", "unresolved"}:
            raise ValueError("Invalid disclosure status")
        citations(note.get("citations"), source_ids)
    result = {
        period: totals["income"][period] - totals["expenses"][period]
        for period in balances
    }
    reconciliation = {
        period: totals["assets"][period]
        - totals["liabilities"][period]
        - totals["equity"][period]
        - result[period]
        for period in balances
    }
    results = {
        "statement_lines": rendered_lines,
        "totals": {
            g: {p: format(v, "f") for p, v in values.items()}
            for g, values in totals.items()
        },
        "result": {p: format(v, "f") for p, v in result.items()},
        "balance_reconciliation": {
            p: format(v, "f") for p, v in reconciliation.items()
        },
        "unresolved_disclosures": [
            n["id"] for n in disclosures if n["status"] == "unresolved"
        ],
        "statutory_completeness": "requires_professional_assessment",
        "filing_ready": False,
        "xbrl_generated": False,
    }
    return seal(
        payload,
        results,
        workflow_id="bilancio-xbrl-it",
        client_id=client_id,
        engagement_id=engagement_id,
    )


def render_memo(record: dict[str, Any]) -> str:
    """Render statement figures and the full professional disclosure assessment."""
    case, results = record["review"], record["results"]
    fr = case["language"] == "fr"
    titles = (
        {
            "assets": "Actif",
            "liabilities": "Capitaux étrangers",
            "equity": "Capitaux propres hors résultat",
            "income": "Produits",
            "expenses": "Charges",
        }
        if fr
        else {
            "assets": "Assets",
            "liabilities": "Liabilities",
            "equity": "Equity before current result",
            "income": "Income",
            "expenses": "Expenses",
        }
    )
    lines = [
        "# " + ("Comptes annuels — projet" if fr else "Annual accounts — draft"),
        "",
        case["entity_name"],
        "",
        "CH-GE · CH-CO · CHF",
        "",
        case["framework_assessment"],
        "",
        case["jurisdiction_basis"],
        "",
        (
            "La réconciliation arithmétique ne constitue ni une approbation des comptes ni une vérification de leur conformité."
            if fr
            else "Arithmetic reconciliation is neither approval nor a determination of statutory compliance."
        ),
    ]
    for group, heading in titles.items():
        lines.extend(
            [
                "",
                "## " + heading,
                "",
                f'| | {case["current_period_end"]} CHF | {case["prior_period_end"]} CHF |',
                "|---|---:|---:|",
            ]
        )
        for line in results["statement_lines"]:
            if line["group"] == group:
                label = line["label"].replace("|", "\\|").replace("\n", " ")
                lines.append(f'| {label} | {line["current"]} | {line["prior"]} |')
        total = results["totals"][group]
        lines.append(f'| Total | {total["current"]} | {total["prior"]} |')
    lines.extend(
        [
            "",
            "## " + ("Résultat" if fr else "Result"),
            "",
            f'{case["current_period_end"]}: {results["result"]["current"]} CHF · {case["prior_period_end"]}: {results["result"]["prior"]} CHF',
            "",
            "## "
            + ("Annexe et points à examiner" if fr else "Notes and review matters"),
        ]
    )
    for note in case["disclosure_review"]:
        lines.extend(
            [
                "",
                "### " + note["title"],
                "",
                note["status"],
                "",
                note["requirement"],
                "",
                note["assessment"],
                "",
                "; ".join(
                    c["source_id"] + ": " + c["locator"] for c in note["citations"]
                ),
            ]
        )
    lines.extend(
        [
            "",
            "## " + ("Sources et limites" if fr else "Sources and limitations"),
            "",
            case["limitations"],
        ]
    )
    for source in case["legal_basis"]:
        lines.append(
            f'\n{source["title"]} · {source["url"]} · {source["locator"]} · {source["applicability"]}'
        )
    for source in case["sources"]:
        lines.append(
            f'\n{source["id"]}: {source["title"]} · SHA-256 {source["sha256"]}'
        )
    if case.get("professional_decision"):
        lines.extend(["", case["professional_decision"]["conclusion"]])
    lines.extend(["", record["record_sha256"], ""])
    return "\n".join(lines)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(run("bilancio-xbrl-it", build_record, render_memo))
