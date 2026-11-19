"""Local candidate tools for a model-directed reconciliation investigation.

Every result is a candidate, never an accepted link. Names and narrative context
are not adjudicated here; exact arithmetic and source membership are mechanical.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from itertools import combinations
from typing import Any, Mapping, Sequence

import bank_first as bf
from reconciliation_expression import evaluate_candidates

__all__ = ["discover", "catalogue"]


def catalogue() -> list[dict[str, str]]:
    return [
        {
            "name": "date_window",
            "purpose": "Equal signed amounts within a chosen day window; keep competing links.",
        },
        {
            "name": "reference_normalized",
            "purpose": "Group explicit references ignoring punctuation and case, preserving letters/digits.",
        },
        {
            "name": "subset_sum",
            "purpose": "Exact two/three-row aggregates; can include signed settlement fees.",
        },
        {
            "name": "reversals",
            "purpose": "Find opposite entries within the bank source; cancellation is not ledger reconciliation.",
        },
        {
            "name": "generated_expression",
            "purpose": "Run a bounded data-only Python expression returning candidate memberships.",
        },
    ]


def discover(
    name: str,
    bank: Sequence[Mapping[str, Any]],
    journal: Sequence[Mapping[str, Any]],
    relationship: Mapping[str, Any],
    *,
    window_days: int = 7,
    expression: str = "",
    limit: int = 64,
    operations: int = 4096,
) -> dict[str, Any]:
    """Return bounded, unallocated candidates with explicit search completeness."""
    if name not in {entry["name"] for entry in catalogue()}:
        raise ValueError("Unknown discovery routine")
    if (
        not 0 <= window_days <= 90
        or not 1 <= limit <= 128
        or not 1 <= operations <= 100_000
    ):
        raise ValueError("Invalid discovery bounds")
    rows = {"bank": bf._records(bank), "journal": bf._records(journal)}
    candidates: list[dict[str, Any]] = []
    examined = 0
    truncated = False

    def day(row):
        try:
            return date.fromisoformat(str(row.get("transaction_date", ""))).toordinal()
        except ValueError:
            return None

    def compatible(left, right):
        scope = {bf._scope(row, relationship) for row in [*left, *right]}
        return len(scope) == 1 and all(next(iter(scope)))

    def add(left, right, kind):
        if not compatible(left, right):
            return
        candidates.append(
            {
                "bank_ids": sorted(r["transaction_id"] for r in left),
                "journal_ids": sorted(r["transaction_id"] for r in right),
                "kind": kind,
                "bank_cents": sum(bf.cents(r["amount_signed"]) for r in left),
                "journal_cents": sum(bf.cents(r["amount_signed"]) for r in right),
                "status": "candidate_only",
            }
        )

    def room():
        nonlocal examined, truncated
        examined += 1
        if examined > operations or len(candidates) >= limit:
            truncated = True
            return False
        return True

    b = sorted(rows["bank"].values(), key=lambda r: r["transaction_id"])
    j = sorted(rows["journal"].values(), key=lambda r: r["transaction_id"])
    if name == "generated_expression":
        inputs = {
            side: [
                {**r, "cents": bf.cents(r["amount_signed"]), "day": day(r)}
                for r in records.values()
            ]
            for side, records in rows.items()
        }
        found = evaluate_candidates(
            expression, inputs["bank"], inputs["journal"], max_steps=operations
        )
        for item in found:
            if set(item) != {"bank_ids", "journal_ids"}:
                raise ValueError("Generated discovery may return membership only")
            for side in rows:
                ids = item[side + "_ids"]
                if (
                    not isinstance(ids, list)
                    or not ids
                    or len(ids) != len(set(ids))
                    or any(i not in rows[side] for i in ids)
                ):
                    raise ValueError("Generated candidate escapes supplied sources")
            if not room():
                break
            add(
                [rows["bank"][i] for i in item["bank_ids"]],
                [rows["journal"][i] for i in item["journal_ids"]],
                name,
            )
    elif name == "reference_normalized":
        groups = defaultdict(lambda: {"bank": [], "journal": []})
        for side, records in rows.items():
            for row in records.values():
                ref = "".join(
                    c for c in str(row.get("reference", "")).casefold() if c.isalnum()
                )
                if ref:
                    groups[(bf._scope(row, relationship), ref)][side].append(row)
        for key in sorted(groups):
            group = groups[key]
            if not room():
                break
            if group["bank"] and group["journal"]:
                add(group["bank"], group["journal"], name)
    elif name == "date_window":
        for left in b:
            for right in j:
                if not room():
                    break
                if (
                    day(left) is not None
                    and day(right) is not None
                    and abs(day(left) - day(right)) <= window_days
                    and bf.cents(left["amount_signed"])
                    == bf.cents(right["amount_signed"])
                ):
                    add([left], [right], name)
            if truncated:
                break
    elif name == "reversals":
        for left, right in combinations(b, 2):
            if not room():
                break
            if (
                day(left) is not None
                and day(right) is not None
                and abs(day(left) - day(right)) <= window_days
                and bf.cents(left["amount_signed"])
                and bf.cents(left["amount_signed"]) == -bf.cents(right["amount_signed"])
            ):
                add([left, right], [], name)
    else:
        for source, targets, reverse in ((b, j, False), (j, b, True)):
            for target in targets:
                pool = [
                    r
                    for r in source
                    if day(r) is not None
                    and day(target) is not None
                    and abs(day(r) - day(target)) <= window_days
                    and compatible([r], [target])
                ]
                for size in (2, 3):
                    for group in combinations(pool, size):
                        if not room():
                            break
                        if sum(bf.cents(r["amount_signed"]) for r in group) == bf.cents(
                            target["amount_signed"]
                        ):
                            add(
                                [target] if reverse else list(group),
                                list(group) if reverse else [target],
                                name,
                            )
                    if truncated:
                        break
                if truncated:
                    break
            if truncated:
                break
    return {
        "routine": name,
        "candidates": candidates,
        "examined": min(examined, operations),
        "truncated": truncated,
        "search_is_exhaustive": not truncated,
        "accepted_matches": 0,
    }
