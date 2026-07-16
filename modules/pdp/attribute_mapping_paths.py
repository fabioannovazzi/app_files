from __future__ import annotations

"""Filesystem paths owned by the PDP attribute mapping pipeline."""

from pathlib import Path

__all__ = [
    "APP_ROOT",
    "ATTRIBUTE_MAPPING_DIR",
    "get_attribute_mapping_dir",
]

APP_ROOT = Path(__file__).resolve().parents[2]
ATTRIBUTE_MAPPING_DIR = APP_ROOT / "data" / "pdp" / "attribute_mapping"


def get_attribute_mapping_dir() -> Path:
    """Return the shared directory for PDP attribute mapping artifacts."""

    return ATTRIBUTE_MAPPING_DIR
