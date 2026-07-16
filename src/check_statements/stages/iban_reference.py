from __future__ import annotations

import re
from typing import Any, Callable, Sequence

from src.check_statements.candidate_graph import CandidateGraph

__all__ = (
    "_stage7_iban",
    "_stage8_reference",
    "_collect_reference_tokens",
)


def _normalise_token(token: str) -> str:
    return token.strip().upper()


def _split_tokens(values: list[str]) -> set[str]:
    toks: set[str] = set()
    for v in values:
        parts = re.split(r"[^A-Za-z0-9]+", v or "")
        for part in parts:
            if not part:
                continue
            toks.add(_normalise_token(part))
    return toks


def _digits_only(token: str) -> str:
    return re.sub(r"[^0-9]", "", token)


_IBAN_PATTERN = re.compile(r"^[A-Z]{2}[0-9A-Z]{5,}$")


def _collect_reference_tokens(tx: "Transaction") -> set[str]:
    refs = list(tx.reference_ids or [])
    meta = getattr(tx, "metadata", {}) or {}
    for key in ("extra_desc", "details", "account_desc", "counter_account_desc"):
        value = meta.get(key)
        if isinstance(value, str) and value.strip():
            refs.append(value)
    if tx.description:
        refs.append(tx.description)
    base_tokens = _split_tokens(refs)
    tokens: set[str] = set()
    year_tokens = {str(y) for y in range(2018, 2031)}
    for tok in base_tokens:
        if _IBAN_PATTERN.match(tok):
            continue
        has_digit = any(ch.isdigit() for ch in tok)
        if not has_digit:
            continue
        if len(tok) >= 4:
            tokens.add(tok)
        digits = _digits_only(tok)
        if digits and digits not in year_tokens:
            if len(digits) >= 5:
                tokens.add(digits)
            elif len(digits) == 4 and digits not in year_tokens:
                tokens.add(digits)
    # Invoice-style patterns (FATT., INVOICE, etc.)
    joined = " ".join(refs)
    for pattern in (
        r"(?i)(?:fatt|ft|invoice|inv|facture|nota)\s*(?:n(?:o)?\.?\s*)?([A-Za-z0-9/\-]{3,})",
        r"\bN[.:]?\s*([A-Za-z0-9/\-]{3,})",
    ):
        for match in re.finditer(pattern, joined):
            candidate = _normalise_token(match.group(1))
            if _IBAN_PATTERN.match(candidate):
                continue
            if any(ch.isdigit() for ch in candidate) and len(candidate) >= 4:
                tokens.add(candidate)
            digits = _digits_only(candidate)
            if digits and digits not in year_tokens:
                if len(digits) >= 5:
                    tokens.add(digits)
                elif len(digits) == 4:
                    tokens.add(digits)
    return tokens


def _stage7_iban(
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
    """Stage 7 – IBAN equality within amount/date window with greedy nearest-date assignment."""
    counters: dict[str, Any] = {
        "stage7_iban": 0,
        "accepted_indices": [],
        "considered_indices": [],
        "present_no_equal": [],
        "considered_not_accepted": [],
    }
    b_iban = [((t.metadata or {}).get("iban") or "") for t in bank]
    l_iban = [((t.metadata or {}).get("iban") or "") for t in ledger]
    edges: list[tuple[int, int, int]] = []  # (dd, bi, li)
    use_graph = candidate_graph is not None
    for bi, b in enumerate(bank):
        if bi in matched_bank_indices:
            continue
        if not b_iban[bi]:
            continue
        for li in bank_candidates[bi]:
            if li in matched_ledger_indices:
                continue
            if not l_iban[li] or l_iban[li] != b_iban[bi]:
                continue
            l = ledger[li]
            if not within_tolerance(b, l) or not within_date(b, l):
                continue
            if use_graph:
                for edge in candidate_graph.edges_for_bank(bi):
                    if edge.ledger_index == li:
                        edge.labels.append("iban")
                        break
            dd = abs((b.date - l.date).days)
            edges.append((dd, bi, li))
            counters["considered_indices"].append(bi)
    for bi, b in enumerate(bank):
        if bi in matched_bank_indices:
            continue
        if b_iban[bi]:
            counters["present_no_equal"].append(bi)
    if not edges:
        return counters
    edges.sort(key=lambda x: (x[0], x[1], x[2]))
    taken_b: set[int] = set()
    taken_l: set[int] = set()
    for dd, bi, li in edges:
        if bi in matched_bank_indices or li in matched_ledger_indices:
            continue
        if assign and (bi in taken_b or li in taken_l):
            continue
        if assign:
            matched_pairs.append((bi, li, "iban"))
            matched_bank_indices.add(bi)
            matched_ledger_indices.add(li)
            taken_b.add(bi)
            taken_l.add(li)
            counters["stage7_iban"] += 1
            counters["accepted_indices"].append(bi)
    acc = set(counters["accepted_indices"])
    cons = set(counters["considered_indices"])
    counters["considered_not_accepted"] = [i for i in cons if i not in acc]
    counters["present_no_equal"] = [i for i in counters["present_no_equal"] if i not in cons]
    return counters


def _stage8_reference(
    bank: Sequence["Transaction"],
    ledger: Sequence["Transaction"],
    matched_pairs: list[tuple[int, int | None, str]],
    matched_bank_indices: set[int],
    matched_ledger_indices: set[int],
    *,
    within_tolerance: Callable[["Transaction", "Transaction"], bool],
    within_date: Callable[["Transaction", "Transaction"], bool],
    candidate_graph: CandidateGraph | None = None,
    assign: bool = True,
) -> dict:
    """Stage 8 – shared reference IDs within amount/date with greedy nearest-date assignment."""
    counters: dict[str, Any] = {"stage8_reference": 0, "accepted_indices": [], "considered_indices": []}
    ref_index: dict[str, list[int]] = {}
    for li, l in enumerate(ledger):
        if li in matched_ledger_indices:
            continue
        for ref in l.reference_ids or []:
            ref_index.setdefault(ref, []).append(li)
    edges: list[tuple[int, int, int]] = []  # (dd, bi, li)
    use_graph = candidate_graph is not None
    for bi, b in enumerate(bank):
        if bi in matched_bank_indices:
            continue
        refs = b.reference_ids or []
        if not refs:
            continue
        for ref in refs:
            for li in ref_index.get(ref, []):
                if li in matched_ledger_indices:
                    continue
                l = ledger[li]
                if not within_tolerance(b, l) or not within_date(b, l):
                    continue
                if use_graph:
                    for edge in candidate_graph.edges_for_bank(bi):
                        if edge.ledger_index == li:
                            edge.labels.append("reference")
                            break
                dd = abs((b.date - l.date).days)
                edges.append((dd, bi, li))
                counters["considered_indices"].append(bi)
    led_tokens: dict[int, set[str]] = {}
    for li, l in enumerate(ledger):
        if li in matched_ledger_indices:
            continue
        led_tokens[li] = _collect_reference_tokens(l)

    direct_considered = set(counters["considered_indices"])

    for bi, b in enumerate(bank):
        if bi in matched_bank_indices or bi in direct_considered:
            continue
        b_toks = _collect_reference_tokens(b)
        if not b_toks:
            continue
        for li, l_toks in led_tokens.items():
            if not l_toks or li in matched_ledger_indices:
                continue
            if b_toks.isdisjoint(l_toks):
                continue
            l = ledger[li]
            if not within_tolerance(b, l) or not within_date(b, l):
                continue
            if use_graph:
                for edge in candidate_graph.edges_for_bank(bi):
                    if edge.ledger_index == li:
                        edge.labels.append("reference")
                        break
            dd = abs((b.date - l.date).days)
            edges.append((dd, bi, li))
            counters["considered_indices"].append(bi)
    if not edges:
        return counters
    edges.sort(key=lambda x: (x[0], x[1], x[2]))
    taken_b: set[int] = set()
    taken_l: set[int] = set()
    for dd, bi, li in edges:
        if bi in matched_bank_indices or li in matched_ledger_indices:
            continue
        if assign and (bi in taken_b or li in taken_l):
            continue
        if assign:
            matched_pairs.append((bi, li, "reference"))
            matched_bank_indices.add(bi)
            matched_ledger_indices.add(li)
            taken_b.add(bi)
            taken_l.add(li)
            counters["stage8_reference"] += 1
            counters["accepted_indices"].append(bi)
    return counters
