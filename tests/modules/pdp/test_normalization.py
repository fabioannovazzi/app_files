from __future__ import annotations

from modules.pdp.normalization import normalize_text
from modules.pdp.profile import FieldNormalizationSpec


def test_normalize_shade_collapses_spaces_and_moves_numbers() -> None:
    spec = FieldNormalizationSpec(trim=True, collapse_spaces=True, normalize_number_position=True)
    result = normalize_text("  132  Dragon   Girl ", spec)
    assert result == "Dragon Girl 132"


def test_normalize_title_strips_trailing_shade_tokens() -> None:
    spec = FieldNormalizationSpec(trim=True, strip_trailing_shade_tokens=True)
    result = normalize_text("Matte Lipstick | 01 Red", spec)
    assert result == "Matte Lipstick"


def test_normalize_brand_trims_and_collapses_spaces() -> None:
    spec = FieldNormalizationSpec(trim=True, collapse_spaces=True)
    result = normalize_text("  Charlotte   Tilbury  ", spec)
    assert result == "Charlotte Tilbury"
