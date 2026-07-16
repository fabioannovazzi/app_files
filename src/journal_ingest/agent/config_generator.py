from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Pattern

# Template sent to an external LLM to generate configuration proposals.
PROMPT_TEMPLATE = """You generate configuration ONLY for a deterministic, language-agnostic journal parser.
Input: 50–150 raw lines from a journal (PDF layout text or CSV preview) with NO ground-truth rows.
Return JSON ONLY with fields:
- entry_header_regex (named groups: entry_date, entry_label, unit, location)
- detail_regex (named groups: line_no, account_code, account_desc, memo, optional debit, credit)
- shapes: date_token, account_code, amount (regexes by SHAPE, not words)
- number_format: { infer: true | false, decimal_candidates: [], thousands_candidates: [] }
- date_formats: array of patterns
- drop_rules: { drop_repeated_headers: bool, drop_page_totals_by_sum: bool, drop_carry_forward_by_repeat: bool }
- optional: column_bounds (int[]), table_area ([top,left,bottom,right])
Constraints:
- No natural-language keywords. Base everything on dates, amount tokens, and account-code shapes.
- Do NOT output extracted rows. JSON only.
- Prefer precise, non-greedy regex.
- Amounts look like 1,234.56 or 1.234,56; dates like dd/mm/yyyy, mm/dd/yyyy, or yyyy-mm-dd."""


@dataclass(slots=True)
class LayoutConfigProposal:
    """Lightweight proposal returned by an agent model."""

    entry_header_regex: str
    detail_regex: str
    shapes: Dict[str, str]
    number_format: Dict[str, Any]
    date_formats: List[str]
    drop_rules: Dict[str, bool]
    column_bounds: Optional[List[int]] = None
    table_area: Optional[List[float]] = None


@dataclass(slots=True, kw_only=True)
class ValidatedConfig(LayoutConfigProposal):
    """Validated configuration with compiled regex patterns."""

    entry_header_pattern: Pattern[str]
    detail_pattern: Pattern[str]


def _infer_number_format(lines: List[str]) -> Dict[str, Any]:
    """Infer number format candidates from sample lines."""

    amount_pattern = re.compile(r"[-+]?\d[\d.,]*")
    decimals: set[str] = set()
    thousands: set[str] = set()
    for line in lines:
        for match in amount_pattern.findall(line):
            if "," in match and "." in match:
                # Decide by last separator
                if match.rfind(",") > match.rfind("."):
                    decimals.add(",")
                    thousands.add(".")
                else:
                    decimals.add(".")
                    thousands.add(",")
            elif "," in match:
                decimals.add(",")
            elif "." in match:
                decimals.add(".")
    if decimals or thousands:
        return {
            "infer": False,
            "decimal_candidates": sorted(decimals),
            "thousands_candidates": sorted(thousands),
        }
    return {"infer": True, "decimal_candidates": [], "thousands_candidates": []}


def propose_layout_config(
    sample_lines: List[str], known_schema: List[str] | None = None
) -> LayoutConfigProposal:
    """Propose a layout configuration based on raw journal lines.

    This heuristic implementation does not attempt to fully understand the
    layout. Instead, it returns generic regex patterns that commonly fit
    double-entry journal exports. Real deployments may replace this function
    with an LLM call using :data:`PROMPT_TEMPLATE`.
    """

    date_shape = r"\d{1,4}[/-]\d{1,2}[/-]\d{2,4}"
    account_code_shape = r"[\d/-]+"
    amount_shape = r"-?[\d.,]+"

    entry_header_regex = (
        rf"^(?P<entry_date>{date_shape})\s+"
        r"(?P<entry_label>[^\n]*?)\s*"
        r"(?P<unit>\S+)?\s*"
        r"(?P<location>\S+)?$"
    )

    detail_regex = (
        rf"^(?P<line_no>\d+)\s+"
        rf"(?P<account_code>{account_code_shape})\s+"
        r"(?P<account_desc>[^\d]+?)\s+"
        r"(?P<memo>.*?)\s*"
        rf"(?P<debit>{amount_shape})?\s*"
        rf"(?P<credit>{amount_shape})?$"
    )

    shapes = {
        "date_token": date_shape,
        "account_code": account_code_shape,
        "amount": amount_shape,
    }

    number_format = _infer_number_format(sample_lines)

    drop_rules = {
        "drop_repeated_headers": True,
        "drop_page_totals_by_sum": True,
        "drop_carry_forward_by_repeat": True,
    }

    date_formats = ["%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d"]

    return LayoutConfigProposal(
        entry_header_regex=entry_header_regex,
        detail_regex=detail_regex,
        shapes=shapes,
        number_format=number_format,
        date_formats=date_formats,
        drop_rules=drop_rules,
    )


def gate_config(
    proposal: LayoutConfigProposal, sample_lines: List[str]
) -> ValidatedConfig:
    """Validate a configuration proposal.

    The function ensures the regex patterns compile and that the detail
    pattern matches at least 60% of the provided sample lines.
    """

    try:
        entry_pattern = re.compile(proposal.entry_header_regex)
        detail_pattern = re.compile(proposal.detail_regex)
    except re.error as exc:  # pragma: no cover - exceptional path
        raise ValueError("Invalid regular expression") from exc

    required_header = {"entry_date", "entry_label", "unit", "location"}
    missing_header = required_header - set(entry_pattern.groupindex)
    if missing_header:
        raise ValueError(f"Missing groups in entry_header_regex: {missing_header}")

    required_detail = {"line_no", "account_code", "account_desc", "memo"}
    missing_detail = required_detail - set(detail_pattern.groupindex)
    if missing_detail:
        raise ValueError(f"Missing groups in detail_regex: {missing_detail}")

    matches = sum(1 for line in sample_lines if detail_pattern.search(line))
    total = len(sample_lines)
    match_rate = matches / total if total else 0.0
    if match_rate < 0.6:
        raise ValueError(f"detail_regex match rate {match_rate:.2f} below threshold")

    return ValidatedConfig(
        drop_rules=proposal.drop_rules,
        entry_header_regex=proposal.entry_header_regex,
        detail_regex=proposal.detail_regex,
        number_format=proposal.number_format,
        date_formats=proposal.date_formats,
        column_bounds=proposal.column_bounds,
        table_area=proposal.table_area,
        shapes=proposal.shapes,
        entry_header_pattern=entry_pattern,
        detail_pattern=detail_pattern,
    )
