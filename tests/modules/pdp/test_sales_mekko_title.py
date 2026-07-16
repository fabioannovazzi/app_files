from __future__ import annotations

from modules.pdp.sales_join import _build_mekko_title


def test_build_mekko_title_appends_single_retailer_and_period() -> None:
    category_label = "face primer"
    headers = ["form", "finish"]
    retailers = ["Ulta"]

    title = _build_mekko_title(
        category_label,
        headers,
        "sales",
        window_months=12,
        period="2025-05-01",
        retailers=retailers,
    )

    assert (
        title
        == "Ulta / Category: Face Primer<BR>Sales by form and finish<BR>Rolling 12 months ending 2025 05"
    )


def test_build_mekko_title_with_multiple_retailers_adds_period() -> None:
    category_label = "face primer"
    headers = ["form", "finish"]
    retailers = ["Ulta", "Sephora"]

    title = _build_mekko_title(
        category_label,
        headers,
        "sales",
        window_months=12,
        period="2025-05-01",
        retailers=retailers,
    )

    assert (
        title
        == "Ulta + Sephora / Category: Face Primer<BR>Sales by form and finish<BR>Rolling 12 months ending 2025 05"
    )
