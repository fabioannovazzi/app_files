from __future__ import annotations

from typing import Callable, Optional, Sequence

import polars as pl
import re
import itertools
import time
import logging

try:
    from rapidfuzz import fuzz  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    fuzz = None  # type: ignore

from src.check_statements.classify import classify_op, is_tax_ledger_entry as _is_tax_ledger_entry

_log = logging.getLogger(__name__)


def _ben_key(s: str) -> str:
    s = (s or "").upper()
    return re.sub(r"[^A-Z0-9]+", "", s)


def _txns_to_polars(
    rows: Sequence["Transaction"],
    idx_name: str,
    prefix: str,
    *,
    use_absolute_amounts: bool = False,
) -> pl.DataFrame:
    """Convert a sequence of transactions into a Polars DataFrame."""
    return pl.DataFrame(
        {
            idx_name: list(range(len(rows))),
            f"{prefix}date": [r.date for r in rows],
            f"{prefix}amount": [
                abs(r.amount) if use_absolute_amounts else r.amount for r in rows
            ],
            f"{prefix}desc": [r.description or "" for r in rows],
            f"{prefix}ben": [r.beneficiary or "" for r in rows],
        }
    )


def _pairs_from_candidates(bank_candidates: list[list[int]]) -> pl.DataFrame:
    """Return a pair DataFrame from ``bank_candidates``."""
    bi_vals: list[int] = []
    li_vals: list[int] = []
    for bi, cand in enumerate(bank_candidates):
        bi_vals.extend([bi] * len(cand))
        li_vals.extend(cand)
    return pl.DataFrame({"bi": bi_vals, "li": li_vals})


def _build_bank_candidates(
    bank: Sequence["Transaction"],
    ledger: Sequence["Transaction"],
    tolerance: float,
    *,
    date_window: int,
    use_absolute_amounts: bool = False,
) -> list[list[int]]:
    """Pre-compute candidate ledger indices per bank row using amount buckets."""
    if not bank or not ledger:
        return [[] for _ in range(len(bank))]
    bank_df = _txns_to_polars(
        bank, "bi", "b_", use_absolute_amounts=use_absolute_amounts
    )
    ledger_df = _txns_to_polars(
        ledger, "li", "l_", use_absolute_amounts=use_absolute_amounts
    )
    bucket_size = abs(tolerance) or 1.0
    bank_df = bank_df.with_columns(
        (pl.col("b_amount") / bucket_size).floor().cast(pl.Int64).alias("bucket")
    )
    ledger_df = ledger_df.with_columns(
        (pl.col("l_amount") / bucket_size).floor().cast(pl.Int64).alias("bucket")
    )
    bank_expanded = pl.concat(
        [
            bank_df.with_columns((pl.col("bucket") - 1).alias("bucket")),
            bank_df,
            bank_df.with_columns((pl.col("bucket") + 1).alias("bucket")),
        ]
    )
    joined = (
        bank_expanded.join(ledger_df, on="bucket", how="inner")
        .filter((pl.col("b_amount") - pl.col("l_amount")).abs() <= tolerance)
        .filter((pl.col("b_date") - pl.col("l_date")).dt.total_days().abs() <= date_window)
    )
    if not use_absolute_amounts:
        joined = joined.filter(pl.col("b_amount") * pl.col("l_amount") >= 0)
    groups = joined.group_by("bi").agg(pl.col("li"))
    mapping = {row["bi"]: row["li"] for row in groups.to_dicts()}
    return [sorted(mapping.get(i, [])) for i in range(len(bank))]


def _assignment_pass(
    bank: Sequence["Transaction"],
    ledger: Sequence["Transaction"],
    bank_candidates: list[list[int]],
    matched_pairs: list[tuple[int, int, str]],
    matched_bank_indices: set[int],
    matched_ledger_indices: set[int],
    *,
    within_tolerance: Callable[["Transaction", "Transaction"], bool],
    within_date: Callable[["Transaction", "Transaction"], bool],
) -> None:
    """Greedy nearest-date assignment under amount/date window constraints."""
    edges: list[tuple[int, int, int]] = []
    for bi, b in enumerate(bank):
        if bi in matched_bank_indices:
            continue
        for li in bank_candidates[bi]:
            if li in matched_ledger_indices:
                continue
            l = ledger[li]
            if not within_tolerance(b, l) or not within_date(b, l):
                continue
            dd = abs((b.date - l.date).days)
            edges.append((dd, bi, li))
    if not edges:
        return
    edges.sort(key=lambda x: (x[0], x[1], x[2]))
    taken_bank: set[int] = set()
    taken_ledger: set[int] = set()
    for dd, bi, li in edges:
        if bi in matched_bank_indices or li in matched_ledger_indices:
            continue
        if bi in taken_bank or li in taken_ledger:
            continue
        matched_pairs.append((bi, li, "assign"))
        matched_bank_indices.add(bi)
        matched_ledger_indices.add(li)
        taken_bank.add(bi)
        taken_ledger.add(li)


def _group_match(
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
    group_candidates_cap: Optional[int] = None,
    max_combos_per_bank: Optional[int] = None,
    group_time_budget_ms: Optional[int] = None,
) -> None:
    if not group_limit or group_limit <= 1:
        return
    gtol = group_tolerance if group_tolerance is not None else tolerance

    b_ops = [((t.metadata or {}).get("op_type") or classify_op(t.description)) for t in bank]
    b_ibans = [((t.metadata or {}).get("iban") or "") for t in bank]
    b_ben_norm = [(t.beneficiary or "").upper() for t in bank]
    b_ben_key = [_ben_key(t.beneficiary or "") for t in bank]
    l_ibans = [((t.metadata or {}).get("iban") or "") for t in ledger]
    l_ben_norm = [(t.beneficiary or "").upper() for t in ledger]
    l_ben_key = [_ben_key(t.beneficiary or "") for t in ledger]
    l_is_tax = [bool(((t.metadata or {}).get("tax_flag"))) or _is_tax_ledger_entry(t) for t in ledger]

    for bi, b_txn in enumerate(bank):
        if update_progress:
            update_progress(2, bi)
        if bi in matched_bank_indices:
            continue
        t0 = time.perf_counter()
        pair_checks = 0
        triple_checks = 0

        base_candidates = [
            li
            for li in range(len(ledger))
            if li not in matched_ledger_indices and within_date(b_txn, ledger[li])
        ]
        candidates: list[int] = []
        b_op = b_ops[bi]
        b_iban = b_ibans[bi]
        b_ben = b_ben_norm[bi]
        for li in base_candidates:
            l_txn = ledger[li]
            l_iban = l_ibans[li]
            l_ben = l_ben_norm[li]
            is_tax = l_is_tax[li]
            if b_op == "F24" and not is_tax:
                continue
            if b_op == "BONIFICO" and is_tax:
                continue
            if b_iban and l_iban and b_iban != l_iban:
                continue
            if b_ben and l_ben and b_ben_key[bi] != l_ben_key[li]:
                continue
            candidates.append(li)

        tgt = abs(b_txn.amount) if use_absolute_amounts else b_txn.amount
        candidates.sort(key=lambda i: abs(((abs(ledger[i].amount) if use_absolute_amounts else ledger[i].amount) - tgt)))
        if isinstance(group_candidates_cap, int) and group_candidates_cap > 0:
            candidates = candidates[:group_candidates_cap]

        max_r = min(group_limit, len(candidates))
        found = False
        if not found and max_r >= 2:
            bucket = max(gtol, 1e-9)
            amt_to_indices: dict[int, list[int]] = {}
            amts: list[float] = []
            for i in candidates:
                ai = abs(ledger[i].amount) if use_absolute_amounts else ledger[i].amount
                amts.append(ai)
                key = int(round(ai / bucket))
                amt_to_indices.setdefault(key, []).append(i)
            target = tgt
            seen: set[int] = set()
            for idx, i in enumerate(candidates):
                ai = amts[idx]
                need = target - ai
                key = int(round(need / bucket))
                for probe in (key - 1, key, key + 1):
                    for j in amt_to_indices.get(probe, []):
                        if j == i or j in seen:
                            continue
                        pair_checks += 1
                        li1, li2 = (i, j) if i < j else (j, i)
                        if any(l in matched_ledger_indices for l in (li1, li2)):
                            continue
                        l1 = ledger[li1]
                        l2 = ledger[li2]
                        if not all(within_date(b_txn, l) for l in (l1, l2)):
                            continue
                        b_type = b_op
                        if b_type == "F24":
                            continue
                        if b_type == "BONIFICO" and (l_is_tax[li1] or l_is_tax[li2]):
                            continue
                        total = (abs(l1.amount) if use_absolute_amounts else l1.amount) + (abs(l2.amount) if use_absolute_amounts else l2.amount)
                        diff = abs(abs(total) - abs(b_txn.amount)) if use_absolute_amounts else abs(total - b_txn.amount)
                        if diff <= gtol:
                            if beneficiary_mode == "hard":
                                if not (_similarity_str(b_ben, l_ben_norm[li1]) >= fuzzy_threshold and _similarity_str(b_ben, l_ben_norm[li2]) >= fuzzy_threshold):
                                    continue
                            matched_bank_indices.add(bi)
                            matched_ledger_indices.update((li1, li2))
                            matched_pairs.append((bi, tuple(sorted((li1, li2))), "group"))
                            found = True
                            seen.add(li1)
                            seen.add(li2)
                            break
                    if found:
                        break

        if not found and max_r >= 3:
            for combo in itertools.combinations(candidates, 3):
                triple_checks += 1
                if not all(within_date(b_txn, ledger[i]) for i in combo):
                    continue
                if isinstance(max_combos_per_bank, int) and triple_checks > max_combos_per_bank:
                    break
                if isinstance(group_time_budget_ms, int):
                    elapsed_ms = (time.perf_counter() - t0) * 1000.0
                    if elapsed_ms > group_time_budget_ms:
                        break
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
                    continue
                total = sum(abs(ledger[i].amount) if use_absolute_amounts else ledger[i].amount for i in combo)
                diff = abs(abs(total) - abs(b_txn.amount)) if use_absolute_amounts else abs(total - b_txn.amount)
                if diff <= gtol:
                    if beneficiary_mode == "hard":
                        if not all(
                            _similarity_str(b_txn.normalised_beneficiary(), ledger[i].normalised_beneficiary()) >= fuzzy_threshold
                            for i in combo
                        ):
                            continue
                    matched_bank_indices.add(bi)
                    matched_ledger_indices.update(combo)
                    matched_pairs.append((bi, tuple(sorted(combo)), "group"))
                    found = True
                    break

        elapsed = (time.perf_counter() - t0) * 1000.0
        try:
            _log.debug(
                "group_match bi=%d candidates=%d pair_checks=%d triple_checks=%d elapsed_ms=%.2f found=%s",
                bi,
                len(candidates),
                pair_checks,
                triple_checks,
                elapsed,
                found,
            )
        except Exception as e:
            _log.exception("Failed to log group_match diagnostics: %s", e)


def _exact_pass(
    bank: Sequence["Transaction"],
    ledger: Sequence["Transaction"],
    bank_candidates: list[list[int]],
    matched_pairs: list[tuple[int, int | tuple[int, ...], str]],
    matched_bank_indices: set[int],
    matched_ledger_indices: set[int],
    *,
    tolerance: float,
    beneficiary_mode: str,
    fuzzy_threshold: float,
    date_window: int,
    use_absolute_amounts: bool,
    update_progress: Optional[Callable[[int, int], None]] = None,
) -> None:
    """Greedy strict pass: require base constraints + one strong signal.

    Strong signals: shared id, equal IBAN, beneficiary similarity, or F24/tax alignment.
    """
    b_ibans = [((t.metadata or {}).get("iban")) for t in bank]
    l_ibans = [((t.metadata or {}).get("iban")) for t in ledger]
    b_ops = [((t.metadata or {}).get("op_type") or classify_op(t.description)) for t in bank]
    l_tax_flags = [bool(((t.metadata or {}).get("tax_flag"))) or _is_tax_ledger_entry(t) for t in ledger]
    b_ben_norm = [(t.beneficiary or "").upper() for t in bank]
    l_ben_norm = [(t.beneficiary or "").upper() for t in ledger]

    def base_ok(bi: int, li: int) -> bool:
        b = bank[bi]
        l = ledger[li]
        amt_diff = abs(abs(b.amount) - abs(l.amount)) if use_absolute_amounts else abs(b.amount - l.amount)
        if amt_diff > tolerance:
            return False
        if abs((b.date - l.date).days) > date_window:
            return False
        return True

    def type_consistent(bi: int, li: int) -> bool:
        b_type = b_ops[bi]
        if b_type == "F24":
            return l_tax_flags[li]
        if b_type in ("FEE",):
            return True
        if b_type == "BONIFICO":
            return not l_tax_flags[li]
        return True

    def score(bi: int, li: int) -> tuple[float, dict[str, bool | float]]:
        b = bank[bi]
        l = ledger[li]
        b_ids = set(b.reference_ids or [])
        l_ids = set(l.reference_ids or [])
        has_id = bool(b_ids and l_ids and (b_ids & l_ids))
        b_iban = b_ibans[bi]
        l_iban = l_ibans[li]
        has_iban = bool(b_iban and l_iban and b_iban == l_iban)
        ben_sim = _similarity_str(b_ben_norm[bi], l_ben_norm[li])
        b_type = b_ops[bi]
        type_align = type_consistent(bi, li)

        sc = 0.0
        if has_id:
            sc += 1.0
        if has_iban:
            sc += 0.40
        ben_thresh = max(85.0, float(fuzzy_threshold))
        if ben_sim >= max(92.0, ben_thresh):
            sc += 0.40
        elif ben_sim >= ben_thresh:
            sc += 0.30
        if type_align and b_type in ("F24", "BONIFICO", "SDD"):
            sc += 0.20
        if b_type == "F24" and type_align:
            sc = max(sc, 0.80)
        return sc, {"has_id": has_id, "has_iban": has_iban, "ben_sim": float(ben_sim), "type_align": type_align}

    for bi, _ in enumerate(bank):
        if update_progress:
            update_progress(0, bi)
        if bi in matched_bank_indices:
            continue
        best_li = None
        best_sc = -1.0
        best_date_diff = None
        alt_count = 0
        for li in bank_candidates[bi]:
            if li in matched_ledger_indices:
                continue
            if not base_ok(bi, li):
                continue
            if not type_consistent(bi, li):
                continue
            sc, signals = score(bi, li)
            strong = (
                bool(signals["has_id"]) or bool(signals["has_iban"]) or float(signals["ben_sim"]) >= max(85.0, float(fuzzy_threshold)) or (bool(signals["type_align"]) and b_ops[bi] == "F24")
            )
            if not strong:
                continue
            if sc < 0.80:
                continue
            dd = abs((bank[bi].date - ledger[li].date).days)
            if sc > best_sc or (sc == best_sc and (best_date_diff is None or dd < best_date_diff)):
                best_sc = sc
                best_li = li
                best_date_diff = dd
                alt_count = 1
            elif sc == best_sc and dd == best_date_diff:
                alt_count += 1
        if best_li is not None and alt_count == 1:
            matched_pairs.append((bi, best_li, "exact"))
            matched_bank_indices.add(bi)
            matched_ledger_indices.add(best_li)
__all__ = (
    "_txns_to_polars",
    "_pairs_from_candidates",
    "_build_bank_candidates",
    "_assignment_pass",
    "_exact_pass",
    "_fuzzy_score",
    "_fuzzy_pass",
    "_fuzzy_margin_pass",
    "_reference_substring_pass",
)


def _token_intersection_ratio(a: str, b: str) -> int:
    if not a or not b:
        return 0
    tok_a = set(re.findall(r"[A-Z0-9]+", a.upper()))
    tok_b = set(re.findall(r"[A-Z0-9]+", b.upper()))
    if not tok_a or not tok_b:
        return 0
    overlap = len(tok_a & tok_b)
    return int(100.0 * overlap / max(len(tok_a), len(tok_b)))


def _similarity_str(a: str, b: str) -> float:
    """Return similarity score in [0, 100]."""
    if not a or not b:
        return 0.0
    if fuzz:
        return float(fuzz.token_set_ratio(a, b))
    return float(_token_intersection_ratio(a, b))


def _fuzzy_score(b_llm: str, l_loc: str, b_loc: str, l_llm: str) -> float:
    """Return the combined fuzzy score used for description matching."""
    if fuzz:
        return float(
            max(
                fuzz.token_set_ratio(b_llm, l_loc),
                fuzz.token_set_ratio(b_loc, l_loc),
                fuzz.token_set_ratio(b_llm, l_llm),
            )
        )
    return float(
        max(
            _token_intersection_ratio(b_llm, l_loc),
            _token_intersection_ratio(b_loc, l_loc),
            _token_intersection_ratio(b_llm, l_llm),
        )
    )


def _fuzzy_pass(
    bank: Sequence["Transaction"],
    ledger: Sequence["Transaction"],
    bank_candidates: list[list[int]],
    matched_pairs: list[tuple[int, int | tuple[int, ...], str]],
    matched_bank_indices: set[int],
    matched_ledger_indices: set[int],
    *,
    norm_map_local: dict[str, str],
    norm_map: dict[str, str],
    fuzzy_threshold: float,
    update_progress: Optional[Callable[[int, int], None]] = None,
) -> None:
    """Run the fuzzy pass using vectorised Polars joins."""

    cand_df = _pairs_from_candidates(bank_candidates)
    if cand_df.is_empty():
        return
    if matched_bank_indices:
        cand_df = cand_df.filter(~pl.col("bi").is_in(list(matched_bank_indices)))
    if matched_ledger_indices:
        cand_df = cand_df.filter(~pl.col("li").is_in(list(matched_ledger_indices)))
    if cand_df.is_empty():
        return
    bank_df = _txns_to_polars(bank, "bi", "b_")
    ledger_df = _txns_to_polars(ledger, "li", "l_")
    # Include lightweight signals for gating in the fuzzy pass
    b_ibans = [((t.metadata or {}).get("iban") or "") for t in bank]
    l_ibans = [((t.metadata or {}).get("iban") or "") for t in ledger]
    b_ops = [
        ((t.metadata or {}).get("op_type") or classify_op(t.description)) for t in bank
    ]
    l_ops = [
        ((t.metadata or {}).get("op_type") or classify_op(t.description))
        for t in ledger
    ]
    bank_df = bank_df.with_columns(
        pl.col("b_desc").map_elements(lambda d: norm_map.get(d, "")).alias("b_llm"),
        pl.col("b_desc")
        .map_elements(lambda d: norm_map_local.get(d, ""))
        .alias("b_loc"),
        pl.Series("b_iban", b_ibans),
        pl.Series("b_op", b_ops),
    )
    ledger_df = ledger_df.with_columns(
        pl.col("l_desc").map_elements(lambda d: norm_map.get(d, "")).alias("l_llm"),
        pl.col("l_desc")
        .map_elements(lambda d: norm_map_local.get(d, ""))
        .alias("l_loc"),
        pl.Series("l_iban", l_ibans),
        pl.Series("l_op", l_ops),
    )
    joined = cand_df.join(bank_df, on="bi").join(ledger_df, on="li")
    # IBAN gating: if both present, they must match
    joined = joined.filter(
        (pl.col("b_iban") == "")
        | (pl.col("l_iban") == "")
        | (pl.col("b_iban") == pl.col("l_iban"))
    )
    # Operation-type gating: avoid mismatches that are known to be invalid
    # - F24 bank entries should only match F24-like ledger entries
    # - BONIFICO should not match F24 entries
    joined = joined.filter(
        (pl.col("b_op") != "F24") | (pl.col("l_op") == "F24")
    ).filter(~((pl.col("b_op") == "BONIFICO") & (pl.col("l_op") == "F24")))
    joined = joined.with_columns(
        pl.struct(["b_llm", "l_loc", "b_loc", "l_llm"])
        .map_elements(
            lambda s: _fuzzy_score(s["b_llm"], s["l_loc"], s["b_loc"], s["l_llm"])
        )
        .alias("score")
    ).filter(pl.col("score") >= fuzzy_threshold)
    joined = joined.sort("score", descending=True)
    joined = joined.unique(subset=["li"], keep="first")
    selected = joined.group_by("bi").agg(pl.col("li").first())
    for row in selected.iter_rows(named=True):
        bi = int(row["bi"])
        li = row["li"]
        if li is None:
            continue
        matched_pairs.append((bi, int(li), "fuzzy"))
        matched_bank_indices.add(bi)
        matched_ledger_indices.add(int(li))
        if update_progress:
            update_progress(1, bi)


def _fuzzy_margin_pass(
    bank: Sequence["Transaction"],
    ledger: Sequence["Transaction"],
    bank_candidates: list[list[int]],
    matched_pairs: list[tuple[int, int | tuple[int, ...], str]],
    matched_bank_indices: set[int],
    matched_ledger_indices: set[int],
    *,
    norm_map_local: dict[str, str],
    norm_map: dict[str, str],
    fuzzy_threshold: float,
    margin_min: float,
    small_set_k: int,
    relax: float = 10.0,
) -> None:
    """Accept top fuzzy candidate when set is small and score margin is clear.

    Safeguards:
    - Only consider bank rows with ≤ ``small_set_k`` candidates (after filtering used pairs).
    - Accept only when top score ≥ (fuzzy_threshold - relax) and (top - second) ≥ margin_min.
    - IBAN and operation-type gates are reused from the fuzzy pass.
    """
    cand_df = _pairs_from_candidates(bank_candidates)
    if cand_df.is_empty():
        return
    if matched_bank_indices:
        cand_df = cand_df.filter(~pl.col("bi").is_in(list(matched_bank_indices)))
    if matched_ledger_indices:
        cand_df = cand_df.filter(~pl.col("li").is_in(list(matched_ledger_indices)))
    if cand_df.is_empty():
        return
    bank_df = _txns_to_polars(bank, "bi", "b_")
    ledger_df = _txns_to_polars(ledger, "li", "l_")
    b_ibans = [((t.metadata or {}).get("iban") or "") for t in bank]
    l_ibans = [((t.metadata or {}).get("iban") or "") for t in ledger]
    b_ops = [
        ((t.metadata or {}).get("op_type") or classify_op(t.description)) for t in bank
    ]
    l_ops = [
        ((t.metadata or {}).get("op_type") or classify_op(t.description))
        for t in ledger
    ]
    bank_df = bank_df.with_columns(
        pl.col("b_desc").map_elements(lambda d: norm_map.get(d, "")).alias("b_llm"),
        pl.col("b_desc")
        .map_elements(lambda d: norm_map_local.get(d, ""))
        .alias("b_loc"),
        pl.Series("b_iban", b_ibans),
        pl.Series("b_op", b_ops),
    )
    ledger_df = ledger_df.with_columns(
        pl.col("l_desc").map_elements(lambda d: norm_map.get(d, "")).alias("l_llm"),
        pl.col("l_desc")
        .map_elements(lambda d: norm_map_local.get(d, ""))
        .alias("l_loc"),
        pl.Series("l_iban", l_ibans),
        pl.Series("l_op", l_ops),
    )
    joined = (
        _pairs_from_candidates(bank_candidates)
        .join(bank_df, on="bi")
        .join(ledger_df, on="li")
        .filter(
            (pl.col("b_iban") == "")
            | (pl.col("l_iban") == "")
            | (pl.col("b_iban") == pl.col("l_iban"))
        )
        .filter((pl.col("b_op") != "F24") | (pl.col("l_op") == "F24"))
        .filter(~((pl.col("b_op") == "BONIFICO") & (pl.col("l_op") == "F24")))
        .with_columns(
            pl.struct(["b_llm", "l_loc", "b_loc", "l_llm"]).map_elements(
                lambda s: _fuzzy_score(
                    s["b_llm"], s["l_loc"], s["b_loc"], s["l_llm"]
                )
            ).alias("score")
        )
    )
    if joined.is_empty():
        return
    # Rank by score per bank row and compute margin
    joined = joined.sort(["bi", "score"], descending=[False, True])
    top_two = joined.group_by("bi").agg(
        pl.col("li").head(2), pl.col("score").head(2)
    )
    for row in top_two.iter_rows(named=True):
        bi = int(row["bi"]) if row["bi"] is not None else None
        li_vals = row["li"] or []
        sc_vals = row["score"] or []
        if bi is None or len(li_vals) == 0:
            continue
        # enforce small candidate set after filtering used pairs
        cand_count = int(
            cand_df.filter(pl.col("bi") == bi)
            .filter(~pl.col("li").is_in(list(matched_ledger_indices)))
            .height
        )
        if cand_count > small_set_k:
            continue
        top = float(sc_vals[0]) if len(sc_vals) >= 1 else 0.0
        second = float(sc_vals[1]) if len(sc_vals) >= 2 else 0.0
        if top >= (fuzzy_threshold - relax) and (top - second) >= margin_min:
            li1 = int(li_vals[0])
            if bi in matched_bank_indices or li1 in matched_ledger_indices:
                continue
            matched_pairs.append((bi, li1, "fuzzy_margin"))
            matched_bank_indices.add(bi)
            matched_ledger_indices.add(li1)


def _reference_substring_pass(
    bank: Sequence["Transaction"],
    ledger: Sequence["Transaction"],
    bank_candidates: list[list[int]],
    matched_pairs: list[tuple[int, int | tuple[int, ...], str]],
    matched_bank_indices: set[int],
    matched_ledger_indices: set[int],
    *,
    within_tolerance: Callable[["Transaction", "Transaction"], bool],
    within_date: Callable[["Transaction", "Transaction"], bool],
    min_len: int = 7,
) -> None:
    """Accept a single candidate when a long numeric reference substring matches.

    Extracts long numeric tokens from the bank description and checks for their
    presence in ledger descriptions among amount/date candidates. Accepts only
    when exactly one candidate contains any of the tokens.
    """
    num_pat = re.compile(r"\b\d{%d,}\b" % int(max(1, min_len)))
    for bi in range(len(bank)):
        if bi in matched_bank_indices:
            continue
        b = bank[bi]
        tokens = set(b.reference_ids or [])
        tokens.update(num_pat.findall(b.description or ""))
        if not tokens:
            continue
        viable: list[int] = []
        for li in bank_candidates[bi]:
            if li in matched_ledger_indices:
                continue
            l = ledger[li]
            if not within_tolerance(b, l) or not within_date(b, l):
                continue
            desc = l.description or ""
            if any(tok in desc for tok in tokens):
                viable.append(li)
        if len(viable) == 1:
            li = viable[0]
            matched_pairs.append((bi, li, "ref_substring"))
            matched_bank_indices.add(bi)
            matched_ledger_indices.add(li)
