"""Carry receipt-replayed matcher results into the semantic controller.

This restores mechanically established cash relationships, not a new name
classifier. Accounting treatment and invoice allocation remain separate.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

__all__ = ["admit_local_matches", "review_population"]


def admit_local_matches(
    bank: Sequence[Mapping[str, Any]],
    journal: Sequence[Mapping[str, Any]],
    relationship: Mapping[str, Any],
    matches: Sequence[Mapping[str, str]],
    purpose: str,
) -> list[dict[str, Any]]:
    """Restore connected match groups from the source-replayed local pass."""
    import bank_first as bf

    if relationship.get("open_item_allocation_authorized"):
        raise ValueError("Journal matcher results cannot authorize invoice allocation")
    records = {"bank": bf._records(bank), "journal": bf._records(journal)}
    components: list[tuple[set[str], set[str]]] = []
    edges = set()
    for match in matches:
        left, right = match["bank_transaction_id"], match["journal_transaction_id"]
        if left not in records["bank"] or right not in records["journal"]:
            raise ValueError(
                "Local match references a row outside its source population"
            )
        if (left, right) in edges:
            raise ValueError("Duplicate local match edge")
        edges.add((left, right))
        b_ids, j_ids = {left}, {right}
        remaining = []
        for b, j in components:
            if b_ids & b or j_ids & j:
                b_ids |= b
                j_ids |= j
            else:
                remaining.append((b, j))
        components = [*remaining, (b_ids, j_ids)]

    accepted = []
    for b_ids, j_ids in components:
        ids = {
            "bank": [i for i in records["bank"] if i in b_ids],
            "journal": [i for i in records["journal"] if i in j_ids],
        }
        rows = [records[s][i] for s in ids for i in ids[s]]
        # The producer has already replayed the matcher and its reviewed scope,
        # direction and tolerance policy. Do not impose a second admission gate.
        sums = {
            s: sum(bf.cents(records[s][i]["amount_signed"]) for i in ids[s])
            for s in ids
        }
        direction = relationship.get("direction_policy", "same_sign")
        difference = (
            sums["bank"] - sums["journal"]
            if direction == "same_sign"
            else abs(sums["bank"]) - abs(sums["journal"])
        )
        evidence = [
            bf._citation(s, records[s][i], field)
            for s in ids
            for i in ids[s]
            for field in ("transaction_date", "amount_signed", "description")
            if records[s][i].get(field)
        ]
        content = {
            "bank_ids": ids["bank"],
            "journal_ids": ids["journal"],
            "rule_id": "receipt_replayed_local_match.v1",
            "scope": list(bf._scope(rows[0], relationship)),
            "evidence_class": "sure",
            "reasons": [],
            "evidence": evidence,
            "local_cash_match": True,
            "cash_only": purpose == "bank_open_items",
            "bank_sum": bf._money(sums["bank"]),
            "journal_sum": bf._money(sums["journal"]),
            "difference": bf._money(difference),
            "confirmed_discrepancy": difference != 0,
        }
        accepted.append({**content, "evidence_sha256": bf.digest(content)})
    return accepted


def review_population(
    bank: Sequence[Mapping[str, Any]],
    journal: Sequence[Mapping[str, Any]],
    admitted: Mapping[str, Any],
) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]]]:
    """Keep completed local cash work out of later searches and context."""
    closed = [g for g in admitted["sure"] if g.get("cash_only")]
    used = {
        side: {i for g in closed for i in g[side + "_ids"]}
        for side in ("bank", "journal")
    }
    return (
        [row for row in bank if row["transaction_id"] not in used["bank"]],
        [row for row in journal if row["transaction_id"] not in used["journal"]],
    )
