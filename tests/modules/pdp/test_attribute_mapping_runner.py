from __future__ import annotations

import polars as pl


def test_attribute_mapping_runner_accepts_retailer_scope(
    monkeypatch,
) -> None:
    import modules.pdp.attribute_mapping_runner as mapping_runner

    calls: list[dict[str, object]] = []

    def fake_run_attribute_mapping(**kwargs: object) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(
        mapping_runner,
        "_run_attribute_mapping",
        fake_run_attribute_mapping,
    )

    mapping_runner.run_attribute_mapping(
        mapping_steps="vision",
        retailers=["kiko"],
        categories=["mascara"],
    )

    assert calls == [
        {
            "mapping_steps": "vision",
            "retailers": ["kiko"],
            "categories": ["mascara"],
        }
    ]


def test_attribute_mapping_runner_delegates_vlm_without_cache_refresh(
    monkeypatch,
) -> None:
    import modules.pdp.attribute_mapping_runner as mapping_runner

    vlm_calls: list[dict[str, object]] = []

    def fake_run_vlm(**kwargs: object) -> None:
        vlm_calls.append(kwargs)

    monkeypatch.setattr(mapping_runner, "_run_attribute_mapping_vlm", fake_run_vlm)

    mapping_runner.run_attribute_mapping_vlm(
        retailers=["kiko"],
        categories=["mascara"],
    )

    assert vlm_calls == [{"retailers": ["kiko"], "categories": ["mascara"]}]


def test_attribute_mapping_inputs_load_from_database(monkeypatch) -> None:
    import modules.pdp.attribute_mapping_core as mapping_core

    calls: list[dict[str, object]] = []

    def fake_load_database_inputs(*args: object, **kwargs: object) -> tuple[
        pl.DataFrame,
        pl.DataFrame,
    ]:
        calls.append({"args": args, "kwargs": kwargs})
        parents = pl.DataFrame(
            [
                {
                    "retailer": "Chewy",
                    "parent_product_id": "P1",
                    "brand": "Cat Brand",
                    "product_name": "Wet Cat Food",
                    "pdp_url": "https://example.test/p1",
                }
            ]
        )
        variants = pl.DataFrame(
            [
                {
                    "retailer": "Chewy",
                    "variant_id": "V1",
                    "parent_product_id": "P1",
                    "category_label": "Wet Cat Food",
                    "brand": "Cat Brand",
                    "product_name": "Wet Cat Food",
                }
            ]
        )
        return parents, variants

    monkeypatch.setattr(
        mapping_core,
        "load_pdp_attribute_mapping_inputs",
        fake_load_database_inputs,
    )

    parents_df, variants_df = mapping_core._load_attribute_mapping_inputs(
        active_mapping_steps=("vision",),
        retailer_scope=("chewy",),
        category_scope=("wet_cat_food",),
    )

    assert calls == [
        {
            "args": (mapping_core.DEFAULT_PDP_STORE_PATH,),
            "kwargs": {
                "retailers": ("chewy",),
                "categories": ("wet_cat_food",),
            },
        }
    ]
    assert parents_df.get_column("retailer").item() == "chewy"
    assert variants_df.get_column("retailer").item() == "chewy"


def test_attribute_mapping_default_steps_do_not_run_web_search() -> None:
    import modules.pdp.attribute_mapping_core as mapping_core

    assert mapping_core._normalize_attribute_mapping_steps(None) == ("vision",)
    assert mapping_core._normalize_attribute_mapping_steps("all") == ("vision", "web")
    assert mapping_core._normalize_attribute_mapping_steps("web") == ("web",)


def test_retailer_scope_merge_preserves_unscoped_retailers() -> None:
    import modules.pdp.attribute_mapping_scope as mapping_scope

    full_df = pl.DataFrame(
        [
            {"retailer": "kiko", "parent_product_id": "k1", "form": None},
            {"retailer": "ulta", "parent_product_id": "u1", "form": "stick"},
        ]
    )
    scoped_df = pl.DataFrame(
        [{"retailer": "kiko", "parent_product_id": "k1", "form": "wand"}]
    )

    merged = mapping_scope.replace_retailer_scope_rows(
        full_df,
        scoped_df,
        ("kiko",),
    ).sort("retailer")

    assert merged.to_dicts() == [
        {"retailer": "kiko", "parent_product_id": "k1", "form": "wand"},
        {"retailer": "ulta", "parent_product_id": "u1", "form": "stick"},
    ]
