from __future__ import annotations

"""Resolve sales dataset names and folder paths."""

import os
import re
from pathlib import Path

__all__ = [
    "APP_ROOT",
    "BASE_SALES_DIR",
    "DATASETS_DIR",
    "JOINED_DATASETS_DIR",
    "DEFAULT_SALES_DATASET",
    "SALES_DATASET_ENV_VAR",
    "get_sales_dataset_csv_dir",
    "get_sales_dataset_dir",
    "get_sales_dataset_join_dir",
    "list_available_sales_dataset_names",
    "get_sales_dataset_name",
    "normalize_sales_dataset_name",
]

APP_ROOT = Path(__file__).resolve().parents[2]
BASE_SALES_DIR = APP_ROOT / "data" / "pdp" / "sales_data"
DATASETS_DIR = BASE_SALES_DIR / "datasets"
JOINED_DATASETS_DIR = BASE_SALES_DIR / "joined_datasets"
DEFAULT_SALES_DATASET = "default"
SALES_DATASET_ENV_VAR = "PDP_SALES_DATASET"


def normalize_sales_dataset_name(dataset: str | None) -> str:
    """Return a safe sales dataset identifier."""

    raw = str(dataset or "").strip().lower()
    if not raw or raw in {"default", "main", "base", "legacy"}:
        return DEFAULT_SALES_DATASET
    sanitized = re.sub(r"[^a-z0-9._-]+", "_", raw).strip("._-")
    if not sanitized:
        return DEFAULT_SALES_DATASET
    return sanitized


def get_sales_dataset_name(dataset: str | None = None) -> str:
    """Resolve dataset name from explicit value or environment."""

    source = dataset if dataset is not None else os.environ.get(SALES_DATASET_ENV_VAR)
    return normalize_sales_dataset_name(source)


def get_sales_dataset_dir(dataset: str | None = None) -> Path:
    """Return the filesystem directory for a sales dataset's inputs/metadata."""

    name = get_sales_dataset_name(dataset)
    if name == DEFAULT_SALES_DATASET:
        return BASE_SALES_DIR
    return DATASETS_DIR / name


def get_sales_dataset_csv_dir(dataset: str | None = None) -> Path:
    """Return the directory containing source sales CSV files."""

    return get_sales_dataset_dir(dataset) / "csv_files"


def get_sales_dataset_join_dir(dataset: str | None = None) -> Path:
    """Return the directory containing joined/full_sales outputs for a dataset."""

    return JOINED_DATASETS_DIR / get_sales_dataset_name(dataset)


def list_available_sales_dataset_names() -> list[str]:
    """Return discovered dataset names from the datasets/joined folders plus default."""

    names: set[str] = {DEFAULT_SALES_DATASET, get_sales_dataset_name()}
    if DATASETS_DIR.is_dir():
        for child in DATASETS_DIR.iterdir():
            if child.is_dir():
                names.add(get_sales_dataset_name(child.name))
    if JOINED_DATASETS_DIR.is_dir():
        for child in JOINED_DATASETS_DIR.iterdir():
            if child.is_dir():
                names.add(get_sales_dataset_name(child.name))
    return sorted(names)
