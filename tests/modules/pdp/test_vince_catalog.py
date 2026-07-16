from __future__ import annotations

from modules.pdp.vince_catalog import (
    vince_color_families,
    vince_parent_id_from_url,
    vince_semantic_attribute_hints,
    vince_style_id_from_parent_id,
)


def test_vince_parent_and_style_ids_from_color_pdp_url() -> None:
    url = (
        "https://www.vince.com/product/oasis-contrast-edge-suede-sneaker-"
        "J8129L2INDIGOFLAX.html?utm=1"
    )

    assert vince_parent_id_from_url(url) == "J8129L2INDIGOFLAX"
    assert vince_style_id_from_parent_id("J8129L2INDIGOFLAX") == "J8129L2"


def test_vince_color_and_semantic_hints() -> None:
    hints = vince_semantic_attribute_hints(
        title="Oasis Contrast-Edge Suede Sneaker",
        description="Soft suede sneaker with side-stripe accents.",
        material="100% Suede.",
        detail_lines=(
            "Lace-up closure.",
            "Rounded toe.",
            "Logo-stamped tongue.",
        ),
    )

    assert vince_color_families("INDIGO/FLAX") == (
        "Multicolor",
        "Blue",
        "Beige",
    )
    assert hints == {
        "closure": ["lace_up"],
        "design_detail": ["logo_detail", "colorblock"],
        "material": ["suede"],
        "toe_shape": ["round_toe"],
    }
