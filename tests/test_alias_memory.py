from __future__ import annotations

from pathlib import Path

from src.check_statements.alias_memory import (
    apply_alias_to_norm,
    load_alias_rules,
    save_alias_rules,
)


def test_alias_memory_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "rules.json"
    mapping = {"shortname": "canonicalname", "aliasco": "examplecompany"}
    save_alias_rules(mapping, path=p)
    loaded = load_alias_rules(path=p)
    assert loaded == mapping
    # Apply returns canonical when present, otherwise identity
    assert apply_alias_to_norm("shortname", loaded) == "canonicalname"
    assert apply_alias_to_norm("unknown", loaded) == "unknown"
