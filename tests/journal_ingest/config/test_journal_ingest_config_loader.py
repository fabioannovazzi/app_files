import json
from pathlib import Path

import pytest
import yaml

from src.journal_ingest.config.loader import get_recipe, load_layout
from src.journal_ingest.config.model import LayoutConfig


@pytest.mark.parametrize("suffix, serializer", [
    (".yaml", lambda d: yaml.safe_dump(d)),
    (".json", lambda d: json.dumps(d)),
])
def test_load_layout_parses_files_and_filters_unknown_keys(tmp_path: Path, suffix, serializer):
    # Arrange
    data = {
        "drop_rules": {"drop_repeated_headers": True},
        "entry_header_regex": r"^header$",
        "detail_regex": r"^detail$",
        "number_format": {"infer": True},
        "date_formats": ["yyyy-MM-dd"],
        "unknown_field": 123,
    }
    p = tmp_path / f"layout{suffix}"
    p.write_text(serializer(data))

    # Act
    cfg = load_layout(p)

    # Assert
    assert isinstance(cfg, LayoutConfig)
    assert cfg.drop_rules["drop_repeated_headers"] is True
    assert cfg.entry_header_regex == r"^header$"
    assert cfg.detail_regex == r"^detail$"
    assert cfg.number_format["infer"] is True
    assert cfg.date_formats == ["yyyy-MM-dd"]
    # Unknown keys are ignored
    assert not hasattr(cfg, "unknown_field")
    # Optional fields default when omitted
    assert cfg.column_bounds is None and cfg.table_area is None


def test_load_layout_missing_required_field_raises_type_error(tmp_path: Path):
    # Arrange: omit required 'date_formats'
    data = {
        "drop_rules": {"drop_repeated_headers": True},
        "entry_header_regex": r"^h$",
        "detail_regex": r"^d$",
        "number_format": {"infer": True},
    }
    p = tmp_path / "incomplete.yaml"
    p.write_text(yaml.safe_dump(data))

    # Act / Assert
    with pytest.raises(TypeError):
        load_layout(p)


def test_get_recipe_unknown_name_returns_default_and_uses_cache():
    # Arrange: load default once
    default_cfg = get_recipe("journal_generic_v1")

    # Act: request an unknown recipe name
    fallback_cfg = get_recipe("__totally_unknown_recipe__")

    # Assert: falls back to default and returns same cached instance
    assert fallback_cfg is default_cfg
    assert isinstance(fallback_cfg, LayoutConfig)
    # sanity-check a couple of expected properties from the default recipe
    assert {"date_token", "account_code", "amount"}.issubset(set(default_cfg.shapes.keys()))
    assert "yyyy-MM-dd" in default_cfg.date_formats
