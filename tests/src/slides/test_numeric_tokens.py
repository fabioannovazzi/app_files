from __future__ import annotations

import pytest

from src.slides.numeric_tokens import NumericToken, parse_numeric_tokens


@pytest.mark.parametrize(
    "unit",
    ["pp", "ppt", "p.p.", "percentage point", "percentage points", "points"],
)
def test_explicit_percentage_points_are_not_percent(unit: str) -> None:
    text = f"−2.5 {unit}"

    tokens = parse_numeric_tokens(text)

    assert tokens == [NumericToken(value=-2.5, unit="pp", raw=text)]


@pytest.mark.parametrize("unit", ["%", "percent", "per cent"])
def test_percent_units_remain_percent(unit: str) -> None:
    text = f"+12{unit}"

    tokens = parse_numeric_tokens(text)

    assert tokens == [NumericToken(value=12, unit="percent", raw=text)]


def test_count_and_percentage_point_change_keep_distinct_units() -> None:
    tokens = parse_numeric_tokens("1,200 customers; change +3 percentage points")

    assert tokens == [
        NumericToken(value=1200, unit="plain", raw="1,200"),
        NumericToken(value=3, unit="pp", raw="+3 percentage points"),
    ]
