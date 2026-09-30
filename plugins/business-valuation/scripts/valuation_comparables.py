"""Source-bound peer decisions and explicit numerator/denominator reconciliations.

Fixed identity, date and arithmetic checks enforce the supplied workpaper contract.
They neither select peers nor judge economic or accounting comparability.
"""

from __future__ import annotations

from valuation_engine import Ledger, ValuationError

__all__ = ["comparable_evidence", "calculate_comparables", "BASIS_LABELS"]

BASIS_LABELS = {
    "initial_universe": "Universo iniziale e ricerca",
    "selection_reason": "Scelta del multiplo applicato",
    "date_alignment": "Allineamento delle date e dei periodi",
    "accounting_alignment": "Principi contabili e normalizzazioni",
    "lease_alignment": "Leasing: metrica, valore operativo e debito",
    "margin_analysis": "Differenze di marginalità",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValuationError(message)


def comparable_evidence(method: dict, mandate: dict, sources: dict) -> dict:
    """Check explicit evidence and period labels without scoring candidate fit."""
    review = method["comparables"]
    target = review["target"]
    records = [review, target, *review["peers"]]
    identities = [row["entity_id"] for row in review["peers"]]
    ids = [row["id"] for row in review["peers"]]
    _require(len(ids) == len(set(ids)), "Duplicate comparable candidate ID")
    _require(
        len(identities) == len(set(identities)),
        "The same declared comparable entity cannot appear twice",
    )
    cutoff = mandate["information_cutoff"]
    for row in [target, *(p for p in review["peers"] if p["decision"] == "include")]:
        data = row if row is target else row["data"]
        _require(
            data["period_start"] <= data["period_end"],
            "Comparable metric period ends before it starts",
        )
        _require(
            data["published_on"] <= cutoff,
            "Comparable evidence was published after the information cutoff",
        )
        if data["period_kind"] == "LTM":
            _require(
                data["period_end"] <= data["published_on"],
                "An LTM observation cannot end after its publication",
            )
        _require(
            data["period_kind"] == target["period_kind"]
            and data["lease_basis"] == target["lease_basis"]
            and data["metric_basis"] == target["metric_basis"],
            "Included peers and target require the same declared period, metric and lease bases",
        )
        if row is not target:
            _require(
                data["kind"] == method["inputs"]["kind"],
                "Included peer multiple kind differs from the target method",
            )
            _require(
                data["price_date"] <= min(cutoff, mandate["valuation_date"]),
                "Comparable price date exceeds valuation date or information cutoff",
            )
    source_ids = sorted({ref for row in records for ref in row["source_ids"]})
    _require(
        set(source_ids) <= sources.keys(),
        "Comparable decisions require declared evidence sources",
    )
    return {
        "source_ids": source_ids,
        "complete": all(row["status"] == "confirmed" for row in records),
    }


def _reconcile(ledger: Ledger, prefix: str, record: dict) -> dict:
    """Reconcile supplied reported amounts and signed adjustments exactly."""
    refs = record["adjustment_inputs"]
    _require(
        len(refs) == len(set(refs))
        and not set(refs) & {record["reported_input"], record["comparable_input"]},
        "Comparable adjustments must be distinct from each other and their totals",
    )
    _require(
        not refs or record["reported_input"] != record["comparable_input"],
        "Adjusted comparable totals require an independently supplied input",
    )
    money = lambda ref: ledger.input(ref, ledger.currency)
    reported = money(record["reported_input"])
    adjustments = [money(ref) for ref in refs]
    supplied = money(record["comparable_input"])
    computed = ledger.add(f"{prefix}/reconciled", "sum", [reported, *adjustments])
    difference = ledger.add(f"{prefix}/difference", "subtract", [supplied, computed])
    _require(
        ledger.value(difference) == 0,
        "Comparable amount does not reconcile to reported amount and signed adjustments",
    )
    return {
        "reported_id": reported,
        "adjustment_ids": adjustments,
        "comparable_id": supplied,
        "computed_id": computed,
        "difference_id": difference,
    }


def calculate_comparables(ledger: Ledger, method: dict) -> dict:
    """Expose each selected peer ratio; leave the applied multiple independently supplied."""
    review = method["comparables"]
    included = [row for row in review["peers"] if row["decision"] == "include"]
    _require(
        bool(included), "No comparable was included; exclude the unsupported method"
    )
    target = review["target"]["metric"]
    _require(
        target["comparable_input"] == method["inputs"]["metric"],
        "Comparable target metric must be the metric actually valued",
    )
    schedule: dict = {
        "target": _reconcile(ledger, "comparables/target", target),
        "peers": [],
    }
    for peer in included:
        data = peer["data"]
        prefix = f"comparables/{peer['id']}"
        numerator = _reconcile(ledger, prefix + "/numerator", data["numerator"])
        metric = _reconcile(ledger, prefix + "/metric", data["metric"])
        _require(
            numerator["comparable_id"] != metric["comparable_id"],
            "Peer numerator and metric require independent amounts",
        )
        _require(
            ledger.value(numerator["comparable_id"]) > 0
            and ledger.value(metric["comparable_id"]) > 0,
            "Included comparable numerator and metric must be positive; record unsupported peers as excluded",
        )
        multiple = ledger.add(
            prefix + "/multiple",
            "divide",
            [numerator["comparable_id"], metric["comparable_id"]],
            "multiple",
        )
        schedule["peers"].append(
            {
                "id": peer["id"],
                "numerator": numerator,
                "metric": metric,
                "multiple_id": multiple,
            }
        )
    return schedule
