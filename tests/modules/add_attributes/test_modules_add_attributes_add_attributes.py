from __future__ import annotations

from typing import Any, Dict

import polars as pl
import pytest
from modules.utilities.session_context import get_session_state

from modules.add_attributes.add_attributes import (
    EnrichAttributesResult,
    column_inference,
    resolve_domains_for_dataset,
    enrich_attributes,
)
from modules.add_attributes.normalization import normalize_product_key


session_state = get_session_state()


@pytest.fixture(autouse=True)
def reset_session_state():
    """Clear UI session_state before each test for isolation."""
    get_session_state().clear()
    yield
    get_session_state().clear()


def test_column_inference_none_when_no_df_and_no_state():
    # Arrange
    get_session_state().clear()

    # Act
    result = column_inference(None)

    # Assert
    assert result is None


def test_column_inference_filters_columns_with_excel_and_warns(monkeypatch):
    import importlib

    mod = importlib.import_module("modules.add_attributes.add_attributes")

    # Arrange: simple DataFrame
    df = pl.DataFrame({"Product": ["A"], "Qty": [1]})

    # Non-numeric columns include both columns for this test
    monkeypatch.setattr(
        mod, "_list_non_numeric_columns", lambda _lf: ["Product", "Qty"]
    )
    # Simulate uploaded Excel bytes and no shared columns
    get_session_state()["attr_excel_bytes"] = b"dummy"
    monkeypatch.setattr(mod, "shared_columns", lambda *_a, **_k: [])

    warnings: list[str] = []
    monkeypatch.setattr(mod.ui, "warning", lambda msg: warnings.append(str(msg)))

    # Act
    result = column_inference(df)

    # Assert: default structure returned and warning emitted about no common columns
    assert isinstance(result, dict)
    assert set(result.keys()) == {
        "product_column",
        "category_column",
        "subcategory_column",
        "merchant_column",
        "brand_column",
        "description_column",
    }
    assert all(result[k] is None for k in result)
    assert any("No common columns" in m for m in warnings)


def test_column_inference_uses_rendered_form_result(monkeypatch):
    import importlib

    mod = importlib.import_module("modules.add_attributes.add_attributes")

    # Arrange
    df = pl.DataFrame({"Product": ["A"], "Category": ["C"]})
    monkeypatch.setattr(
        mod, "_list_non_numeric_columns", lambda _lf: ["Product", "Category"]
    )

    # Render step writes the user's selection into session_state
    def fake_render(
        result: Dict[str, str | None],
        columns: list[str],
        *,
        source_mode: str | None = None,
    ) -> None:
        get_session_state()["attr_inference_result"] = {
            "product_column": "Product",
            "category_column": "Category",
            "subcategory_column": None,
            "merchant_column": None,
            "brand_column": None,
            "description_column": None,
        }

    monkeypatch.setattr(mod, "_render_inference_form", fake_render)

    # Act
    result = column_inference(df)

    # Assert
    assert result == get_session_state()["attr_inference_result"]


def test_field_configuration_matches_source_expectations():
    import importlib

    mod = importlib.import_module("modules.add_attributes.add_attributes")

    # Web Search should hide description and allow optional line
    llm_fields, llm_line = mod._field_configuration_for_source(
        mod.SOURCE_DETERMINISTIC_LLM
    )
    assert all(field.result_key != "description_column" for field in llm_fields)
    assert any(field.result_key == "merchant_column" for field in llm_fields)
    assert llm_line.show and llm_line.allow_none and not llm_line.required

    # Product Text should surface segment/line/description and optional brand
    det_fields, det_line = mod._field_configuration_for_source(mod.SOURCE_DETERMINISTIC)
    det_keys = {field.result_key for field in det_fields}
    assert {
        "product_column",
        "category_column",
        "subcategory_column",
        "description_column",
        "brand_column",
    } == det_keys
    assert det_line.show and not det_line.required and det_line.allow_none

    # Excel keeps only product/category and has no line selector
    excel_fields, excel_line = mod._field_configuration_for_source(mod.SOURCE_EXCEL)
    assert {field.result_key for field in excel_fields} == {
        "product_column",
        "category_column",
    }
    assert not excel_line.show


def test_resolve_domains_for_dataset_brand_and_merchant_only(monkeypatch):
    captured: dict[str, set[str]] = {}

    def fake_lookup_websites(llm_wrapper, names, aliases=None, service_tier=None):
        captured["names"] = set(names)
        return {n: f"https://{n}.com" for n in names}

    import importlib

    mod = importlib.import_module("modules.add_attributes.add_attributes")
    monkeypatch.setattr(mod, "lookup_websites", fake_lookup_websites)

    df = pl.DataFrame(
        {
            "product_col": ["Prod A", "Prod B"],
            "brand": pl.Series(["Acme", ["Globex"]], dtype=pl.Object),
            "merchant": pl.Series(
                [
                    "ShopA",
                    ["ShopB", "ShopC"],
                ],
                dtype=pl.Object,
            ),
            "category": ["laptops", None],
        }
    )

    domains = resolve_domains_for_dataset(
        df,
        brand_col="brand",
        merchant_col="merchant",
        category_col="category",
        default_category="general",
        llm_wrapper=object(),
    )

    # Only brand/merchant sites are collected; category websites are ignored.
    assert captured["names"] == {"acme", "globex", "shopa", "shopb", "shopc"}
    assert domains["prod a"] == [
        "https://acme.com",
        "https://shopa.com",
    ]
    assert domains["prod b"] == [
        "https://globex.com",
        "https://shopb.com",
        "https://shopc.com",
    ]


def test_resolve_domains_for_dataset_canonicalizes_product_keys():
    df = pl.DataFrame({"product_col": ["Widget 100ml", "Widget 100 mL"]})

    domains = resolve_domains_for_dataset(
        df,
        brand_col=None,
        merchant_col=None,
        category_col=None,
        default_category="general",
        llm_wrapper=object(),
    )

    norm_key = normalize_product_key("Widget 100ml")
    assert set(domains) == {norm_key}
    assert domains[norm_key] == []


def test_resolve_domains_for_dataset_requires_product_col():
    df = pl.DataFrame({"product": ["P1"]})

    with pytest.raises(ValueError):
        resolve_domains_for_dataset(
            df,
            brand_col=None,
            merchant_col=None,
            category_col=None,
            default_category="general",
            llm_wrapper=object(),
        )


def test_enrich_attributes_raises_for_unknown_category(monkeypatch):
    import importlib

    mod = importlib.import_module("modules.add_attributes.add_attributes")

    # Arrange
    df = pl.DataFrame({"Product": ["A"]})
    monkeypatch.setattr(
        mod,
        "get_attribute_taxonomy",
        lambda: {"categories": [{"id": "known", "attributes": []}]},
    )

    # Act / Assert
    with pytest.raises(ValueError, match="Category 'missing' not found"):
        enrich_attributes(df, "missing", lambda *_a, **_k: {})


def test_enrich_attributes_creates_attr_and_source_columns(monkeypatch):
    import importlib

    mod = importlib.import_module("modules.add_attributes.add_attributes")

    # Arrange: taxonomy with a single attribute that should be present/renamed
    monkeypatch.setattr(
        mod,
        "get_attribute_taxonomy",
        lambda: {"categories": [{"id": "lipstick", "attributes": [{"id": "finish"}]}]},
    )
    monkeypatch.setattr(
        mod,
        "get_attribute_activity_config",
        lambda: {
            "categories": [
                {
                    "id": "lipstick",
                    "attributes": [{"id": "finish", "status": "active"}],
                }
            ]
        },
    )

    df = pl.DataFrame(
        {
            "Product": ["X"],
            "finish_raw": ["matte"],
        }
    )

    # Act
    result = enrich_attributes(df, "lipstick", lambda *_a, **_k: {}, throttle=0)

    # Assert: data contains the normalised attribute column and its source
    assert isinstance(result, EnrichAttributesResult)
    data = result.data
    assert data.height == 1
    assert "finish" in data.columns
    assert "attr_source_finish" in data.columns
    assert data.get_column("finish").to_list() == ["matte"]
    # No LLM used -> source stays None
    assert data.get_column("attr_source_finish").to_list() == [None]

    # Websites table is present with expected structure
    websites = result.websites
    assert websites.height == 1
    assert set(websites.columns) == {"product", "websites"}


def test_enrich_attributes_sets_na_for_missing_values(monkeypatch):
    import importlib

    mod = importlib.import_module("modules.add_attributes.add_attributes")

    monkeypatch.setattr(
        mod,
        "get_attribute_taxonomy",
        lambda: {"categories": [{"id": "lipstick", "attributes": [{"id": "finish"}]}]},
    )

    monkeypatch.setattr(
        mod,
        "get_attribute_activity_config",
        lambda: {
            "categories": [
                {
                    "id": "lipstick",
                    "attributes": [{"id": "finish", "status": "active"}],
                }
            ]
        },
    )

    df = pl.DataFrame({"Product": ["X"]})

    result = enrich_attributes(df, "lipstick", lambda *_a, **_k: {}, throttle=0)

    assert result.data.get_column("finish").to_list() == ["N/A"]
    websites = result.websites
    assert websites.height == 1
    assert set(websites.columns) == {"product", "websites"}


def test_enrich_attributes_skips_inactive_attributes(monkeypatch):
    import importlib

    mod = importlib.import_module("modules.add_attributes.add_attributes")

    monkeypatch.setattr(
        mod,
        "get_attribute_taxonomy",
        lambda: {
            "categories": [
                {
                    "id": "lipstick",
                    "attributes": [
                        {"id": "finish"},
                        {"id": "form"},
                    ],
                }
            ]
        },
    )

    monkeypatch.setattr(
        mod,
        "get_attribute_activity_config",
        lambda: {
            "categories": [
                {
                    "id": "lipstick",
                    "attributes": [
                        {"id": "finish", "status": "not active"},
                        {"id": "form", "status": "active"},
                    ],
                }
            ]
        },
    )

    prompts: list[str] = []

    def fake_llm(prompt: str, _domains: list[str] | None = None) -> dict[str, str]:
        prompts.append(prompt)
        return {"form": "stick"}

    df = pl.DataFrame({"Product": ["Lip Product"]})

    result = enrich_attributes(df, "lipstick", fake_llm, throttle=0)

    assert result.data.get_column("form").to_list() == ["stick"]
    assert result.data.get_column("finish").to_list() == ["N/A"]
    assert len(prompts) == 1
    assert "form" in prompts[0].lower()
    assert "finish" not in prompts[0].lower()


def test_enrich_attributes_without_llm_wrapper_handles_brand_columns(monkeypatch):
    import importlib

    mod = importlib.import_module("modules.add_attributes.add_attributes")

    monkeypatch.setattr(
        mod,
        "get_attribute_taxonomy",
        lambda: {"categories": [{"id": "lipstick", "attributes": [{"id": "finish"}]}]},
    )
    monkeypatch.setattr(mod, "BRAND_ALIASES", {})
    monkeypatch.setattr(
        mod,
        "get_attribute_activity_config",
        lambda: {
            "categories": [
                {
                    "id": "lipstick",
                    "attributes": [{"id": "finish", "status": "active"}],
                }
            ]
        },
    )

    df = pl.DataFrame({"Product": ["Lip"], "brand": ["Acme"]})

    result = mod.enrich_attributes(
        df,
        "lipstick",
        lambda *_a, **_k: {},
        throttle=0,
        brand_col="brand",
        llm_wrapper=None,
    )

    assert result.data.get_column("finish").to_list() == ["N/A"]
    assert result.websites.height == 1
    assert set(result.websites.columns) == {"product", "websites"}


def test_load_brand_aliases_missing_file_returns_empty_dict(tmp_path):
    import importlib

    mod = importlib.import_module("modules.add_attributes.add_attributes")
    missing = tmp_path / "aliases.json"

    aliases = mod._load_brand_aliases(missing)

    assert aliases == {}


def test_enrich_attributes_handles_numeric_and_placeholder_values(monkeypatch):
    import importlib

    mod = importlib.import_module("modules.add_attributes.add_attributes")

    monkeypatch.setattr(
        mod,
        "get_attribute_taxonomy",
        lambda: {"categories": [{"id": "clothing", "attributes": [{"id": "size"}]}]},
    )
    monkeypatch.setattr(
        mod,
        "get_attribute_activity_config",
        lambda: {
            "categories": [
                {
                    "id": "clothing",
                    "attributes": [{"id": "size", "status": "active"}],
                }
            ]
        },
    )

    df = pl.DataFrame({"Product": ["A", "B"], "size": [10, None]})

    result = mod.enrich_attributes(df, "clothing", lambda *_a, **_k: {}, throttle=0)

    size_col = result.data.get_column("size")
    assert size_col.dtype == pl.String
    assert size_col.to_list() == ["10", "N/A"]


def test_render_attribute_classification_joins_brand_and_total_amount(monkeypatch):
    import importlib

    mod = importlib.import_module("modules.add_attributes.add_attributes")

    mapping = {"product_column": "Product", "brand_column": "Brand"}
    df = pl.DataFrame({"Product": ["P1"]})

    session_state["attr_top_products"] = ["P1"]
    session_state["attr_top_data"] = pl.DataFrame(
        {
            "Product": ["P1"],
            "Brand": ["B1"],
            "Revenue": [10.0],
            "TopProduct": [True],
        }
    )
    session_state["attr_ranking"] = pl.DataFrame({"Product": ["P1"], "rank": [1]})
    session_state["attr_amount_col"] = "Revenue"
    session_state["attr_auto_join"] = False
    session_state["llm_wrapper"] = object()

    def fake_prepare(*_a, **_k):
        return {"attr": ["val"]}

    def fake_classify(*_a, **_k):
        return pl.DataFrame({"Product": ["P1"], "attr": ["val"]})

    class DummyProgress:
        def progress(self, *_a, **_k):
            return None

    class DummySpinner:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

    def fake_button(*_a, key: str | None = None, **_k):
        return key == "attr_classify_btn"

    monkeypatch.setattr(mod, "_prepare_objective_attribute_map", fake_prepare)
    monkeypatch.setattr(mod, "_classify_attributes_batch", fake_classify)
    monkeypatch.setattr(mod, "_fetch_top_websites", lambda *_a, **_k: pl.DataFrame())
    monkeypatch.setattr(mod.ui, "progress", lambda *_a, **_k: DummyProgress())
    monkeypatch.setattr(mod.ui, "spinner", lambda *_a, **_k: DummySpinner())
    monkeypatch.setattr(mod.ui, "button", fake_button)
    monkeypatch.setattr(mod.ui, "data_editor", lambda df, **_k: df)
    monkeypatch.setattr(mod.ui, "download_button", lambda *a, **k: None)
    captured: dict[str, pl.DataFrame] = {}

    def fake_convert(df: pl.DataFrame) -> bytes:
        captured["df"] = df
        return b"excel"

    monkeypatch.setattr(mod, "convert_df_excel", fake_convert)
    monkeypatch.setattr(mod.ui, "info", lambda *a, **k: None)

    mod._render_attribute_classification(mapping, df)

    table = session_state.get("attr_classification")
    assert table is not None
    assert "Brand" in table.columns
    assert "total_amount" in table.columns
    assert "TopProduct" not in table.columns
    assert table.get_column("Brand").to_list() == ["B1"]
    assert table.get_column("total_amount").to_list() == [10.0]
    assert "rank" not in table.columns
    expected_ranking = session_state["attr_ranking"]
    exported = captured["df"]
    assert "Brand" in exported.columns
    assert exported.get_column("Brand").to_list() == ["B1"]
    if "rank" in expected_ranking.columns:
        assert (
            exported.get_column("rank").to_list()
            == expected_ranking.get_column("rank").to_list()
        )


def test_render_attribute_classification_sorts_rank_nulls_last(monkeypatch):
    import importlib

    mod = importlib.import_module("modules.add_attributes.add_attributes")

    mapping = {"product_column": "Product"}
    df = pl.DataFrame({"Product": ["P1", "P2", "P3"]})

    session_state["attr_top_products"] = ["P1", "P2", "P3"]
    session_state["attr_top_data"] = pl.DataFrame(
        {
            "Product": ["P1", "P2", "P3"],
            "Revenue": [10.0, 5.0, 1.0],
            "TopProduct": [True, True, True],
        }
    )
    session_state["attr_ranking"] = pl.DataFrame(
        {"Product": ["P1", "P3"], "rank": [1, 2]}
    )
    session_state["attr_amount_col"] = "Revenue"
    session_state["attr_auto_join"] = False
    session_state["llm_wrapper"] = object()

    def fake_prepare(*_a, **_k):
        return {"attr": ["val"]}

    def fake_classify(*_a, **_k):
        return pl.DataFrame({"Product": ["P1", "P2", "P3"], "attr": ["v1", "v2", "v3"]})

    class DummyProgress:
        def progress(self, *_a, **_k):
            return None

    class DummySpinner:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

    def fake_button(*_a, key: str | None = None, **_k):
        return key == "attr_classify_btn"

    captured: dict[str, pl.DataFrame] = {}

    def fake_write_csv(df: pl.DataFrame, *args, **kwargs) -> bytes:
        captured["export"] = df
        return b"csv"

    monkeypatch.setattr(mod, "_prepare_objective_attribute_map", fake_prepare)
    monkeypatch.setattr(mod, "_classify_attributes_batch", fake_classify)
    monkeypatch.setattr(mod, "_fetch_top_websites", lambda *_a, **_k: pl.DataFrame())
    monkeypatch.setattr(mod.ui, "progress", lambda *_a, **_k: DummyProgress())
    monkeypatch.setattr(mod.ui, "spinner", lambda *_a, **_k: DummySpinner())
    monkeypatch.setattr(mod.ui, "button", fake_button)
    monkeypatch.setattr(mod.ui, "data_editor", lambda df, **_k: df)
    monkeypatch.setattr(mod.ui, "download_button", lambda *a, **k: None)
    monkeypatch.setattr(mod.ui, "info", lambda *a, **k: None)
    monkeypatch.setattr(mod.ui, "warning", lambda *a, **k: None)
    monkeypatch.setattr(pl.DataFrame, "write_csv", fake_write_csv)
    monkeypatch.setattr(mod, "convert_df_excel", lambda *_a, **_k: b"excel")

    mod._render_attribute_classification(mapping, df)

    table = session_state.get("attr_classification")
    assert table.get_column("Product").to_list() == ["P1", "P3", "P2"]
    assert captured["export"].get_column("Product").to_list() == ["P1", "P3", "P2"]


def test_render_attribute_classification_sorts_total_amount_nulls_last(monkeypatch):
    import importlib

    mod = importlib.import_module("modules.add_attributes.add_attributes")

    mapping = {"product_column": "Product"}
    df = pl.DataFrame({"Product": ["P1", "P2", "P3"]})

    session_state["attr_top_products"] = ["P1", "P2", "P3"]
    session_state["attr_top_data"] = pl.DataFrame(
        {
            "Product": ["P1", "P2", "P3"],
            "Revenue": [10.0, None, 5.0],
            "TopProduct": [True, True, True],
        }
    )
    session_state["attr_ranking"] = pl.DataFrame({})
    session_state["attr_amount_col"] = "Revenue"
    session_state["attr_auto_join"] = False
    session_state["llm_wrapper"] = object()

    def fake_prepare(*_a, **_k):
        return {"attr": ["val"]}

    def fake_classify(*_a, **_k):
        return pl.DataFrame({"Product": ["P1", "P2", "P3"], "attr": ["v1", "v2", "v3"]})

    class DummyProgress:
        def progress(self, *_a, **_k):
            return None

    class DummySpinner:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

    def fake_button(*_a, key: str | None = None, **_k):
        return key == "attr_classify_btn"

    captured: dict[str, pl.DataFrame] = {}

    def fake_write_csv(df: pl.DataFrame, *args, **kwargs) -> bytes:
        captured["export"] = df
        return b"csv"

    monkeypatch.setattr(mod, "_prepare_objective_attribute_map", fake_prepare)
    monkeypatch.setattr(mod, "_classify_attributes_batch", fake_classify)
    monkeypatch.setattr(mod, "_fetch_top_websites", lambda *_a, **_k: pl.DataFrame())
    monkeypatch.setattr(mod.ui, "progress", lambda *_a, **_k: DummyProgress())
    monkeypatch.setattr(mod.ui, "spinner", lambda *_a, **_k: DummySpinner())
    monkeypatch.setattr(mod.ui, "button", fake_button)
    monkeypatch.setattr(mod.ui, "data_editor", lambda df, **_k: df)
    monkeypatch.setattr(mod.ui, "download_button", lambda *a, **k: None)
    monkeypatch.setattr(mod.ui, "info", lambda *a, **k: None)
    monkeypatch.setattr(mod.ui, "warning", lambda *a, **k: None)
    monkeypatch.setattr(pl.DataFrame, "write_csv", fake_write_csv)
    monkeypatch.setattr(mod, "convert_df_excel", lambda *_a, **_k: b"excel")

    mod._render_attribute_classification(mapping, df)

    table = session_state.get("attr_classification")
    assert table.get_column("total_amount").to_list() == [10.0, 5.0, None]
    assert captured["export"].get_column("total_amount").to_list() == [10.0, 5.0, None]


def test_render_attribute_classification_sorts_rank_nulls_last(monkeypatch):
    import importlib

    mod = importlib.import_module("modules.add_attributes.add_attributes")

    mapping = {"product_column": "Product"}
    df = pl.DataFrame({"Product": ["P1", "P2", "P3"]})

    session_state["attr_top_products"] = ["P1", "P2", "P3"]
    session_state["attr_top_data"] = pl.DataFrame(
        {
            "Product": ["P1", "P2", "P3"],
            "Revenue": [10.0, 5.0, 1.0],
            "TopProduct": [True, True, True],
        }
    )
    session_state["attr_ranking"] = pl.DataFrame(
        {"Product": ["P1", "P3"], "rank": [1, 2]}
    )
    session_state["attr_amount_col"] = "Revenue"
    session_state["attr_auto_join"] = False
    session_state["llm_wrapper"] = object()

    def fake_prepare(*_a, **_k):
        return {"attr": ["val"]}

    def fake_classify(*_a, **_k):
        return pl.DataFrame({"Product": ["P1", "P2", "P3"], "attr": ["v1", "v2", "v3"]})

    class DummyProgress:
        def progress(self, *_a, **_k):
            return None

    class DummySpinner:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

    def fake_button(*_a, key: str | None = None, **_k):
        return key == "attr_classify_btn"

    captured: dict[str, pl.DataFrame] = {}

    def fake_write_csv(df: pl.DataFrame, *args, **kwargs) -> bytes:
        captured["export"] = df
        return b"csv"

    monkeypatch.setattr(mod, "_prepare_objective_attribute_map", fake_prepare)
    monkeypatch.setattr(mod, "_classify_attributes_batch", fake_classify)
    monkeypatch.setattr(mod, "_fetch_top_websites", lambda *_a, **_k: pl.DataFrame())
    monkeypatch.setattr(mod.ui, "progress", lambda *_a, **_k: DummyProgress())
    monkeypatch.setattr(mod.ui, "spinner", lambda *_a, **_k: DummySpinner())
    monkeypatch.setattr(mod.ui, "button", fake_button)
    monkeypatch.setattr(mod.ui, "data_editor", lambda df, **_k: df)
    monkeypatch.setattr(mod.ui, "download_button", lambda *a, **k: None)
    monkeypatch.setattr(mod.ui, "info", lambda *a, **k: None)
    monkeypatch.setattr(mod.ui, "warning", lambda *a, **k: None)
    monkeypatch.setattr(pl.DataFrame, "write_csv", fake_write_csv)
    monkeypatch.setattr(mod, "convert_df_excel", lambda *_a, **_k: b"excel")

    mod._render_attribute_classification(mapping, df)

    table = session_state.get("attr_classification")
    assert table.get_column("Product").to_list() == ["P1", "P3", "P2"]
    assert captured["export"].get_column("Product").to_list() == ["P1", "P3", "P2"]


def test_render_attribute_classification_sorts_total_amount_nulls_last(monkeypatch):
    import importlib

    mod = importlib.import_module("modules.add_attributes.add_attributes")

    mapping = {"product_column": "Product"}
    df = pl.DataFrame({"Product": ["P1", "P2", "P3"]})

    session_state["attr_top_products"] = ["P1", "P2", "P3"]
    session_state["attr_top_data"] = pl.DataFrame(
        {
            "Product": ["P1", "P2", "P3"],
            "Revenue": [10.0, None, 5.0],
            "TopProduct": [True, True, True],
        }
    )
    session_state["attr_ranking"] = pl.DataFrame({})
    session_state["attr_amount_col"] = "Revenue"
    session_state["attr_auto_join"] = False
    session_state["llm_wrapper"] = object()

    def fake_prepare(*_a, **_k):
        return {"attr": ["val"]}

    def fake_classify(*_a, **_k):
        return pl.DataFrame({"Product": ["P1", "P2", "P3"], "attr": ["v1", "v2", "v3"]})

    class DummyProgress:
        def progress(self, *_a, **_k):
            return None

    class DummySpinner:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

    def fake_button(*_a, key: str | None = None, **_k):
        return key == "attr_classify_btn"

    captured: dict[str, pl.DataFrame] = {}

    def fake_write_csv(df: pl.DataFrame, *args, **kwargs) -> bytes:
        captured["export"] = df
        return b"csv"

    monkeypatch.setattr(mod, "_prepare_objective_attribute_map", fake_prepare)
    monkeypatch.setattr(mod, "_classify_attributes_batch", fake_classify)
    monkeypatch.setattr(mod, "_fetch_top_websites", lambda *_a, **_k: pl.DataFrame())
    monkeypatch.setattr(mod.ui, "progress", lambda *_a, **_k: DummyProgress())
    monkeypatch.setattr(mod.ui, "spinner", lambda *_a, **_k: DummySpinner())
    monkeypatch.setattr(mod.ui, "button", fake_button)
    monkeypatch.setattr(mod.ui, "data_editor", lambda df, **_k: df)
    monkeypatch.setattr(mod.ui, "download_button", lambda *a, **k: None)
    monkeypatch.setattr(mod.ui, "info", lambda *a, **k: None)
    monkeypatch.setattr(mod.ui, "warning", lambda *a, **k: None)
    monkeypatch.setattr(pl.DataFrame, "write_csv", fake_write_csv)
    monkeypatch.setattr(mod, "convert_df_excel", lambda *_a, **_k: b"excel")

    mod._render_attribute_classification(mapping, df)

    table = session_state.get("attr_classification")
    assert table.get_column("total_amount").to_list() == [10.0, 5.0, None]
    assert captured["export"].get_column("total_amount").to_list() == [10.0, 5.0, None]


def test_render_attribute_classification_sorts_rank_nulls_last(monkeypatch):
    import importlib

    mod = importlib.import_module("modules.add_attributes.add_attributes")

    mapping = {"product_column": "Product"}
    df = pl.DataFrame({"Product": ["P1", "P2", "P3"]})

    session_state["attr_top_products"] = ["P1", "P2", "P3"]
    session_state["attr_top_data"] = pl.DataFrame(
        {
            "Product": ["P1", "P2", "P3"],
            "Revenue": [10.0, 5.0, 1.0],
            "TopProduct": [True, True, True],
        }
    )
    session_state["attr_ranking"] = pl.DataFrame(
        {"Product": ["P1", "P3"], "rank": [1, 2]}
    )
    session_state["attr_amount_col"] = "Revenue"
    session_state["attr_auto_join"] = False
    session_state["llm_wrapper"] = object()

    def fake_prepare(*_a, **_k):
        return {"attr": ["val"]}

    def fake_classify(*_a, **_k):
        return pl.DataFrame({"Product": ["P1", "P2", "P3"], "attr": ["v1", "v2", "v3"]})

    class DummyProgress:
        def progress(self, *_a, **_k):
            return None

    class DummySpinner:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

    def fake_button(*_a, key: str | None = None, **_k):
        return key == "attr_classify_btn"

    captured: dict[str, pl.DataFrame] = {}

    def fake_write_csv(df: pl.DataFrame, *args, **kwargs) -> bytes:
        captured["export"] = df
        return b"csv"

    monkeypatch.setattr(mod, "_prepare_objective_attribute_map", fake_prepare)
    monkeypatch.setattr(mod, "_classify_attributes_batch", fake_classify)
    monkeypatch.setattr(mod, "_fetch_top_websites", lambda *_a, **_k: pl.DataFrame())
    monkeypatch.setattr(mod.ui, "progress", lambda *_a, **_k: DummyProgress())
    monkeypatch.setattr(mod.ui, "spinner", lambda *_a, **_k: DummySpinner())
    monkeypatch.setattr(mod.ui, "button", fake_button)
    monkeypatch.setattr(mod.ui, "data_editor", lambda df, **_k: df)
    monkeypatch.setattr(mod.ui, "download_button", lambda *a, **k: None)
    monkeypatch.setattr(mod.ui, "info", lambda *a, **k: None)
    monkeypatch.setattr(mod.ui, "warning", lambda *a, **k: None)
    monkeypatch.setattr(pl.DataFrame, "write_csv", fake_write_csv)
    monkeypatch.setattr(mod, "convert_df_excel", lambda *_a, **_k: b"excel")

    mod._render_attribute_classification(mapping, df)

    table = session_state.get("attr_classification")
    assert table.get_column("Product").to_list() == ["P1", "P3", "P2"]
    assert captured["export"].get_column("Product").to_list() == ["P1", "P3", "P2"]


def test_render_attribute_classification_sorts_total_amount_nulls_last(monkeypatch):
    import importlib

    mod = importlib.import_module("modules.add_attributes.add_attributes")

    mapping = {"product_column": "Product"}
    df = pl.DataFrame({"Product": ["P1", "P2", "P3"]})

    session_state["attr_top_products"] = ["P1", "P2", "P3"]
    session_state["attr_top_data"] = pl.DataFrame(
        {
            "Product": ["P1", "P2", "P3"],
            "Revenue": [10.0, None, 5.0],
            "TopProduct": [True, True, True],
        }
    )
    session_state["attr_ranking"] = pl.DataFrame({})
    session_state["attr_amount_col"] = "Revenue"
    session_state["attr_auto_join"] = False
    session_state["llm_wrapper"] = object()

    def fake_prepare(*_a, **_k):
        return {"attr": ["val"]}

    def fake_classify(*_a, **_k):
        return pl.DataFrame({"Product": ["P1", "P2", "P3"], "attr": ["v1", "v2", "v3"]})

    class DummyProgress:
        def progress(self, *_a, **_k):
            return None

    class DummySpinner:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

    def fake_button(*_a, key: str | None = None, **_k):
        return key == "attr_classify_btn"

    captured: dict[str, pl.DataFrame] = {}

    def fake_write_csv(df: pl.DataFrame, *args, **kwargs) -> bytes:
        captured["export"] = df
        return b"csv"

    monkeypatch.setattr(mod, "_prepare_objective_attribute_map", fake_prepare)
    monkeypatch.setattr(mod, "_classify_attributes_batch", fake_classify)
    monkeypatch.setattr(mod, "_fetch_top_websites", lambda *_a, **_k: pl.DataFrame())
    monkeypatch.setattr(mod.ui, "progress", lambda *_a, **_k: DummyProgress())
    monkeypatch.setattr(mod.ui, "spinner", lambda *_a, **_k: DummySpinner())
    monkeypatch.setattr(mod.ui, "button", fake_button)
    monkeypatch.setattr(mod.ui, "data_editor", lambda df, **_k: df)
    monkeypatch.setattr(mod.ui, "download_button", lambda *a, **k: None)
    monkeypatch.setattr(mod.ui, "info", lambda *a, **k: None)
    monkeypatch.setattr(mod.ui, "warning", lambda *a, **k: None)
    monkeypatch.setattr(pl.DataFrame, "write_csv", fake_write_csv)
    monkeypatch.setattr(mod, "convert_df_excel", lambda *_a, **_k: b"excel")

    mod._render_attribute_classification(mapping, df)

    table = session_state.get("attr_classification")
    assert table.get_column("total_amount").to_list() == [10.0, 5.0, None]
    assert captured["export"].get_column("total_amount").to_list() == [10.0, 5.0, None]


def test_classify_attributes_batch_aggregates_queue(monkeypatch):
    import importlib

    mod = importlib.import_module("modules.add_attributes.add_attributes")

    df = pl.DataFrame({"Product": []})

    monkeypatch.setattr(
        mod,
        "classify_attributes_for_products",
        lambda *_a, **_k: df,
    )

    called: dict[str, Any] = {}

    def fake_aggregate(top_k: int):
        called["agg"] = top_k
        return [{"category": "c", "attribute": "a", "value": "v", "count": 1}]

    def fake_save(entries):
        called["save"] = entries

    monkeypatch.setattr(mod, "aggregate_pending_values", fake_aggregate)
    monkeypatch.setattr(mod, "save_taxonomy_review_queue", fake_save)

    out = mod._classify_attributes_batch(
        llm_wrapper=None,
        data=df,
        product_col="Product",
        products=[],
        attr_map={},
        group_col=None,
        groups=None,
        use_batch=False,
        service_tier="",
    )

    assert out is df
    assert called["agg"] == 20
    assert called["save"] == [
        {"category": "c", "attribute": "a", "value": "v", "count": 1}
    ]


def test_classify_attributes_handles_label_lookup(monkeypatch):
    import importlib

    ac = importlib.import_module("modules.add_attributes.attribute_classification")

    taxonomy = {
        "categories": [
            {
                "id": "lip_gloss",
                "label": "Lip Gloss",
                "attributes": [
                    {
                        "id": "applicator_type",
                        "label": "Applicator Type",
                        "nodes": [
                            {"id": "doe_foot", "label": "Doe Foot"},
                        ],
                    }
                ],
            }
        ]
    }

    df = pl.DataFrame(
        {
            "Product": ["Gloss One"],
            "Segment": ["lip gloss"],
            "description": ["Doe foot applicator"],
        }
    )

    monkeypatch.setattr(ac, "get_attribute_taxonomy", lambda: taxonomy)
    product_key = normalize_product_key("Gloss One")
    cache = {"lip gloss": {"": {product_key: {"applicator type": "Doe Foot"}}}}
    monkeypatch.setattr(ac, "load_cache", lambda: cache)
    monkeypatch.setattr(ac, "save_cache", lambda _data: None)
    monkeypatch.setattr(ac, "normalize_all_categories", lambda: None)

    result = ac.classify_attributes_for_products(
        llm_wrapper=None,
        df=df,
        product_col="Product",
        products=["Gloss One"],
        attr_map={},
        group_col="Segment",
        groups=["lip gloss"],
        deterministic_only=True,
    )

    lower_cols = {c.lower() for c in result.columns}
    assert any(name in lower_cols for name in {"applicator_type", "applicator type"})


def test_render_attribute_classification_sorts_rank_with_nulls_last(monkeypatch):
    import importlib

    mod = importlib.import_module("modules.add_attributes.add_attributes")

    mapping = {"product_column": "Product"}
    df = pl.DataFrame({"Product": ["A", "B"]})

    session_state["attr_top_products"] = ["A", "B"]
    session_state["attr_top_data"] = pl.DataFrame({"Product": ["A", "B"]})
    session_state["attr_ranking"] = pl.DataFrame({"Product": ["A"], "rank": [1]})
    session_state["attr_groups"] = []
    session_state["attr_obj_missing"] = []
    session_state["attr_service_tier"] = "flex"
    session_state["attr_llm_mode"] = "flex"

    def fake_classify(*_a, **_k):
        return pl.DataFrame({"Product": ["B", "A"]})

    class DummyProgress:
        def progress(self, *_a, **_k):
            return None

    class DummySpinner:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

    captured: dict[str, pl.DataFrame] = {}

    def fake_convert(df: pl.DataFrame) -> bytes:
        captured["df"] = df
        return b""

    monkeypatch.setattr(
        mod, "_prepare_objective_attribute_map", lambda *_a, **_k: {"x": []}
    )
    monkeypatch.setattr(mod, "_classify_attributes_batch", fake_classify)
    monkeypatch.setattr(mod.ui, "progress", lambda *_a, **_k: DummyProgress())
    monkeypatch.setattr(mod.ui, "spinner", lambda *_a, **_k: DummySpinner())
    monkeypatch.setattr(mod.ui, "button", lambda *_a, **_k: True)
    monkeypatch.setattr(mod.ui, "data_editor", lambda d, **_k: d)
    monkeypatch.setattr(mod, "convert_df_excel", fake_convert)
    monkeypatch.setattr(mod.ui, "download_button", lambda *a, **k: None)
    monkeypatch.setattr(mod.ui, "info", lambda *a, **k: None)

    mod._render_attribute_classification(mapping, df)

    table = session_state.get("attr_classification")
    assert table.select("Product").to_series().to_list() == ["A", "B"]
    assert captured["df"].select("Product").to_series().to_list() == ["A", "B"]
