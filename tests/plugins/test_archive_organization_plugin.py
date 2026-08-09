from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugins" / "archive-organization"


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


scenario = _load_module(
    "archive_organization_plugin_scenario",
    PLUGIN_ROOT / "tests" / "test_archive_organization.py",
)
core = scenario.organizer
contract = _load_module(
    "archive_organization_plugin_contract",
    ROOT / "scripts" / "validate_plugin_review_contract.py",
)


def test_generated_archive_organization_review_contract(tmp_path: Path) -> None:
    context_path, snapshot, _ = scenario._prepared_run(tmp_path)

    result = core.build_review_package(
        context_path,
        scenario._proposals(tmp_path, snapshot),
    )

    output_dir = Path(result["output_dir"])
    for artifact_name in (
        "run_intake.json",
        "review_payload.json",
        "ui_decisions.json",
        "final_artifacts.json",
    ):
        assert (output_dir / artifact_name).is_file()
    report = contract.validate_contract(output_dir)
    assert report.ok, report.errors
