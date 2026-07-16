from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

__all__ = ["NumericToken", "parse_numeric_tokens"]

NumericUnit = Literal["percent", "pp", "plain"]

_NUMBER_TOKEN = re.compile(
    r"""
    (?P<sign>[+\-−])?
    (?P<num>\d+(?:,\d{3})*(?:\.\d+)?)
    (?P<unit>
        %|
        \s*percent\b|
        \s*per\s*cent\b|
        \s*(?:pp|ppt)\b|
        \s*p\.p\.|
        \s*(?:percentage\s+points?)\b|
        \s*points?\b
    )?
    """,
    re.IGNORECASE | re.VERBOSE,
)


@dataclass(frozen=True, slots=True)
class NumericToken:
    value: float
    unit: NumericUnit
    raw: str


def _unit_from_raw(raw: str) -> NumericUnit:
    cleaned = (raw or "").strip().lower()
    if not cleaned:
        return "plain"
    if "%" in cleaned or "percent" in cleaned or "per cent" in cleaned:
        return "percent"
    if "pp" in cleaned or "ppt" in cleaned or "point" in cleaned:
        return "pp"
    return "plain"


def parse_numeric_tokens(text: str) -> list[NumericToken]:
    tokens: list[NumericToken] = []
    for match in _NUMBER_TOKEN.finditer(text or ""):
        raw = match.group(0)
        number = (match.group("num") or "").replace(",", "")
        if not number:
            continue
        try:
            value = float(number)
        except ValueError:
            continue
        sign = match.group("sign")
        if sign in {"-", "−"}:
            value = -value
        tokens.append(
            NumericToken(
                value=value,
                unit=_unit_from_raw(match.group("unit") or ""),
                raw=raw,
            )
        )
    return tokens
