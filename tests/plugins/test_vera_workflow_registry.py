from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "vera_registry_test_builder", ROOT / "scripts/build_vera_workflow_registry.py"
)
assert SPEC and SPEC.loader
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)


def test_registry_matches_canonical_components_and_entrypoints() -> None:
    retained = json.loads((ROOT / BUILDER.REGISTRY).read_text(encoding="utf-8"))

    generated = BUILDER.build_registry(ROOT)

    assert retained == generated
    assert "model_data_report.json" in generated["managed_run_required_artifacts"]
    assert "model_data_report.md" in generated["managed_run_required_artifacts"]


def test_registry_rejects_missing_component_skill(tmp_path: Path) -> None:
    vera = tmp_path / "plugins/vera"
    vera.mkdir(parents=True)
    (vera / "components.json").write_text(json.dumps({"plugins": ["example"]}))
    (tmp_path / "plugins/example").mkdir()

    with pytest.raises(ValueError, match="has no skill"):
        BUILDER.build_registry(tmp_path)
