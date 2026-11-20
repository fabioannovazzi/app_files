"""Carry receipt-replayed matcher results into the semantic controller.

This restores mechanically established cash relationships, not a new name
classifier. Accounting treatment and invoice allocation remain separate.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

__all__ = ["admit_local_matches", "review_population", "residual_cash_passes"]


def admit_local_matches(
    bank: Sequence[Mapping[str, Any]],
    journal: Sequence[Mapping[str, Any]],
    relationship: Mapping[str, Any],
    matches: Sequence[Mapping[str, str]],
    purpose: str,
    *,
    evidence_version: int = 3,
) -> list[dict[str, Any]]:
    """Restore connected match groups from the source-replayed local pass."""
    import bank_first as bf

    if evidence_version not in {1, 2, 3}:
        raise ValueError("Unsupported local evidence version")
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
        # Tolerance discovers candidates; it does not establish their identity.
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
        # Preserve source identity evidence for accounting carry-forward. The
        # legacy projection remains available only for exact saved-run replay.
        fields = ("transaction_date", "amount_signed", "description")
        if evidence_version >= 2:
            fields += ("reference", "movement_number", "beneficiary", "party_ref")
        evidence = [
            bf._citation(s, records[s][i], field)
            for s in ids
            for i in ids[s]
            for field in fields
            if records[s][i].get(field)
        ]
        corroborated = True
        if evidence_version >= 3 and purpose == "bank_open_items" and difference:
            # A unique near amount alone caused a false cash link in the PDF
            # benchmark. Only an unambiguous shared source reference can close
            # it locally; fee explanations and other context remain semantic.
            references = {
                side: {bf._text(records[side][i].get("reference")) for i in ids[side]}
                for side in ids
            }
            corroborated = (
                len(ids["bank"]) == len(ids["journal"]) == 1
                and len(references["bank"]) == 1
                and references["bank"] == references["journal"]
                and "" not in references["bank"]
                and all(
                    sum(
                        bf._text(r.get("reference")) in references[side]
                        for r in records[side].values()
                    )
                    == 1
                    for side in ids
                )
                and not (
                    records["bank"][ids["bank"][0]].get("party_ref")
                    and records["journal"][ids["journal"][0]].get("party_ref")
                    and bf._text(records["bank"][ids["bank"][0]]["party_ref"])
                    != bf._text(records["journal"][ids["journal"][0]]["party_ref"])
                )
            )
        content = {
            "bank_ids": ids["bank"],
            "journal_ids": ids["journal"],
            "rule_id": "receipt_replayed_local_match.v1",
            "scope": list(bf._scope(rows[0], relationship)),
            "evidence_class": "sure" if corroborated else "probable",
            "reasons": (
                [] if corroborated else ["nonzero_cash_difference_needs_corroboration"]
            ),
            "evidence": evidence,
            "local_cash_match": True,
            "cash_only": purpose == "bank_open_items",
            "bank_sum": bf._money(sums["bank"]),
            "journal_sum": bf._money(sums["journal"]),
            "difference": bf._money(difference),
            "confirmed_discrepancy": difference != 0 and corroborated,
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


def residual_cash_passes(
    bank: Sequence[Mapping[str, Any]],
    journal: Sequence[Mapping[str, Any]],
    relationship: Mapping[str, Any],
    accepted: Sequence[Mapping[str, Any]],
    purpose: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Exact residual cash proposals, with semantic aggregates left unallocated.

    Date/amount conservation and disjoint membership are mechanical. These
    links do not establish invoice identity or correct accounting treatment.
    """
    from collections import defaultdict
    from datetime import date
    from itertools import combinations

    import bank_first as bf

    if (
        relationship.get("open_item_allocation_authorized")
        or relationship.get("direction_policy", "same_sign") != "same_sign"
    ):
        return [], []
    used = {
        side: {i for g in accepted for i in g[side + "_ids"]}
        for side in ("bank", "journal")
    }
    buckets = {side: defaultdict(list) for side in used}
    for side, rows in (("bank", bank), ("journal", journal)):
        for row in rows:
            if row["transaction_id"] in used[side]:
                continue
            scope = bf._scope(row, relationship)
            try:
                day = date.fromisoformat(str(row.get("transaction_date", "")))
            except ValueError:
                continue
            amount = bf.cents(row["amount_signed"])
            if all(scope) and amount:
                buckets[side][(scope, day.isoformat(), amount)].append(row)

    def compatible(left, right):
        # A conflicting explicit identity must not be overridden by arithmetic.
        for field in ("party_ref", "reference"):
            a = {str(r[field]).strip() for r in left if r.get(field)}
            b = {str(r[field]).strip() for r in right if r.get(field)}
            if a and b and a != b:
                return False
        return True

    local = []
    for key in sorted(buckets["bank"].keys() & buckets["journal"].keys()):
        left, right = buckets["bank"][key], buckets["journal"][key]
        if len(left) != len(right) or not compatible(left, right):
            continue
        repeated = len(left) > 1
        if repeated and (
            relationship.get("relationship_shape") != "many_to_many"
            or not all(
                any(
                    token in str(r.get("description", "")).casefold()
                    for token in ("commission", "bank fee", "bank charge")
                )
                for r in left
            )
        ):
            continue
        # Connected edges express group membership, not arbitrary individual pairs.
        edges = [
            {
                "bank_transaction_id": l["transaction_id"],
                "journal_transaction_id": right[0]["transaction_id"],
            }
            for l in left
        ]
        edges += [
            {
                "bank_transaction_id": left[0]["transaction_id"],
                "journal_transaction_id": r["transaction_id"],
            }
            for r in right[1:]
        ]
        group = admit_local_matches(left, right, relationship, edges, purpose)[0]
        group["rule_id"] = (
            "residual_same_day_fee_group.v1"
            if repeated
            else "residual_same_day_unique.v1"
        )
        group["evidence_sha256"] = bf.digest(
            {k: v for k, v in group.items() if k != "evidence_sha256"}
        )
        local.append(group)
        for side in used:
            used[side].update(group[side + "_ids"])

    residual = {side: defaultdict(list) for side in used}
    for side in used:
        for (scope, day, amount), rows in buckets[side].items():
            residual[side][(scope, day, amount > 0)].extend(
                r for r in rows if r["transaction_id"] not in used[side]
            )
    probable = []
    # Bound combinatorial work; skipped dense populations remain in semantic scope.
    budget = 4096
    for source, target in (("bank", "journal"), ("journal", "bank")):
        for key in sorted(residual[source].keys() & residual[target].keys()):
            for row in sorted(residual[target][key], key=lambda r: r["transaction_id"]):
                pool = sorted(
                    (
                        r
                        for r in residual[source][key]
                        if abs(bf.cents(r["amount_signed"]))
                        < abs(bf.cents(row["amount_signed"]))
                    ),
                    key=lambda r: r["transaction_id"],
                )
                for size in (2, 3):
                    for combo in combinations(pool, size):
                        if budget == 0:
                            return local, probable
                        budget -= 1
                        if sum(bf.cents(r["amount_signed"]) for r in combo) != bf.cents(
                            row["amount_signed"]
                        ):
                            continue
                        if not compatible(combo, [row]):
                            continue
                        probable.append(
                            {
                                source + "_ids": [r["transaction_id"] for r in combo],
                                target + "_ids": [row["transaction_id"]],
                                "rule_id": "residual_same_day_subset_candidate.v1",
                                "evidence_class": "probable",
                                "reasons": ["exact_sum_does_not_establish_identity"],
                            }
                        )
    return local, probable
