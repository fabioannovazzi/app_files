from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = ROOT / "scripts" / "build_codex_plugin_zip.py"
ASSURANCE_CONSUMERS = {
    "audit-reconciliation",
    "bandi-agevolazioni",
    "check-entries",
    "client-file-preparation",
    "concordato-plan-review",
    "deep-research-validator",
    "financial-analysis",
    "journal-bank-reconciliation",
    "journal-sampling",
    "management-control-pack",
    "new-client",
    "passive-invoice-audit",
    "previdenza-inps",
    "prompt-optimizer",
    "registro-imprese-sari",
    "report-builder",
    "sales-plan",
    "variance-analysis",
    "studio-archive",
    "vera",
}
ASSURANCE_FILES = {
    "vera_assurance/__init__.py",
    "vera_assurance/contracts.py",
    "vera_assurance/decisions.py",
    "vera_assurance/envelope.py",
    "vera_assurance/money.py",
    "vera_assurance/review_output_transaction.cjs",
    "vera_assurance/relationships.py",
    "vera_assurance/serialization.py",
}


def _load_builder() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "vera_assurance_package_builder",
        BUILD_SCRIPT,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_every_current_vera_assurance_consumer_vendors_the_complete_core() -> None:
    builder = _load_builder()
    configurations = builder.load_vendor_module_config()

    for consumer in ASSURANCE_CONSUMERS:
        entries = builder.shared_vendor_module_entries(configurations[consumer])
        assert ASSURANCE_FILES <= set(entries), consumer


def test_staged_vera_assurance_tree_imports_without_repository_pythonpath(
    tmp_path: Path,
) -> None:
    builder = _load_builder()
    config = builder.load_vendor_module_config()["journal-sampling"]
    entries = builder.shared_vendor_module_entries(config)
    module_root = tmp_path / "installed-plugin" / "vendor" / "modules"
    for relative, source in entries.items():
        destination = module_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)

    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    environment["PYTHONNOUSERSITE"] = "1"
    code = (
        "import json, pathlib, sys; "
        "root = pathlib.Path(sys.argv[1]).resolve(); "
        "sys.path.insert(0, str(root)); "
        "import vera_assurance; "
        "print(json.dumps({'module': str(pathlib.Path("
        "vera_assurance.__file__).resolve()), "
        "'decimal': vera_assurance.decimal_text("
        "__import__('decimal').Decimal('1.20'))}))"
    )

    result = subprocess.run(
        [sys.executable, "-I", "-c", code, str(module_root)],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert Path(payload["module"]).is_relative_to(module_root)
    assert payload["decimal"] == "1.2"


def test_financial_analysis_vendors_its_dedicated_contract_module() -> None:
    builder = _load_builder()
    config = builder.load_vendor_module_config()["financial-analysis"]

    entries = builder.shared_vendor_module_entries(config)

    assert {
        "vera_assurance/__init__.py",
        "vera_assurance/money.py",
        "vera_assurance/serialization.py",
        "vera_financial_analysis/__init__.py",
        "vera_financial_analysis/contracts.py",
        "vera_financial_analysis/fdd.py",
        "vera_financial_analysis/registry.py",
    } <= set(entries)
