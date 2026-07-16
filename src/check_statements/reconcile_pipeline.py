from __future__ import annotations


"""Staged reconciliation helpers extracted from core logic."""

import logging
import re
import time
from pathlib import Path
from collections import Counter
from typing import Any, Callable, Dict, Iterable, List, Literal, Optional, Sequence, Tuple

from src.check_statements.filters import load_fee_patterns as load_fee_patterns_impl
from src.check_statements.matching import (
    _assignment_pass,
    _build_bank_candidates,
    _group_match,
)
from src.check_statements.candidate_graph import CandidateEdge, CandidateGraph
from src.check_statements.models import Transaction
from src.check_statements.normalisation import (
    _clean_description_local,
    _similarity,
    beneficiary_similarity,
)
from src.check_statements.party_normalisation import (
    _clean_party_for_evidence,
    _preferred_bank_party,
    _preferred_ledger_party,
    _ledger_payroll_text,
)

from src.check_statements.stages.cash_card import _stage3_cash, _stage4_card
from src.check_statements.stages.payroll_tax import _stage5_category_gate
from src.check_statements.stages.beneficiary import (
    _stage6_beneficiary_invoice as _stage6_beneficiary_invoice_extracted,
)
from src.check_statements.stages.iban_reference import (
    _stage7_iban as _stage7_iban_extracted,
    _stage8_reference as _stage8_reference_extracted,
    _collect_reference_tokens,
)
from src.check_statements.classify import (
    classify_op,
    is_tax_ledger_entry as _is_tax_ledger_entry,
    _lex_for,
)

logger = logging.getLogger(__name__)


def load_fee_patterns(path: Path | None = None) -> List[re.Pattern[str]]:
    return load_fee_patterns_impl(path)

## moved to src.check_statements.matching: _assignment_pass


def _stage2_fixers_and_routing(
    bank: Sequence["Transaction"],
    ledger: Sequence["Transaction"],
    bank_candidates: list[list[int]],
    matched_pairs: list[tuple[int, int | None, str]],
    matched_bank_indices: set[int],
    matched_ledger_indices: set[int],
    *,
    within_tolerance: Callable[["Transaction", "Transaction"], bool],
    within_date: Callable[["Transaction", "Transaction"], bool],
    candidate_graph: "CandidateGraph" | None = None,
) -> dict:
    """Apply deterministic cures on leftovers: small fees mapping and simple routing.

    - Small fees: detect by patterns/op_type and accept as synthetic pairs (ledger None).
    - This function is conservative; it doesn't attempt complex routing for RIBA/cheques yet.
    Returns counters for diagnostics.
    """
    counters: dict[str, Any] = {"fix_fee": 0, "accepted_indices": []}
    try:
        fee_patterns = load_fee_patterns()
    except Exception:  # pragma: no cover - keep pipeline running, but log it
        logger.exception("Stage-2 fixers: failed to load fee patterns")
        fee_patterns = []

    fee_graph = candidate_graph is not None
    # When the candidate graph is available, we enrich it with fee evidence so
    # the final evidence-driven assignment can reuse these edges.

    def _is_fee_ledger(li: int) -> bool:
        tx = ledger[li]
        meta = tx.metadata or {}
        fields = [
            tx.description or "",
            meta.get("extra_desc") or "",
            meta.get("details") or "",
            meta.get("account_desc") or "",
            meta.get("counter_account_desc") or "",
        ]
        combined = " ".join(str(f).upper() for f in fields if isinstance(f, str))
        if not combined:
            return False
        if any(token in combined for token in ("FEE", "COMMISSION", "COMMISS", "SPESE", "CHARGE")):
            return True
        return any(p.search(combined) for p in fee_patterns)

    ledger_fee_candidates = {
        li
        for li in range(len(ledger))
        if li not in matched_ledger_indices and _is_fee_ledger(li)
    }

    def _fee_similarity(b_txn: "Transaction", l_txn: "Transaction") -> int:
        words = set(
            w
            for w in re.split(r"[^A-Z0-9]+", (b_txn.description or "").upper())
            if len(w) >= 3
        )
        meta = l_txn.metadata or {}
        ledger_text = " ".join(
            str(part or "").upper()
            for part in (
                l_txn.description,
                meta.get("extra_desc"),
                meta.get("details"),
                meta.get("account_desc"),
                meta.get("counter_account_desc"),
            )
        )
        if not words or not ledger_text.strip():
            return 0
        matches = 0
        for w in words:
            if w and w in ledger_text:
                matches += 1
        return matches

    candidate_indices: list[int] = []
    for bi, b in enumerate(bank):
        if bi in matched_bank_indices:
            continue
        desc = (b.description or "").casefold()
        op = (b.metadata or {}).get("op_type") or classify_op(b.description)
        is_small = abs(float(b.amount)) <= 10.0
        is_fee_like = op == "FEE" or any(p.search(desc) for p in fee_patterns)
        if is_fee_like or is_small:
            candidate_indices.append(bi)

    if candidate_indices:
        ABS_LIMIT = 120
        FRACTION_LIMIT = 0.3
        bank_total = len(bank)
        frac_threshold = FRACTION_LIMIT * max(1, bank_total)
        if len(candidate_indices) > ABS_LIMIT and len(candidate_indices) > frac_threshold:
            logger.warning(
                "Stage-2 fix_fee gated: potential=%d exceeds limits (abs=%d, frac=%.0f%% of %d)",
                len(candidate_indices),
                ABS_LIMIT,
                100.0 * FRACTION_LIMIT,
                bank_total,
            )
            return counters

    for bi in candidate_indices:
        if bi in matched_bank_indices:
            continue
        b_txn = bank[bi]
        matched = False
        if ledger_fee_candidates:
            scan = bank_candidates[bi] if bank_candidates[bi] else list(range(len(ledger)))
            fee_matches: list[int] = []
            for li in scan:
                if li in matched_ledger_indices or li not in ledger_fee_candidates:
                    continue
                l_txn = ledger[li]
                if not within_tolerance(b_txn, l_txn) or not within_date(b_txn, l_txn):
                    continue
                fee_matches.append(li)
            if len(fee_matches) == 1:
                li = fee_matches[0]
                matched_pairs.append((bi, li, "fix_fee"))
                matched_bank_indices.add(bi)
                matched_ledger_indices.add(li)
                counters["fix_fee"] += 1
                counters["accepted_indices"].append(bi)
                matched = True
                if fee_graph:
                    for edge in candidate_graph.edges_for_bank(bi):
                        if edge.ledger_index == li:
                            edge.labels.append("fix_fee")
                            break
            elif len(fee_matches) > 1:
                scored = [(_fee_similarity(b_txn, ledger[li]), li) for li in fee_matches]
                scored.sort(reverse=True)
                top_score, li = scored[0]
                if top_score > 0 and (len(scored) == 1 or top_score > scored[1][0]):
                    matched_pairs.append((bi, li, "fix_fee"))
                    matched_bank_indices.add(bi)
                    matched_ledger_indices.add(li)
                    counters["fix_fee"] += 1
                    counters["accepted_indices"].append(bi)
                    matched = True
                    if fee_graph:
                        for edge in candidate_graph.edges_for_bank(bi):
                            if edge.ledger_index == li:
                                edge.labels.append("fix_fee")
                                break
        if matched:
            continue
        matched_pairs.append((bi, None, "fix_fee"))
        matched_bank_indices.add(bi)
        counters["fix_fee"] += 1
        counters["accepted_indices"].append(bi)
    return counters


# moved to src.check_statements.stages.cash_card: _stage3_cash, _stage4_card


# moved to src.check_statements.stages.payroll_tax: _stage5_category_gate


def staged_reconcile(
    bank: Sequence["Transaction"],
    ledger: Sequence["Transaction"],
    *,
    tolerance: float,
    date_window: int,
    use_absolute_amounts: bool,
    up_to_stage: int,
    dense_day: bool | None = None,
    # V1 learning: alias-only, global; enabled by default
    learn_alias_from_unique: bool = True,
    learning_min_support: int = 2,
    learning_budget: int = 20,
    llm_wrapper: Any | None = None,
) -> tuple[list[tuple[int, int | None, str]], list[int], list[int | None], dict]:
    """Run staged acceptance up to a chosen strictness stage.

    Stages implemented:
      1) Amount and Date Window
      2) Bank Fees and Charges
      3) Cash Withdrawals/Deposits
      4) Card Payments
      5) Payroll and Taxes
      6) Beneficiary Name
      7) IBAN
      8) References (Invoice/CRO/TRN)
    """
    bank = list(bank)
    ledger = list(ledger)
    # Always use the candidate graph/evidence-driven assignment.
    matched_pairs: list[tuple[int, int | None, str]] = []
    matched_bank_indices: set[int] = set()
    matched_ledger_indices: set[int] = set()
    counters: dict[str, Any] = {
        "stage1_assign": 0,
        "stage2_fix_fee": 0,
        "stage3_cash": 0,
        "stage3_evidence": 0,
        "stage4_card": 0,
        "stage4_evidence": 0,
        "stage5_salary_gate": 0,
        "stage6_beneficiary": 0,
        "stage7_iban": 0,
        "stage8_reference": 0,
        "stage3_at_least": 0,
        "stage4_at_least": 0,
        "stage1_no_candidates": [],
        "stage1_has_candidates_unassigned": [],
        "stage2_fix_fee_indices": [],
        "stage3_cash_indices": [],
        "stage4_card_indices": [],
        "stage5_salary_gate_indices": [],
        "stage5_empty_desc_unmatched": [],
        "stage6_considered_not_accepted": [],
        "stage6_present_not_considered": [],
        "stage7_considered_not_accepted": [],
        "stage7_present_no_equal": [],
        "stage5_at_least": 0,
        "stage6_at_least": 0,
        "stage7_at_least": 0,
        "stage8_at_least": 0,
        "stage1_candidate_edges": 0,
    }
    stage_flags: dict[int, dict[str, bool]] = {}

    def within_tolerance(a: Transaction, b: Transaction) -> bool:
        if use_absolute_amounts:
            return abs(abs(a.amount) - abs(b.amount)) <= tolerance
        return abs(a.amount - b.amount) <= tolerance

    def within_date(a: Transaction, b: Transaction) -> bool:
        return abs((a.date - b.date).days) <= date_window

    bank_candidates = _build_bank_candidates(
        bank,
        ledger,
        tolerance,
        date_window=date_window,
        use_absolute_amounts=use_absolute_amounts,
    )

    # Log a single aggregate count of ambiguous rows (same message once per call)
    total_candidate_pairs = 0
    row_viable: list[list[int]] = [[] for _ in range(len(bank_candidates))]
    for bi, cand in enumerate(bank_candidates):
        viable: list[int] = []
        for li in cand:
            if within_tolerance(bank[bi], ledger[li]) and within_date(bank[bi], ledger[li]):
                viable.append(li)
        row_viable[bi] = viable
        total_candidate_pairs += len(viable)
    # Suppress noisy Stage‑1 candidate summary log

    candidate_graph: CandidateGraph | None = None
    try:
        fee_patterns = load_fee_patterns()
    except Exception:  # pragma: no cover - keep pipeline running, but log it
        logger.exception("staged_reconcile: failed to load fee patterns")
        fee_patterns = []
    if up_to_stage >= 1:
        candidate_graph = CandidateGraph(len(bank))
        for bi, viable in enumerate(row_viable):
            for li in viable:
                b_txn = bank[bi]
                l_txn = ledger[li]
                if use_absolute_amounts:
                    amt_delta = abs(abs(b_txn.amount) - abs(l_txn.amount))
                else:
                    amt_delta = abs(b_txn.amount - l_txn.amount)
                dd = abs((b_txn.date - l_txn.date).days)
                candidate_graph.add_edge(
                    CandidateEdge(
                        bank_index=bi,
                        ledger_index=li,
                        amount_delta=amt_delta,
                        date_diff_days=dd,
                    )
                )

    ledger_candidate_counts = [0 for _ in range(len(ledger))]
    for viable in row_viable:
        for li in viable:
            if 0 <= li < len(ledger):
                ledger_candidate_counts[li] += 1

    # Stage 1
    stage1_unique_assign = 0
    if up_to_stage >= 1:
        counters["stage1_candidate_edges"] = int(total_candidate_pairs)
        def _is_fee_like_bank_row(idx: int) -> bool:
            tx = bank[idx]
            desc = (tx.description or "").upper()
            meta = tx.metadata or {}
            op_meta = meta.get("op_type") if isinstance(meta, dict) else None
            op = op_meta or classify_op(tx.description)
            amount_val = float(tx.amount) if tx.amount is not None else 0.0
            is_small = abs(amount_val) <= 10.0
            is_fee = op == "FEE" or any(p.search(desc) for p in fee_patterns)
            return is_small or is_fee

        # Graph mode: only accept Stage‑1 unique 1:1 edges (non-fee),
        # deferring the rest to the final evidence-driven assignment.
        for bi, cands in enumerate(row_viable):
            if bi in matched_bank_indices:
                continue
            if len(cands) != 1:
                continue
            li = cands[0]
            if li in matched_ledger_indices:
                continue
            if ledger_candidate_counts[li] != 1:
                continue
            if _is_fee_like_bank_row(bi):
                continue
            matched_pairs.append((bi, li, "assign"))
            matched_bank_indices.add(bi)
            matched_ledger_indices.add(li)
            stage1_unique_assign += 1
        counters["stage1_assign"] = int(stage1_unique_assign)
        unmatched_after_1 = [
            i for i in range(len(bank)) if i not in matched_bank_indices
        ]
        for bi in unmatched_after_1:
            csz = len(row_viable[bi])
            if csz == 0:
                counters["stage1_no_candidates"].append(bi)
            else:
                counters["stage1_has_candidates_unassigned"].append(bi)

    # Stage 2
    if up_to_stage >= 2:
        before = len(matched_bank_indices)
        c = _stage2_fixers_and_routing(
            bank,
            ledger,
            bank_candidates,
            matched_pairs,
            matched_bank_indices,
            matched_ledger_indices,
            within_tolerance=within_tolerance,
            within_date=within_date,
            candidate_graph=candidate_graph,
        )
        counters["stage2_fix_fee"] = c.get("fix_fee", 0)
        counters["stage2_fix_fee_indices"] = c.get("accepted_indices", [])

    # Stage 3
    if up_to_stage >= 3:
        c = _stage3_cash(
            bank,
            ledger,
            bank_candidates,
            matched_pairs,
            matched_bank_indices,
            matched_ledger_indices,
            within_tolerance=within_tolerance,
            within_date=within_date,
            candidate_graph=candidate_graph,
            assign=False,
        )

    # Stage 4
    if up_to_stage >= 4:
        c = _stage4_card(
            bank,
            ledger,
            bank_candidates,
            matched_pairs,
            matched_bank_indices,
            matched_ledger_indices,
            within_tolerance=within_tolerance,
            within_date=within_date,
            candidate_graph=candidate_graph,
            assign=False,
        )

    # Stage 5
    if up_to_stage >= 5:
        c = _stage5_category_gate(
            bank,
            ledger,
            bank_candidates,
            matched_pairs,
            matched_bank_indices,
            matched_ledger_indices,
            within_tolerance=within_tolerance,
            within_date=within_date,
            tolerance=tolerance,
            use_absolute_amounts=use_absolute_amounts,
            candidate_graph=candidate_graph,
            assign=False,
        )
        counters["stage5_payroll_hits"] = c.get("payroll_hits", [])
        counters["stage5_tax_hits"] = c.get("tax_hits", [])
        # Unmatched with empty/vague desc (candidates for manual/category review)
        unmatched_after_5 = [
            i for i in range(len(bank)) if i not in matched_bank_indices
        ]
        for bi in unmatched_after_5:
            desc = (bank[bi].description or "").strip().upper()
            if not desc or len(desc) <= 3:
                counters["stage5_empty_desc_unmatched"].append(bi)

    # Stage 6: Beneficiary/Invoice (only when no IBAN present)
    if up_to_stage >= 6:
        c = _stage6_beneficiary_invoice_extracted(
            bank,
            ledger,
            bank_candidates,
            matched_pairs,
            matched_bank_indices,
            matched_ledger_indices,
            within_tolerance=within_tolerance,
            within_date=within_date,
            beneficiary_similarity_fn=beneficiary_similarity,
            sim_threshold=90.0 if (dense_day is True) else 85.0,
            candidate_graph=candidate_graph,
            assign=False,
        )
        counters["stage6_beneficiary"] = c.get("stage6_beneficiary", 0)
        counters["stage6_considered_not_accepted"] = c.get(
            "considered_not_accepted", []
        )
        counters["stage6_present_not_considered"] = c.get("present_not_considered", [])
        counters["stage6_beneficiary_hits"] = c.get("beneficiary_hits", [])

    # Stage 7: IBAN
    if up_to_stage >= 7:
        c = _stage7_iban_extracted(
            bank,
            ledger,
            bank_candidates,
            matched_pairs,
            matched_bank_indices,
            matched_ledger_indices,
            within_tolerance=within_tolerance,
            within_date=within_date,
            candidate_graph=candidate_graph,
            assign=False,
        )
        counters["stage7_iban"] = c.get("stage7_iban", 0)
        counters["stage7_considered_not_accepted"] = c.get(
            "considered_not_accepted", []
        )
        counters["stage7_present_no_equal"] = c.get("present_no_equal", [])

    # Stage 8: Reference ID
    if up_to_stage >= 8:
        c = _stage8_reference_extracted(
            bank,
            ledger,
            matched_pairs,
            matched_bank_indices,
            matched_ledger_indices,
            within_tolerance=within_tolerance,
            within_date=within_date,
            candidate_graph=candidate_graph,
            assign=False,
        )
        counters["stage8_reference"] = c.get("stage8_reference", 0)

    if up_to_stage >= 1:
        def _assign_candidates_with_evidence() -> int:
            if candidate_graph is None:
                return 0
            label_priority = {
                "reference": 0,
                "iban": 1,
                "beneficiary": 2,
                "payroll": 3,
                "tax": 3,
                "card": 4,
                "cash": 5,
            }
            label_stage = {
                "reference": 8,
                "iban": 7,
                "beneficiary": 6,
                "payroll": 5,
                "tax": 5,
                "card": 4,
                "cash": 3,
            }
            label_to_how = {
                "reference": "reference",
                "iban": "iban",
                "beneficiary": "beneficiary",
                "payroll": "salary_gate",
                "tax": "salary_gate",
                "card": "card",
                "cash": "cash",
            }
            fallback_priority = 100
            ranked: list[tuple[int, int, int, float, int, int, str | None]] = []
            for bi in range(len(bank)):
                if bi in matched_bank_indices:
                    continue
                for edge in candidate_graph.edges_for_bank(bi):
                    li = edge.ledger_index
                    if li in matched_ledger_indices:
                        continue
                    labels_ordered = list(dict.fromkeys(edge.labels))
                    allowed_labels = [
                        lbl for lbl in labels_ordered if label_stage.get(lbl, 0) <= up_to_stage
                    ]
                    label_set = set(allowed_labels)
                    label_count = len(label_set)
                    if label_count:
                        best_label = min(
                            label_set,
                            key=lambda lbl: (label_priority.get(lbl, fallback_priority), lbl),
                        )
                        best_pri = label_priority.get(best_label, fallback_priority)
                    else:
                        best_label = None
                        best_pri = fallback_priority
                    ranked.append(
                        (
                            -label_count,
                            best_pri,
                            abs(edge.date_diff_days),
                            abs(edge.amount_delta),
                            bi,
                            li,
                            best_label,
                        )
                    )
            if not ranked:
                return 0
            ranked.sort()
            taken_bank: set[int] = set()
            taken_ledger: set[int] = set()
            assigned = 0
            for _, _, _, _, bi, li, best_label in ranked:
                if bi in matched_bank_indices or li in matched_ledger_indices:
                    continue
                if bi in taken_bank or li in taken_ledger:
                    continue
                how = label_to_how.get(best_label, "assign")
                matched_pairs.append((bi, li, how))
                matched_bank_indices.add(bi)
                matched_ledger_indices.add(li)
                taken_bank.add(bi)
                taken_ledger.add(li)
                assigned += 1
            return assigned

        _assign_candidates_with_evidence()

    counters["stage1_assign"] = int(
        sum(1 for _bi, _li, how in matched_pairs if how == "assign")
    )

    stage_origin_by_bank: dict[int, int] = {}
    stage_lookup: dict[str, int] = {
        "assign": 1,
        "exact": 1,
        "fuzzy": 1,
        "fuzzy_margin": 1,
        "ref_substring": 1,
        "group": 1,
        "fix_fee": 2,
        "cash": 3,
        "card": 4,
        "salary_gate": 5,
        "beneficiary": 6,
        "iban": 7,
        "reference": 8,
    }
    for bi, _li_any, how in matched_pairs:
        if bi in stage_origin_by_bank:
            continue
        stage_origin_by_bank[bi] = stage_lookup.get(how, 1)

    # Inclusive evidence counts across all matched pairs (AND semantics with Stage 1)
    def _metadata_dict(tx: Transaction) -> dict[str, Any]:
        meta = getattr(tx, "metadata", None)
        return meta if isinstance(meta, dict) else {}

    def _resolve_lang(meta: dict[str, Any]) -> str | None:
        value = meta.get("language") or meta.get("lang")
        return value if isinstance(value, str) else None

    def _resolve_op(tx: Transaction) -> str:
        meta = _metadata_dict(tx)
        op_meta = meta.get("op_type")
        if isinstance(op_meta, str) and op_meta.strip():
            return op_meta
        return classify_op(tx.description, _resolve_lang(meta))

    def _payroll_tokens(lang: str | None) -> tuple[str, ...]:
        raw = _lex_for(lang).get("payroll_tokens", [])
        return tuple(str(token).casefold() for token in raw)

    b_ibans = [_metadata_dict(t).get("iban") for t in bank]
    l_ibans = [_metadata_dict(t).get("iban") for t in ledger]
    b_ops = [_resolve_op(t) for t in bank]
    l_ops = [_resolve_op(t) for t in ledger]

    # Beneficiary similarity baseline
    # Slightly more permissive for evidence counting to avoid under-reporting
    ben_thresh = 88.0 if dense_day else 80.0
    stage3_at_least = 0
    stage4_at_least = 0
    stage3_evidence = 0
    stage4_evidence = 0
    stage5_count = 0
    stage6_count = 0
    stage7_count = 0
    stage8_count = 0
    # Cumulative (at least) counts: hierarchical 5 -> 6 -> 7 -> 8
    stage5_at_least = 0
    stage6_at_least = 0
    stage7_at_least = 0
    stage8_at_least = 0
    # Debug tallies to help explain zeros
    dbg_bank_payroll = 0
    dbg_ledger_payroll = 0
    dbg_bank_tax = 0
    dbg_ledger_tax = 0
    dbg_beneficiary_pairs = 0
    dbg_beneficiary_hits = 0
    dbg_iban_pairs = 0
    dbg_ref_pairs = 0
    stage5_pay_hits: set[int] = set()
    stage5_tax_hits: set[int] = set()
    seen_bi: set[int] = set()
    ledger_payroll_cache: dict[int, str] = {}
    reference_tokens_bank: dict[int, set[str]] = {}
    reference_tokens_ledger: dict[int, set[str]] = {}
    for bi, li_any, _how in matched_pairs:
        if bi in seen_bi:
            continue
        seen_bi.add(bi)
        stage_flag_entry = {
            "s1": stage_origin_by_bank.get(bi) == 1,
            "s2": stage_origin_by_bank.get(bi) == 2,
            "s3": False,
            "s4": False,
            "s5": False,
            "s6": False,
            "s7": False,
            "s8": False,
        }
        if li_any is None:
            stage_flags[bi] = stage_flag_entry
            continue
        b = bank[bi]
        b_meta = _metadata_dict(b)
        desc = (b.description or "").casefold()
        b_ids = set(b.reference_ids or [])
        b_iban = b_ibans[bi]
        bank_op = b_ops[bi]
        li_list = li_any if isinstance(li_any, tuple) else (li_any,)
        evidence_flags = {
            "s3": False,
            "s4": False,
            "s5": False,
            "s6": False,
            "s7": False,
            "s8": False,
        }
        for li in li_list:
            l = ledger[li]
            l_meta = _metadata_dict(l)
            ledger_op = l_ops[li]
            if (
                not evidence_flags["s3"]
                and bank_op == "ATM"
                and ledger_op == "ATM"
                and within_tolerance(b, l)
                and within_date(b, l)
            ):
                evidence_flags["s3"] = True
            if (
                not evidence_flags["s4"]
                and bank_op == "CARD"
                and ledger_op == "CARD"
                and within_tolerance(b, l)
                and within_date(b, l)
            ):
                evidence_flags["s4"] = True
            ledger_text = ledger_payroll_cache.get(li)
            if ledger_text is None:
                ledger_text = _ledger_payroll_text(l, l_meta)
                ledger_payroll_cache[li] = ledger_text
            acc_desc = (
                ledger_text
                or str(
                    l_meta.get("counter_account_desc")
                    or l_meta.get("account_desc")
                    or l_meta.get("account_name")
                    or l.description
                    or ""
                ).casefold()
            )
            bank_tax = (bank_op == "F24") or _is_tax_ledger_entry(b)
            ledger_tax = _is_tax_ledger_entry(l)
            b_lang = _resolve_lang(b_meta)
            l_lang = _resolve_lang(l_meta)
            bank_pay = any(k in desc for k in _payroll_tokens(b_lang))
            ledg_pay = any(k in acc_desc for k in _payroll_tokens(l_lang))
            if bank_pay:
                dbg_bank_payroll += 1
            if ledg_pay:
                dbg_ledger_payroll += 1
            if bank_tax:
                dbg_bank_tax += 1
            if ledger_tax:
                dbg_ledger_tax += 1
            payroll_hit = within_date(b, l) and bank_pay and ledg_pay
            tax_hit = within_date(b, l) and bank_tax and ledger_tax
            if payroll_hit or tax_hit:
                evidence_flags["s5"] = True
                if payroll_hit:
                    stage5_pay_hits.add(bi)
                if tax_hit:
                    stage5_tax_hits.add(bi)
            if not within_tolerance(b, l) or not within_date(b, l):
                continue
            l_iban = l_ibans[li]
            if b_iban and l_iban and b_iban == l_iban:
                evidence_flags["s7"] = True
                dbg_iban_pairs += 1
            l_ids = set(l.reference_ids or [])
            ref_matched = False
            if b_ids and l_ids and (b_ids & l_ids):
                evidence_flags["s8"] = True
                dbg_ref_pairs += 1
                ref_matched = True
            if not ref_matched:
                b_tokens = reference_tokens_bank.get(bi)
                if b_tokens is None:
                    b_tokens = _collect_reference_tokens(b)
                    reference_tokens_bank[bi] = b_tokens
                l_tokens = reference_tokens_ledger.get(li)
                if l_tokens is None:
                    l_tokens = _collect_reference_tokens(l)
                    reference_tokens_ledger[li] = l_tokens
                if b_tokens and l_tokens and not b_tokens.isdisjoint(l_tokens):
                    evidence_flags["s8"] = True
                    dbg_ref_pairs += 1

            b_name_raw = _preferred_bank_party(b, b_meta)
            l_name_raw = _preferred_ledger_party(l, l_meta)
            b_name = _clean_party_for_evidence(b_name_raw, b_lang)
            l_name = _clean_party_for_evidence(l_name_raw, l_lang)
            ben_sim = _similarity((b_name or "").upper(), (l_name or "").upper())
            if (b_name or None) and (l_name or None):
                dbg_beneficiary_pairs += 1
            if ben_sim >= ben_thresh:
                evidence_flags["s6"] = True
                dbg_beneficiary_hits += 1
            if all(evidence_flags.values()):
                break
        if (
            evidence_flags["s3"]
            or evidence_flags["s4"]
            or evidence_flags["s5"]
            or evidence_flags["s6"]
            or evidence_flags["s7"]
            or evidence_flags["s8"]
        ):
            stage3_at_least += 1
        if (
            evidence_flags["s4"]
            or evidence_flags["s5"]
            or evidence_flags["s6"]
            or evidence_flags["s7"]
            or evidence_flags["s8"]
        ):
            stage4_at_least += 1
        if evidence_flags["s3"]:
            stage3_evidence += 1
        if evidence_flags["s4"]:
            stage4_evidence += 1
        stage5_count += 1 if evidence_flags["s5"] else 0
        stage6_count += 1 if evidence_flags["s6"] else 0
        stage7_count += 1 if evidence_flags["s7"] else 0
        stage8_count += 1 if evidence_flags["s8"] else 0
        if (
            evidence_flags["s5"]
            or evidence_flags["s6"]
            or evidence_flags["s7"]
            or evidence_flags["s8"]
        ):
            stage5_at_least += 1
        if evidence_flags["s6"] or evidence_flags["s7"] or evidence_flags["s8"]:
            stage6_at_least += 1
        if evidence_flags["s7"] or evidence_flags["s8"]:
            stage7_at_least += 1
        if evidence_flags["s8"]:
            stage8_at_least += 1
        stage_flag_entry.update(evidence_flags)
        stage_flags[bi] = stage_flag_entry

    counters["stage3_at_least"] = int(stage3_at_least)
    counters["stage4_at_least"] = int(stage4_at_least)
    counters["stage3_evidence"] = int(stage3_evidence)
    counters["stage4_evidence"] = int(stage4_evidence)
    counters["stage5_salary_gate"] = int(stage5_count)
    counters["stage6_beneficiary"] = int(stage6_count)
    counters["stage7_iban"] = int(stage7_count)
    counters["stage8_reference"] = int(stage8_count)
    counters["stage5_at_least"] = int(stage5_at_least)
    counters["stage6_at_least"] = int(stage6_at_least)
    counters["stage7_at_least"] = int(stage7_at_least)
    counters["stage8_at_least"] = int(stage8_at_least)
    counters["__evidence_debug__"] = {
        "bank_payroll_hits": int(dbg_bank_payroll),
        "ledger_payroll_hits": int(dbg_ledger_payroll),
        "bank_tax_hits": int(dbg_bank_tax),
        "ledger_tax_hits": int(dbg_ledger_tax),
        "beneficiary_pairs": int(dbg_beneficiary_pairs),
        "beneficiary_hits": int(dbg_beneficiary_hits),
        "iban_pairs": int(dbg_iban_pairs),
        "ref_pairs": int(dbg_ref_pairs),
    }
    counters["stage5_payroll_hits"] = sorted(stage5_pay_hits)
    counters["stage5_tax_hits"] = sorted(stage5_tax_hits)
    counters["stage_flags"] = stage_flags

    if stage_origin_by_bank:
        origin_counter = Counter(stage_origin_by_bank.values())
        counters["stage_origin_counts"] = dict(origin_counter)
        counters["matched_bank_total"] = int(sum(origin_counter.values()))

    if stage_flags:
        stage3_indices = sorted(bi for bi, flags in stage_flags.items() if flags.get("s3"))
        stage4_indices = sorted(bi for bi, flags in stage_flags.items() if flags.get("s4"))
        stage5_indices = sorted(bi for bi, flags in stage_flags.items() if flags.get("s5"))
        stage6_indices = sorted(bi for bi, flags in stage_flags.items() if flags.get("s6"))
        stage7_indices = sorted(bi for bi, flags in stage_flags.items() if flags.get("s7"))
        stage8_indices = sorted(bi for bi, flags in stage_flags.items() if flags.get("s8"))
        if stage3_indices:
            counters["stage3_cash"] = len(stage3_indices)
        counters["stage3_cash_indices"] = stage3_indices
        if stage4_indices:
            counters["stage4_card"] = len(stage4_indices)
        counters["stage4_card_indices"] = stage4_indices
        if stage5_indices:
            counters["stage5_salary_gate"] = len(stage5_indices)
        counters["stage5_salary_gate_indices"] = stage5_indices
        if stage6_indices:
            counters["stage6_beneficiary"] = len(stage6_indices)
        counters.setdefault("stage6_beneficiary_hits", [])
        counters["stage6_beneficiary_hits"] = sorted(set(counters["stage6_beneficiary_hits"]) | set(stage6_indices))
        counters["stage6_considered_not_accepted"] = sorted(set(counters.get("stage6_considered_not_accepted", [])))
        if stage7_indices:
            counters["stage7_iban"] = len(stage7_indices)
        counters["stage7_present_no_equal"] = sorted(set(counters.get("stage7_present_no_equal", [])))
        counters["stage7_considered_not_accepted"] = sorted(set(counters.get("stage7_considered_not_accepted", [])))
        if stage8_indices:
            counters["stage8_reference"] = len(stage8_indices)
        counters["stage8_reference_indices"] = stage8_indices


    unmatched_bank = [i for i in range(len(bank)) if i not in matched_bank_indices]
    unmatched_ledger: list[int | None] = [
        i for i in range(len(ledger)) if i not in matched_ledger_indices
    ]

    # -------------------------------------------------------------
    # V1 learning scaffold (alias-only, global): collect unique amount+date
    # seeds and persist deterministic alias mappings for future runs.
    if learn_alias_from_unique:
        try:
            from src.check_statements.alias_memory import load_alias_rules, save_alias_rules  # type: ignore
            from src.check_statements.alias_seed import collect_matched_seed_pairs  # type: ignore
            from src.check_statements.alias_pattern_grouping import group_seed_patterns  # type: ignore
        except Exception:  # pragma: no cover - optional feature
            load_alias_rules = lambda: {}  # type: ignore
            save_alias_rules = lambda _m: None  # type: ignore

            def collect_matched_seed_pairs(*_args, **_kwargs):  # type: ignore
                return []

            def group_seed_patterns(*_args, **_kwargs):  # type: ignore
                return []

        alias_map = load_alias_rules()

        unique_candidates = _build_bank_candidates(
            bank,
            ledger,
            tolerance,
            date_window=min(date_window, 1),
            use_absolute_amounts=use_absolute_amounts,
        )

        seed_pairs = collect_matched_seed_pairs(
            bank,
            ledger,
            matched_pairs,
            unique_candidates,
            exclude_types={"FEE"},
            existing_alias_map=alias_map,
        )

        seeds_count = len(seed_pairs)
        counters["alias_learning_seeds"] = int(seeds_count)
        if seeds_count:
            pattern_groups = group_seed_patterns(
                seed_pairs,
                min_support=int(learning_min_support),
                max_groups=int(learning_budget),
            )
            counters["alias_learning_pattern_groups"] = [
                grp.to_payload(max_examples=3) for grp in pattern_groups
            ]
            field_counts = Counter()
            for seed in seed_pairs:
                field_counts.update(
                    feature.field
                    for feature in seed.features
                    if feature.bank.normalized or feature.ledger.normalized
                )
            counters["alias_learning_seed_feature_counts"] = dict(field_counts)
            counters["alias_learning_seed_samples"] = [
                seed.to_summary(max_values=3) for seed in seed_pairs[: min(5, seeds_count)]
            ]
            sample_for_log = [seed_pairs[0].to_summary(max_values=2)]
            logger.info(
                "Alias learning: seed_count=%d groups=%d feature_counts=%s sample=%s",
                seeds_count,
                len(pattern_groups),
                dict(field_counts),
                sample_for_log,
            )

            support: dict[tuple[str, str], set] = {}
            for seed in seed_pairs:
                feature = seed.feature_by_field("beneficiary")
                if not feature or not feature.has_both():
                    continue
                bk = feature.bank.normalized[0]
                lk = feature.ledger.normalized[0]
                support.setdefault((bk, lk), set()).add(seed.date)

            supported = [
                (bk, lk, len(ds))
                for (bk, lk), ds in support.items()
                if len(ds) >= int(learning_min_support)
            ]
            supported.sort(key=lambda item: (item[2], len(item[1])), reverse=True)

            updates: dict[str, str] = {}
            for bk, lk, _cnt in supported[: int(learning_budget)]:
                if bk == lk or alias_map.get(bk) == lk:
                    continue
                updates[bk] = lk

            counters["alias_learning_supported"] = int(len(supported))
            counters["alias_learning_updates"] = int(len(updates))

            if updates:
                alias_map.update(updates)
                try:
                    save_alias_rules(alias_map)
                    logger.info(
                        "Alias learning: seeds=%d supported=%d updates=%d",
                        seeds_count,
                        len(supported),
                        len(updates),
                    )
                except Exception:
                    pass
        else:
            counters.setdefault("alias_learning_seed_feature_counts", {})
            counters.setdefault("alias_learning_seed_samples", [])
            counters.setdefault("alias_learning_pattern_groups", [])
            logger.info("Alias learning: seed_count=0 feature_counts={} sample=[]")

    return matched_pairs, unmatched_bank, unmatched_ledger, counters


# moved to src.check_statements.stages.beneficiary: _stage6_beneficiary_invoice


## moved to src.check_statements.stages.iban_reference: _stage7_iban


## moved to src.check_statements.stages.iban_reference: _stage8_reference


def _group_match_local(
    bank: Sequence["Transaction"],
    ledger: Sequence["Transaction"],
    bank_candidates: list[list[int]],
    matched_pairs: list[tuple[int, int | tuple[int, ...], str]],
    matched_bank_indices: set[int],
    matched_ledger_indices: set[int],
    *,
    group_limit: int,
    tolerance: float,
    group_tolerance: float | None,
    beneficiary_mode: str,
    fuzzy_threshold: float,
    use_absolute_amounts: bool,
    within_tolerance: Callable[["Transaction", "Transaction"], bool],
    within_date: Callable[["Transaction", "Transaction"], bool],
    update_progress: Optional[Callable[[int, int], None]] = None,
    # New optional guardrails (defaults preserve current behaviour)
    group_candidates_cap: Optional[int] = None,
    max_combos_per_bank: Optional[int] = None,
    group_time_budget_ms: Optional[int] = None,
) -> None:
    """Run group matching pass over remaining transactions.

    Constraints:
    - same op_type across group
    - consistent counterparty (same beneficiary/IBAN when present)
    - never group tax/F24 with suppliers or fees
    """
    if not group_limit or group_limit <= 1:
        return
    gtol = group_tolerance if group_tolerance is not None else tolerance
    import time

    # Precompute repeated attributes for gating
    b_ops = [
        ((t.metadata or {}).get("op_type") or classify_op(t.description)) for t in bank
    ]
    b_ibans = [((t.metadata or {}).get("iban") or "") for t in bank]
    b_ben_norm = [(t.beneficiary or "").upper() for t in bank]
    b_ben_key = [normalise_name(t.beneficiary) if t.beneficiary else "" for t in bank]
    l_ibans = [((t.metadata or {}).get("iban") or "") for t in ledger]
    l_ben_norm = [(t.beneficiary or "").upper() for t in ledger]
    l_ben_key = [normalise_name(t.beneficiary) if t.beneficiary else "" for t in ledger]
    l_is_tax = [
        bool(((t.metadata or {}).get("tax_flag"))) or _is_tax_ledger_entry(t)
        for t in ledger
    ]

    for bi, b_txn in enumerate(bank):
        if update_progress:
            update_progress(2, bi)
        if bi in matched_bank_indices:
            continue
        # Start a small timer and counters for instrumentation
        t0 = time.perf_counter()
        pair_checks = 0
        triple_checks = 0

        # Build base candidates from unmatched ledger entries within the date window.
        # We do NOT use amount‑narrowed candidates here because group sums may
        # require components far from the bank amount individually (e.g. 60+40≈100).
        base_candidates = [
            li
            for li in range(len(ledger))
            if li not in matched_ledger_indices and within_date(b_txn, ledger[li])
        ]
        candidates: list[int] = []
        b_op = b_ops[bi]
        b_iban = b_ibans[bi]
        b_ben = b_ben_norm[bi]
        # Respect optional cap early to avoid blow-ups
        # We will filter for availability/date/type/party consistency
        for li in base_candidates:
            l_txn = ledger[li]
            l_iban = l_ibans[li]
            l_ben = l_ben_norm[li]
            is_tax = l_is_tax[li]
            # Type constraints
            if b_op == "F24" and not is_tax:
                continue
            if b_op == "BONIFICO" and is_tax:
                continue
            # Consistent counterparty heuristic: same IBAN or same beneficiary when both present
            if b_iban and l_iban and b_iban != l_iban:
                continue
            if b_ben and l_ben and b_ben_key[bi] != l_ben_key[li]:
                continue
            candidates.append(li)

        # Sort by absolute difference to try promising pairs first
        tgt = abs(b_txn.amount) if use_absolute_amounts else b_txn.amount
        candidates.sort(
            key=lambda i: abs(
                (abs(ledger[i].amount) if use_absolute_amounts else ledger[i].amount)
                - tgt
            )
        )

        # Optionally cap candidate count to avoid combinatorial explosion
        if isinstance(group_candidates_cap, int) and group_candidates_cap > 0:
            candidates = candidates[:group_candidates_cap]

        max_r = min(group_limit, len(candidates))
        found = False
        # Fast-path: pair grouping via tolerant two-sum (O(k))
        if not found and max_r >= 2:
            bucket = max(gtol, 1e-9)
            # Map rounded amount bucket -> list of indices
            amt_to_indices: dict[int, list[int]] = {}
            amts: list[float] = []
            for i in candidates:
                ai = abs(ledger[i].amount) if use_absolute_amounts else ledger[i].amount
                amts.append(ai)
                key = int(round(ai / bucket))
                amt_to_indices.setdefault(key, []).append(i)
            target = tgt
            seen: set[int] = set()  # to avoid using same index twice
            for idx, i in enumerate(candidates):
                ai = amts[idx]
                need = target - ai
                key = int(round(need / bucket))
                # Probe nearby buckets to account for tolerance
                for probe in (key - 1, key, key + 1):
                    for j in amt_to_indices.get(probe, []):
                        if j == i or j in seen:
                            continue
                        pair_checks += 1
                        total = ai + (
                            abs(ledger[j].amount)
                            if use_absolute_amounts
                            else ledger[j].amount
                        )
                        diff = (
                            abs(abs(total) - abs(target))
                            if use_absolute_amounts
                            else abs(total - target)
                        )
                        if diff <= gtol:
                            # Final beneficiary hard-gating if requested
                            if beneficiary_mode == "hard":
                                if (
                                    _similarity(
                                        b_txn.normalised_beneficiary(),
                                        ledger[i].normalised_beneficiary(),
                                    )
                                    < fuzzy_threshold
                                    or _similarity(
                                        b_txn.normalised_beneficiary(),
                                        ledger[j].normalised_beneficiary(),
                                    )
                                    < fuzzy_threshold
                                ):
                                    continue
                            matched_bank_indices.add(bi)
                            matched_ledger_indices.update((i, j))
                            matched_pairs.append((bi, tuple(sorted((i, j))), "group"))
                            found = True
                            break
                    if found:
                        break
                if found:
                    break
                seen.add(i)

        # Optional triples with pruning and guardrails
        if not found and max_r >= 3:
            # Only try triples if candidate list is reasonably small
            for combo in itertools.combinations(candidates, 3):
                triple_checks += 1
                if not all(within_date(b_txn, ledger[i]) for i in combo):
                    continue
                # Stop if exceeding combo/time limits
                if (
                    isinstance(max_combos_per_bank, int)
                    and triple_checks > max_combos_per_bank
                ):
                    break
                if isinstance(group_time_budget_ms, int):
                    elapsed_ms = (time.perf_counter() - t0) * 1000.0
                    if elapsed_ms > group_time_budget_ms:
                        break
                # op_type consistency within the group
                same_type = True
                for i in combo:
                    li_is_tax = l_is_tax[i]
                    if b_op == "F24" and not li_is_tax:
                        same_type = False
                        break
                    if b_op == "BONIFICO" and li_is_tax:
                        same_type = False
                        break
                if not same_type:
                    continue
                if b_op == "F24":
                    # never group F24 with anything else
                    continue
                total = sum(
                    abs(ledger[i].amount) if use_absolute_amounts else ledger[i].amount
                    for i in combo
                )
                diff = (
                    abs(abs(total) - abs(b_txn.amount))
                    if use_absolute_amounts
                    else abs(total - b_txn.amount)
                )
                if diff <= gtol:
                    if beneficiary_mode == "hard":
                        if not all(
                            _similarity(
                                b_txn.normalised_beneficiary(),
                                ledger[i].normalised_beneficiary(),
                            )
                            >= fuzzy_threshold
                            for i in combo
                        ):
                            continue
                    matched_bank_indices.add(bi)
                    matched_ledger_indices.update(combo)
                    matched_pairs.append((bi, tuple(sorted(combo)), "group"))
                    found = True
                    break

        elapsed = (time.perf_counter() - t0) * 1000.0
        logger.debug(
            "group_match bi=%d candidates=%d pair_checks=%d triple_checks=%d elapsed_ms=%.2f found=%s",
            bi,
            len(candidates),
            pair_checks,
            triple_checks,
            elapsed,
            found,
        )
