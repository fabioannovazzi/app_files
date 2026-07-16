from __future__ import annotations

from modules.pdp.attribute_mapping_paths import (
    APP_ROOT,
    ATTRIBUTE_MAPPING_DIR,
    get_attribute_mapping_dir,
)


def test_attribute_mapping_dir_is_not_under_sales_data() -> None:
    assert get_attribute_mapping_dir() == ATTRIBUTE_MAPPING_DIR
    assert ATTRIBUTE_MAPPING_DIR == APP_ROOT / "data" / "pdp" / "attribute_mapping"
    assert "sales_data" not in str(ATTRIBUTE_MAPPING_DIR)
