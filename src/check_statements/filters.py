from __future__ import annotations

import re
import json
import logging
from pathlib import Path
from typing import Any, List, Tuple

logger = logging.getLogger(__name__)

# Centralized fee-pattern loader (shared by multiple passes)
FEE_PATTERN_PATH = Path(__file__).resolve().parent.parent / "config" / "fee_patterns.json"


def load_fee_patterns(path: Path | None = None) -> List[re.Pattern[str]]:
    """Load case-insensitive regex patterns identifying bank fees.

    Falls back to an empty list when the file is missing or malformed.
    """
    cfg = path or FEE_PATTERN_PATH
    try:
        patterns = json.loads(cfg.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.warning("Fee patterns file not found: %s", cfg)
        return []
    compiled: List[re.Pattern[str]] = []
    for pat in patterns:
        try:
            compiled.append(re.compile(pat, re.IGNORECASE))
        except re.error:
            logger.warning("Invalid fee pattern: %s", pat)
    return compiled


# ------------------------
# Bank pre-aggregation (fee folding)
# ------------------------

_RE_INSTANT_MAIN = re.compile(r"(?i)bon(?:\.\s*)?ifo?co|bonifico|\bistan", re.I)
_RE_INSTANT_FEE = re.compile(r"(?i)comm\.?|commissione|commissioni.*istan|comm.*istan", re.I)
_RE_PREPAID_MAIN = re.compile(r"(?i)ricaric.*(carta|prepag)", re.I)
_RE_PREPAID_FEE = re.compile(r"(?i)comm.*ricaric.*(carta|prepag)", re.I)
_RE_CBILL_MAIN = re.compile(r"(?i)cbill", re.I)
_RE_CBILL_FEE = re.compile(r"(?i)comm.*cbill", re.I)


def _preaggregate_bank_transactions(
    rows: list["Transaction"],
    *,
    small_fee_threshold: float = 10.0,
) -> tuple[list["Transaction"], list[int]]:
    """Fold obvious fee children (instant/prepaid/CBILL) into adjacent parents.

    Behaviour is identical to the inlined version previously in
    check_statements_logic; moved here to reduce file size.
    """
    if not rows:
        return rows, list(range(0))

    def _norm(s: str) -> str:
        return " ".join((s or "").upper().split())

    # local imports to avoid heavy, top-level dependencies
    from parsers.extractors import extract_references  # type: ignore

    norm_desc: list[str] = [_norm(t.description) for t in rows]
    ref_ids: list[set[str]] = [set(extract_references(t.description)) for t in rows]

    def is_fee_like(i: int) -> bool:
        s = norm_desc[i]
        if _RE_INSTANT_FEE.search(s) or _RE_PREPAID_FEE.search(s) or _RE_CBILL_FEE.search(s):
            return True
        for pat in load_fee_patterns():
            if pat.search(s):
                return True
        return False

    def parent_type(j: int) -> str | None:
        s = norm_desc[j]
        if _RE_CBILL_MAIN.search(s):
            return "cbill"
        if _RE_PREPAID_MAIN.search(s):
            return "prepaid"
        if _RE_INSTANT_MAIN.search(s) or "ISTANTAN" in s:
            return "instant"
        return None

    def fee_type(i: int) -> str | None:
        s = norm_desc[i]
        if _RE_CBILL_FEE.search(s):
            return "cbill"
        if _RE_PREPAID_FEE.search(s):
            return "prepaid"
        if _RE_INSTANT_FEE.search(s) or "ISTANTAN" in s:
            return "instant"
        return None

    n = len(rows)
    drop: set[int] = set()

    for i in range(n):
        if i in drop:
            continue
        fee_row = rows[i]
        if fee_row.amount is None:
            continue
        if abs(float(fee_row.amount)) > float(small_fee_threshold):
            continue
        if not is_fee_like(i):
            continue

        # candidate neighbours: previous then next
        neigh_indices = [j for j in (i - 1, i + 1) if 0 <= j < n and j not in drop]
        if not neigh_indices:
            continue
        ftype = fee_type(i)
        folded = False
        for j in neigh_indices:
            parent = rows[j]
            if parent.amount is None:
                continue
            if parent.date != fee_row.date:
                continue
            if (parent.amount >= 0) != (fee_row.amount >= 0):
                continue
            if abs(float(parent.amount)) <= abs(float(fee_row.amount)):
                continue
            ptype = parent_type(j)
            if ftype and ptype and ftype != ptype:
                continue
            share_id = bool(ref_ids[i] & ref_ids[j])
            if ptype or ftype or share_id:
                parent.amount = float(parent.amount) + float(fee_row.amount)
                meta = parent.metadata or {}
                folded_list = list(meta.get("folded_fee_children", []))
                folded_list.append({
                    "orig_index": i,
                    "amount": float(fee_row.amount),
                    "description": rows[i].description,
                })
                meta["folded_fee_children"] = folded_list
                meta["folded_fee_total"] = float(meta.get("folded_fee_total", 0.0)) + float(
                    fee_row.amount
                )
                parent.metadata = meta
                drop.add(i)
                folded = True
                break
        if folded:
            continue

    new_rows: list["Transaction"] = []
    new_map: list[int] = []
    for idx, tx in enumerate(rows):
        if idx in drop:
            continue
        new_rows.append(tx)
        new_map.append(idx)
    return new_rows, new_map


# ------------------------
# Early non-transaction filter (apply before matching)
# ------------------------


def _early_filter_bank_transactions(
    rows: list["Transaction"],
) -> tuple[list["Transaction"], list[int], int]:
    """Lightweight early prune using a safe subset of drop patterns.

    Only removes obvious headers/footers/page furniture and numeric balance
    summary lines. Does NOT apply numeric-table heuristics or EXTRAFIDO rules.
    """
    if not rows:
        return rows, list(range(0)), 0
    try:
        from finance.bank_statements.ignore_patterns import DROP_PATTERNS  # type: ignore
    except Exception:
        return rows, list(range(len(rows))), 0

    keep_keys = {
        "drop_summary_headers",
        "drop_page_furniture",
        "drop_mis_extracted_headers",
        "drop_obvious_page_markers",
        "drop_balance_summary",
    }
    pats: list[re.Pattern[str]] = []
    for k in keep_keys:
        pats.extend(DROP_PATTERNS.get(k, []))

    def _norm(s: str) -> str:
        return " ".join((s or "").upper().split())

    kept_idx: list[int] = []
    for i, t in enumerate(rows):
        desc = _norm(t.description)
        if any(p.search(desc) for p in pats):
            continue
        kept_idx.append(i)

    new_rows = [rows[i] for i in kept_idx]
    return new_rows, kept_idx, (len(rows) - len(new_rows))

