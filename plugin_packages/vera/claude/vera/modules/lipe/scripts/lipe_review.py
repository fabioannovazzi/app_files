"""Preserve model proposals and attributable professional decisions without guessing tax law.

Only reference closure, exact source quotations and content bindings are enforced
mechanically. Category, tax effect, explanation and resolution are supplied by
the model/professional; no name, code prefix or amount classifies an anomaly.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Callable

from lipe_core import ContractError, digest, engine_hash, rules_hash

__all__ = ["assess_observations", "review_bindings"]


def _quoted(value: str, quote: str) -> bool:
    """Match a transcribed field with boundaries, ignoring whitespace and case."""
    normalized = " ".join(quote.split()).casefold()
    token = re.escape(" ".join(value.split()).casefold())
    return re.search(r"(?<!\w)" + token + r"(?!\w)", normalized) is not None


def _check_date(value: str, quote: str) -> None:
    parsed = date.fromisoformat(value)
    if not any(
        _quoted(candidate, quote)
        for candidate in (
            value,
            parsed.strftime("%d/%m/%Y"),
            parsed.strftime("%d.%m.%Y"),
        )
    ):
        raise ContractError("Date absent from source quotation")


def review_bindings(case: dict, observation: dict) -> dict[str, str]:
    """Identify the facts and proposal being reviewed, not the reviewer's identity."""
    return {
        "facts_hash": digest(
            {
                key: value
                for key, value in case.items()
                if key not in {"observations", "correspondence"}
            }
        ),
        "observation_hash": digest(
            {key: value for key, value in observation.items() if key != "decision"}
        ),
        "engine_hash": engine_hash(),
        "rules_hash": rules_hash(),
    }


def assess_observations(
    case: dict,
    reconciliation: list[dict],
    findings: list[dict],
    reference: Callable[[dict], str],
    check_amount: Callable[[str, str, str], None],
    blockers: list[str],
) -> list[dict]:
    """Reject unsupported references and surface missing/stale declared decisions."""
    review = case["anomaly_review"]
    if review is None or review["status"] != "CONFIRMED":
        blockers.append("ANOMALY_REVIEW_NOT_CONFIRMED")
    periods = {module["period"] for module in case["modules"]}
    rows = {row["row_id"] for register in case["registers"] for row in register["rows"]}
    comparisons = {item["comparison_id"]: item for item in reconciliation}
    finding_ids = {item["finding_id"]: item for item in findings}
    seen: set[str] = set()
    output = []
    for observation in case["observations"]:
        identity = observation["observation_id"]
        if identity in seen:
            raise ContractError("Duplicate observation_id")
        seen.add(identity)
        if not set(observation["periods"]).issubset(periods):
            raise ContractError("Observation outside the selected quarter")
        if not set(observation["row_ids"]).issubset(rows):
            raise ContractError("Observation references unknown register rows")
        for ref in observation["evidence"]:
            reference(ref)
        for document in observation["documents"]:
            quote = reference(document["evidence"])
            for field in ("protocol", "invoice_number", "counterparty"):
                if document[field] is not None and not _quoted(document[field], quote):
                    raise ContractError(
                        f"Document {field} absent from source quotation"
                    )
            if document["date"]:
                _check_date(document["date"], quote)
            if document["amount"] is not None:
                if document["amount_basis"] is None:
                    raise ContractError("Document amount requires its stated basis")
                check_amount(document["amount"], quote, document["number_format"])
        effect_periods = [item["period"] for item in observation["vp6_effect"]]
        if len(effect_periods) != len(set(effect_periods)) or not set(
            effect_periods
        ).issubset(observation["periods"]):
            raise ContractError("Invalid or duplicate observation effect period")
        for comparison_id in observation["related_comparisons"]:
            if comparison_id not in comparisons:
                raise ContractError("Observation references unknown reconciliation")
            if comparisons[comparison_id]["period"] not in observation["periods"]:
                raise ContractError("Observation and reconciliation periods differ")
        for finding_id in observation["related_findings"]:
            if finding_id not in finding_ids:
                raise ContractError("Observation references unknown mechanical finding")
            if finding_ids[finding_id]["period"] not in observation["periods"]:
                raise ContractError("Observation and mechanical finding periods differ")
        bindings = review_bindings(case, observation)
        decision = observation["decision"]
        state = "OPEN"
        if decision and decision["review"]["status"] == "CONFIRMED":
            state = (
                "RESOLUTION_RECORDED"
                if decision["bindings"] == bindings
                else "STALE_DECISION"
            )
        if state != "RESOLUTION_RECORDED":
            blockers.append(f"OBSERVATION_{state}:{identity}")
        item = dict(observation, state=state, review_bindings=bindings)
        output.append(item)
        for comparison_id in observation["related_comparisons"]:
            comparisons[comparison_id]["explanations"].append(
                {
                    "observation_id": identity,
                    "assessment": observation["assessment"],
                    "state": state,
                    "resolution": decision["resolution"] if decision else None,
                }
            )
    correspondence = case["correspondence"]
    if correspondence and correspondence["filing_deadline"]:
        deadline = correspondence["filing_deadline"]
        _check_date(deadline["date"], reference(deadline["evidence"]))
    return output
