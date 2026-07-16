from __future__ import annotations

from pathlib import Path

import polars as pl

from modules.pdp import attribute_review_logic as logic


def test_refresh_review_cache_reloads_when_stage_signature_changes(
    monkeypatch, tmp_path
):
    dummy_tables = (
        pl.DataFrame(),
        pl.DataFrame(),
        pl.DataFrame(),
        set(),
        pl.DataFrame(),
        {},
        {},
    )

    load_calls = {"count": 0}

    def fake_load(pdp_store_path: Path):
        load_calls["count"] += 1
        return dummy_tables

    monkeypatch.setattr(logic, "load_persisted_pdp_attributes", fake_load)
    monkeypatch.setattr(logic, "get_attribute_cache_mtime", lambda _path: 123.0)

    stage_signatures = [
        (("det_ts", 1), ("llm_ts", 2)),
        (("det_ts", 1), ("llm_ts_new", 3)),
    ]
    signature_index = {"value": 0}

    def fake_stage_signature(_path):
        return stage_signatures[signature_index["value"]]

    monkeypatch.setattr(logic, "_stage_tables_signature", fake_stage_signature)

    pdp_store_path = tmp_path / "pdp_store"

    cache = logic.refresh_review_cache(pdp_store_path, None)
    assert load_calls["count"] == 1
    assert cache["stage_signature"] == stage_signatures[0]

    cache = logic.refresh_review_cache(pdp_store_path, cache)
    assert load_calls["count"] == 1

    signature_index["value"] = 1
    cache = logic.refresh_review_cache(pdp_store_path, cache)
    assert load_calls["count"] == 2
    assert cache["stage_signature"] == stage_signatures[1]


def test_prepare_attribute_filters_surfaces_placeholder_choices() -> None:
    records = pl.DataFrame(
        {"finish": ["matte", "not in taxonomy (shade)", None, "n/a"]}
    )
    tables = logic.ReviewTables(
        parents=pl.DataFrame(),
        variants=pl.DataFrame(),
        combined=records,
        parents_all=records,
    )
    category_lookup = {
        "lipstick": {
            "id": "lipstick",
            "label": "Lipstick",
            "attributes": [{"id": "finish", "label": "Finish"}],
        }
    }

    setup = logic.prepare_attribute_filters(tables, category_lookup, ["lipstick"])
    finish_attr = next(
        attr for attr in setup.valid_attributes if attr["id"] == "finish"
    )

    assert "matte" in finish_attr["values"]
    assert "N/A" in finish_attr["values"]
    assert "Not in taxonomy" in finish_attr["values"]


def test_apply_attribute_filters_handles_na_and_not_in_taxonomy_separately() -> None:
    frame = pl.DataFrame(
        {
            "finish": [
                "matte",
                "n/a",
                "not in taxonomy (shade)",
                "not in taxonomy (n/a (not stated))",
                None,
                "unknown",
            ],
        }
    )
    attr_lookup = {"finish": "finish"}

    filtered_na = logic.apply_attribute_filters(frame, {"finish": ["N/A"]}, attr_lookup)
    na_values = filtered_na.get_column("finish").to_list()
    assert set(na_values) == {
        "n/a",
        "not in taxonomy (n/a (not stated))",
        None,
        "unknown",
    }

    filtered_notax = logic.apply_attribute_filters(
        frame, {"finish": ["Not in taxonomy"]}, attr_lookup
    )
    assert filtered_notax.height == 1
    assert filtered_notax.get_column("finish").to_list()[0] == "not in taxonomy (shade)"


def test_compute_attribute_coverage_counts_not_in_taxonomy_with_annotation() -> None:
    frame = pl.DataFrame(
        {
            "finish": [
                "matte",
                "not in taxonomy (shade)",
                "not in taxonomy (n/a (not stated))",
                "not in taxonomy",
                None,
                "n/a",
            ]
        }
    )
    setup = logic.AttributeFilterSetup(
        placeholder_values=logic.PlaceholderValues,
        valid_attributes=[{"id": "finish", "label": "Finish", "column": "finish"}],
        attr_column_lookup={"finish": "finish"},
        attribute_filters=[("finish", "Finish", "finish")],
        allowed_attr_ids={"finish"},
        filter_source=frame,
    )

    report = logic.compute_attribute_coverage_report(frame, setup, {})
    metrics = report["attributes"][0]
    assert metrics["not_in_taxonomy"] == 1
    assert metrics["missing"] == 4
