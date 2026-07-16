from __future__ import annotations

from typing import Callable, Mapping, Sequence

from src.check_statements.classify import classify_op
from src.check_statements.candidate_graph import CandidateGraph


def _resolve_op_type(tx: "Transaction") -> str:
    """Return the operation type using description and metadata context."""
    meta: Mapping[str, object] | None
    try:
        meta = tx.metadata  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - defensive against unexpected attrs
        meta = None
    if not isinstance(meta, Mapping):
        meta = {}
    raw = meta.get("op_type")
    if isinstance(raw, str) and raw.strip():
        return raw.strip().upper()
    lang = None
    try:
        lang = meta.get("language") or meta.get("lang")
    except Exception:
        lang = None
    parts: list[str] = []
    desc = getattr(tx, "description", "") or ""
    if desc:
        parts.append(str(desc))
    extra_desc = meta.get("extra_desc")
    if isinstance(extra_desc, str) and extra_desc.strip():
        parts.append(extra_desc)
    details = meta.get("details")
    if isinstance(details, str) and details.strip():
        parts.append(details)
    combined = " ".join(parts)
    return classify_op(combined, lang)


def _stage3_cash(
    bank: Sequence["Transaction"],
    ledger: Sequence["Transaction"],
    bank_candidates: list[list[int]],
    matched_pairs: list[tuple[int, int | None, str]],
    matched_bank_indices: set[int],
    matched_ledger_indices: set[int],
    *,
    within_tolerance: Callable[["Transaction", "Transaction"], bool],
    within_date: Callable[["Transaction", "Transaction"] , bool],
    candidate_graph: CandidateGraph | None = None,
    assign: bool = True,
) -> dict:
    """Match ATM withdrawals on both sides using amount and date proximity."""
    counters: dict[str, int | list[int]] = {"cash": 0, "accepted_indices": []}
    use_graph = candidate_graph is not None
    for bi, b in enumerate(bank):
        if bi in matched_bank_indices:
            continue
        b_op = _resolve_op_type(b)
        if b_op != "ATM":
            continue
        best = None
        best_dd = None
        base_candidates = bank_candidates[bi]
        scan_indices = base_candidates if base_candidates else list(range(len(ledger)))
        for li in scan_indices:
            if li in matched_ledger_indices:
                continue
            l = ledger[li]
            l_op = _resolve_op_type(l)
            if l_op != "ATM":
                continue
            if not within_tolerance(b, l) or not within_date(b, l):
                continue
            if use_graph:
                for edge in candidate_graph.edges_for_bank(bi):
                    if edge.ledger_index == li:
                        edge.labels.append("cash")
                        break
            dd = abs((b.date - l.date).days)
            if best is None or dd < best_dd:
                best = li
                best_dd = dd
        if best is not None and assign:
            matched_pairs.append((bi, best, "cash"))
            matched_bank_indices.add(bi)
            matched_ledger_indices.add(best)
            counters["cash"] = int(counters["cash"]) + 1  # type: ignore[index]
            counters["accepted_indices"].append(bi)  # type: ignore[index]
    return counters


def _stage4_card(
    bank: Sequence["Transaction"],
    ledger: Sequence["Transaction"],
    bank_candidates: list[list[int]],
    matched_pairs: list[tuple[int, int | None, str]],
    matched_bank_indices: set[int],
    matched_ledger_indices: set[int],
    *,
    within_tolerance: Callable[["Transaction", "Transaction"], bool],
    within_date: Callable[["Transaction", "Transaction"], bool],
    candidate_graph: CandidateGraph | None = None,
    assign: bool = True,
) -> dict:
    """Match card payments when both sides share the same operation type."""
    counters: dict[str, int | list[int]] = {"card": 0, "accepted_indices": []}
    use_graph = candidate_graph is not None
    for bi, b in enumerate(bank):
        if bi in matched_bank_indices:
            continue
        b_op = _resolve_op_type(b)
        if b_op != "CARD":
            continue
        best = None
        best_dd = None
        base_candidates = bank_candidates[bi]
        scan_indices = base_candidates if base_candidates else list(range(len(ledger)))
        for li in scan_indices:
            if li in matched_ledger_indices:
                continue
            l = ledger[li]
            l_op = _resolve_op_type(l)
            if l_op != "CARD":
                continue
            if not within_tolerance(b, l) or not within_date(b, l):
                continue
            if use_graph:
                for edge in candidate_graph.edges_for_bank(bi):
                    if edge.ledger_index == li:
                        edge.labels.append("card")
                        break
            dd = abs((b.date - l.date).days)
            if best is None or dd < best_dd:
                best = li
                best_dd = dd
        if best is not None and assign:
            matched_pairs.append((bi, best, "card"))
            matched_bank_indices.add(bi)
            matched_ledger_indices.add(best)
            counters["card"] = int(counters["card"]) + 1  # type: ignore[index]
            counters["accepted_indices"].append(bi)  # type: ignore[index]
    return counters
