from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
CLARA_ROOT = ROOT / "plugins" / "clara"
ATTRIBUTE_ROOT = ROOT / "plugins" / "attribute-reporting"


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_clara_declares_attribute_reporting_as_embedded_component() -> None:
    components = json.loads(
        (CLARA_ROOT / "components.json").read_text(encoding="utf-8")
    )

    assert components["schema_version"] == 1
    assert "attribute-reporting" in components["plugins"]


def test_clara_attribute_reporting_wrapper_delegates_to_single_source() -> None:
    skill_root = CLARA_ROOT / "skills" / "attribute-reporting"
    wrapper = (skill_root / "SKILL.md").read_text(encoding="utf-8")
    metadata = (skill_root / "agents" / "openai.yaml").read_text(encoding="utf-8")

    assert "name: attribute-reporting" in wrapper
    assert "../../modules/attribute-reporting" in wrapper
    assert "../../../attribute-reporting" in wrapper
    assert "skills/attribute-reporting/SKILL.md" in wrapper
    assert "check_dependencies.py --module attribute-reporting" in wrapper
    assert "route to Clara's distinct `brand-fit` skill" in wrapper
    assert (
        'display_name: "Compare assortment, new-product, and best-seller attributes"'
        in metadata
    )
    assert "Use $attribute-reporting" in metadata
    assert (ATTRIBUTE_ROOT / "skills" / "attribute-reporting" / "SKILL.md").is_file()


def test_clara_routes_retail_attribute_requests_to_component_skill() -> None:
    manifest = json.loads(
        (CLARA_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    fixtures = json.loads(
        (CLARA_ROOT / "evals" / "trigger_fixtures.json").read_text(encoding="utf-8")
    )
    router = (CLARA_ROOT / "skills" / "clara" / "SKILL.md").read_text(encoding="utf-8")
    catalog = (
        CLARA_ROOT / "skills" / "clara" / "references" / "workflow-catalog.md"
    ).read_text(encoding="utf-8")
    attribute_cases = {
        item["id"]: item
        for item in fixtures["should_trigger"]
        if item.get("expected_skill") == "clara:attribute-reporting"
    }

    assert manifest["version"] == "0.1.160"
    assert "retail-attribute-reporting" in manifest["keywords"]
    assert "Retailer Signals" in manifest["interface"]["longDescription"]
    assert "references/workflow-catalog.md" in router
    assert "- `attribute-reporting`:" in catalog
    assert set(attribute_cases) == {
        "retail-attribute-report-from-current-data",
        "retail-attribute-report-fresh-scrape",
    }
    for case in attribute_cases.values():
        assert set(case["must_not_route_to"]) == {
            "clara:interview",
            "clara:transcribe",
            "clara:deck-correction",
            "clara:brand-fit",
        }


def test_clara_dependency_checker_delegates_to_attribute_component(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.syspath_prepend(str(CLARA_ROOT / "scripts"))
    checker = _load_module(
        "clara_component_dependency_checker",
        CLARA_ROOT / "scripts" / "check_dependencies.py",
    )
    component_root = tmp_path / "attribute-reporting"
    component_checker = component_root / "scripts" / "check_dependencies.py"
    component_checker.parent.mkdir(parents=True)
    component_checker.write_text("# delegated checker\n", encoding="utf-8")
    calls: list[tuple[list[str], Path, bool]] = []

    def fake_run(
        command: list[str],
        *,
        cwd: Path,
        env: dict[str, str],
        check: bool,
    ) -> SimpleNamespace:
        calls.append((command, cwd, check))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(checker, "component_root", lambda _name: component_root)
    runtime_target = tmp_path / "runtime"
    runtime_python = runtime_target / "bin" / "python"
    monkeypatch.setattr(
        checker,
        "ensure_runtime",
        lambda _root, _module: (True, runtime_target, "ready"),
    )
    monkeypatch.setattr(checker, "runtime_python", lambda _target: runtime_python)
    monkeypatch.setattr(
        checker,
        "runtime_environment",
        lambda _target: {"MPARANZA_MANAGED_RUNTIME_VERIFY": "1"},
    )
    monkeypatch.setattr(checker.subprocess, "run", fake_run)

    result = checker.main(["--module", "attribute-reporting"])

    assert result == 0
    assert calls == [
        ([str(runtime_python), str(component_checker)], component_root, False)
    ]


def test_clara_package_entries_embed_attribute_reporting_and_vendor_runtime() -> None:
    builder = _load_module(
        "clara_component_package_builder",
        ROOT / "scripts" / "build_codex_plugin_zip.py",
    )
    package = {item.plugin: item for item in builder.load_packages()}["clara"]

    entries = builder.expected_zip_entries(package)

    component_root = f"{package.package_root}/plugins/clara/modules/attribute-reporting"
    assert f"{component_root}/skills/attribute-reporting/SKILL.md" in entries
    assert f"{component_root}/scripts/prepare_run.py" in entries
    assert f"{component_root}/scripts/check_report.py" in entries
    assert (
        f"{component_root}/vendor/modules/pdp/attribute_table_templates.py" in entries
    )
    assert f"{component_root}/vendor/modules/utilities/utils.py" in entries


def test_selecting_attribute_reporting_rebuilds_clara_package_only() -> None:
    builder = _load_module(
        "clara_component_package_selector",
        ROOT / "scripts" / "build_codex_plugin_zip.py",
    )

    selected = builder.select_packages(
        builder.load_packages(), builder.load_bundles(), ["attribute-reporting"]
    )

    assert {target.target_name for target in selected} == {"clara"}


def test_clara_public_page_describes_retail_pipeline_and_public_example() -> None:
    page = (ROOT / "static" / "shared" / "clara" / "index.html").read_text(
        encoding="utf-8"
    )
    function_copy = (
        ROOT / "static" / "shared" / "product-function-pages.js"
    ).read_text(encoding="utf-8")

    assert 'href="../clara-retailer-signals/index.html?lang=en"' in page
    assert 'href="../clara-brand-fit/index.html?lang=en"' in page
    assert page.count('"functions.retailerSignals"') == 6
    assert page.count('"functions.brandFit"') == 6
    assert '"clara-retailer-signals"' in function_copy
    assert "The comparison describes captured data" in function_copy
    assert '"clara-brand-fit"' in function_copy
    assert (
        "The comparison uses stored data and is not a live shelf check."
        in function_copy
    )

    retailer_example = (
        ROOT / "static" / "shared" / "attribute-reporting" / "cashmere" / "index.html"
    ).read_text(encoding="utf-8")
    assert "Clara · Retailer Signals · public example" in retailer_example
    assert "From retailer signal to brand review" in retailer_example
    assert (
        'href="/static/shared/attribute-reporting/brand-fit/guest-in-residence/index.html"'
        in retailer_example
    )
