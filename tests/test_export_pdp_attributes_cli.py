from __future__ import annotations

import types
from pathlib import Path

import polars as pl
import pytest

import scripts.aggregate_product_families as aggregate_product_families
import scripts.export_pdp_attributes as export_cli
from scripts.export_pdp_attributes import (
    _run_amazon_family_aggregation,
    _run_vlm_attribute_mapping,
    _should_auto_aggregate_amazon,
)


def test_should_auto_aggregate_amazon_for_all_retailers_scope() -> None:
    assert _should_auto_aggregate_amazon(None) is True


def test_should_auto_aggregate_amazon_for_amazon_only_scope() -> None:
    assert _should_auto_aggregate_amazon(("amazon",)) is True


def test_should_not_auto_aggregate_amazon_for_mixed_scope() -> None:
    assert _should_auto_aggregate_amazon(("amazon", "sephora")) is False


def test_should_not_auto_aggregate_amazon_for_non_amazon_scope() -> None:
    assert _should_auto_aggregate_amazon(("sephora",)) is False


def test_run_amazon_family_aggregation_passes_expected_args(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    def _fake_main(argv: list[str] | None = None) -> int:
        captured["argv"] = argv
        return 0

    monkeypatch.setattr(aggregate_product_families, "main", _fake_main)

    _run_amazon_family_aggregation(
        pdp_store_path=tmp_path / "pdp_store",
        categories=("blush", "bronzer"),
    )

    assert captured["argv"] == [
        "--retailer",
        "amazon",
        "--pdp-store-path",
        str(tmp_path / "pdp_store"),
        "--category",
        "blush",
        "--category",
        "bronzer",
    ]


def test_run_amazon_family_aggregation_raises_on_non_zero_exit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def _failing_main(argv: list[str] | None = None) -> int:
        return 2

    monkeypatch.setattr(aggregate_product_families, "main", _failing_main)

    with pytest.raises(RuntimeError):
        _run_amazon_family_aggregation(
            pdp_store_path=tmp_path / "pdp_store",
            categories=("blush",),
        )


def test_run_vlm_attribute_mapping_passes_expected_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _fake_run_attribute_mapping_vlm(*, retailers=None, categories=None) -> None:
        captured["retailers"] = retailers
        captured["categories"] = categories

    monkeypatch.setattr(
        "modules.pdp.attribute_mapping_runner.run_attribute_mapping_vlm",
        _fake_run_attribute_mapping_vlm,
    )

    _run_vlm_attribute_mapping(
        retailers=("chewy",),
        categories=("wet_cat_food",),
    )

    assert captured == {
        "retailers": ("chewy",),
        "categories": ("wet_cat_food",),
    }


def test_main_run_vlm_refreshes_export_without_rerunning_llm(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    notifications: list[tuple[str, dict[str, object]]] = []
    export_calls: list[dict[str, object]] = []
    vlm_calls: list[dict[str, object]] = []

    args = types.SimpleNamespace(
        retailer=["chewy"],
        category=["wet_cat_food"],
        notify_email=None,
        deterministic_only=False,
        run_vlm=True,
        parent_id=None,
        dump_llm_json=None,
        clear_retailer=False,
        skip_amazon_family_aggregation=True,
        no_notify=False,
        no_llm_batch=False,
    )

    frame = pl.DataFrame(
        {
            "retailer": ["chewy"],
            "parent_product_id": ["123"],
            "variant_id": ["123"],
        }
    )

    def _fake_parse_args():
        return args

    def _fake_export_attribute_frames(**kwargs):
        export_calls.append(kwargs)
        return frame, frame, frame, set(), {}

    def _fake_run_vlm_attribute_mapping(*, retailers=None, categories=None):
        vlm_calls.append({"retailers": retailers, "categories": categories})

    def _fake_send_run_notification(*, run_name, status, **kwargs):
        notifications.append((status, kwargs.get("details", {})))

    monkeypatch.setattr(export_cli, "_parse_args", _fake_parse_args)
    monkeypatch.setattr(export_cli, "_configure_logging", lambda: None)
    monkeypatch.setattr(export_cli, "load_env_from_secrets_file", lambda: None)
    monkeypatch.setattr(
        export_cli,
        "enforce_default_pdp_store_path",
        lambda path: tmp_path / "pdp_store",
    )
    monkeypatch.setattr(export_cli, "is_postgres_enabled", lambda: True)
    monkeypatch.setattr(
        export_cli, "resolve_notification_recipients", lambda emails: []
    )
    monkeypatch.setattr(
        export_cli, "send_run_notification", _fake_send_run_notification
    )
    monkeypatch.setattr(
        export_cli, "_export_attribute_frames", _fake_export_attribute_frames
    )
    monkeypatch.setattr(
        export_cli, "_run_vlm_attribute_mapping", _fake_run_vlm_attribute_mapping
    )

    exit_code = export_cli.main()

    assert exit_code == 0
    assert len(export_calls) == 2
    assert export_calls[0]["deterministic_only"] is False
    assert export_calls[0]["clear_retailer"] is False
    assert export_calls[1]["deterministic_only"] is True
    assert export_calls[1]["clear_retailer"] is False
    assert vlm_calls == [{"retailers": ("chewy",), "categories": ("wet_cat_food",)}]
    assert notifications[-1][0] == "success"
    assert notifications[-1][1]["run_vlm"] is True
