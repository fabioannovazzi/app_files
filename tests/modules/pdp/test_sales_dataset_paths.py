from __future__ import annotations

from modules.pdp.sales_dataset_paths import (
    BASE_SALES_DIR,
    DATASETS_DIR,
    JOINED_DATASETS_DIR,
    SALES_DATASET_ENV_VAR,
    get_sales_dataset_csv_dir,
    get_sales_dataset_dir,
    get_sales_dataset_join_dir,
    get_sales_dataset_name,
    list_available_sales_dataset_names,
    normalize_sales_dataset_name,
)


def test_normalize_sales_dataset_name_defaults_to_default() -> None:
    assert normalize_sales_dataset_name(None) == "default"
    assert normalize_sales_dataset_name("") == "default"
    assert normalize_sales_dataset_name(" main ") == "default"
    assert normalize_sales_dataset_name("legacy") == "default"


def test_get_sales_dataset_dir_for_default_and_named_dataset() -> None:
    assert get_sales_dataset_dir("default") == BASE_SALES_DIR
    assert get_sales_dataset_dir("kiko") == (BASE_SALES_DIR / "datasets" / "kiko")
    assert get_sales_dataset_csv_dir("default") == (BASE_SALES_DIR / "csv_files")
    assert get_sales_dataset_csv_dir("kiko") == (
        BASE_SALES_DIR / "datasets" / "kiko" / "csv_files"
    )
    assert get_sales_dataset_join_dir("default") == (JOINED_DATASETS_DIR / "default")
    assert get_sales_dataset_join_dir("kiko") == (JOINED_DATASETS_DIR / "kiko")


def test_get_sales_dataset_name_reads_environment(monkeypatch) -> None:
    monkeypatch.setenv(SALES_DATASET_ENV_VAR, " Kiko 2026 ")
    assert get_sales_dataset_name() == "kiko_2026"
    assert get_sales_dataset_dir() == (BASE_SALES_DIR / "datasets" / "kiko_2026")
    assert get_sales_dataset_join_dir() == (JOINED_DATASETS_DIR / "kiko_2026")


def test_list_available_sales_dataset_names_discovers_dataset_directories(
    monkeypatch,
    tmp_path,
) -> None:
    datasets_dir = tmp_path / "datasets"
    joined_dir = tmp_path / "joined"
    (datasets_dir / "kiko").mkdir(parents=True, exist_ok=True)
    (datasets_dir / "US Cosmetics").mkdir(parents=True, exist_ok=True)
    (joined_dir / "kiko").mkdir(parents=True, exist_ok=True)
    (joined_dir / "legacy").mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("modules.pdp.sales_dataset_paths.DATASETS_DIR", datasets_dir)
    monkeypatch.setattr(
        "modules.pdp.sales_dataset_paths.JOINED_DATASETS_DIR", joined_dir
    )

    names = list_available_sales_dataset_names()
    assert names == ["default", "kiko", "us_cosmetics"]
