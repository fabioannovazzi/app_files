from __future__ import annotations

"""Public entry points for shared PDP attribute mapping."""

from typing import Sequence

from modules.pdp.attribute_mapping_core import (
    run_attribute_mapping as _run_attribute_mapping,
)
from modules.pdp.attribute_mapping_core import (
    run_attribute_mapping_vlm as _run_attribute_mapping_vlm,
)
from modules.pdp.attribute_mapping_core import (
    run_attribute_mapping_web as _run_attribute_mapping_web,
)

__all__ = [
    "run_attribute_mapping",
    "run_attribute_mapping_vlm",
    "run_attribute_mapping_web",
]


def run_attribute_mapping(
    mapping_steps: Sequence[str] | str | None = None,
    retailers: Sequence[str] | str | None = None,
    categories: Sequence[str] | str | None = None,
) -> None:
    """Run shared PDP attribute enrichment without loading sales CSVs."""

    _run_attribute_mapping(
        mapping_steps=mapping_steps,
        retailers=retailers,
        categories=categories,
    )


def run_attribute_mapping_vlm(
    retailers: Sequence[str] | str | None = None,
    categories: Sequence[str] | str | None = None,
) -> None:
    """Run only the image/VLM PDP attribute enrichment step."""

    _run_attribute_mapping_vlm(retailers=retailers, categories=categories)


def run_attribute_mapping_web(
    retailers: Sequence[str] | str | None = None,
    categories: Sequence[str] | str | None = None,
) -> None:
    """Run only the web-search PDP attribute enrichment step."""

    _run_attribute_mapping_web(retailers=retailers, categories=categories)
