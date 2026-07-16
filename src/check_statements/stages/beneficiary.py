from __future__ import annotations

from typing import Any, Callable, Sequence

try:
    # Optional alias memory (global rules); tolerate absence in minimal test envs
    from src.check_statements.alias_memory import load_alias_rules, apply_alias_to_norm  # type: ignore
    from src.parsers.extractors import normalise_name  # type: ignore
except Exception:  # pragma: no cover - keep stage working without alias module
    def load_alias_rules():  # type: ignore
        return {}

    def apply_alias_to_norm(s: str, m: dict[str, str]) -> str:  # type: ignore
        return s

    def normalise_name(s: str) -> str:  # type: ignore
        return s.strip().lower()

from src.check_statements.candidate_graph import CandidateGraph
from src.check_statements.party_normalisation import (
    _clean_party_for_evidence,
    _preferred_bank_party,
    _preferred_ledger_party,
)


def _stage6_beneficiary_invoice(
    bank: Sequence["Transaction"],
    ledger: Sequence["Transaction"],
    bank_candidates: list[list[int]],
    matched_pairs: list[tuple[int, int | None, str]],
    matched_bank_indices: set[int],
    matched_ledger_indices: set[int],
    *,
    within_tolerance: Callable[["Transaction", "Transaction"], bool],
    within_date: Callable[["Transaction", "Transaction"], bool],
    beneficiary_similarity_fn: Callable[[str, str], float],
    sim_threshold: float = 85.0,
    candidate_graph: CandidateGraph | None = None,
    assign: bool = True,
) -> dict:
    """Stage 6 – beneficiary-based matches (no IBAN) within amount/date window.

    Greedy assignment by highest beneficiary similarity, tie-broken by nearest date.
    """
    counters: dict[str, Any] = {
        "stage6_beneficiary": 0,
        "accepted_indices": [],
        "considered_indices": [],
        "present_not_considered": [],
        "considered_not_accepted": [],
        "beneficiary_hits": [],
    }
    bank_meta = [getattr(t, "metadata", {}) or {} for t in bank]
    ledger_meta = [getattr(t, "metadata", {}) or {} for t in ledger]

    def _resolve_lang(meta: dict[str, Any]) -> str | None:
        value = meta.get("language") or meta.get("lang")
        return value if isinstance(value, str) and value.strip() else None

    bank_langs = [_resolve_lang(meta) for meta in bank_meta]
    ledger_langs = [_resolve_lang(meta) for meta in ledger_meta]
    b_iban = [(m.get("iban") or "") for m in bank_meta]
    l_iban = [(m.get("iban") or "") for m in ledger_meta]
    bank_names = [
        _clean_party_for_evidence(_preferred_bank_party(tx, meta), lang)
        for (tx, meta, lang) in zip(bank, bank_meta, bank_langs)
    ]
    ledger_names = [
        _clean_party_for_evidence(_preferred_ledger_party(tx, meta), lang)
        for (tx, meta, lang) in zip(ledger, ledger_meta, ledger_langs)
    ]
    # Apply learned alias rules globally (V1): map both sides to a canonical
    # normalised form to increase similarity for recurring counterparties.
    try:
        _alias_map = load_alias_rules()
    except Exception:  # pragma: no cover
        _alias_map = {}
    if _alias_map:
        def _canon(x: str) -> str:
            if not x:
                return x
            try:
                n = normalise_name(x)
            except Exception:
                n = x.strip().lower()
            try:
                return apply_alias_to_norm(n, _alias_map)
            except Exception:
                return n
        bank_names = [_canon(x) if x else x for x in bank_names]
        ledger_names = [_canon(x) if x else x for x in ledger_names]

    edges: list[tuple[float, int, int, int]] = []  # (-sim, dd, bi, li)
    for bi, b in enumerate(bank):
        if bi in matched_bank_indices:
            continue
        for li in bank_candidates[bi]:
            if li in matched_ledger_indices:
                continue
            # Skip candidates with an IBAN only when the bank row also has IBAN,
            # so IBAN equality can take precedence at Stage 7. If the bank
            # side lacks IBAN, allow beneficiary matching to proceed.
            if l_iban[li] and b_iban[bi]:
                continue
            l = ledger[li]
            if not within_tolerance(b, l) or not within_date(b, l):
                continue
            b_name = bank_names[bi]
            l_name = ledger_names[li]
            if not b_name or not l_name:
                continue
            # Compute similarity in upper case (downstream uses case-insensitive fuzz)
            sim = beneficiary_similarity_fn((b_name or "").upper(), (l_name or "").upper()) * 100.0
            if sim >= sim_threshold:
                if candidate_graph is not None:
                    for edge in candidate_graph.edges_for_bank(bi):
                        if edge.ledger_index == li:
                            if "beneficiary" not in edge.labels:
                                edge.labels.append("beneficiary")
                            break
                if bi not in counters["beneficiary_hits"]:
                    counters["beneficiary_hits"].append(bi)
                dd = abs((b.date - l.date).days)
                edges.append((-float(sim), dd, bi, li))
                counters["considered_indices"].append(bi)
    # Track bank rows that have a beneficiary (and no IBAN) but weren't considered (no viable candidates)
    for bi, b in enumerate(bank):
        if bi in matched_bank_indices:
            continue
        if b_iban[bi]:
            continue
        if bank_names[bi]:
            counters["present_not_considered"].append(bi)
    if not edges:
        cons = set(counters["considered_indices"])
        counters["present_not_considered"] = [i for i in counters["present_not_considered"] if i not in cons]
        return counters
    edges.sort(key=lambda x: (x[0], x[1], x[2], x[3]))
    taken_b: set[int] = set()
    taken_l: set[int] = set()
    for _neg_sim, _dd, bi, li in edges:
        if bi in matched_bank_indices or li in matched_ledger_indices:
            continue
        if assign and (bi in taken_b or li in taken_l):
            continue
        if assign:
            matched_pairs.append((bi, li, "beneficiary"))
            matched_bank_indices.add(bi)
            matched_ledger_indices.add(li)
            counters["stage6_beneficiary"] += 1
            counters["accepted_indices"].append(bi)
            taken_b.add(bi)
            taken_l.add(li)
    # Compute considered but not accepted
    acc = set(counters["accepted_indices"])
    cons = set(counters["considered_indices"])
    counters["considered_not_accepted"] = [i for i in cons if i not in acc]
    counters["present_not_considered"] = [i for i in counters["present_not_considered"] if i not in cons]
    return counters
