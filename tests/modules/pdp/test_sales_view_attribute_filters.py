from __future__ import annotations

from datetime import date

import polars as pl
import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # type: ignore  # pylint: disable=wrong-import-position

from modules.auth.config import get_auth_config
from modules.pdp.api import app
from modules.pdp.attribute_review_logic import ReviewTables


def _build_minimal_review_tables() -> ReviewTables:
    combined = pl.DataFrame(
        {
            "retailer": ["ulta", "ulta"],
            "brand": ["branda", "branda"],
            "category_key": ["cat1", "cat1"],
            "form": ["Powder", "Liquid"],
        }
    )
    empty_like = pl.DataFrame(schema=combined.schema)
    return ReviewTables(
        parents=empty_like,
        variants=empty_like,
        combined=combined,
        parents_all=empty_like,
    )


def _build_mapping_review_tables() -> ReviewTables:
    parents = pl.DataFrame(
        {
            "retailer": ["ulta", "ulta"],
            "brand": ["branda", "branda"],
            "category_key": ["cat1", "cat1"],
            "parent_product_id": ["p1", "p2"],
            "product_name": ["Powder Parent", "Liquid Parent"],
            "form": ["Powder", "Liquid"],
        }
    )
    variants = pl.DataFrame(
        {
            "retailer": ["ulta", "ulta"],
            "brand": ["branda", "branda"],
            "category_key": ["cat1", "cat1"],
            "parent_product_id": ["p1", "p2"],
            "variant_id": ["v1", "v2"],
            "variant_description": ["Powder Variant", "Liquid Variant"],
            "form": ["Powder", "Liquid"],
        }
    )
    combined = pl.concat([parents, variants], how="diagonal_relaxed")
    return ReviewTables(
        parents=parents,
        variants=variants,
        combined=combined,
        parents_all=parents,
    )


def _build_minimal_review_tables_with_variant_hybrids() -> ReviewTables:
    parents = pl.DataFrame(
        {
            "retailer": ["ulta", "ulta"],
            "brand": ["branda", "branda"],
            "category_key": ["cat1", "cat1"],
            "category_label": ["cat1", "cat1"],
            "parent_product_id": ["p1", "p2"],
            "product_name": ["Powder Parent", "Liquid Parent"],
        }
    )
    variants = pl.DataFrame(
        {
            "retailer": ["ulta", "ulta"],
            "brand": ["branda", "branda"],
            "category_key": ["cat1", "cat1"],
            "category_label": ["cat1", "cat1"],
            "parent_product_id": ["p1", "p2"],
            "variant_id": ["sku1", "sku2"],
            "variant_description": ["Powder Variant", "Liquid Variant"],
            "also_blush": [True, False],
        }
    )
    combined = pl.concat([parents, variants], how="diagonal_relaxed")
    return ReviewTables(
        parents=parents,
        variants=variants,
        combined=combined,
        parents_all=parents,
    )


def _build_minimal_joined_sales_frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "month": [date(2025, 1, 1), date(2025, 1, 1)],
            "merchant": ["ulta", "ulta"],
            "category": ["cat1", "cat1"],
            "brand": ["branda", "branda"],
            "sku": ["sku1", "sku2"],
            "sales": [100.0, 50.0],
            "units": [10.0, 5.0],
            "variant_id": ["sku1", "sku2"],
            "parent_product_id": ["p1", "p2"],
            "category_label": ["cat1", "cat1"],
            "form": ["Powder", "Liquid"],
        }
    )


def _build_minimal_joined_sales_frame_with_hybrids() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "month": [date(2025, 1, 1), date(2025, 1, 1)],
            "merchant": ["ulta", "ulta"],
            "category": ["cat1", "cat1"],
            "brand": ["branda", "branda"],
            "sku": ["sku1", "sku2"],
            "sales": [100.0, 50.0],
            "units": [10.0, 5.0],
            "variant_id": ["sku1", "sku2"],
            "parent_product_id": ["p1", "p2"],
            "category_label": ["cat1", "cat1"],
            "form": ["Powder", "Liquid"],
            "also_blush": [True, False],
            "also_highlighter": [False, True],
        }
    )


def _build_minimal_full_sales_frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "month": [date(2025, 1, 1), date(2025, 1, 1)],
            "merchant": ["ulta", "ulta"],
            "category": ["cat1", "cat1"],
            "brand": ["branda", "branda"],
            "sku": ["sku1", "sku2"],
            "sales": [100.0, 50.0],
            "units": [10.0, 5.0],
        }
    )


def _build_full_sales_frame_with_non_pdp_row() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "month": [date(2025, 1, 1), date(2025, 1, 1), date(2025, 1, 1)],
            "merchant": ["ulta", "ulta", "ulta"],
            "category": ["cat1", "cat1", "cat1"],
            "brand": ["branda", "branda", "branda"],
            "sku": ["sku1", "sku2", "sku3"],
            "sales": [100.0, 50.0, 200.0],
            "units": [10.0, 5.0, 20.0],
        }
    )


def _build_review_tables_with_partial_variant_price_bands() -> ReviewTables:
    parents = pl.DataFrame(
        {
            "retailer": ["ulta", "ulta"],
            "brand": ["branda", "branda"],
            "category_key": ["cat1", "cat1"],
            "category_label": ["cat1", "cat1"],
            "parent_product_id": ["p1", "p2"],
            "product_name": ["Parent 1", "Parent 2"],
        }
    )
    variants = pl.DataFrame(
        {
            "retailer": ["ulta", "ulta"],
            "brand": ["branda", "branda"],
            "category_key": ["cat1", "cat1"],
            "category_label": ["cat1", "cat1"],
            "parent_product_id": ["p1", "p2"],
            "variant_id": ["sku1", "sku2"],
            "variant_description": ["Variant 1", "Variant 2"],
            "price_band": ["value", "mid"],
        }
    )
    combined = pl.concat([parents, variants], how="diagonal_relaxed")
    return ReviewTables(
        parents=parents,
        variants=variants,
        combined=combined,
        parents_all=parents,
    )


def _build_full_sales_frame_for_price_band_dimension() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "month": [date(2025, 1, 1), date(2025, 1, 1), date(2025, 1, 1)],
            "merchant": ["ulta", "ulta", "ulta"],
            "category": ["cat1", "cat1", "cat1"],
            "brand": ["branda", "branda", "branda"],
            "sku": ["sku1", "sku2", "sku3"],
            "sales": [100.0, 200.0, 300.0],
            "units": [10.0, 10.0, 10.0],
        }
    )


def _build_minimal_taxonomy() -> dict:
    return {
        "categories": [
            {
                "id": "cat1",
                "label": "cat1",
                "attributes": [{"id": "form", "label": "Format"}],
            }
        ]
    }


@pytest.fixture(autouse=True)
def _disable_auth_for_sales_view_tests(monkeypatch: pytest.MonkeyPatch):
    for env_var in ("AUTH_ENABLED", "GOOGLE_CLIENT_ID", "AUTH_SESSION_SECRET"):
        monkeypatch.delenv(env_var, raising=False)
    get_auth_config.cache_clear()
    yield
    get_auth_config.cache_clear()


def test_sales_metrics_attribute_filters_applied_when_attribute_dimension_selected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    tables = _build_minimal_review_tables()
    joined_sales = _build_minimal_joined_sales_frame()
    full_sales = _build_minimal_full_sales_frame()

    monkeypatch.setattr("modules.pdp.api._get_tables", lambda: tables)
    monkeypatch.setattr(
        "modules.pdp.api.load_sales_data",
        lambda _retailer=None, dataset=None: joined_sales,
    )
    monkeypatch.setattr(
        "modules.pdp.api.load_full_sales_data",
        lambda _retailer=None, dataset=None: full_sales,
    )
    monkeypatch.setattr(
        "modules.pdp.api.get_attribute_taxonomy", _build_minimal_taxonomy
    )

    client = TestClient(app)

    # Act
    response = client.get(
        "/review/sales/metrics",
        params=[
            ("retailer", "ulta"),
            ("category", "cat1"),
            ("dimension", "form"),
            ("window_months", "1"),
            ("filters", "form:Powder"),
        ],
    )

    # Assert
    assert response.status_code == 200
    payload = response.json()
    assert payload["dimension_headers"] == ["Format"]
    assert payload["total_sales"] == pytest.approx(100.0)
    assert payload["rows"], "Expected at least one aggregated row"
    assert all(row["dimensions"]["Format"] == "Powder" for row in payload["rows"])


def test_attribute_metadata_exposes_hybrid_values_when_hybrids_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    tables = _build_minimal_review_tables()
    tables = ReviewTables(
        parents=tables.parents,
        variants=tables.variants,
        combined=tables.combined.with_columns(
            pl.Series("also_blush", [True, False]),
            pl.Series("also_highlighter", [False, True]),
        ),
        parents_all=tables.parents_all,
    )

    monkeypatch.setattr("modules.pdp.api._get_tables", lambda: tables)
    monkeypatch.setattr(
        "modules.pdp.api.get_attribute_taxonomy", _build_minimal_taxonomy
    )
    monkeypatch.setattr(
        "modules.pdp.api._annotate_records_with_sales_and_price",
        lambda frame, *_args, **_kwargs: (frame, pl.DataFrame()),
    )

    client = TestClient(app)

    # Act
    response = client.get(
        "/review/filters",
        params=[("retailer", "ulta"), ("category", "cat1")],
    )

    # Assert
    assert response.status_code == 200
    payload = response.json()
    assert payload["also_blush_values"] == ["yes", "no"]
    assert payload["hybrid_values"]["also_blush"] == ["yes", "no"]
    assert payload["hybrid_values"]["also_highlighter"] == ["yes", "no"]


def test_sales_metrics_also_blush_filter_forces_join_and_filters_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    tables = _build_minimal_review_tables()
    joined_sales = _build_minimal_joined_sales_frame_with_hybrids()
    full_sales = _build_full_sales_frame_with_non_pdp_row()

    monkeypatch.setattr("modules.pdp.api._get_tables", lambda: tables)
    monkeypatch.setattr(
        "modules.pdp.api.load_sales_data",
        lambda _retailer=None, dataset=None: joined_sales,
    )
    monkeypatch.setattr(
        "modules.pdp.api.load_full_sales_data",
        lambda _retailer=None, dataset=None: full_sales,
    )
    monkeypatch.setattr(
        "modules.pdp.api.get_attribute_taxonomy", _build_minimal_taxonomy
    )

    client = TestClient(app)

    # Act
    response = client.get(
        "/review/sales/metrics",
        params=[
            ("retailer", "ulta"),
            ("category", "cat1"),
            ("dimension", "brand"),
            ("window_months", "1"),
            ("also_blush", "yes"),
        ],
    )

    # Assert
    assert response.status_code == 200
    payload = response.json()
    assert payload["dimension_headers"] == ["Brands"]
    assert payload["total_sales"] == pytest.approx(100.0)
    assert payload["rows"], "Expected at least one aggregated row"


def test_sales_metrics_supports_also_highlighter_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    tables = _build_minimal_review_tables()
    joined_sales = _build_minimal_joined_sales_frame_with_hybrids()
    full_sales = _build_full_sales_frame_with_non_pdp_row()

    monkeypatch.setattr("modules.pdp.api._get_tables", lambda: tables)
    monkeypatch.setattr(
        "modules.pdp.api.load_sales_data",
        lambda _retailer=None, dataset=None: joined_sales,
    )
    monkeypatch.setattr(
        "modules.pdp.api.load_full_sales_data",
        lambda _retailer=None, dataset=None: full_sales,
    )
    monkeypatch.setattr(
        "modules.pdp.api.get_attribute_taxonomy", _build_minimal_taxonomy
    )

    client = TestClient(app)

    # Act
    response = client.get(
        "/review/sales/metrics",
        params=[
            ("retailer", "ulta"),
            ("category", "cat1"),
            ("dimension", "brand"),
            ("window_months", "1"),
            ("also_highlighter", "yes"),
        ],
    )

    # Assert
    assert response.status_code == 200
    payload = response.json()
    assert payload["dimension_headers"] == ["Brands"]
    assert payload["total_sales"] == pytest.approx(50.0)
    assert payload["rows"], "Expected at least one aggregated row"


def test_sales_metrics_supports_hybrid_dimension_grouping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    tables = _build_minimal_review_tables()
    joined_sales = _build_minimal_joined_sales_frame_with_hybrids()
    full_sales = _build_full_sales_frame_with_non_pdp_row()

    monkeypatch.setattr("modules.pdp.api._get_tables", lambda: tables)
    monkeypatch.setattr(
        "modules.pdp.api.load_sales_data",
        lambda _retailer=None, dataset=None: joined_sales,
    )
    monkeypatch.setattr(
        "modules.pdp.api.load_full_sales_data",
        lambda _retailer=None, dataset=None: full_sales,
    )
    monkeypatch.setattr(
        "modules.pdp.api.get_attribute_taxonomy", _build_minimal_taxonomy
    )

    client = TestClient(app)

    # Act
    response = client.get(
        "/review/sales/metrics",
        params=[
            ("retailer", "ulta"),
            ("category", "cat1"),
            ("dimension", "also_blush"),
            ("window_months", "1"),
        ],
    )

    # Assert
    assert response.status_code == 200
    payload = response.json()
    assert payload["dimension_headers"] == ["Also blush"]
    assert payload["rows"], "Expected grouped rows by hybrid dimension"
    observed = {row["dimensions"]["Also blush"] for row in payload["rows"]}
    assert observed == {"yes", "no"}


def test_sales_metrics_hybrid_filter_enriches_prejoined_rows_when_column_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    tables = _build_minimal_review_tables_with_variant_hybrids()
    joined_sales_without_hybrid_column = _build_minimal_joined_sales_frame()
    full_sales = _build_full_sales_frame_with_non_pdp_row()

    monkeypatch.setattr("modules.pdp.api._get_tables", lambda: tables)
    monkeypatch.setattr(
        "modules.pdp.api.load_sales_data",
        lambda _retailer=None, dataset=None: joined_sales_without_hybrid_column,
    )
    monkeypatch.setattr(
        "modules.pdp.api.load_full_sales_data",
        lambda _retailer=None, dataset=None: full_sales,
    )
    monkeypatch.setattr(
        "modules.pdp.api.get_attribute_taxonomy", _build_minimal_taxonomy
    )

    client = TestClient(app)

    # Act
    response = client.get(
        "/review/sales/metrics",
        params=[
            ("retailer", "ulta"),
            ("category", "cat1"),
            ("dimension", "brand"),
            ("window_months", "1"),
            ("also_blush", "yes"),
        ],
    )

    # Assert
    assert response.status_code == 200
    payload = response.json()
    assert payload["dimension_headers"] == ["Brands"]
    assert payload["total_sales"] == pytest.approx(100.0)
    assert payload["rows"], "Expected at least one aggregated row"


def test_sales_metrics_price_band_dimension_uses_full_sales_price_bands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    tables = _build_review_tables_with_partial_variant_price_bands()
    full_sales = _build_full_sales_frame_for_price_band_dimension()

    monkeypatch.setattr("modules.pdp.api._get_tables", lambda: tables)
    monkeypatch.setattr(
        "modules.pdp.api.load_sales_data",
        lambda _retailer=None, dataset=None: full_sales,
    )
    monkeypatch.setattr(
        "modules.pdp.api.load_full_sales_data",
        lambda _retailer=None, dataset=None: full_sales,
    )
    monkeypatch.setattr(
        "modules.pdp.api.get_attribute_taxonomy", _build_minimal_taxonomy
    )

    client = TestClient(app)

    # Act
    response = client.get(
        "/review/sales/metrics",
        params=[
            ("retailer", "ulta"),
            ("category", "cat1"),
            ("dimension", "price_band"),
            ("window_months", "1"),
        ],
    )

    # Assert
    assert response.status_code == 200
    payload = response.json()
    assert payload["dimension_headers"] == ["Price bands"]
    assert payload["total_sales"] == pytest.approx(600.0)
    assert payload["rows"], "Expected grouped rows by price band"
    segments = {row["dimensions"]["Price bands"] for row in payload["rows"]}
    assert "N/A" not in segments


def test_sales_joined_csv_attribute_filters_applied_when_attribute_dimension_selected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    # Arrange
    tables = _build_minimal_review_tables()
    joined_sales = _build_minimal_joined_sales_frame()
    full_sales = _build_minimal_full_sales_frame()

    monkeypatch.setattr("modules.pdp.api._get_tables", lambda: tables)
    monkeypatch.setattr(
        "modules.pdp.api.load_sales_data",
        lambda _retailer=None, dataset=None: joined_sales,
    )
    monkeypatch.setattr(
        "modules.pdp.api.load_full_sales_data",
        lambda _retailer=None, dataset=None: full_sales,
    )
    monkeypatch.setattr(
        "modules.pdp.api.get_attribute_taxonomy", _build_minimal_taxonomy
    )
    monkeypatch.setattr("modules.pdp.api.get_cache_dir", lambda _name: str(tmp_path))

    client = TestClient(app)

    # Act
    response = client.get(
        "/review/sales/joined.csv",
        params=[
            ("retailer", "ulta"),
            ("category", "cat1"),
            ("dimension", "form"),
            ("filters", "form:Powder"),
        ],
    )

    # Assert
    assert response.status_code == 200
    csv_text = response.text
    assert "Format" in csv_text
    assert "Powder" in csv_text
    assert "Liquid" not in csv_text


def test_sales_metrics_attribute_filters_force_join_when_no_attribute_dimension_selected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    tables = _build_minimal_review_tables()
    joined_sales = _build_minimal_joined_sales_frame()
    full_sales = _build_full_sales_frame_with_non_pdp_row()

    monkeypatch.setattr("modules.pdp.api._get_tables", lambda: tables)
    monkeypatch.setattr(
        "modules.pdp.api.load_sales_data",
        lambda _retailer=None, dataset=None: joined_sales,
    )
    monkeypatch.setattr(
        "modules.pdp.api.load_full_sales_data",
        lambda _retailer=None, dataset=None: full_sales,
    )
    monkeypatch.setattr(
        "modules.pdp.api.get_attribute_taxonomy", _build_minimal_taxonomy
    )

    client = TestClient(app)

    # Act
    response = client.get(
        "/review/sales/metrics",
        params=[
            ("retailer", "ulta"),
            ("category", "cat1"),
            ("dimension", "brand"),
            ("window_months", "1"),
            ("filters", "form:Powder"),
        ],
    )

    # Assert
    assert response.status_code == 200
    payload = response.json()
    assert payload["dimension_headers"] == ["Brands"]
    assert payload["total_sales"] == pytest.approx(100.0)
    assert payload["rows"], "Expected at least one aggregated row"


def test_sales_joined_csv_attribute_filters_force_join_when_no_attribute_dimension_selected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    # Arrange
    tables = _build_minimal_review_tables()
    joined_sales = _build_minimal_joined_sales_frame()
    full_sales = _build_minimal_full_sales_frame()

    monkeypatch.setattr("modules.pdp.api._get_tables", lambda: tables)
    monkeypatch.setattr(
        "modules.pdp.api.load_sales_data",
        lambda _retailer=None, dataset=None: joined_sales,
    )
    monkeypatch.setattr(
        "modules.pdp.api.load_full_sales_data",
        lambda _retailer=None, dataset=None: full_sales,
    )
    monkeypatch.setattr(
        "modules.pdp.api.get_attribute_taxonomy", _build_minimal_taxonomy
    )
    monkeypatch.setattr("modules.pdp.api.get_cache_dir", lambda _name: str(tmp_path))

    client = TestClient(app)

    # Act
    response = client.get(
        "/review/sales/joined.csv",
        params=[
            ("retailer", "ulta"),
            ("category", "cat1"),
            ("dimension", "brand"),
            ("filters", "form:Powder"),
        ],
    )

    # Assert
    assert response.status_code == 200
    csv_text = response.text
    assert "Format" in csv_text
    assert "Powder" in csv_text
    assert "Liquid" not in csv_text


def test_sales_metrics_csv_download_respects_chart_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    tables = _build_minimal_review_tables()
    joined_sales = _build_minimal_joined_sales_frame()
    full_sales = _build_minimal_full_sales_frame()

    monkeypatch.setattr("modules.pdp.api._get_tables", lambda: tables)
    monkeypatch.setattr(
        "modules.pdp.api.load_sales_data",
        lambda _retailer=None, dataset=None: joined_sales,
    )
    monkeypatch.setattr(
        "modules.pdp.api.load_full_sales_data",
        lambda _retailer=None, dataset=None: full_sales,
    )
    monkeypatch.setattr(
        "modules.pdp.api.get_attribute_taxonomy", _build_minimal_taxonomy
    )

    client = TestClient(app)

    # Act
    response = client.get(
        "/review/sales/metrics.csv",
        params=[
            ("retailer", "ulta"),
            ("category", "cat1"),
            ("dimension", "form"),
            ("window_months", "1"),
            ("filters", "form:Powder"),
        ],
    )

    # Assert
    assert response.status_code == 200
    csv_text = response.text
    assert "Month,Sales,Units,Sales share,Unit share,Format" in csv_text
    assert "Powder" in csv_text
    assert "Liquid" not in csv_text


def test_sales_attribute_mapping_csv_respects_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    tables = _build_mapping_review_tables()

    monkeypatch.setattr("modules.pdp.api._get_tables_for_coverage", lambda: tables)
    monkeypatch.setattr(
        "modules.pdp.api.get_attribute_taxonomy", _build_minimal_taxonomy
    )

    client = TestClient(app)

    # Act
    response = client.get(
        "/review/sales/attribute-mapping.csv",
        params=[
            ("retailer", "ulta"),
            ("category", "cat1"),
            ("record_type", "variant"),
            ("filters", "form:Powder"),
        ],
    )

    # Assert
    assert response.status_code == 200
    csv_text = response.text
    assert "Format" in csv_text
    assert "Powder Variant" in csv_text
    assert "Liquid Variant" not in csv_text


def test_coverage_does_not_use_sales_dataset_and_excludes_sales_weighting_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    tables = _build_mapping_review_tables()

    monkeypatch.setattr("modules.pdp.api._get_tables_for_coverage", lambda: tables)
    monkeypatch.setattr(
        "modules.pdp.api.get_attribute_taxonomy", _build_minimal_taxonomy
    )

    def _fail_if_sales_loaded(_retailer=None, dataset=None):  # noqa: ANN001
        raise AssertionError(
            "Coverage endpoint should not load the joined sales dataset."
        )

    monkeypatch.setattr("modules.pdp.api.load_sales_data", _fail_if_sales_loaded)

    client = TestClient(app)

    # Act
    response = client.get(
        "/review/coverage",
        params=[
            ("retailer", "ulta"),
            ("category", "cat1"),
            ("record_type", "variant"),
        ],
    )

    # Assert
    assert response.status_code == 200
    payload = response.json()
    assert "weighting" not in payload
    assert "total_sales" not in payload
    assert payload["total_records"] == 2


def test_coverage_returns_503_while_slide_ocr_is_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("modules.pdp.api.is_any_ocr_running", lambda: True)

    client = TestClient(app)

    response = client.get(
        "/review/coverage",
        params=[
            ("retailer", "ulta"),
            ("category", "cat1"),
            ("record_type", "variant"),
        ],
    )

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Review pages are temporarily unavailable while slide OCR is running. "
        "Try again later."
    )


def test_records_not_in_taxonomy_filter_returns_raw_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    parents = pl.DataFrame(
        {
            "retailer": ["ulta", "ulta"],
            "brand": ["branda", "branda"],
            "category_key": ["cat1", "cat1"],
            "parent_product_id": ["p1", "p2"],
            "product_name": ["Powder Parent", "Liquid Parent"],
            "form": ["Powder", "Liquid"],
        }
    )
    variants = pl.DataFrame(
        {
            "retailer": ["ulta", "ulta"],
            "brand": ["branda", "branda"],
            "category_key": ["cat1", "cat1"],
            "parent_product_id": ["p1", "p2"],
            "variant_id": ["v1", "v2"],
            "variant_description": ["Powder Variant", "Liquid Variant"],
            "form": ["not in taxonomy (powder finish)", "Liquid"],
        }
    )
    combined = pl.concat([parents, variants], how="diagonal_relaxed")
    tables = ReviewTables(
        parents=parents,
        variants=variants,
        combined=combined,
        parents_all=parents,
    )

    monkeypatch.setattr("modules.pdp.api._get_tables_for_coverage", lambda: tables)
    monkeypatch.setattr(
        "modules.pdp.api.get_attribute_taxonomy", _build_minimal_taxonomy
    )

    client = TestClient(app)

    # Act
    response = client.get(
        "/review/records",
        params=[
            ("retailer", "ulta"),
            ("category", "cat1"),
            ("record_type", "variant"),
            ("filters", "form:Not in taxonomy"),
            ("limit", "10"),
        ],
    )

    # Assert
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert len(payload["records"]) == 1
    assert payload["records"][0]["form"] == "not in taxonomy (powder finish)"
