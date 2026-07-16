from __future__ import annotations

from typing import Any, Callable, Sequence

from src.check_statements.classify import (
    classify_op,
    is_tax_ledger_entry as _is_tax_ledger_entry,
    _lex_for,
)
from src.check_statements.candidate_graph import CandidateEdge, CandidateGraph
from src.check_statements.party_normalisation import _ledger_payroll_text


def _stage5_category_gate(
    bank: Sequence["Transaction"],
    ledger: Sequence["Transaction"],
    bank_candidates: list[list[int]],
    matched_pairs: list[tuple[int, int | None, str]],
    matched_bank_indices: set[int],
    matched_ledger_indices: set[int],
    *,
    within_tolerance: Callable[["Transaction", "Transaction"], bool],
    within_date: Callable[["Transaction", "Transaction"], bool],
    tolerance: float,
    use_absolute_amounts: bool,
    candidate_graph: CandidateGraph | None = None,
    assign: bool = True,
) -> dict:
    """Stage 5 – accept category-specific rows when BOTH sides show the same evidence.

    Categories:
    - Payroll: BANK description mentions payroll synonyms AND LEDGER account is payroll‑labelled.
    - Tax/VAT (F24): BANK op classified as F24 OR bank row smells like tax, AND LEDGER is tax posting.
    """
    counters: dict[str, Any] = {
        "salary_gate": 0,
        "accepted_indices": [],
        "considered_indices": [],
        "payroll_hits": [],
        "tax_hits": [],
    }
    # Language-aware payroll tokens (normalised to upper case)
    payroll_kw_b: dict[int, tuple[str, ...]] = {}
    payroll_kw_l: dict[int, tuple[str, ...]] = {}

    def _payroll_tokens(lang: str | None) -> tuple[str, ...]:
        raw = _lex_for(lang).get("payroll_tokens", [])
        return tuple(str(token).casefold() for token in raw)

    ledger_payroll_text: dict[int, str] = {}
    use_graph = candidate_graph is not None

    def _label_edge(bi: int, li: int, label: str) -> None:
        if candidate_graph is None:
            return
        existing = None
        for edge in candidate_graph.edges_for_bank(bi):
            if edge.ledger_index == li:
                existing = edge
                break
        if existing is None:
            b_amt = abs(bank[bi].amount) if use_absolute_amounts else bank[bi].amount
            l_amt = abs(ledger[li].amount) if use_absolute_amounts else ledger[li].amount
            amt_delta = abs(b_amt - l_amt)
            dd = abs((bank[bi].date - ledger[li].date).days)
            existing = CandidateEdge(
                bank_index=bi,
                ledger_index=li,
                amount_delta=float(amt_delta),
                date_diff_days=dd,
            )
            candidate_graph.add_edge(existing)
        if label not in existing.labels:
            existing.labels.append(label)
    for bi, b in enumerate(bank):
        if bi in matched_bank_indices:
            continue
        desc = (b.description or "").strip().casefold()
        try:
            b_lang = (b.metadata or {}).get("language") or (b.metadata or {}).get("lang")
        except Exception:
            b_lang = None
        payroll_kw = payroll_kw_b.setdefault(bi, _payroll_tokens(b_lang))
        b_op = (b.metadata or {}).get("op_type") or classify_op(b.description, b_lang)
        # Payroll branch: bank mentions payroll AND ledger account payroll-like
        if any(k in desc for k in payroll_kw):
            counters["considered_indices"].append(bi)
            best = None
            best_dd = None
            base_candidates = bank_candidates[bi]
            scan_indices = base_candidates if base_candidates else list(range(len(ledger)))
            for li in scan_indices:
                if li in matched_ledger_indices:
                    continue
                l = ledger[li]
                meta = l.metadata or {}
                try:
                    l_lang = (meta or {}).get("language") or (meta or {}).get("lang")
                except Exception:
                    l_lang = None
                payroll_kw_l_i = payroll_kw_l.setdefault(li, _payroll_tokens(l_lang))
                ledger_text = ledger_payroll_text.get(li)
                if ledger_text is None:
                    ledger_text = _ledger_payroll_text(l, meta)
                    ledger_payroll_text[li] = ledger_text
                if not ledger_text:
                    continue
                if not any(k in ledger_text for k in payroll_kw_l_i):
                    continue
                # Payroll on both sides: accept by nearest date only (ignore amount diff)
                if not within_date(b, l):
                    continue
                if use_graph:
                    _label_edge(bi, li, "payroll")
                counters["payroll_hits"].append(bi)
                dd = abs((b.date - l.date).days)
                if best is None or dd < best_dd:
                    best = li
                    best_dd = dd
            if best is not None:
                if assign:
                    matched_pairs.append((bi, best, "salary_gate"))
                    matched_bank_indices.add(bi)
                    matched_ledger_indices.add(best)
                counters["salary_gate"] += 1
                counters["accepted_indices"].append(bi)
                continue
        # Tax/VAT branch: bank indicates taxes AND ledger looks like tax posting
        if b_op == "F24" or _is_tax_ledger_entry(b):
            counters["considered_indices"].append(bi)
            best = None
            best_dd = None
            for li in bank_candidates[bi]:
                if li in matched_ledger_indices:
                    continue
                l = ledger[li]
                if not _is_tax_ledger_entry(l):
                    continue
                if not within_tolerance(b, l) or not within_date(b, l):
                    continue
                if use_graph:
                    _label_edge(bi, li, "tax")
                counters["tax_hits"].append(bi)
                dd = abs((b.date - l.date).days)
                if best is None or dd < best_dd:
                    best = li
                    best_dd = dd
            if best is not None:
                if assign:
                    matched_pairs.append((bi, best, "salary_gate"))
                    matched_bank_indices.add(bi)
                    matched_ledger_indices.add(best)
                counters["salary_gate"] += 1
                counters["accepted_indices"].append(bi)
    return counters
