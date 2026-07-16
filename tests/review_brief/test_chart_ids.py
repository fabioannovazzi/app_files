from __future__ import annotations

from datetime import date

import polars as pl

from src.review_brief.charts import build_dimension_stacked
from src.review_brief.models import DimensionSpec


def test_chart_instance_id_changes_with_time_window_and_filters() -> None:
    segment = DimensionSpec(id="brand", label="Brand", column="brand")

    df_base = pl.DataFrame(
        {
            "month": [date(2024, 1, 1), date(2024, 2, 1)],
            "sales": [10.0, 20.0],
            "brand": ["A", "A"],
        }
    )
    df_shifted = pl.DataFrame(
        {
            "month": [date(2024, 1, 1), date(2024, 3, 1)],
            "sales": [10.0, 20.0],
            "brand": ["A", "A"],
        }
    )

    base = build_dimension_stacked(
        joined=df_base,
        category_key="face_primer",
        category_label="Face primer",
        retailers=["ulta"],
        brands=[],
        universe="full",
        segment=segment,
        placeholder_values=set(),
        top_n=8,
    ).chart
    shifted = build_dimension_stacked(
        joined=df_shifted,
        category_key="face_primer",
        category_label="Face primer",
        retailers=["ulta"],
        brands=[],
        universe="full",
        segment=segment,
        placeholder_values=set(),
        top_n=8,
    ).chart
    filtered = build_dimension_stacked(
        joined=df_base,
        category_key="face_primer",
        category_label="Face primer",
        retailers=["ulta"],
        brands=["example_brand"],
        universe="full",
        segment=segment,
        placeholder_values=set(),
        top_n=8,
    ).chart

    assert base.definition_id == shifted.definition_id
    assert base.chart_id != shifted.chart_id
    assert base.definition_id == filtered.definition_id
    assert base.chart_id != filtered.chart_id

