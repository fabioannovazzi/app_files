from __future__ import annotations

import re

__all__ = [
    "format_brief_text_numbers",
    "format_delta_pp",
    "format_share_pct",
]


_ARROW_DELTA_PATTERN = re.compile(
    r"""
    (?P<prefix>.*?)
    (?P<start>\d+(?:\.\d+)?)%
    \s*(?:→|->|\u2192)\s*
    (?P<end>\d+(?:\.\d+)?)%
    \s*\(\s*
    (?P<sign>[+\-−‑–])?
    (?P<delta>\d+(?:\.\d+)?)\s*
    (?:(?:p\.p\.)|pp|ppt|percentage\s+points?|points?)
    \s*\)
    """,
    re.IGNORECASE | re.VERBOSE,
)

_PERCENT_TOKEN = re.compile(r"(?<!<)(?P<num>\d+(?:\.\d+)?)%")

_PP_TOKEN = re.compile(
    r"(?P<sign>[+\-−‑–])\s*(?P<num>\d+(?:\.\d+)?)\s*(?:(?:p\.p\.)|pp|ppt|percentage\s+points?|points?)",
    re.IGNORECASE,
)


def format_share_pct(value: float) -> str:
    """Format a share percentage for NotebookLM briefs.

    Rules:
    - Use one decimal place for shares >= 1%.
    - Use "<1%" for shares between 0 and 1.
    """

    if 0.0 < value < 1.0:
        return "<1%"
    return f"{value:.1f}%"


def format_delta_pp(value: float, *, approximate: bool = False) -> str:
    """Format a delta in percentage points for NotebookLM briefs.

    Rules:
    - Use whole-number pp deltas.
    - Use "up N pp" / "down N pp" phrasing (avoid "+N" and "p.p.").
    - When approximate is True, prefix the magnitude with "~".
    """

    rounded = int(round(value))
    if rounded == 0:
        return "flat 0 pp"
    direction = "up" if rounded > 0 else "down"
    magnitude = abs(rounded)
    approx_prefix = "~" if approximate else ""
    return f"{direction} {approx_prefix}{magnitude} pp"


def format_brief_text_numbers(text: str) -> str:
    """Normalize % and pp formatting in free text for NotebookLM.

    The formatter is conservative: it touches only percent tokens ("%") and
    pp/percentage-point tokens, leaving all other numbers unchanged.
    """

    if not text:
        return ""

    def _arrow_repl(match: re.Match[str]) -> str:
        prefix = match.group("prefix") or ""
        start_val = float(match.group("start"))
        end_val = float(match.group("end"))
        delta_raw = float(match.group("delta"))
        sign = match.group("sign") or ""
        if sign in {"-", "−", "‑", "–"}:
            delta_raw = -delta_raw

        start_fmt = format_share_pct(start_val)
        end_fmt = format_share_pct(end_val)

        rounded = int(round(delta_raw))
        approx = (start_fmt == "<1%" or end_fmt == "<1%") and abs(delta_raw - rounded) > 0.05
        delta_fmt = format_delta_pp(delta_raw, approximate=approx)
        return f"{prefix}{start_fmt} → {end_fmt} ({delta_fmt})"

    updated = _ARROW_DELTA_PATTERN.sub(_arrow_repl, text)

    def _percent_repl(match: re.Match[str]) -> str:
        raw = match.group("num") or ""
        try:
            value = float(raw)
        except ValueError:
            return match.group(0)
        return format_share_pct(value)

    updated = _PERCENT_TOKEN.sub(_percent_repl, updated)

    def _pp_repl(match: re.Match[str]) -> str:
        raw = match.group("num") or ""
        try:
            value = float(raw)
        except ValueError:
            return match.group(0)
        sign = match.group("sign") or ""
        if sign in {"-", "−", "‑", "–"}:
            value = -value
        return format_delta_pp(value)

    updated = _PP_TOKEN.sub(_pp_repl, updated)
    return updated
