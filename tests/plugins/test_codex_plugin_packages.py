from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = ROOT / "scripts" / "build_codex_plugin_zip.py"
COMMERCIALISTA_MODULE_NAMES = {
    "audit-reconciliation",
    "check-entries",
    "concordato-plan-review",
    "deep-research-validator",
    "client-file-preparation",
    "new-client",
    "journal-bank-reconciliation",
    "journal-sampling",
    "prompt-optimizer",
    "previdenza-inps",
    "registro-imprese-sari",
    "report-builder",
}
STANDALONE_PLUGIN_NAMES = {"attribute-reporting", "clara"}
PRIVATE_STANDALONE_PLUGIN_NAMES = {"attribute-reporting"}
UNIFIED_PLUGIN_NAMES = {"vera"}
VERA_PUBLIC_PAGE_PATHS = (
    Path("static/shared/check-entries/index.html"),
    Path("static/shared/concordato-plan-review/index.html"),
    Path("static/shared/deep-research-validator/index.html"),
    Path("static/shared/journal-bank-reconciliation/index.html"),
    Path("static/shared/journal-sampling/index.html"),
    Path("static/shared/new-client/geneva.html"),
    Path("static/shared/new-client/index.html"),
    Path("static/shared/new-client/uk.html"),
    Path("static/shared/new-client/zurich.html"),
    Path("static/shared/previdenza-inps/index.html"),
    Path("static/shared/prompt-optimizer/index.html"),
    Path("static/shared/registro-imprese-sari/index.html"),
    Path("static/shared/riconciliazione-partite/index.html"),
    Path("static/shared/report-builder/index.html"),
)
REPORTING_ENGINE_PLUGIN_NAMES = {
    "distribution-analysis",
    "funnel-analysis",
    "mix-contribution-analysis",
    "period-comparison",
    "scatter-bubble-analysis",
    "set-overlap-analysis",
    "statement-analysis",
    "variance-analysis",
}
WORKFLOW_PLUGIN_NAMES = (
    COMMERCIALISTA_MODULE_NAMES
    | REPORTING_ENGINE_PLUGIN_NAMES
    | (STANDALONE_PLUGIN_NAMES - PRIVATE_STANDALONE_PLUGIN_NAMES)
)
STANDARD_ACCOUNTING_PLUGIN_NAMES = UNIFIED_PLUGIN_NAMES
PLUGINS_WITH_LEGACY_USER_EMAIL: set[str] = set()
PLUGIN_PROVIDER_CONFIGS = (
    ROOT / "plugins" / "_shared" / "vendor" / "modules" / "utilities" / "config.py",
    ROOT
    / "plugins"
    / "_shared"
    / "variance"
    / "vendor"
    / "modules"
    / "utilities"
    / "config.py",
)
PLUGIN_MODEL_API_SCRIPT_EXCEPTIONS: set[Path] = set()
FORBIDDEN_PLUGIN_MODEL_API_PATTERNS = (
    "api.openai.com",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "DEEPSEEK",
    "GEMINI_API_KEY",
    "from openai",
    "import openai",
    "modules.llm.batch_runner",
    "modules.llm.model_router",
    "query_llm_return",
    "run_step_json",
    "run_step_text",
    "select_provider(",
)


def _restore_application_import_path() -> None:
    """Undo plugin-script import path pollution before importing the app."""
    root = str(ROOT)
    while root in sys.path:
        sys.path.remove(root)
    sys.path.insert(0, root)

    plugins_root = ROOT / "plugins"
    for module_name, module in list(sys.modules.items()):
        if module_name != "modules" and not module_name.startswith("modules."):
            continue
        module_file = getattr(module, "__file__", None)
        if not module_file:
            del sys.modules[module_name]
            continue
        try:
            module_path = Path(module_file).resolve()
        except OSError:
            continue
        if plugins_root in module_path.parents:
            del sys.modules[module_name]


@pytest.mark.parametrize("config_path", PLUGIN_PROVIDER_CONFIGS)
def test_vendored_plugin_provider_router_fails_closed(config_path: Path) -> None:
    source = config_path.read_text(encoding="utf-8")
    select_provider_source = source[: source.index("def get_naming_params")]

    assert "QueryChoiceDict" not in select_provider_source
    assert "defaultFixQuery" not in source
    assert "checkPatternsQuery" not in source
    assert "descriptionNormaliserQuery" not in source
    assert "ocrFallbackQuery" not in source
    assert "web_search_preview" not in source
    assert "deepseek-reasoner" not in source
    assert "gemini-2.5" not in source
    assert "anthropicKey" not in source
    assert "deepseekKey" not in source

    spec = importlib.util.spec_from_file_location(
        f"plugin_vendor_config_{config_path.parent.parent.parent.name}",
        config_path,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    for query_step in (
        "defaultFixQuery",
        "checkPatternsQuery",
        "descriptionNormaliserQuery",
        "ocrFallbackQuery",
    ):
        with pytest.raises(RuntimeError, match="disabled in local plugin runtimes"):
            module.select_provider(query_step)


def test_plugin_scripts_do_not_call_model_apis_except_voice() -> None:
    violations: list[str] = []

    for path in sorted((ROOT / "plugins").glob("*/scripts/*.py")):
        if path in PLUGIN_MODEL_API_SCRIPT_EXCEPTIONS:
            continue
        source = path.read_text(encoding="utf-8")
        matches = [
            pattern
            for pattern in FORBIDDEN_PLUGIN_MODEL_API_PATTERNS
            if pattern in source
        ]
        if matches:
            rel_path = path.relative_to(ROOT)
            violations.append(f"{rel_path}: {', '.join(matches)}")

    assert violations == []


NON_PLOTTING_REVIEW_TOOL_CONTRACTS = {
    "audit-reconciliation": (
        "validate_audit_reconciliation_review",
        "render_audit_reconciliation_review",
        "save_audit_reconciliation_decisions",
        "apply_audit_reconciliation_decisions",
    ),
    "check-entries": (
        "validate_check_entries_review",
        "render_check_entries_review",
        "save_check_entries_decisions",
        "apply_check_entries_decisions",
    ),
    "client-file-preparation": (
        "validate_client_file_preparation_review",
        "render_client_file_preparation_review",
        "save_client_file_preparation_decisions",
        "apply_client_file_preparation_decisions",
    ),
    "new-client": (
        "validate_new_client_review",
        "render_new_client_review",
        "save_new_client_decisions",
        "apply_new_client_decisions",
    ),
    "concordato-plan-review": (
        "validate_concordato_plan_review",
        "render_concordato_plan_review",
        "save_concordato_plan_decisions",
        "apply_concordato_plan_decisions",
    ),
    "deep-research-validator": (
        "validate_deep_research_review",
        "render_deep_research_review",
        "save_deep_research_decisions",
        "apply_deep_research_decisions",
    ),
    "journal-bank-reconciliation": (
        "validate_journal_bank_review",
        "render_journal_bank_review",
        "save_journal_bank_decisions",
        "apply_journal_bank_decisions",
    ),
    "journal-sampling": (
        "validate_journal_sampling_review",
        "render_journal_sampling_review",
        "save_journal_sampling_decisions",
        "apply_journal_sampling_decisions",
    ),
    "prompt-optimizer": (
        "validate_prompt_optimizer_review",
        "render_prompt_optimizer_review",
        "save_prompt_optimizer_decisions",
        "apply_prompt_optimizer_decisions",
    ),
    "previdenza-inps": (
        "validate_previdenza_inps_review",
        "render_previdenza_inps_review",
        "save_previdenza_inps_decisions",
        "apply_previdenza_inps_decisions",
    ),
    "registro-imprese-sari": (
        "validate_registro_imprese_sari_review",
        "render_registro_imprese_sari_review",
        "save_registro_imprese_sari_decisions",
        "apply_registro_imprese_sari_decisions",
    ),
    "report-builder": (
        "validate_report_builder_review",
        "render_report_builder_review",
        "save_report_builder_decisions",
        "apply_report_builder_decisions",
    ),
}
ACCOUNTING_STATIC_PLUGIN_PAGES = (
    ROOT / "static" / "shared" / "vera" / "index.html",
    ROOT / "static" / "shared" / "riconciliazione-partite" / "index.html",
    ROOT / "static" / "shared" / "new-client" / "index.html",
    ROOT / "static" / "shared" / "journal-sampling" / "index.html",
    ROOT / "static" / "shared" / "check-entries" / "index.html",
    ROOT / "static" / "shared" / "journal-bank-reconciliation" / "index.html",
    ROOT / "static" / "shared" / "report-builder" / "index.html",
    ROOT / "static" / "shared" / "concordato-plan-review" / "index.html",
    ROOT / "static" / "shared" / "previdenza-inps" / "index.html",
    ROOT / "static" / "shared" / "prompt-optimizer" / "index.html",
    ROOT / "static" / "shared" / "registro-imprese-sari" / "index.html",
    ROOT / "static" / "shared" / "deep-research-validator" / "index.html",
)
STANDALONE_STATIC_PLUGIN_PAGES = (ROOT / "static" / "shared" / "clara" / "index.html",)
STATIC_PLUGIN_PAGES = ACCOUNTING_STATIC_PLUGIN_PAGES + STANDALONE_STATIC_PLUGIN_PAGES
PUBLIC_PLUGIN_EXPLAINER_PAGES = (
    ROOT / "static" / "shared" / "clara" / "index.html",
    ROOT / "static" / "shared" / "check-entries" / "index.html",
    ROOT / "static" / "shared" / "concordato-plan-review" / "index.html",
    ROOT / "static" / "shared" / "deep-research-validator" / "index.html",
    ROOT / "static" / "shared" / "journal-bank-reconciliation" / "index.html",
    ROOT / "static" / "shared" / "journal-sampling" / "index.html",
    ROOT / "static" / "shared" / "new-client" / "index.html",
    ROOT / "static" / "shared" / "new-client" / "geneva.html",
    ROOT / "static" / "shared" / "new-client" / "uk.html",
    ROOT / "static" / "shared" / "new-client" / "zurich.html",
    ROOT / "static" / "shared" / "previdenza-inps" / "index.html",
    ROOT / "static" / "shared" / "prompt-optimizer" / "index.html",
    ROOT / "static" / "shared" / "registro-imprese-sari" / "index.html",
    ROOT / "static" / "shared" / "report-builder" / "index.html",
    ROOT / "static" / "shared" / "riconciliazione-partite" / "index.html",
)
ACCOUNTING_BUNDLE_ZIP = ROOT / "plugin_packages" / "vera" / "vera-plugin.zip"
VERA_DOWNLOAD_HREF = "/downloads/vera"
VERA_MARKETPLACE_HREF = (
    "https://chatgpt.com/auth/login?next="
    "%2Fplugins%2Fplugins_6a57ac5ce65c8191ae7bd0a51160eb7d"
)
ACCOUNTING_BUNDLE_LINK = VERA_MARKETPLACE_HREF


def load_builder():
    spec = importlib.util.spec_from_file_location(
        "build_codex_plugin_zip", BUILD_SCRIPT
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_module_from_path(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def extracted_clara_plugin(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Extract the configured Clara package once for installed-runtime tests."""

    builder = load_builder()
    package = {item.plugin: item for item in builder.load_packages()}["clara"]
    extraction_root = tmp_path_factory.mktemp("extracted_clara_package")
    with ZipFile(package.output_zip) as archive:
        archive.extractall(extraction_root)
    return extraction_root / package.package_root / "plugins" / "clara"


def isolated_plugin_env() -> dict[str, str]:
    """Return an environment that cannot borrow repository Python paths."""

    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env["PYTHONNOUSERSITE"] = "1"
    return env


def write_reporting_smoke_dataset(path: Path) -> None:
    """Write a tiny AC/PY sales dataset with known comparison totals."""

    path.write_text(
        "Date,Brand,Sales\n"
        "2025-01-31,Alpha,100\n"
        "2025-01-31,Beta,80\n"
        "2025-02-28,Alpha,110\n"
        "2025-02-28,Beta,85\n"
        "2025-03-31,Alpha,120\n"
        "2025-03-31,Beta,90\n"
        "2025-04-30,Alpha,130\n"
        "2025-04-30,Beta,95\n"
        "2025-05-31,Alpha,140\n"
        "2025-05-31,Beta,100\n"
        "2025-06-30,Alpha,150\n"
        "2025-06-30,Beta,105\n"
        "2026-01-31,Alpha,115\n"
        "2026-01-31,Beta,83\n"
        "2026-02-28,Alpha,125\n"
        "2026-02-28,Beta,90\n"
        "2026-03-31,Alpha,135\n"
        "2026-03-31,Beta,96\n"
        "2026-04-30,Alpha,145\n"
        "2026-04-30,Beta,103\n"
        "2026-05-31,Alpha,160\n"
        "2026-05-31,Beta,110\n"
        "2026-06-30,Alpha,180\n"
        "2026-06-30,Beta,165\n",
        encoding="utf-8",
    )


def test_configured_plugin_zips_match_repo_source() -> None:
    builder = load_builder()

    for package in builder.load_packages():
        expected = builder.expected_zip_entries(package)
        with ZipFile(package.output_zip) as archive:
            actual_names = {
                name for name in archive.namelist() if not name.endswith("/")
            }

            assert actual_names == set(expected)
            for name, content in expected.items():
                assert archive.read(name) == content


def test_chatgpt_upload_entries_put_vera_manifest_at_zip_root() -> None:
    builder = load_builder()
    vera = {bundle.name: bundle for bundle in builder.load_bundles()}["vera"]

    entries = builder.chatgpt_upload_entries(vera)
    manifest = json.loads(entries[".codex-plugin/plugin.json"])
    prompts = manifest["interface"]["defaultPrompt"]

    assert ".codex-plugin/plugin.json" in entries
    assert "modules/previdenza-inps/.codex-plugin/plugin.json" in entries
    assert "modules/registro-imprese-sari/.codex-plugin/plugin.json" in entries
    assert "apps" not in manifest
    assert "mcpServers" not in manifest
    assert manifest["repository"] == "https://github.com/fabioannovazzi/app_files"
    assert manifest["license"] == "AGPL-3.0-only"
    assert entries["LICENSE"] == (ROOT / "LICENSE").read_bytes()
    assert manifest["interface"]["shortDescription"] == ("AI companion for accountants")
    assert len(prompts) == 3
    assert any("OCR locale" in prompt and "INPS" in prompt for prompt in prompts)
    assert any("SARI" in prompt and "Registro Imprese" in prompt for prompt in prompts)
    assert not any(
        name.rsplit("/", maxsplit=1)[-1] in {".app.json", ".mcp.json"}
        for name in entries
    )
    assert not any("mcp" in name.split("/") for name in entries)
    assert not any(name.startswith("vera-codex-plugin/") for name in entries)
    assert not any(name.startswith("plugins/vera/") for name in entries)
    assert not any(name.endswith("marketplace.json") for name in entries)


@pytest.mark.parametrize("plugin_name", ["clara", "vera"])
def test_chatgpt_upload_entries_put_each_plugin_manifest_at_zip_root(
    plugin_name: str,
) -> None:
    builder = load_builder()
    targets = {package.plugin: package for package in builder.load_packages()}
    targets.update({bundle.name: bundle for bundle in builder.load_bundles()})

    entries = builder.chatgpt_upload_entries(targets[plugin_name])
    manifest = json.loads(entries[".codex-plugin/plugin.json"])

    assert manifest["name"] == plugin_name
    assert ".codex-plugin/plugin.json" in entries
    assert not any(name.startswith(f"{plugin_name}-codex-plugin/") for name in entries)


def test_chatgpt_manifest_rejects_more_than_three_default_prompts() -> None:
    builder = load_builder()
    source_path = ROOT / "plugins" / "vera" / ".codex-plugin" / "plugin.json"
    manifest = json.loads(source_path.read_text(encoding="utf-8"))
    manifest["interface"]["defaultPrompt"] = ["one", "two", "three", "four"]

    with pytest.raises(
        ValueError,
        match=r"interface\.defaultPrompt must contain at most 3 prompts; found 4",
    ):
        builder.project_chatgpt_manifest(json.dumps(manifest).encode("utf-8"))


def test_chatgpt_upload_zip_matches_source_without_replacing_install_zip(
    tmp_path: Path,
) -> None:
    builder = load_builder()
    vera = {bundle.name: bundle for bundle in builder.load_bundles()}["vera"]
    install_zip_before = vera.output_zip.read_bytes()
    source_manifest_path = ROOT / "plugins" / "vera" / ".codex-plugin" / "plugin.json"
    source_manifest_before = source_manifest_path.read_bytes()
    output = tmp_path / "vera-chatgpt-upload.zip"

    result = builder.build_chatgpt_upload(vera, output)

    assert result == output
    assert builder.verify_chatgpt_upload(vera, output) == []
    assert vera.output_zip.read_bytes() == install_zip_before
    assert source_manifest_path.read_bytes() == source_manifest_before
    with ZipFile(output) as archive:
        names = {name for name in archive.namelist() if not name.endswith("/")}
        assert names == set(builder.chatgpt_upload_entries(vera))
        assert archive.read("LICENSE") == (ROOT / "LICENSE").read_bytes()
        assert archive.read(
            ".codex-plugin/plugin.json"
        ) == builder.project_chatgpt_manifest(source_manifest_before)


def _bundled_node_or_skip() -> str:
    node = shutil.which("node")
    if node is not None:
        return node
    candidates = sorted(
        (Path.home() / ".cache" / "codex-runtimes").glob("*/dependencies/node/bin/node")
    )
    if not candidates:
        pytest.skip("The Codex-bundled Node.js runtime is required for this test.")
    return candidates[-1].as_posix()


def _projected_review_tools(
    node: str,
    server_path: Path,
    *server_args: str,
) -> set[str]:
    message = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {},
    }
    completed = subprocess.run(
        [node, server_path.as_posix(), *server_args, "--stdio"],
        cwd=server_path.parent.parent,
        input=json.dumps(message) + "\n",
        capture_output=True,
        check=True,
        text=True,
        timeout=20,
    )
    responses = [
        json.loads(line) for line in completed.stdout.splitlines() if line.strip()
    ]
    response = next(item for item in responses if item.get("id") == 1)
    return {tool["name"] for tool in response["result"]["tools"]}


def test_projected_vera_upload_keeps_executable_new_client_review_bridges(
    tmp_path: Path,
) -> None:
    builder = load_builder()
    vera = {bundle.name: bundle for bundle in builder.load_bundles()}["vera"]
    upload = builder.build_chatgpt_upload(
        vera,
        tmp_path / "vera-chatgpt-upload.zip",
    )
    extracted = tmp_path / "projected-vera"
    with ZipFile(upload) as archive:
        archive.extractall(extracted)

    node = _bundled_node_or_skip()
    dispatcher = extracted / "scripts" / "run_component_mcp.cjs"
    assert dispatcher.is_file()
    for component in ("new-client", "client-file-preparation"):
        component_root = extracted / "modules" / component
        projected_server = component_root / "scripts" / "review_mcp_server.cjs"
        local_bridge = component_root / "scripts" / "review_server.py"

        assert projected_server.is_file()
        assert local_bridge.is_file()
        assert not (component_root / "mcp").exists()
        assert _projected_review_tools(node, dispatcher, component) == set(
            NON_PLOTTING_REVIEW_TOOL_CONTRACTS[component]
        )

        review_server = _load_module_from_path(
            f"projected_{component.replace('-', '_')}_review_server",
            local_bridge,
        )
        workbench = review_server.LocalReviewWorkbench(
            plugin_dir=component_root,
            output_dir=tmp_path,
        )
        assert workbench.mcp_server_path == projected_server


def test_configured_bundle_zip_matches_repo_source() -> None:
    builder = load_builder()

    bundles = builder.load_bundles()
    assert {bundle.name for bundle in bundles} == {"vera"}
    for bundle in bundles:
        expected = builder.expected_zip_entries(bundle)
        with ZipFile(bundle.output_zip) as archive:
            actual_names = {
                name for name in archive.namelist() if not name.endswith("/")
            }

            assert actual_names == set(expected)
            for name, content in expected.items():
                assert archive.read(name) == content


def test_configured_downloads_include_repository_license() -> None:
    builder = load_builder()
    license_bytes = (ROOT / "LICENSE").read_bytes()

    for target in [*builder.load_packages(), *builder.load_bundles()]:
        entry_name = f"{target.package_root}/LICENSE"

        with ZipFile(target.output_zip) as archive:
            assert archive.read(entry_name) == license_bytes


def test_clara_download_includes_deck_revision_authorities() -> None:
    builder = load_builder()
    clara = {package.plugin: package for package in builder.load_packages()}["clara"]
    expected = builder.expected_zip_entries(clara)

    for relative_path in (
        "docs/specs/pptx_templates/ag-style-spec.md",
        "docs/specs/pptx_templates/bain-style-spec.md",
        ".agents/skills/advisory-output-shaper/SKILL.md",
    ):
        entry_name = f"{clara.package_root}/{relative_path}"
        assert expected[entry_name] == (ROOT / relative_path).read_bytes()


def test_accounting_bundle_contains_only_vera_and_its_modules() -> None:
    builder = load_builder()
    bundles = {bundle.name: bundle for bundle in builder.load_bundles()}

    standard_bundle = bundles["vera"]
    assert STANDALONE_PLUGIN_NAMES.isdisjoint(standard_bundle.plugin_names)
    assert set(standard_bundle.plugin_names) == STANDARD_ACCOUNTING_PLUGIN_NAMES

    standard_entries = builder.expected_zip_entries(standard_bundle)

    for plugin_name in REPORTING_ENGINE_PLUGIN_NAMES:
        assert not any(f"/plugins/{plugin_name}/" in name for name in standard_entries)
    for module_name in COMMERCIALISTA_MODULE_NAMES:
        module_path = f"/plugins/vera/modules/{module_name}/"
        assert any(module_path in name for name in standard_entries)
        assert not any(f"/plugins/{module_name}/" in name for name in standard_entries)


def test_vera_routes_every_commercialista_module() -> None:
    plugin_root = ROOT / "plugins" / "vera"
    components = json.loads(
        (plugin_root / "components.json").read_text(encoding="utf-8")
    )
    mcp_config = json.loads((plugin_root / ".mcp.json").read_text(encoding="utf-8"))
    routed_mcp_modules = {
        server["args"][-1] for server in mcp_config["mcpServers"].values()
    }
    skill_names = {
        path.parent.name for path in (plugin_root / "skills").glob("*/SKILL.md")
    }

    assert components["schema_version"] == 1
    assert set(components["plugins"]) == COMMERCIALISTA_MODULE_NAMES
    assert routed_mcp_modules == COMMERCIALISTA_MODULE_NAMES
    assert COMMERCIALISTA_MODULE_NAMES - {"client-file-preparation"} <= skill_names
    assert "client-file-preparation" not in skill_names
    assert components["workflow_roles"] == {
        "new-client": {
            "kind": "workflow",
            "internal_engines": ["client-file-preparation"],
        },
        "client-file-preparation": {
            "kind": "internal_engine",
            "parent_workflow": "new-client",
        },
    }


def test_component_package_selection_rebuilds_unified_bundles() -> None:
    builder = load_builder()

    targets = builder.select_packages(
        builder.load_packages(), builder.load_bundles(), ["check-entries"]
    )

    assert {target.target_name for target in targets} == {"vera"}


def test_generated_workbench_packages_include_local_review_server() -> None:
    builder = load_builder()
    shared_server = (ROOT / "scripts" / "serve_review_workbench.py").read_bytes()

    for package in builder.load_packages():
        plugin_dir = ROOT / "plugins" / package.plugin
        adapter_path = plugin_dir / "assets" / "review-workbench-adapter.json"
        if not adapter_path.exists():
            continue
        expected = builder.expected_zip_entries(package)
        entry_name = (
            f"{package.package_root}/plugins/{package.plugin}/scripts/review_server.py"
        )
        if (plugin_dir / "scripts" / "review_server.py").exists():
            assert entry_name in expected
            assert expected[entry_name] != shared_server
        else:
            assert expected[entry_name] == shared_server


def test_every_repo_plugin_is_classified_for_release() -> None:
    builder = load_builder()

    present_plugins = {path.name for path in builder.discover_plugin_dirs()}
    configured_plugins = {package.plugin for package in builder.load_packages()}
    for package in builder.load_packages():
        configured_plugins.update(
            builder.embedded_plugin_names(ROOT / "plugins" / package.plugin)
        )
    for bundle in builder.load_bundles():
        configured_plugins.update(bundle.plugin_names)
        for plugin_name in bundle.plugin_names:
            configured_plugins.update(
                builder.embedded_plugin_names(ROOT / "plugins" / plugin_name)
            )
    configured_plugins.update(builder.load_non_downloadable_plugins())

    assert present_plugins
    assert present_plugins == configured_plugins


def test_mcp_plugins_declare_app_manifest_for_widget_handoff() -> None:
    builder = load_builder()

    plugin_dirs = builder.discover_plugin_dirs()
    mcp_plugin_dirs = [path for path in plugin_dirs if (path / ".mcp.json").exists()]

    assert mcp_plugin_dirs
    for plugin_dir in mcp_plugin_dirs:
        manifest = json.loads(
            (plugin_dir / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        app_manifest_path = plugin_dir / ".app.json"

        assert manifest["mcpServers"] == "./.mcp.json"
        assert manifest["apps"] == "./.app.json"
        assert app_manifest_path.exists()
        assert json.loads(app_manifest_path.read_text(encoding="utf-8")) == {"apps": {}}


def test_plugin_skills_include_run_output_location_policy() -> None:
    builder = load_builder()

    for plugin_dir in builder.discover_plugin_dirs():
        skill_files = sorted((plugin_dir / "skills").glob("*/SKILL.md"))
        combined_skill_text = "\n".join(
            path.read_text(encoding="utf-8") for path in skill_files
        )

        assert builder.REQUIRED_OUTPUT_LOCATION_SNIPPET in combined_skill_text


def test_changed_plugin_sources_bump_manifest_version() -> None:
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD", "--", "plugins"],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        return

    changed_plugins = {
        Path(line).parts[1]
        for line in result.stdout.splitlines()
        if line.strip() and len(Path(line).parts) >= 3
    }

    for plugin_name in sorted(changed_plugins):
        manifest_path = ROOT / "plugins" / plugin_name / ".codex-plugin" / "plugin.json"
        if not manifest_path.exists():
            continue
        previous_result = subprocess.run(
            ["git", "show", f"HEAD:plugins/{plugin_name}/.codex-plugin/plugin.json"],
            cwd=ROOT,
            capture_output=True,
            check=False,
            text=True,
        )
        if previous_result.returncode != 0:
            continue
        current_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        previous_manifest = json.loads(previous_result.stdout)

        assert current_manifest["version"] != previous_manifest["version"], (
            f"{plugin_name}: plugin source changed without a manifest version bump; "
            "Codex can keep using the installed same-version cache."
        )


def test_repo_local_marketplace_has_no_plugins() -> None:
    marketplace_path = ROOT / ".agents" / "plugins" / "marketplace.json"
    marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))

    assert marketplace["name"] == "mp"
    assert marketplace["interface"]["displayName"] == "Mparanza"
    assert marketplace["plugins"] == []


def test_configured_plugin_zips_do_not_include_local_junk() -> None:
    builder = load_builder()
    forbidden_parts = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
    forbidden_names = {".DS_Store"}

    for package in builder.load_packages():
        with ZipFile(package.output_zip) as archive:
            for name in archive.namelist():
                parts = set(Path(name).parts)
                assert not (parts & forbidden_parts)
                assert Path(name).name not in forbidden_names


def test_plotting_plugins_are_embedded_in_clara_package_only() -> None:
    builder = load_builder()

    assert builder.load_non_downloadable_plugins() == set()
    clara_package = {package.plugin: package for package in builder.load_packages()}[
        "clara"
    ]
    clara_components = set(builder.embedded_plugin_names(ROOT / "plugins" / "clara"))
    assert REPORTING_ENGINE_PLUGIN_NAMES <= clara_components
    assert "reporting-engine" not in clara_components
    assert not (ROOT / "plugins" / "reporting-engine").exists()
    assert (ROOT / "plugins" / "clara" / "modules" / "reporting-engine").is_dir()
    clara_entries = builder.expected_zip_entries(clara_package)
    component_prefix = f"{clara_package.package_root}/plugins/clara/modules"
    for plugin_name in REPORTING_ENGINE_PLUGIN_NAMES:
        assert (
            f"{component_prefix}/{plugin_name}/.codex-plugin/plugin.json"
            in clara_entries
        )
    assert (
        f"{component_prefix}/reporting-engine/catalog/png_gallery_manifest.json"
        in clara_entries
    )
    assert (
        f"{component_prefix}/reporting-engine/catalog/mechanical_acceptance_summary.json"
        in clara_entries
    )
    assert (
        f"{component_prefix}/reporting-engine/fixtures/mechanical_acceptance/universal_complete.csv"
        in clara_entries
    )
    assert (
        f"{component_prefix}/reporting-engine/catalog/semantic_layer.schema.json"
        in clara_entries
    )
    assert (
        f"{component_prefix}/reporting-engine/catalog/semantic_acceptance_summary.json"
        in clara_entries
    )
    assert (
        f"{component_prefix}/reporting-engine/scripts/semantic_layer.py"
        in clara_entries
    )
    assert (
        f"{component_prefix}/reporting-engine/references/semantic_layer.md"
        in clara_entries
    )
    assert (
        f"{component_prefix}/reporting-engine/fixtures/semantic_layer/retail_monthly.semantic.json"
        in clara_entries
    )
    assert (
        f"{component_prefix}/reporting-engine/fixtures/semantic_layer/retail_monthly.snapshot_cases.json"
        in clara_entries
    )
    assert (
        f"{component_prefix}/reporting-engine/fixtures/semantic_layer/retail_monthly_refresh.csv"
        in clara_entries
    )

    for target in [*builder.load_packages(), *builder.load_bundles()]:
        entries = builder.expected_zip_entries(target)
        for plugin_name in REPORTING_ENGINE_PLUGIN_NAMES:
            assert not any(
                f"{target.package_root}/plugins/{plugin_name}/" in name
                for name in entries
            )


@pytest.mark.parametrize(
    ("component", "runner"),
    (
        ("distribution-analysis", "run_distribution.py"),
        ("funnel-analysis", "run_funnel_analysis.py"),
        ("mix-contribution-analysis", "run_mix_contribution.py"),
        ("period-comparison", "run_period_comparison.py"),
        ("scatter-bubble-analysis", "run_scatter_bubble.py"),
        ("set-overlap-analysis", "run_set_overlap.py"),
        ("statement-analysis", "run_statement_analysis.py"),
        ("variance-analysis", "run_variance.py"),
    ),
)
def test_extracted_clara_chart_components_import_without_repository_paths(
    extracted_clara_plugin: Path,
    tmp_path: Path,
    component: str,
    runner: str,
) -> None:
    runner_path = extracted_clara_plugin / "modules" / component / "scripts" / runner

    result = subprocess.run(
        [sys.executable, str(runner_path), "--help"],
        cwd=tmp_path,
        env=isolated_plugin_env(),
        capture_output=True,
        check=False,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert "ModuleNotFoundError" not in result.stderr
    assert "ImportError" not in result.stderr


def test_extracted_clara_semantic_fixture_validates(
    extracted_clara_plugin: Path,
) -> None:
    component_root = extracted_clara_plugin / "modules" / "reporting-engine"
    profiler_spec = importlib.util.spec_from_file_location(
        "extracted_reporting_engine_profiler",
        component_root / "scripts" / "profile_dataset.py",
    )
    semantic_spec = importlib.util.spec_from_file_location(
        "extracted_reporting_engine_semantic",
        component_root / "scripts" / "semantic_layer.py",
    )
    assert profiler_spec and profiler_spec.loader
    assert semantic_spec and semantic_spec.loader
    profiler = importlib.util.module_from_spec(profiler_spec)
    semantic = importlib.util.module_from_spec(semantic_spec)
    profiler_spec.loader.exec_module(profiler)
    semantic_spec.loader.exec_module(semantic)
    fixture_root = component_root / "fixtures" / "semantic_layer"
    profile = profiler.profile_dataset(
        fixture_root / "retail_monthly.csv", dataset_id="retail_monthly"
    )
    layer = json.loads(
        (fixture_root / "retail_monthly.semantic.json").read_text(encoding="utf-8")
    )
    manifest = json.loads(
        (component_root / "catalog" / "selection_manifest.json").read_text(
            encoding="utf-8"
        )
    )

    report = semantic.validate_semantic_layer(layer, profile, manifest)

    assert report["status"] == "contract_valid"
    assert report["semantic_readiness"] == "ready_as_scoped_semantic_input"
    assert report["counts"]["analysis_validities"]["valid"] == 9
    assert report["errors"] == []


def test_extracted_clara_semantic_acceptance_cli(
    extracted_clara_plugin: Path,
    tmp_path: Path,
) -> None:
    component_root = extracted_clara_plugin / "modules" / "reporting-engine"
    fixture_root = component_root / "fixtures" / "semantic_layer"
    output_path = tmp_path / "semantic_acceptance.json"

    result = subprocess.run(
        [
            sys.executable,
            str(component_root / "scripts" / "semantic_layer.py"),
            "acceptance",
            "--dataset",
            str(fixture_root / "retail_monthly.csv"),
            "--dataset-id",
            "retail_monthly",
            "--layer",
            str(fixture_root / "retail_monthly.semantic.json"),
            "--source",
            str(fixture_root / "retail_monthly_source_notes.md"),
            "--snapshot-suite",
            str(fixture_root / "retail_monthly.snapshot_cases.json"),
            "--output",
            str(output_path),
        ],
        cwd=tmp_path,
        env=isolated_plugin_env(),
        capture_output=True,
        check=False,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["result"] == "pass"
    assert report["validation"]["semantic_readiness"] == (
        "ready_as_scoped_semantic_input"
    )
    assert report["validation"]["counts"]["analysis_validities"]["valid"] == 9
    assert {
        case["case_id"]: case["actual_status"]
        for case in report["snapshot_reuse_proof"]
    } == {
        "origin_snapshot": "compatible",
        "changed_values_new_months_and_members": "compatible",
        "new_unclassified_column": "compatible_with_extensions",
        "bound_metrics_removed": "incompatible",
    }


def test_extracted_clara_attaches_refresh_to_existing_semantic_version(
    extracted_clara_plugin: Path,
    tmp_path: Path,
) -> None:
    component_root = extracted_clara_plugin / "modules" / "reporting-engine"
    fixture_root = component_root / "fixtures" / "semantic_layer"
    profiler_spec = importlib.util.spec_from_file_location(
        "extracted_reporting_engine_refresh_profiler",
        component_root / "scripts" / "profile_dataset.py",
    )
    assert profiler_spec and profiler_spec.loader
    profiler = importlib.util.module_from_spec(profiler_spec)
    profiler_spec.loader.exec_module(profiler)
    profile_path = tmp_path / "refresh_profile.json"
    profile_path.write_text(
        json.dumps(
            profiler.profile_dataset(
                fixture_root / "retail_monthly_refresh.csv",
                dataset_id="retail_monthly",
            )
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "snapshot_attachment.json"

    result = subprocess.run(
        [
            sys.executable,
            str(component_root / "scripts" / "semantic_layer.py"),
            "attach",
            "--profile",
            str(profile_path),
            "--layer",
            str(fixture_root / "retail_monthly.semantic.json"),
            "--output",
            str(output_path),
        ],
        cwd=tmp_path,
        env=isolated_plugin_env(),
        capture_output=True,
        check=False,
        text=True,
        timeout=60,
    )

    attachment = json.loads(output_path.read_text(encoding="utf-8"))
    assert result.returncode == 0, result.stderr
    assert attachment["attachment_status"] == "attached"
    assert attachment["compatibility"]["status"] == "compatible"
    assert attachment["semantic_version"] == 1


def test_extracted_clara_renders_known_period_comparison(
    extracted_clara_plugin: Path,
    tmp_path: Path,
) -> None:
    dataset = tmp_path / "sample_sales.csv"
    write_reporting_smoke_dataset(dataset)
    output_dir = tmp_path / "period_trend"
    renderer = (
        extracted_clara_plugin
        / "modules"
        / "reporting-engine"
        / "scripts"
        / "render_capability.py"
    )

    result = subprocess.run(
        [
            sys.executable,
            str(renderer),
            "period_comparison.trend",
            str(dataset),
            "--output-dir",
            str(output_dir),
            "--role-bindings-json",
            json.dumps({"period_axis": "Date", "comparison_metric": "Sales"}),
            "--options-json",
            json.dumps(
                {
                    "period_window": {
                        "current": {"year": 2026, "month_cutoff": 6},
                        "previous": {"year": 2025, "month_cutoff": 6},
                    },
                    "current_period_label": "2026",
                    "previous_period_label": "2025",
                    "reporting_entity": "Clara smoke test",
                }
            ),
            "--currency",
            "EUR",
            "--artifact-mode",
            "data_and_render",
        ],
        cwd=tmp_path,
        env=isolated_plugin_env(),
        capture_output=True,
        check=False,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
    manifest = json.loads((output_dir / "render_manifest.json").read_text())
    context = json.loads((output_dir / "period_comparison_context.json").read_text())
    chart_html = (output_dir / "year_over_year_line.html").read_text(encoding="utf-8")
    plot_call = chart_html.rsplit("Plotly.newPlot(", maxsplit=1)[-1]
    ac_trace = re.search(r'"name":"AC".*?"text":(\[[^\]]*\])', plot_call)

    assert manifest["runner"]["status"] == "ok"
    assert manifest["adapter_id"] == "reporting-engine.period_comparison"
    assert manifest["legacy_plugin_source"] == "period-comparison"
    assert context["totals"] == {
        "current": 1507.0,
        "previous": 1305.0,
        "delta": 202.0,
        "delta_percent": pytest.approx(15.478927203065135),
    }
    assert context["monthly"][-1]["current_amount"] == 345.0
    assert context["monthly"][-1]["previous_amount"] == 255.0
    assert ac_trace is not None
    assert json.loads(ac_trace.group(1))[-1] == "345.0"


def test_extracted_clara_renders_distribution_with_variant(
    extracted_clara_plugin: Path,
    tmp_path: Path,
) -> None:
    dataset = tmp_path / "sample_sales.csv"
    write_reporting_smoke_dataset(dataset)
    output_dir = tmp_path / "distribution_boxplot"
    renderer = (
        extracted_clara_plugin
        / "modules"
        / "reporting-engine"
        / "scripts"
        / "render_capability.py"
    )

    result = subprocess.run(
        [
            sys.executable,
            str(renderer),
            "distribution.boxplot",
            str(dataset),
            "--output-dir",
            str(output_dir),
            "--role-bindings-json",
            json.dumps(
                {
                    "distribution_metric": "Sales",
                    "panel_dimension": "Brand",
                }
            ),
            "--currency",
            "EUR",
            "--artifact-mode",
            "data_and_render",
            "--include-variants",
        ],
        cwd=tmp_path,
        env=isolated_plugin_env(),
        capture_output=True,
        check=False,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
    manifest = json.loads((output_dir / "render_manifest.json").read_text())
    context = json.loads((output_dir / "distribution_context.json").read_text())
    recipe = json.loads((output_dir / "render_request_recipe.json").read_text())

    assert manifest["runner"]["status"] == "ok"
    assert manifest["adapter_id"] == "reporting-engine.distribution"
    assert manifest["legacy_plugin_source"] == "distribution-analysis"
    assert recipe["options"]["charts"] == ["boxplot"]
    assert recipe["mappings"]["small_multiples_dimension"] == "Brand"
    assert (output_dir / "boxplot.html").is_file()
    assert (output_dir / "boxplot_small_multiples.html").is_file()
    summary_by_period = {row["Period"]: row for row in context["summary"]}
    assert summary_by_period == {
        "~Jun-2025": {
            "Period": "~Jun-2025",
            "rows": 12,
            "mean": 108.75,
            "median": 102.5,
            "std": pytest.approx(22.066531630091262),
            "min": 80.0,
            "max": 150.0,
        },
        "~Jun-2026": {
            "Period": "~Jun-2026",
            "rows": 12,
            "mean": pytest.approx(125.58333333333333),
            "median": 120.0,
            "std": pytest.approx(31.601088397059808),
            "min": 83.0,
            "max": 180.0,
        },
    }


def test_all_repo_plugins_declare_and_check_dependencies() -> None:
    builder = load_builder()

    for plugin_root in builder.discover_plugin_dirs():
        plugin_name = plugin_root.name
        assert (plugin_root / "requirements.txt").exists(), plugin_name
        assert (plugin_root / "scripts" / "check_dependencies.py").exists(), plugin_name

        skill_files = sorted((plugin_root / "skills").glob("*/SKILL.md"))
        assert skill_files, plugin_name
        combined_skill_text = "\n".join(
            path.read_text(encoding="utf-8") for path in skill_files
        )
        assert "check_dependencies.py" in combined_skill_text, plugin_name
        assert "requirements" in combined_skill_text.lower(), plugin_name


def test_all_dependency_checkers_accept_explicit_requirements_files() -> None:
    builder = load_builder()

    for plugin_root in builder.discover_plugin_dirs():
        plugin_name = plugin_root.name
        checker = plugin_root / "scripts" / "check_dependencies.py"
        result = subprocess.run(
            [sys.executable, str(checker), "--help"],
            check=True,
            text=True,
            capture_output=True,
        )

        assert "--requirements" in result.stdout, plugin_name


def test_all_plugin_skills_define_material_choice_intake() -> None:
    builder = load_builder()

    for plugin_root in builder.discover_plugin_dirs():
        plugin_name = plugin_root.name
        skill_files = sorted((plugin_root / "skills").glob("*/SKILL.md"))
        assert skill_files, plugin_name
        combined_skill_text = "\n".join(
            path.read_text(encoding="utf-8") for path in skill_files
        )
        lowered_skill_text = combined_skill_text.lower()

        assert (
            "material choices" in lowered_skill_text
            or "material research-angle" in lowered_skill_text
        ), plugin_name
        assert (
            "ask only those unresolved choices in chat" in lowered_skill_text
            or "ask the choice in chat" in lowered_skill_text
        ), plugin_name
        assert "actual inputs" in lowered_skill_text, plugin_name
        assert "unless the facts cue them" in lowered_skill_text, plugin_name


def test_plugin_skills_do_not_require_continue_theater() -> None:
    builder = load_builder()
    banned_continue_prompts = (
        "type `continue`",
        "type continue",
        "enter `continue`",
        "enter continue",
        "write `continue`",
        "write continue",
        "say `continue`",
        "say continue",
        "reply `continue`",
        "reply continue",
    )
    required_checkpoint_terms = (
        "external",
        "destructive",
        "approval-sensitive",
        "material",
    )

    for plugin_root in builder.discover_plugin_dirs():
        plugin_name = plugin_root.name
        skill_files = sorted((plugin_root / "skills").glob("*/SKILL.md"))
        assert skill_files, plugin_name
        combined_skill_text = "\n".join(
            path.read_text(encoding="utf-8") for path in skill_files
        )
        lowered_skill_text = combined_skill_text.lower()

        for phrase in banned_continue_prompts:
            assert phrase not in lowered_skill_text, plugin_name
        assert all(term in lowered_skill_text for term in required_checkpoint_terms), (
            f"{plugin_name}: skills must explain that explicit continuation or approval "
            "is only for external, destructive, approval-sensitive, or material decisions"
        )


def test_builder_source_validation_includes_interaction_pattern_audit(
    tmp_path: Path,
) -> None:
    builder = load_builder()
    plugin_root = tmp_path / "bad-review"
    skill_root = plugin_root / "skills" / "bad-review"
    skill_root.mkdir(parents=True)
    (skill_root / "SKILL.md").write_text(
        "Ask the user to type continue before every step.",
        encoding="utf-8",
    )

    errors = builder.validate_plugin_interaction_patterns(plugin_root)

    assert any("interaction pattern continue_theater" in error for error in errors)
    assert any(
        "interaction pattern approval_boundary_missing" in error for error in errors
    )


def test_builder_source_validation_includes_workbench_demo_audit(
    tmp_path: Path,
) -> None:
    builder = load_builder()
    plugin_root = tmp_path / "bad-workbench"
    adapter_root = plugin_root / "assets"
    adapter_root.mkdir(parents=True)
    (adapter_root / "review-workbench-adapter.json").write_text(
        json.dumps(
            {
                "schemaVersion": "1.0",
                "plugin": "bad-workbench",
                "detailGroups": [{"title": "Evidence", "fields": ["support"]}],
                "localized": {"it": {"title": "Demo"}},
                "demo": {
                    "review_type": "bad_review",
                    "items": [
                        {
                            "id": "row-1",
                            "item_type": "matched_row",
                            "title": "Matched row",
                            "allowed_actions": ["accept"],
                            "recommended_action": "accept",
                            "data": {"status": "matched"},
                            "evidence": [],
                        }
                    ],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    errors = builder.validate_plugin_workbench_demo(plugin_root)

    assert any("workbench demo demo_queue_too_shallow" in error for error in errors)
    assert any("workbench demo demo_evidence_missing" in error for error in errors)


def test_builder_source_validation_includes_review_payload_contract_coverage(
    tmp_path: Path,
) -> None:
    builder = load_builder()
    plugin_root = tmp_path / "uncovered-workbench"
    adapter_root = plugin_root / "assets"
    adapter_root.mkdir(parents=True)
    (adapter_root / "review-workbench-adapter.json").write_text(
        json.dumps(
            {
                "schemaVersion": "1.0",
                "plugin": "uncovered-workbench",
                "demo": {"items": []},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    errors = builder.validate_plugin_contract_coverage(plugin_root)

    assert any(
        "review payload contract coverage generated_payload_contract_test_missing"
        in error
        for error in errors
    )


def test_builder_validation_matches_dependency_standard() -> None:
    builder = load_builder()

    assert (
        builder.validate_package_config(builder.load_packages(), builder.load_bundles())
        == []
    )
    assert builder.validate_bundle_config(builder.load_bundles()) == []
    for plugin_root in builder.discover_plugin_dirs():
        assert builder.validate_plugin_source(plugin_root) == []


@pytest.mark.parametrize(
    "required_snippet",
    (
        "Should I transmit this technical problem to the developer so we can fix it?",
        "Do not continue with a chat interview, offer a fallback, or ask any",
        "does not authorize transmission of the user's improvement suggestion.",
        "Only in a later turn, after the failure-report choice has been handled",
        "credentials, secrets, or other identifying information.",
        "obtain separate suggestion-transmission consent.",
        "Should I transmit this suggestion to the developer so we can improve",
    ),
)
def test_builder_rejects_transmitted_feedback_policy_missing_safeguard(
    tmp_path: Path, required_snippet: str
) -> None:
    builder = load_builder()
    plugin_root = tmp_path / "vera"
    skill_path = plugin_root / "skills" / "vera" / "SKILL.md"
    skill_path.parent.mkdir(parents=True)
    source_skill = (
        ROOT / "plugins" / "vera" / "skills" / "vera" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert required_snippet in source_skill
    skill_path.write_text(
        source_skill.replace(required_snippet, "", 1),
        encoding="utf-8",
    )

    errors = builder.validate_plugin_source(plugin_root)

    assert (
        "vera: skill instructions must include plugin improvement feedback policy"
        in errors
    )


def test_dependency_checkers_are_packaged_in_download_zips() -> None:
    builder = load_builder()

    for package in builder.load_packages():
        checker = (
            f"{package.package_root}/plugins/"
            f"{package.plugin}/scripts/check_dependencies.py"
        )
        requirements = (
            f"{package.package_root}/plugins/" f"{package.plugin}/requirements.txt"
        )
        with ZipFile(package.output_zip) as archive:
            names = set(archive.namelist())
            assert checker in names
            assert requirements in names


def test_standard_accounting_bundle_marketplace_contains_public_plugins() -> None:
    with ZipFile(ACCOUNTING_BUNDLE_ZIP) as archive:
        names = set(archive.namelist())
        marketplace = json.loads(
            archive.read("vera-codex-plugin/.agents/plugins/marketplace.json")
        )

    entries = marketplace["plugins"]
    bundled_plugins = {entry["name"] for entry in entries}

    assert marketplace["name"] == "mp-vera"
    assert marketplace["interface"]["displayName"] == "MP Vera"
    assert bundled_plugins == STANDARD_ACCOUNTING_PLUGIN_NAMES
    for entry in entries:
        plugin = entry["name"]
        assert entry["source"]["path"] == f"./plugins/{plugin}"
        assert (
            f"vera-codex-plugin/plugins/{plugin}/" ".codex-plugin/plugin.json"
        ) in names


def test_only_clara_and_vera_have_private_zip_artifacts() -> None:
    builder = load_builder()
    configured_targets = [*builder.load_packages(), *builder.load_bundles()]
    configured_zip_paths = sorted(
        target.output_zip.relative_to(ROOT).as_posix() for target in configured_targets
    )
    zip_paths = {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "plugin_packages").glob("*/*.zip")
    }
    expected_install_zip_paths = {
        "plugin_packages/clara/clara-plugin.zip",
        "plugin_packages/vera/vera-plugin.zip",
    }
    allowed_upload_zip_paths = {
        target.output_zip.with_name(f"{target.target_name}-chatgpt-upload.zip")
        .relative_to(ROOT)
        .as_posix()
        for target in configured_targets
    }

    assert {target.target_name for target in configured_targets} == {"clara", "vera"}
    assert set(configured_zip_paths) == expected_install_zip_paths
    assert expected_install_zip_paths <= zip_paths
    assert zip_paths <= expected_install_zip_paths | allowed_upload_zip_paths


def test_repo_plugins_declare_distinct_icons() -> None:
    builder = load_builder()
    icon_payloads = {}

    for package in builder.load_packages():
        manifest = json.loads(
            (package.plugin_dir / ".codex-plugin" / "plugin.json").read_text(
                encoding="utf-8"
            )
        )
        interface = manifest["interface"]
        icon_reference = interface["composerIcon"]
        assert interface["logo"] == icon_reference, package.plugin
        icon_path = package.plugin_dir / icon_reference.removeprefix("./")
        assert icon_path.exists(), package.plugin
        icon_payloads[package.plugin] = icon_path.read_bytes()

        with ZipFile(package.output_zip) as archive:
            icon_entry = (
                f"{package.package_root}/plugins/{package.plugin}/"
                f"{icon_reference.removeprefix('./')}"
            )
            assert icon_entry in archive.namelist()

    assert len(set(icon_payloads.values())) == len(icon_payloads)


def test_repo_plugins_declare_public_metadata() -> None:
    builder = load_builder()
    required_interface_fields = (
        "displayName",
        "shortDescription",
        "longDescription",
        "developerName",
        "category",
        "capabilities",
        "websiteURL",
        "privacyPolicyURL",
        "termsOfServiceURL",
        "defaultPrompt",
        "brandColor",
        "composerIcon",
        "logo",
    )

    for package in builder.load_packages():
        manifest = json.loads(
            (package.plugin_dir / ".codex-plugin" / "plugin.json").read_text(
                encoding="utf-8"
            )
        )
        assert manifest["name"] == package.plugin
        assert manifest["version"]
        assert manifest["description"]
        assert manifest["homepage"]
        assert manifest["repository"]
        assert manifest["license"]
        assert manifest["skills"] == "./skills/"
        assert manifest["author"]["name"]
        assert manifest["author"]["email"]
        assert manifest["keywords"]

        interface = manifest["interface"]
        for field in required_interface_fields:
            assert interface[field], f"{package.plugin}: {field}"
        assert package.category == interface["category"]
        assert len(interface["defaultPrompt"]) <= 3, package.plugin


def test_all_repo_plugins_declare_canonical_open_source_metadata() -> None:
    builder = load_builder()
    canonical_repository = "https://github.com/fabioannovazzi/app_files"

    for plugin_root in builder.discover_plugin_dirs():
        manifest = json.loads(
            (plugin_root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )

        assert manifest["repository"] == canonical_repository, plugin_root.name
        assert manifest["license"] == "AGPL-3.0-only", plugin_root.name


def test_all_repo_plugins_include_end_of_run_feedback_policy() -> None:
    builder = load_builder()

    for plugin_root in builder.discover_plugin_dirs():
        plugin_name = plugin_root.name
        skill_files = sorted((plugin_root / "skills").glob("*/SKILL.md"))
        combined_skill_text = "\n".join(
            path.read_text(encoding="utf-8") for path in skill_files
        )
        normalized_skill_text = " ".join(combined_skill_text.split())

        assert "## Plugin Improvement Feedback" in combined_skill_text, plugin_name
        if plugin_name in {"clara", "vera"}:
            assert (
                "Localize the consent question to the conversation language."
                in combined_skill_text
            ), plugin_name
            assert (
                "Vuoi che trasmetta questo problema tecnico allo sviluppatore "
                "così possiamo risolverlo?" in combined_skill_text
            ), plugin_name
            assert (
                "Should I transmit this technical problem to the developer so we "
                "can fix it?" in combined_skill_text
            ), plugin_name
            assert (
                "Do not continue with a chat interview, offer a fallback, or ask any "
                "suggestion question in the same turn." in normalized_skill_text
            ), plugin_name
            assert (
                "Consent to transmit the technical problem does not authorize "
                "transmission of the user's improvement suggestion."
                in normalized_skill_text
            ), plugin_name
            assert (
                "client or customer names or data, source documents, run or case "
                "details, credentials, secrets, or other identifying information"
                in normalized_skill_text
            ), plugin_name
            assert (
                "follow the normal text-suggestion path below: draft a separate "
                "sanitized suggestion, show its exact text, and obtain separate "
                "suggestion-transmission consent." in normalized_skill_text
            ), plugin_name
            assert (
                "Vuoi che trasmetta questo suggerimento allo sviluppatore così "
                f"possiamo migliorare {plugin_name.title()}?" in combined_skill_text
            ), plugin_name
            assert (
                "Should I transmit this suggestion to the developer so we can improve "
                f"{plugin_name.title()}?" in combined_skill_text
            ), plugin_name
            assert "scripts/change_requests.py submit-problem" in combined_skill_text
            assert (
                "scripts/change_requests.py reserve-suggestion-prompt"
                in combined_skill_text
            )
            assert "scripts/change_requests.py submit-suggestion" in combined_skill_text
            assert "scripts/change_requests.py start-interview" in combined_skill_text
            assert (
                "Always use the generic client-free string below" in combined_skill_text
            )
            generic_voice_command = (
                'python scripts/change_requests.py start-interview --opportunity "General '
                f"{plugin_name.title()} improvement suggestion; no client, customer, "
                'source, run, or case details supplied." --language <language>'
            )
            assert generic_voice_command in combined_skill_text
            assert "at most one minute" in combined_skill_text
            assert "only if needed, one short follow-up" in combined_skill_text
            specialist_handoff = (
                "After substantive use of this workflow, read and follow the "
                "`Plugin Improvement Feedback` section in "
                f"`../{plugin_name}/SKILL.md`."
            )
            for skill_file in skill_files:
                if skill_file.parent.name == plugin_name:
                    continue
                assert specialist_handoff in skill_file.read_text(
                    encoding="utf-8"
                ), skill_file
        else:
            assert (
                "Keep the improvement note local to chat or run artifacts."
                in combined_skill_text
            ), plugin_name
        assert "email those suggestions" not in combined_skill_text, plugin_name
        assert "personal email address" not in combined_skill_text, plugin_name


def test_all_repo_plugin_skills_include_codex_native_run_ux_contract() -> None:
    builder = load_builder()
    required_snippets = (
        "## Codex-Native Run UX",
        "checklist",
        "Run Intake table",
        "Decision Table",
        "Default output policy",
        "not choices to propose",
        "Artifact Card",
        "codex_run_review.md",
        "generated ZIPs",
    )

    for plugin_root in builder.discover_plugin_dirs():
        skill_files = sorted((plugin_root / "skills").glob("*/SKILL.md"))
        assert skill_files, plugin_root.name

        for skill_file in skill_files:
            skill_text = skill_file.read_text(encoding="utf-8")
            normalized_skill_text = " ".join(skill_text.split())
            if plugin_root.name == "vera" and skill_file.parent.name != "vera":
                assert "Read that module's" in normalized_skill_text
                assert "plugin working directory" in normalized_skill_text
                continue
            if plugin_root.name == "clara" and skill_file.parent.name in {
                "attribute-reporting",
                "brand-fit",
            }:
                assert "Read that component's" in normalized_skill_text
                assert "working directory" in normalized_skill_text
                continue
            for snippet in required_snippets:
                assert (
                    snippet in skill_text or snippet in normalized_skill_text
                ), f"{plugin_root.name}: {skill_file}"
            assert (
                "approval checkpoint" in skill_text
                or "inclusion checkpoint" in skill_text
                or "execution checkpoint" in skill_text
                or "approval checkpoint" in normalized_skill_text
                or "inclusion checkpoint" in normalized_skill_text
                or "execution checkpoint" in normalized_skill_text
            ), f"{plugin_root.name}: {skill_file}"


def test_only_legacy_email_plugins_include_user_run_notification_policy() -> None:
    builder = load_builder()

    for plugin_root in builder.discover_plugin_dirs():
        plugin_name = plugin_root.name
        skill_files = sorted((plugin_root / "skills").glob("*/SKILL.md"))
        combined_skill_text = "\n".join(
            path.read_text(encoding="utf-8") for path in skill_files
        )

        if plugin_name not in PLUGINS_WITH_LEGACY_USER_EMAIL:
            assert "## User Run Notifications" not in combined_skill_text, plugin_name
            continue

        assert "## User Run Notifications" in combined_skill_text, plugin_name
        assert "At the start of a substantive plugin run" in combined_skill_text
        assert "recipient email address" in combined_skill_text, plugin_name
        assert "completion or handled-error email" in combined_skill_text, plugin_name
        assert "Codex Gmail connector" in combined_skill_text, plugin_name
        assert "plugin scripts, SMTP, Resend, mailto links" in combined_skill_text
        assert "Gmail is unavailable" in combined_skill_text, plugin_name
        assert "separate from Plugin Improvement Feedback" in combined_skill_text


def test_non_plotting_review_plugins_document_save_apply_contract() -> None:
    builder = load_builder()

    plugin_roots = {
        plugin_root.name: plugin_root for plugin_root in builder.discover_plugin_dirs()
    }
    for plugin_name, tool_names in NON_PLOTTING_REVIEW_TOOL_CONTRACTS.items():
        plugin_root = plugin_roots[plugin_name]
        skill_files = sorted((plugin_root / "skills").glob("*/SKILL.md"))
        combined_skill_text = "\n".join(
            path.read_text(encoding="utf-8") for path in skill_files
        )

        for tool_name in tool_names:
            assert tool_name in combined_skill_text, plugin_name
        assert "ui_decisions.json" in combined_skill_text, plugin_name
        assert "applied_decisions.json" in combined_skill_text, plugin_name
        assert "final_artifacts.json" in combined_skill_text, plugin_name


def test_all_repo_plugins_include_trigger_eval_fixtures() -> None:
    builder = load_builder()

    for plugin_root in builder.discover_plugin_dirs():
        plugin_name = plugin_root.name
        fixture_path = plugin_root / "evals" / "trigger_fixtures.json"
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))

        assert payload["plugin"] == plugin_name
        assert payload["version"] == 1
        assert payload["should_trigger"], plugin_name
        assert payload["should_not_trigger"], plugin_name
        for case in payload["should_trigger"]:
            assert case["id"]
            assert case["prompt"]
            assert case["required_signals"]
        for case in payload["should_not_trigger"]:
            assert case["id"]
            assert case["prompt"]


def test_static_plugin_pages_do_not_show_feedback_mailto_footer() -> None:
    forbidden_snippets = (
        "mailto:",
        "Dicci cosa possiamo migliorare",
        "Tell us what we can improve",
        "Dites-nous ce que nous pouvons",
        "Sagen Sie uns, was wir verbessern",
        "feedback-note",
    )

    for page_path in STATIC_PLUGIN_PAGES:
        page = page_path.read_text(encoding="utf-8")
        for snippet in forbidden_snippets:
            assert snippet not in page, page_path.as_posix()


def test_static_plugin_pages_use_the_unified_vera_install_action() -> None:
    stale_download_snippets = (
        'href="downloads/check-entries-plugin.zip',
        'href="downloads/concordato-plan-review-plugin.zip',
        'href="downloads/clara-plugin.zip',
        'href="downloads/deep-research-validator-plugin.zip',
        'href="downloads/distribution-analysis-plugin.zip',
        'href="downloads/client-file-preparation-plugin.zip',
        'href="downloads/new-client-plugin.zip',
        'href="downloads/journal-bank-reconciliation-plugin.zip',
        'href="downloads/journal-sampling-plugin.zip',
        'href="downloads/mix-contribution-analysis-plugin.zip',
        'href="downloads/period-comparison-plugin.zip',
        'href="downloads/prompt-optimizer-plugin.zip',
        'href="downloads/report-builder-plugin.zip',
        'href="downloads/riconciliazione-partite-plugin.zip',
        'href="downloads/scatter-bubble-analysis-plugin.zip',
        'href="downloads/variance-analysis-plugin.zip',
    )
    standard_pages = tuple(
        page_path
        for page_path in ACCOUNTING_STATIC_PLUGIN_PAGES
        if page_path.parent.name != "vera"
    )
    for page_path in standard_pages:
        page = page_path.read_text(encoding="utf-8")

        assert ACCOUNTING_BUNDLE_LINK in page, page_path.as_posix()
        assert "Plugins4Accountants" not in page, page_path.as_posix()
        assert "Vera" in page, page_path.as_posix()
        assert "bundle" not in page.lower(), page_path.as_posix()
        assert "data-free-download-link" not in page, page_path.as_posix()
        assert VERA_DOWNLOAD_HREF not in page, page_path.as_posix()
        assert "Plugin Pack" not in page, page_path.as_posix()
        assert "Download ZIP" not in page, page_path.as_posix()
        assert "Scarica ZIP" not in page, page_path.as_posix()
        assert re.search(r'href="#(?:install|scarica|download)"', page)
        for snippet in stale_download_snippets:
            assert snippet not in page, page_path.as_posix()

    for plugin_name in REPORTING_ENGINE_PLUGIN_NAMES:
        assert not (
            ROOT
            / "static"
            / "shared"
            / plugin_name
            / "downloads"
            / f"{plugin_name}-plugin.zip"
        ).exists()
        assert not (
            ROOT / "static" / "shared" / plugin_name / "LEGGIMI_INSTALLAZIONE.txt"
        ).exists()


def test_static_plugin_pages_share_quiet_white_theme() -> None:
    shell = (ROOT / "static" / "shared" / "plugin-page-shell.css").read_text(
        encoding="utf-8"
    )
    journey_shell = (ROOT / "static" / "shared" / "vera-journey.css").read_text(
        encoding="utf-8"
    )

    assert "--plugin-hero-title-size: 2.875rem;" in shell
    assert "--plugin-section-title-size: 2.125rem;" in shell
    assert "--plugin-lead-size: 1.1875rem;" in shell
    assert "font-size: var(--plugin-hero-title-size)" in shell
    assert "font-size: var(--plugin-section-title-size)" in shell
    assert "font-size: var(--plugin-lead-size)" in shell
    assert "font-size: clamp(1.08rem" not in shell
    assert "--vj-white: #ffffff;" in journey_shell
    assert "background: var(--vj-white);" in journey_shell

    for page_path in ACCOUNTING_STATIC_PLUGIN_PAGES:
        page = page_path.read_text(encoding="utf-8")

        if page_path.parent.name == "new-client":
            assert re.search(
                r'href="\.\./vera-journey\.css\?v=20260721-new-client-[^"]+"',
                page,
            )
            continue

        assert (
            "--paper: #ffffff;" in page
            or "--bg: #ffffff;" in page
            or "--white: #FFFFFF;" in page
            or "--white: #ffffff;" in page
        ), page_path.as_posix()
        assert "font-size: clamp(3rem" not in page, page_path.as_posix()
        assert "font-size: clamp(42px, 7vw" not in page, page_path.as_posix()
        assert "background: rgba(251, 252, 251" not in page, page_path.as_posix()


@pytest.mark.parametrize(
    "page_path",
    (
        ROOT / "static" / "shared" / "vera" / "index.html",
        ROOT / "static" / "shared" / "clara" / "index.html",
        *VERA_PUBLIC_PAGE_PATHS,
    ),
)
def test_public_product_pages_load_instrument_sans(page_path: Path) -> None:
    page = page_path.read_text(encoding="utf-8")

    assert "family=Instrument+Sans" in page, page_path.as_posix()


@pytest.mark.parametrize(
    "stylesheet_path",
    (
        ROOT / "static" / "shared" / "plugin-page-shell.css",
        ROOT / "static" / "shared" / "vera" / "index.html",
        ROOT / "static" / "shared" / "clara" / "clara-page.css",
    ),
)
def test_public_product_styles_apply_instrument_sans_to_form_controls(
    stylesheet_path: Path,
) -> None:
    stylesheet = stylesheet_path.read_text(encoding="utf-8")

    assert 'font-family: "Instrument Sans"' in stylesheet
    assert re.search(
        r"button,\s*input,\s*optgroup,\s*select,\s*textarea\s*"
        r"\{\s*font-family:\s*inherit;",
        stylesheet,
    )


def test_public_plugin_explainer_pages_use_shared_white_shell() -> None:
    shell = (ROOT / "static" / "shared" / "plugin-page-shell.css").read_text(
        encoding="utf-8"
    )

    assert "--paper: #ffffff;" in shell
    assert "--bg: #ffffff;" in shell
    assert "--shadow: none;" in shell
    assert "display: block !important;" in shell
    assert "width: auto;" in shell
    assert "max-width: none;" in shell
    assert "height: 34px;" in shell
    assert ".brand::before" not in shell
    assert 'content: "Home";' not in shell
    assert "prefers-reduced-motion" in shell
    assert "linear-gradient" not in shell.lower()
    assert "radial-gradient" not in shell.lower()
    for color in ("#002060", "#0070c0", "#00b0f0", "#f3fbff"):
        assert color in shell
    for stale_accent in ("#496a60", "#27313a", "#e7eee9"):
        assert stale_accent not in shell

    for page_path in PUBLIC_PLUGIN_EXPLAINER_PAGES:
        page = page_path.read_text(encoding="utf-8")

        if page_path == ROOT / "static" / "shared" / "clara" / "index.html":
            assert 'href="clara-page.css?v=' in page, page_path.as_posix()
        else:
            assert 'href="../plugin-page-shell.css' in page, page_path.as_posix()


@pytest.mark.parametrize("relative_path", VERA_PUBLIC_PAGE_PATHS)
def test_vera_downstream_pages_show_mparanza_logo(relative_path: Path) -> None:
    page = (ROOT / relative_path).read_text(encoding="utf-8")
    header_match = re.search(r"<header(?:\s[^>]*)?>.*?</header>", page, re.DOTALL)

    assert (
        'href="../plugin-page-shell.css?v=20260720-logo"' in page
    ), relative_path.as_posix()
    assert header_match is not None, relative_path.as_posix()
    if relative_path.name in {"geneva.html", "uk.html", "zurich.html"}:
        renderer = (
            ROOT / "static" / "shared" / "new-client" / "jurisdiction-pages.js"
        ).read_text(encoding="utf-8")
        assert '<header class="topbar"></header>' in page
        assert 'src="jurisdiction-pages.js?v=' in page
        assert 'class="brand"' in renderer
        assert (
            '<img src="https://mparanza.com/images/MPARANZA-HORIZONTAL.png" '
            'alt="Mparanza">' in renderer
        )
        return

    header = header_match.group(0)
    assert 'class="brand"' in header
    assert (
        '<img src="https://mparanza.com/images/MPARANZA-HORIZONTAL.png" '
        'alt="Mparanza">' in header
    )


def test_static_plugin_pages_are_public_and_plugin_downloads_are_removed() -> None:
    _restore_application_import_path()

    from fastapi.testclient import TestClient

    from src.fastapi_app_entry import app

    client = TestClient(app)
    paths = [
        path.relative_to(ROOT).as_posix() for path in ACCOUNTING_STATIC_PLUGIN_PAGES
    ]
    download_paths = ("/downloads/vera", "/downloads/clara")
    old_individual_free_download_paths = (
        "/static/shared/check-entries/downloads/check-entries-plugin.zip",
        "/static/shared/prompt-optimizer/downloads/prompt-optimizer-plugin.zip",
    )
    for path in paths:
        response = client.get(f"/{path}")

        assert response.status_code == 200, path
    for path in download_paths:
        response = client.get(path, follow_redirects=False)

        assert response.status_code == 404, path
    removed_pro_response = client.get(
        "/downloads/accounting-plugin-pack/pro", follow_redirects=False
    )
    assert removed_pro_response.status_code == 404
    for clara_asset in (
        "/static/shared/clara/index.html",
        "/static/shared/clara/clara-page.css",
        "/static/shared/clara/icon.svg",
    ):
        response = client.get(clara_asset)

        assert response.status_code == 200, clara_asset
    for path in old_individual_free_download_paths:
        response = client.get(path, follow_redirects=False)

        assert response.status_code == 404, path


def test_manual_vera_download_is_removed() -> None:
    _restore_application_import_path()

    from fastapi.testclient import TestClient

    from src.fastapi_app_entry import app

    with TestClient(app) as client:
        response = client.get(
            f"{VERA_DOWNLOAD_HREF}?lang=it",
            follow_redirects=False,
        )

        assert response.status_code == 404


def test_clara_downloads_and_removed_explainers_return_404(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _restore_application_import_path()

    from fastapi.testclient import TestClient

    from modules.auth import dependencies as auth_dependencies
    from modules.auth.config import get_auth_config
    from modules.auth.google_identity import GoogleUserInfo
    from modules.auth.session import create_session_cookie
    from modules.pdp import api as pdp_api
    from src.fastapi_app_entry import app

    pro_email = "pro@example.com"
    free_email = "free@example.com"
    permissions_file = tmp_path / "site_page_permissions.json"
    permissions_file.write_text(
        json.dumps({"clara": [pro_email]}),
        encoding="utf-8",
    )
    structure_file = tmp_path / "permission_structure.json"
    structure_file.write_text(
        json.dumps(
            {
                "clara": [
                    "/downloads/clara",
                    "/static/shared/clara/downloads",
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AUTH_ENABLED", "1")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "dummy-client-id")
    monkeypatch.setenv("AUTH_SESSION_SECRET", "dummy-secret")
    monkeypatch.setattr(auth_dependencies, "_SITE_PERMISSIONS_FILE", permissions_file)
    monkeypatch.setattr(auth_dependencies, "_PERMISSION_STRUCTURE_FILE", structure_file)
    auth_dependencies._get_site_permissions.cache_clear()
    auth_dependencies._get_permission_structure.cache_clear()
    get_auth_config.cache_clear()
    try:
        config = get_auth_config()
        removed_plugin_download_paths = (
            "/downloads/clara",
            "/static/shared/clara/downloads/clara-plugin.zip",
        )
        removed_download_paths = ("/downloads/accounting-plugin-pack/pro",)
        studio_redirect_paths = (
            "/static/shared/deep-research-validator/downloads/"
            "deep-research-validator-plugin.zip",
        )
        old_engine_download_paths = (
            "/static/shared/distribution-analysis/downloads/"
            "distribution-analysis-plugin.zip",
            "/static/shared/funnel-analysis/downloads/funnel-analysis-plugin.zip",
            "/static/shared/mix-contribution-analysis/downloads/"
            "mix-contribution-analysis-plugin.zip",
            "/static/shared/scatter-bubble-analysis/downloads/"
            "scatter-bubble-analysis-plugin.zip",
            "/static/shared/set-overlap-analysis/downloads/"
            "set-overlap-analysis-plugin.zip",
            "/static/shared/statement-analysis/downloads/statement-analysis-plugin.zip",
            "/static/shared/variance-analysis/downloads/variance-analysis-plugin.zip",
        )
        public_plugin_pages = (
            "/static/shared/deep-research-validator/index.html",
            "/static/shared/clara/index.html",
        )
        removed_plugin_pages = (
            "/static/shared/audit-reconciliation/index.html",
            "/static/shared/reporting/index.html",
            "/static/shared/research/index.html",
            "/static/shared/mix-contribution-analysis/index.html",
            "/static/shared/period-comparison/index.html",
            "/static/shared/scatter-bubble-analysis/index.html",
            "/static/shared/variance-analysis/index.html",
            "/static/shared/distribution-analysis/index.html",
            "/static/shared/set-overlap-analysis/index.html",
            "/static/shared/funnel-analysis/index.html",
            "/static/shared/statement-analysis/index.html",
        )
        with TestClient(app) as free_client:
            token, _ = create_session_cookie(GoogleUserInfo(email=free_email), config)
            free_client.cookies.set(config.session_cookie_name, token)

            for page_path in public_plugin_pages:
                response = free_client.get(page_path, follow_redirects=False)
                assert response.status_code == 200

            for page_path in removed_plugin_pages:
                response = free_client.get(page_path, follow_redirects=False)
                assert response.status_code == 404

            for download_path in removed_plugin_download_paths:
                response = free_client.get(
                    f"{download_path}?lang=en", follow_redirects=False
                )
                assert response.status_code == 404
            for download_path in removed_download_paths:
                response = free_client.get(download_path, follow_redirects=False)
                assert response.status_code == 404
            for download_path in studio_redirect_paths:
                response = free_client.get(download_path, follow_redirects=False)
                assert response.status_code == 404
            for download_path in old_engine_download_paths:
                response = free_client.get(download_path, follow_redirects=False)
                assert response.status_code == 404

        with TestClient(app) as pro_client:
            token, _ = create_session_cookie(GoogleUserInfo(email=pro_email), config)
            pro_client.cookies.set(config.session_cookie_name, token)

            for download_path in removed_plugin_download_paths:
                response = pro_client.get(download_path, follow_redirects=False)
                assert response.status_code == 404
            for download_path in removed_download_paths:
                response = pro_client.get(download_path, follow_redirects=False)
                assert response.status_code == 404
            for download_path in studio_redirect_paths:
                response = pro_client.get(download_path, follow_redirects=False)
                assert response.status_code == 404
            for download_path in old_engine_download_paths:
                response = pro_client.get(download_path, follow_redirects=False)
                assert response.status_code == 404
    finally:
        auth_dependencies._get_site_permissions.cache_clear()
        auth_dependencies._get_permission_structure.cache_clear()
        get_auth_config.cache_clear()


def test_clara_forbidden_page_has_no_vera_download() -> None:
    template = (ROOT / "templates" / "forbidden.html").read_text(encoding="utf-8")
    api_source = (ROOT / "modules" / "pdp" / "api.py").read_text(encoding="utf-8")
    page_copy = f"{template}\n{api_source}"

    assert "Clara access" in template
    assert "Clara is available only to authorized users." in api_source
    assert "Download Vera" not in template
    assert "Pro Accounting Plugin Pack" not in api_source
    assert "standard Accounting Plugin Pack" not in template
    assert "standard_plugin_pack_href" not in template
    assert "accredited accountant access" not in page_copy
    assert "Pro Plugin Pack" not in page_copy


def test_reconciliation_page_describes_actual_reconciliation_problem() -> None:
    page = (
        ROOT / "static" / "shared" / "riconciliazione-partite" / "index.html"
    ).read_text(encoding="utf-8")

    assert "In pratica" not in page
    assert "Problema che risolve" in page
    assert (
        "Riconcilia partite, pagamenti e supporti in un file Excel rivedibile" in page
    )
    assert "Metti partite aperte, mastrini, banca e supporti" in page
    assert "Cosa dai / cosa ottieni" in page
    assert "Excel conserva il dettaglio riga per riga" in page
    assert "Prompt pronti" in page
    assert "Riconciliazione completa" in page
    assert "Mastrino vs banca/supporti" in page
    assert "Supporti post cut-off" in page
    assert "Usa il default factoring" in page
    assert "pagamento in estratto conto bancario" in page
    assert '<a href="#scarica" data-journey="nav.open">Apri Vera</a>' in page


def test_new_client_page_describes_one_connected_client_journey() -> None:
    page = (ROOT / "static" / "shared" / "new-client" / "index.html").read_text(
        encoding="utf-8"
    )

    for snippet in (
        '<html lang="it">',
        "Nuovo cliente",
        "Un solo percorso per il nuovo cliente, dalla prima cartella ai riesami.",
        "Cosa fornisci",
        "Cosa prepara Vera",
        "Cosa ricevi",
        "Un solo percorso",
        "Le mancanze diventano richieste precise.",
        "Memo studio",
        "Richiesta cliente",
        "Scegli la giurisdizione",
        "Svizzera · Ginevra",
        "Svizzera · Zurigo",
        "United Kingdom",
        'id="prompt-example"',
        'id="file-preparation"',
        'id="relationship"',
        'id="italy"',
        'href="geneva.html?lang=it"',
        'href="zurich.html?lang=it"',
        'href="uk.html?lang=it"',
    ):
        assert snippet in page
    for stale_snippet in (
        "plugin guida Codex",
        "check_dependencies.py",
        "gli script raccolgono",
        "Codex legge gli output",
        "First pass over a client folder",
        "Turn a messy client folder into a first work pack",
        "Complete intake",
        "XML invoices",
        "Tax fields",
        "Tax notice",
        "Operational first pass",
        "Istruttoria cliente",
        "Onboarding cliente",
    ):
        assert stale_snippet not in page


@pytest.mark.parametrize("relative_path", VERA_PUBLIC_PAGE_PATHS)
def test_vera_public_page_browser_title_uses_vera_brand(
    relative_path: Path,
) -> None:
    page = (ROOT / relative_path).read_text(encoding="utf-8")

    assert "| Vera</title>" in page
    assert "| Mparanza" not in page


def test_new_client_jurisdiction_pages_define_local_scope() -> None:
    new_client_root = ROOT / "static" / "shared" / "new-client"
    jurisdiction_source = (new_client_root / "jurisdiction-pages.js").read_text(
        encoding="utf-8"
    )
    pages = {
        "geneva.html": ("geneva", "fr"),
        "zurich.html": ("zurich", "de"),
        "uk.html": ("uk", "en"),
    }

    for filename, (jurisdiction, default_language) in pages.items():
        page = (new_client_root / filename).read_text(encoding="utf-8")
        assert f'data-jurisdiction="{jurisdiction}"' in page
        assert f'data-presentation-language="{default_language}"' in page
        assert 'src="jurisdiction-pages.js?v=' in page
        assert f'slug: "{filename}"' in jurisdiction_source
        assert f'defaultLanguage: "{default_language}"' in jurisdiction_source
        for language in ("it", "en", "fr", "de"):
            assert f'hreflang="{language}"' in page

    assert 'const SUPPORTED_LANGUAGES = ["it", "en", "fr", "de"]' in (
        jurisdiction_source
    )
    assert "const page = jurisdictions[document.body.dataset.jurisdiction]" in (
        jurisdiction_source
    )
    assert "document.body.dataset.presentationLanguage = language" in (
        jurisdiction_source
    )
    assert 'url.searchParams.set("lang", language)' in jurisdiction_source
    assert 'href="index.html?lang=${language}#core-model"' in jurisdiction_source
    assert "Report Builder" not in jurisdiction_source
    assert "dataset.jurisdiction =" not in jurisdiction_source
    for localized_scope in (
        "La preparazione documentale è disponibile per questo mercato; la "
        "configurazione professionale oggi prosegue con il country pack Italia.",
        "Document preparation is available for this market; professional setup "
        "currently continues with the Italy country pack.",
        "La préparation documentaire est disponible pour ce marché ; la mise en "
        "place professionnelle se poursuit actuellement avec le pack Italie.",
        "Die Dokumentvorbereitung ist für diesen Markt verfügbar; die "
        "professionelle Einrichtung wird derzeit mit dem Länderpaket Italien "
        "fortgesetzt.",
    ):
        assert localized_scope in jurisdiction_source


def test_new_client_page_scopes_the_professional_country_pack_to_italy() -> None:
    page = (ROOT / "static" / "shared" / "new-client" / "index.html").read_text(
        encoding="utf-8"
    )

    for localized_scope in (
        "Il country pack professionale oggi disponibile è quello italiano.",
        "The professional country pack currently available is Italy.",
        "Le pack professionnel actuellement disponible est celui de l’Italie.",
        "Das derzeit verfügbare professionelle Länderpaket ist Italien.",
    ):
        assert localized_scope in page


def test_journal_sampling_page_matches_plugin_site_pattern() -> None:
    page = (ROOT / "static" / "shared" / "journal-sampling" / "index.html").read_text(
        encoding="utf-8"
    )

    for snippet in (
        "Crea un campione riproducibile da un giornale disordinato",
        "Journal Sampling",
        "Create a reproducible sample from a messy journal export",
        "Créer un échantillon reproductible depuis un journal désordonné",
        "Eine reproduzierbare Stichprobe aus einem uneinheitlichen Journal erstellen",
        "Sample selection you can replay",
        "Campione riproducibile e controllabile",
        "Create the sample from the work folder",
        "inspection.json",
        "suggested_recipe.json",
        "normalized_journal.csv",
        "sampling_audit.json",
        "/?lang=${safeLang}",
    ):
        assert snippet in page
    for stale_snippet in (
        "Gli script Python deterministici",
        "Deterministic Python scripts",
        "How it runs in Codex",
    ):
        assert stale_snippet not in page


def test_homepage_routes_accountant_plugins_through_vera() -> None:
    source = (ROOT / "modules" / "pdp" / "api.py").read_text(encoding="utf-8")

    assert source.count('"href": "/static/shared/vera/index.html"') == 4
    assert source.count('"label": "Vera"') == 4
    assert source.count('"tooltip_key": "vera"') == 4
    for direct_workflow_link in (
        '"href": "/static/shared/audit-reconciliation/index.html"',
        '"href": "/static/shared/report-builder/index.html"',
        '"href": "/static/shared/new-client/index.html"',
        '"href": "/static/shared/new-client/uk.html"',
        '"href": "/static/shared/new-client/geneva.html"',
        '"href": "/static/shared/new-client/zurich.html"',
        '"href": "/static/shared/research/index.html"',
        '"href": "/static/shared/journal-sampling/index.html"',
        '"href": "/static/shared/check-entries/index.html"',
        '"href": "/static/shared/journal-bank-reconciliation/index.html"',
        '"href": "/static/shared/riconciliazione-partite/index.html"',
        '"href": "/static/shared/concordato-plan-review/index.html"',
    ):
        assert direct_workflow_link not in source


def test_prompt_optimizer_page_matches_plugin_site_pattern() -> None:
    page = (ROOT / "static" / "shared" / "prompt-optimizer" / "index.html").read_text(
        encoding="utf-8"
    )

    for snippet in (
        "Optimize Prompt",
        "Ottimizza prompt",
        "Optimiser le prompt",
        "Prompt optimieren",
        "Un brief che Deep Research può seguire e tu puoi controllare.",
        "Fornisci",
        "Vera prepara",
        "Ricevi",
        "Come viene preparato",
        "Da un quesito disordinato a una ricerca controllabile.",
        "Un solo prompt per iniziare.",
        "Un passaggio dentro un percorso più lungo.",
        "question_inventory.json",
        "prompt_recipe.json",
        "optimized_prompt.md",
        "prompt_audit.json",
        "prompt_package.md",
        "source_domains.txt",
        "source_domains_comma.txt",
        "README_HUMAN.md",
        ACCOUNTING_BUNDLE_LINK,
        "/?lang=${safeLang}",
    ):
        assert snippet in page


def test_new_client_keeps_language_and_market_selection_separate() -> None:
    page = (ROOT / "static" / "shared" / "new-client" / "index.html").read_text(
        encoding="utf-8"
    )
    market_links = {
        "italy": (
            "index.html?lang=it#italy",
            'localizedHref("index.html", lang, "#italy")',
        ),
        "geneva": ("geneva.html?lang=it", 'localizedHref("geneva.html", lang)'),
        "zurich": ("zurich.html?lang=it", 'localizedHref("zurich.html", lang)'),
        "uk": ("uk.html?lang=it", 'localizedHref("uk.html", lang)'),
    }

    for language in ("it", "en", "fr", "de"):
        assert f'data-lang="{language}"' in page
    assert "return `${path}?lang=${lang}${fragment}`;" in page
    for market, (initial_href, localized_call) in market_links.items():
        assert f'id="market-{market}-link" href="{initial_href}"' in page
        assert (
            f'document.getElementById("market-{market}-link").href = '
            f"{localized_call};"
        ) in page
    assert 'setLanguage(params.get("lang") || "it", false)' in page
    assert "window.location.replace" not in page


def test_vera_page_groups_core_workflows_and_italy_specializations() -> None:
    page = (ROOT / "static" / "shared" / "vera" / "index.html").read_text(
        encoding="utf-8"
    )
    core_start = page.index('id="core"')
    core_end = page.index("</section>", core_start)
    italy_start = page.index('id="italia"')
    italy_end = page.index("</section>", italy_start)
    core = page[core_start:core_end]
    italy = page[italy_start:italy_end]

    for module_link in (
        "../new-client/index.html#journey",
        "../journal-sampling/index.html",
        "../check-entries/index.html#journey",
        "../journal-bank-reconciliation/index.html",
        "../riconciliazione-partite/index.html",
        "../report-builder/index.html",
        "../prompt-optimizer/index.html",
        "../deep-research-validator/index.html",
    ):
        assert f'href="{module_link}"' in core
    for module_link in (
        "../check-entries/index.html#italy-adapter",
        "../report-builder/index.html#italy-preset",
        "../concordato-plan-review/index.html",
        "../previdenza-inps/index.html",
        "../registro-imprese-sari/index.html",
    ):
        assert f'href="{module_link}"' in italy
    assert core.count(" data-module-link") == 8
    assert core.count('class="module-row"') == 8
    assert italy.count(" data-module-link") == 5
    assert italy.count('class="module-row"') == 5
    assert core.count('<article class="workstream">') == 3
    assert 'id="modello"' in page
    assert 'id="core"' in page
    assert 'id="italia"' in page
    assert 'id="video"' in page
    assert 'id="installa"' in page
    assert "Core multilingue + pacchetto Italia" in page
    assert "Cambia la lingua del lavoro, non la giurisdizione applicata" in page
    assert "FatturaPA" not in core
    assert "FatturaPA" in italy
    assert 'src="../video-library.js?v=2026072002"' in page
    assert 'window.MparanzaVideos.getCatalog("vera", lang)' in page
    assert (
        "https://chatgpt.com/auth/login?next=%2Fplugins%2Fplugins_6a57ac5ce65c8191ae7bd0a51160eb7d"
        in page
    )
    assert "data-vera-install-link" in page
    for stale_snippet in (
        "/downloads/vera",
        "data-download-link",
        "data-free-download-link",
        "manual ZIP",
        "ZIP manuale",
        "ZIP manuel",
        "manuelle ZIP",
    ):
        assert stale_snippet not in page


def test_vera_page_localizes_every_module_title() -> None:
    page = (ROOT / "static" / "shared" / "vera" / "index.html").read_text(
        encoding="utf-8"
    )

    title_keys = (
        "module.newClient.title",
        "module.sampling.title",
        "module.entries.title",
        "module.bank.title",
        "module.reconciliation.title",
        "module.report.title",
        "module.prompt.title",
        "module.research.title",
        "module.entriesItaly.title",
        "module.reportItaly.title",
        "module.concordato.title",
        "module.previdenza.title",
        "module.registro.title",
    )
    for title_key in title_keys:
        assert page.count(f'data-i18n="{title_key}"') == 1
        assert page.count(f'"{title_key}":') == 4

    visible_copy_keys = set(re.findall(r'data-i18n(?:-aria-label)?="([^"]+)"', page))
    for copy_key in visible_copy_keys:
        assert page.count(f'"{copy_key}":') == 4, copy_key

    for untranslated_italian_copy in (
        "matching rivedibile",
        "workpaper Excel",
        "Tie-out numerico",
        "fiscali e compliance",
        "pacchetto corretto",
    ):
        assert untranslated_italian_copy not in page


def test_unlinked_family_explainer_pages_are_removed() -> None:
    for page_path in (
        ROOT / "static" / "shared" / "audit-reconciliation" / "index.html",
        ROOT / "static" / "shared" / "reporting" / "index.html",
        ROOT / "static" / "shared" / "research" / "index.html",
    ):
        assert not page_path.exists()


def test_deep_research_validator_page_matches_plugin_site_pattern() -> None:
    page = (
        ROOT / "static" / "shared" / "deep-research-validator" / "index.html"
    ).read_text(encoding="utf-8")

    for snippet in (
        "Validate Deep Research",
        "Valida Deep Research",
        "Valider Deep Research",
        "Deep Research validieren",
        "Use it when",
        "Quando usarlo",
        "Review by material claim",
        "Revisione per affermazioni",
        "Select claims",
        "Sceglie le affermazioni",
        "Check sources",
        "Controlla le fonti",
        "Sapere quali conclusioni reggono, prima di usarle.",
        "Fornisci",
        "Vera prepara",
        "Ricevi",
        "Un solo prompt per iniziare.",
        "La validazione chiude il circuito della ricerca.",
        "document_inventory.json",
        "source_inventory.json",
        "claims_review.json",
        "validation_audit.json",
        "validated_document.md",
        "validation_package.md",
        ACCOUNTING_BUNDLE_LINK,
        "/?lang=${lang}",
    ):
        assert snippet in page


def test_previdenza_inps_page_explains_the_reviewable_case_journey() -> None:
    page = (ROOT / "static" / "shared" / "previdenza-inps" / "index.html").read_text(
        encoding="utf-8"
    )

    for snippet in (
        "Previdenza INPS",
        "INPS Social Security Review",
        "Revue de prévoyance INPS",
        "INPS-Sozialversicherung prüfen",
        "Porta un caso INPS disperso a un fascicolo pronto da rivedere.",
        "Fornisci",
        "Vera prepara",
        "Ricevi",
        "Cronologia del caso",
        "Matrice delle evidenze",
        "Dal fascicolo approvato alla relazione Word.",
        "case_records_validated.json",
        "evidence_matrix.csv",
        "studio_memo.docx",
        ACCOUNTING_BUNDLE_LINK,
        'href="../report-builder/index.html?lang=it"',
    ):
        assert snippet in page


def test_registro_imprese_sari_page_explains_the_practice_plan_journey() -> None:
    page = (
        ROOT / "static" / "shared" / "registro-imprese-sari" / "index.html"
    ).read_text(encoding="utf-8")

    for snippet in (
        "Registro Imprese e SARI",
        "Business Register and SARI",
        "Registre des entreprises et SARI",
        "Unternehmensregister und SARI",
        "Porta una richiesta camerale a un piano di pratica chiaro e citato.",
        "Fornisci",
        "Vera prepara",
        "Ricevi",
        "Piano della pratica",
        "Checklist DIRE",
        "Registro delle fonti",
        "practice_plan_validated.json",
        "dire_practice_plan.json",
        "review_handoff.md",
        ACCOUNTING_BUNDLE_LINK,
        'href="../prompt-optimizer/index.html?lang=it"',
    ):
        assert snippet in page


def test_homepage_routes_deep_research_validator_through_vera() -> None:
    source = (ROOT / "modules" / "pdp" / "api.py").read_text(encoding="utf-8")
    page = (ROOT / "static" / "shared" / "vera" / "index.html").read_text(
        encoding="utf-8"
    )

    assert '"href": "/static/shared/deep-research-validator/index.html"' not in source
    assert "../deep-research-validator/index.html" in page
    assert "Validate Deep Research" in page


def test_check_entries_page_matches_plugin_site_pattern() -> None:
    page = (ROOT / "static" / "shared" / "check-entries" / "index.html").read_text(
        encoding="utf-8"
    )

    for snippet in (
        "Check Entries",
        "Collega ogni scrittura campionata al supporto disponibile.",
        "Connect every sampled entry to its available support.",
        "Reliez chaque écriture échantillonnée à son justificatif disponible.",
        "Verbinden Sie jede Stichprobenbuchung mit dem verfügbaren Beleg.",
        "Cosa dai / cosa ottieni",
        "Entry checks tied to documents",
        "Controlli con supporto collegato",
        "Start broad, finish with targeted requests",
        "ZIP FatturaPA",
        "Authorized connection",
        "Targeted PDFs",
        "normalized_entries.csv",
        "invoice_inventory.json",
        "pdf_inventory.json",
        "check_results.csv",
        "check_audit.json",
        ACCOUNTING_BUNDLE_LINK,
        "/?lang=${safeLang}",
    ):
        assert snippet in page
    for stale_snippet in (
        "Deterministic Python scripts",
        "Gli script Python deterministici",
        "How it runs in Codex",
    ):
        assert stale_snippet not in page


def test_homepage_routes_check_entries_through_vera() -> None:
    source = (ROOT / "modules" / "pdp" / "api.py").read_text(encoding="utf-8")
    page = (ROOT / "static" / "shared" / "vera" / "index.html").read_text(
        encoding="utf-8"
    )

    assert '"href": "/static/shared/check-entries/index.html"' not in source
    assert "Verifica registrazioni" not in source
    assert "../check-entries/index.html" in page


def test_journal_bank_reconciliation_page_matches_plugin_site_pattern() -> None:
    page = (
        ROOT / "static" / "shared" / "journal-bank-reconciliation" / "index.html"
    ).read_text(encoding="utf-8")

    for snippet in (
        "Riconciliazione banca-contabilità",
        "Porta banca e contabilità in una riconciliazione con eccezioni visibili.",
        "Bring bank and accounting into one reconciliation with visible exceptions.",
        "Réunissez banque et comptabilité dans un rapprochement aux exceptions visibles.",
        "Führen Sie Bank und Buchhaltung in einer Abstimmung mit sichtbaren Ausnahmen zusammen.",
        "Cosa dai / cosa ottieni",
        "Prompt pronti",
        "Ready prompts",
        "Complete reconciliation",
        "Con campione movimenti",
        "Avec seuils explicites",
        "Mit festen Schwellen",
        "Matches and exceptions stay separate",
        "Abbinamenti ed eccezioni restano separati",
        "Keep thresholds explicit",
        "normalized_bank.csv",
        "normalized_journal.csv",
        "reconciliation_matches.csv",
        "unmatched_bank.csv",
        "unmatched_journal.csv",
        "reconciliation_audit.json",
        ACCOUNTING_BUNDLE_LINK,
        "/?lang=${safeLang}",
    ):
        assert snippet in page
    for stale_snippet in (
        "Deterministic Python scripts",
        "Codex handles changing customer formats",
        "Reviewable reconciliation, guided in Codex",
    ):
        assert stale_snippet not in page


def test_homepage_routes_journal_bank_reconciliation_through_vera() -> None:
    source = (ROOT / "modules" / "pdp" / "api.py").read_text(encoding="utf-8")
    page = (ROOT / "static" / "shared" / "vera" / "index.html").read_text(
        encoding="utf-8"
    )

    assert (
        '"href": "/static/shared/journal-bank-reconciliation/index.html"' not in source
    )
    assert "../journal-bank-reconciliation/index.html" in page


def test_report_builder_page_matches_plugin_site_pattern() -> None:
    page = (ROOT / "static" / "shared" / "report-builder" / "index.html").read_text(
        encoding="utf-8"
    )

    for snippet in (
        "Build report",
        "Turn source tables into a reviewable Word report.",
        "Da tabelle sorgente a un report Word rivedibile.",
        "Transformer les tableaux source en rapport Word révisable.",
        "Quelltabellen in einen prüfbaren Word-Bericht verwandeln.",
        "Ready prompts",
        "Prompt pronti",
        "Build a DOCX draft from spreadsheets, CSVs and readable PDFs.",
        "Prepara una bozza DOCX da Excel, CSV e PDF leggibili.",
        "Find tables",
        "Assign sections",
        "Draft report",
        "Open report.docx first",
        "Complete management report",
        "Relazione ente locale",
        "Annual financial statement",
        "inspection.json",
        "suggested_recipe.json",
        "report_tables.json",
        "report_analysis.json",
        "report_draft.md",
        "report.docx",
        "report_audit.json",
        ACCOUNTING_BUNDLE_LINK,
        "/?lang=${safeLang}",
    ):
        assert snippet in page


@pytest.mark.parametrize(
    ("relative_path", "title_assignment"),
    (
        (
            "vera/index.html",
            'document.title = strings["meta.title"]',
        ),
        (
            "report-builder/index.html",
            'document.title = `${copy[safeLang]["hero.title"]} | Vera`',
        ),
        (
            "concordato-plan-review/index.html",
            "document.title = `${t.hero.title} | Vera`",
        ),
    ),
)
def test_vera_pages_set_browser_title_from_active_locale(
    relative_path: str, title_assignment: str
) -> None:
    page = (ROOT / "static" / "shared" / relative_path).read_text(encoding="utf-8")

    assert title_assignment in page


def test_clara_page_matches_plugin_site_pattern() -> None:
    page = (ROOT / "static" / "shared" / "clara" / "index.html").read_text(
        encoding="utf-8"
    )
    styles = (ROOT / "static" / "shared" / "clara" / "clara-page.css").read_text(
        encoding="utf-8"
    )

    for snippet in (
        "Clara",
        "Clara prepares the work. The judgment remains yours.",
        "Clara prepara il lavoro. Il giudizio resta tuo.",
        "Create or correct a presentation in your corporate style",
        "Crea o correggi una presentazione nel tuo stile aziendale",
        "Choose the deck format",
        "Scegli il formato del deck",
        "Open the project folder and describe what you need",
        "Apri la cartella del progetto e descrivi ciò che ti serve",
        "The project is not just a presentation",
        "Il progetto non è solo una presentazione",
        "Interviews, documents, and data analysis",
        "Interviste, documenti e analisi dati",
        "Conduct an interview with a dedicated link",
        "Conduci un'intervista con un link dedicato",
        "Transcribe a meeting or recording",
        "Trascrivi una riunione o una registrazione",
        "From sources to a document for review",
        "Dalle fonti al documento da rivedere",
        "From data to a clear answer",
        "Dai dati a una risposta chiara",
        "images and reports stay on your computer",
        "immagini e report restano sul tuo computer",
        "no API key is required",
        "non serve una chiave API",
        "Install Clara and open your first project",
        "Installa Clara e apri il primo progetto",
        "You can find Clara in the OpenAI Marketplace.",
        "La trovi nel Marketplace di OpenAI.",
        "Install Clara",
        "Installa Clara",
        "https://chatgpt.com/auth/login?next=%2Fplugins%2Fplugins_6a57b17fb5848191be710192d93fe03a",
        "data-clara-install-link",
        "/?lang=${safeLang}",
    ):
        assert snippet in page
    for stale_snippet in (
        "Advisor Case Workspace",
        "A local Codex workspace for case materials, voice notes, judgement and reviewed outputs.",
        "Un workspace Codex locale per materiali, voce, judgement e output rivisti.",
        "Collaboration without a shared database",
        "Collaborazione senza database condiviso",
        "Fabio",
        "quando Clara non basta",
        "Client-pack inclusion gate",
        "Pending consultant judgement is never silently promoted",
        "Download Pro ZIP",
        "data-reporting-download-link",
        "data-pro-download-link",
        "data-clara-download-link",
        "/downloads/clara",
        "Download ZIP",
        "Scarica lo ZIP",
        "Télécharger le ZIP",
        "ZIP herunterladen",
        "manual fallback",
        "alternativa manuale",
        "Pro Plugin Pack",
        "/downloads/accounting-plugin-pack/pro",
        'href="downloads/clara-plugin.zip',
        "font-size: clamp",
        "Download not authorized",
        "Download non autorizzato",
        "Turn your sources into client-ready deliverables.",
        "Trasforma le tue fonti in deliverable pronti per il cliente.",
        "Create, revise, or follow an existing style",
        "Crea, correggi o segui uno stile esistente",
        "Choose the final format",
        "Scegli il formato finale",
        "Start with a folder and a normal request",
        "Parti da una cartella e da una richiesta normale",
        "When the project is more than a presentation",
        "Other Clara workflows",
        "Altri flussi di Clara",
        "Install the published Clara release",
        "Installa la versione pubblicata di Clara",
    ):
        assert stale_snippet not in page
    assert (
        '<a class="button" href="https://chatgpt.com/auth/login?next=%2Fplugins%2F'
        'plugins_6a57b17fb5848191be710192d93fe03a" target="_blank" '
        'rel="noopener noreferrer" data-clara-install-link '
        'data-i18n="install.open">Install Clara</a>'
    ) in page
    assert "font-size: clamp(58px, 8vw, 92px)" in styles
    assert "font-size: clamp(30px, 4vw, 43px)" in styles
    assert "font-size: clamp(21px, 2.4vw, 27px)" in styles


def test_clara_public_page_browser_title_is_clara() -> None:
    page = (ROOT / "static" / "shared" / "clara" / "index.html").read_text(
        encoding="utf-8"
    )

    assert "<title>Clara</title>" in page
    assert page.count('title: "Clara"') == 4
    assert "Clara | Mparanza" not in page


def test_clara_public_page_routes_presentation_video_by_language() -> None:
    page = (ROOT / "static" / "shared" / "clara" / "index.html").read_text(
        encoding="utf-8"
    )

    for language, video_id in {
        "en": "3zvFm3fGdQ8",
        "it": "mU-QhOp7EOk",
        "fr": "Qe8rbIh8fhg",
        "de": "BPp_fcfYRS8",
    }.items():
        assert f'{language}: {{ id: "{video_id}"' in page
    assert 'id="presentation-video-thumbnail"' in page
    assert 'id="presentation-video-duration"' in page


def test_clara_public_page_keeps_copy_corrections_in_every_locale() -> None:
    page = (ROOT / "static" / "shared" / "clara" / "index.html").read_text(
        encoding="utf-8"
    )

    for text in (
        "Create or correct high-impact HTML decks and PowerPoint presentations.",
        "Crea e correggi deck HTML di impatto e presentazioni PowerPoint.",
        "Créez ou corrigez des decks HTML percutants et des présentations PowerPoint.",
        "Erstellen oder korrigieren Sie wirkungsvolle HTML-Decks und PowerPoint-Präsentationen.",
        "Analyze Excel, CSV, and Parquet files with checked calculations and charts chosen to fit the question.",
        "Analizza file Excel, CSV e Parquet con calcoli controllati e grafici scelti in base alla domanda.",
        "Analysez des fichiers Excel, CSV et Parquet avec des calculs vérifiés et des graphiques choisis en fonction de la question.",
        "Analysieren Sie Excel-, CSV- und Parquet-Dateien mit geprüften Berechnungen und Diagrammen, die zur Fragestellung passen.",
        "Start with an Excel, CSV, or Parquet file and describe the business question.",
        "Parti da un file Excel, CSV o Parquet e descrivi la domanda di business.",
        "Partez d'un fichier Excel, CSV ou Parquet et décrivez votre question métier.",
        "Beginnen Sie mit einer Excel-, CSV- oder Parquet-Datei und beschreiben Sie die geschäftliche Fragestellung.",
        "Choose the deck format",
        "Scegli il formato del deck",
        "Choisissez le format du deck",
        "Wählen Sie das Deck-Format",
        "choose an HTML deck for interactivity, navigation, and animations.",
        "scegli un deck HTML quando vuoi interattività, navigazione e animazioni.",
        "choisissez un deck HTML pour l'interactivité, la navigation et les animations.",
        "wählen Sie ein HTML-Deck für Interaktivität, Navigation und Animationen.",
        "The project is not just a presentation",
        "Il progetto non è solo una presentazione",
        "Le projet n'est pas seulement une présentation",
        "Das Projekt ist nicht nur eine Präsentation",
    ):
        assert text in page

    for key in (
        "meta.description",
        "aria.page_navigation",
        "aria.language",
        "aria.promise_strip",
        "formats.html.title.link",
        "retail.retailer_signals.copy.link",
        "retail.brand_fit.copy.link",
    ):
        assert page.count(f'"{key}"') == 5

    for stale_text in (
        "browser presentations",
        "Start with a folder and a normal request",
        "Parti da una cartella e da una richiesta normale",
        "Retailer Signals and Brand Fit are available now",
        "PowerPoint PPTX",
        "Formato HTML",
        "navigation, speaker notes, and animations.",
        "navigazione, note per chi presenta e animazioni.",
        "navigation, les notes de présentation et les animations.",
        "Navigation, Sprechernotizen und Animationen.",
        '"retail.retailer_signals.kicker"',
        '"retail.brand_fit.kicker"',
        'href="#workflow" class="button',
    ):
        assert stale_text not in page

    assert (
        '<a href="/static/shared/4c8e62f349a776e9d2b0ca48f15796b72cb8d4e5a1cf0937a2e84bfc63dd52a9/'
        'index.html#cover" target="_blank" rel="noopener noreferrer" '
        'data-i18n="formats.html.title.link">interactive</a>'
    ) in page


def test_homepage_routes_report_builder_through_vera() -> None:
    source = (ROOT / "modules" / "pdp" / "api.py").read_text(encoding="utf-8")
    page = (ROOT / "static" / "shared" / "vera" / "index.html").read_text(
        encoding="utf-8"
    )

    assert '"href": "/static/shared/report-builder/index.html"' not in source
    assert "../report-builder/index.html" in page


def test_concordato_plan_review_page_matches_plugin_site_pattern() -> None:
    page = (
        ROOT / "static" / "shared" / "concordato-plan-review" / "index.html"
    ).read_text(encoding="utf-8")

    for snippet in (
        "Revisione numeri di piano",
        "Concordato Plan Review",
        "Contrôler les chiffres du plan avant la position du réviseur.",
        "Planzahlen prüfen, bevor der Prüfer Stellung nimmt.",
        "Prompt pronti",
        "Ready prompts",
        "Controlla i numeri del piano",
        "Check plan numbers before the reviewer takes a position.",
        "schede rettificate",
        "adjusted schedules",
        "Tableaux ajustés",
        "Angepasste Aufstellungen",
        "Il ponte mostra cosa torna",
        "The bridge shows what ties",
        "How to set up the review",
        "inventory.json",
        "amount_candidates.csv",
        "exact_amount_matches.csv",
        "concordato_tie_out_workpaper.xlsx",
        "concordato_review_summary.docx",
        "run_audit.json",
        "codex_run_review.md",
        ACCOUNTING_BUNDLE_LINK,
        'data-journey="cta.open"',
        "/?lang=${safeLang}",
    ):
        assert snippet in page
    for stale_snippet in (
        "Deterministic Python scripts",
        "Codex reviews the bridge",
        "Codex rivede il ponte",
        "DB ajustée",
        "angepasste DB",
        "adjusted DB",
    ):
        assert stale_snippet not in page


def test_homepage_routes_concordato_plan_review_through_vera() -> None:
    source = (ROOT / "modules" / "pdp" / "api.py").read_text(encoding="utf-8")
    page = (ROOT / "static" / "shared" / "vera" / "index.html").read_text(
        encoding="utf-8"
    )

    assert '"href": "/static/shared/concordato-plan-review/index.html"' not in source
    assert "../concordato-plan-review/index.html" in page


def test_old_plotting_plugin_pages_are_removed() -> None:
    for page_path in (
        ROOT / "static" / "shared" / "mix-contribution-analysis" / "index.html",
        ROOT / "static" / "shared" / "period-comparison" / "index.html",
        ROOT / "static" / "shared" / "scatter-bubble-analysis" / "index.html",
        ROOT / "static" / "shared" / "variance-analysis" / "index.html",
        ROOT / "static" / "shared" / "distribution-analysis" / "index.html",
        ROOT / "static" / "shared" / "set-overlap-analysis" / "index.html",
        ROOT / "static" / "shared" / "funnel-analysis" / "index.html",
        ROOT / "static" / "shared" / "statement-analysis" / "index.html",
        ROOT / "static" / "shared" / "pro-charting" / "index.html",
    ):
        assert not page_path.exists()


def test_reporting_component_manifests_use_clara_homepage() -> None:
    for plugin_name in REPORTING_ENGINE_PLUGIN_NAMES:
        manifest = json.loads(
            (
                ROOT / "plugins" / plugin_name / ".codex-plugin" / "plugin.json"
            ).read_text(encoding="utf-8")
        )
        assert manifest["homepage"] == (
            "https://mparanza.com/static/shared/clara/index.html"
        )


def test_standard_family_plugin_manifests_use_family_homepages() -> None:
    expected_homepages = {
        "audit-reconciliation": (
            "https://mparanza.com/static/shared/riconciliazione-partite/index.html"
        ),
        "check-entries": (
            "https://mparanza.com/static/shared/check-entries/index.html"
        ),
        "client-file-preparation": (
            "https://mparanza.com/static/shared/new-client/index.html#file-preparation"
        ),
        "new-client": ("https://mparanza.com/static/shared/new-client/index.html"),
        "concordato-plan-review": (
            "https://mparanza.com/static/shared/concordato-plan-review/index.html"
        ),
        "journal-bank-reconciliation": (
            "https://mparanza.com/static/shared/journal-bank-reconciliation/index.html"
        ),
        "journal-sampling": (
            "https://mparanza.com/static/shared/journal-sampling/index.html"
        ),
        "deep-research-validator": (
            "https://mparanza.com/static/shared/deep-research-validator/index.html"
        ),
        "prompt-optimizer": (
            "https://mparanza.com/static/shared/prompt-optimizer/index.html"
        ),
        "previdenza-inps": (
            "https://mparanza.com/static/shared/previdenza-inps/index.html"
        ),
        "registro-imprese-sari": (
            "https://mparanza.com/static/shared/registro-imprese-sari/index.html"
        ),
        "report-builder": (
            "https://mparanza.com/static/shared/report-builder/index.html"
        ),
        "vera": ("https://mparanza.com/static/shared/vera/index.html"),
        "clara": ("https://mparanza.com/static/shared/clara/index.html"),
    }

    assert set(expected_homepages) | REPORTING_ENGINE_PLUGIN_NAMES == (
        WORKFLOW_PLUGIN_NAMES | {"vera"}
    )
    for plugin_name, expected_homepage in expected_homepages.items():
        manifest = json.loads(
            (
                ROOT / "plugins" / plugin_name / ".codex-plugin" / "plugin.json"
            ).read_text(encoding="utf-8")
        )

        assert manifest["homepage"] == expected_homepage


def test_vera_public_icon_matches_plugin_source() -> None:
    assert (ROOT / "static" / "shared" / "vera" / "icon.svg").read_bytes() == (
        ROOT / "plugins" / "vera" / "assets" / "icon.svg"
    ).read_bytes()


def test_clara_public_icon_matches_plugin_source() -> None:
    assert (ROOT / "static" / "shared" / "clara" / "icon.svg").read_bytes() == (
        ROOT / "plugins" / "clara" / "assets" / "icon.svg"
    ).read_bytes()


@pytest.mark.parametrize(
    ("page_name", "style_path", "expected_home_link"),
    (
        (
            "vera",
            "static/shared/vera/index.html",
            '<a class="brand" href="/?lang=it" data-home-link aria-label="Mparanza">',
        ),
        (
            "clara",
            "static/shared/clara/clara-page.css",
            '<a class="brand" href="/" aria-label="Mparanza">',
        ),
    ),
)
def test_companion_header_home_link_uses_mparanza_logo(
    page_name: str, style_path: str, expected_home_link: str
) -> None:
    page = (ROOT / "static" / "shared" / page_name / "index.html").read_text(
        encoding="utf-8"
    )
    header = page.split('<header class="topbar">', maxsplit=1)[1].split(
        "</header>", maxsplit=1
    )[0]

    assert expected_home_link in header
    assert (
        '<img src="https://mparanza.com/images/MPARANZA-HORIZONTAL.png" '
        'alt="Mparanza">' in header
    )
    assert 'src="icon.svg"' not in header
    styles = (ROOT / style_path).read_text(encoding="utf-8")
    assert "width: auto; height: 34px;" in styles


def test_clara_public_page_uses_vera_visual_system() -> None:
    page = (ROOT / "static" / "shared" / "clara" / "index.html").read_text(
        encoding="utf-8"
    )
    stylesheet = (ROOT / "static" / "shared" / "clara" / "clara-page.css").read_text(
        encoding="utf-8"
    )

    assert 'href="clara-page.css?v=' in page
    assert 'src="icon.svg"' in page
    assert 'class="promise-strip"' in page
    for color in ("#002060", "#0070C0", "#00B0F0", "#FFFFFF"):
        assert color in stylesheet
    for black in ("#000000", "#171816"):
        assert black not in stylesheet


def test_vera_public_page_uses_deck_blue_palette_without_black() -> None:
    page = (ROOT / "static" / "shared" / "vera" / "index.html").read_text(
        encoding="utf-8"
    )

    for color in ("#002060", "#0070C0", "#00B0F0", "#FFFFFF"):
        assert color in page
    for black in ("#000000", "#000", "#171816"):
        assert black not in page


@pytest.mark.parametrize(
    ("companion", "install_attribute"),
    (
        ("clara", "data-clara-install-link"),
        ("vera", "data-vera-install-link"),
    ),
)
def test_companion_overview_video_follows_the_intended_product_story(
    companion: str, install_attribute: str
) -> None:
    page = (ROOT / "static" / "shared" / companion / "index.html").read_text(
        encoding="utf-8"
    )
    if companion == "vera":
        assert page.index('id="core"') < page.index('id="italia"')
        assert page.index('id="italia"') < page.index('id="video"')
        assert page.index('id="video"') < page.index('id="installa"')
        assert page.count('class="overview-video"') == 1
        return

    hero_start = page.index('<section class="hero">')
    hero_end = page.index("</section>", hero_start)
    hero = page[hero_start:hero_end]
    assert hero.index(install_attribute) < hero.index('class="video-story"')
    assert page.count('class="video-story"') == 1


def test_homepage_only_links_clara_for_consultants_in_all_locales() -> None:
    source = (ROOT / "modules" / "pdp" / "api.py").read_text(encoding="utf-8")

    assert '"href": "/static/shared/reporting/index.html"' not in source
    assert "/static/shared/pro-charting/index.html" not in source
    assert source.count('"href": "/static/shared/clara/index.html"') == 4
    assert '"href": "/static/shared/variance-analysis/index.html"' not in source
    assert '"href": "/static/shared/period-comparison/index.html"' not in source
    assert '"href": "/static/shared/mix-contribution-analysis/index.html"' not in source
    assert '"href": "/static/shared/scatter-bubble-analysis/index.html"' not in source
    assert '"href": "/static/shared/distribution-analysis/index.html"' not in source
    assert "pro_charting_plugin" not in source
    assert '"label": "Reporting"' not in source
    assert source.count('"label": "Clara"') == 4


@pytest.mark.parametrize("lang", ("en", "it", "fr", "de"))
def test_homepage_content_exposes_clara_without_reporting_or_pro_badges(
    lang: str,
) -> None:
    _restore_application_import_path()

    from modules.pdp import api as pdp_api

    content = pdp_api._get_landing_page_content(lang)
    consultant_links = content["sections"][0]["groups"][1]["links"]

    assert consultant_links == [
        {
            "label": "Clara",
            "href": "/static/shared/clara/index.html",
            "active": True,
            "tooltip_key": "clara_plugin",
            "public": True,
        }
    ]


@pytest.mark.parametrize(
    ("lang", "expected_lead"),
    (
        ("en", "A Codex plugin for presentations and ongoing project work."),
        (
            "it",
            "Un plugin Codex per creare presentazioni e dare continuità "
            "al lavoro sui progetti.",
        ),
        (
            "fr",
            "Un plugin Codex pour créer des présentations et poursuivre "
            "le travail sur les projets dans la durée.",
        ),
        (
            "de",
            "Ein Codex-Plugin für Präsentationen und die fortlaufende "
            "Arbeit an Projekten.",
        ),
    ),
)
def test_homepage_clara_lead_localizes_ongoing_project_work(
    lang: str,
    expected_lead: str,
) -> None:
    _restore_application_import_path()

    from modules.pdp import api as pdp_api

    clara = pdp_api._get_landing_page_content(lang)["sections"][0]["groups"][1]

    assert clara["id"] == "clara"
    assert clara["lead"] == expected_lead


@pytest.mark.parametrize(
    (
        "lang",
        "expected_group_titles",
        "expected_audiences",
        "removed_section_titles",
    ),
    (
        (
            "en",
            ("Codex for accountants", "Codex for consultants"),
            ("For accountants", "For consultants"),
            ("Attribute Analysis", "Deck Toolkit"),
        ),
        (
            "it",
            ("Codex per commercialisti", "Codex per consulenti"),
            ("Per commercialisti", "Per consulenti"),
            ("Analisi attributi", "Toolkit presentazioni"),
        ),
        (
            "fr",
            (
                "Codex pour les experts-comptables",
                "Codex pour les consultants",
            ),
            ("Pour les experts-comptables", "Pour les consultants"),
            ("Analyse des attributs", "Toolkit deck"),
        ),
        (
            "de",
            (
                "Codex für Steuerberaterinnen und Steuerberater",
                "Codex für Beraterinnen und Berater",
            ),
            (
                "Für Steuerberaterinnen und Steuerberater",
                "Für Beraterinnen und Berater",
            ),
            ("Attributanalyse", "Deck-Toolkit"),
        ),
    ),
)
def test_homepage_only_exposes_codex_role_groups(
    lang: str,
    expected_group_titles: tuple[str, str],
    expected_audiences: tuple[str, str],
    removed_section_titles: tuple[str, str],
) -> None:
    _restore_application_import_path()

    from modules.pdp import api as pdp_api

    content = pdp_api._get_landing_page_content(lang)
    sections = content["sections"]
    serialized_sections = json.dumps(sections, ensure_ascii=False)

    assert len(sections) == 1
    assert sections[0]["preserve_order"] is True
    assert sections[0]["groups"][0]["title"] == expected_group_titles[0]
    assert sections[0]["groups"][1]["title"] == expected_group_titles[1]
    assert sections[0]["groups"][0]["audience"] == expected_audiences[0]
    assert sections[0]["groups"][1]["audience"] == expected_audiences[1]
    assert sections[0]["groups"][0]["links"][0]["href"] == (
        "/static/shared/vera/index.html"
    )
    assert sections[0]["groups"][1]["links"][0]["href"] == (
        "/static/shared/clara/index.html"
    )
    assert removed_section_titles[0] not in serialized_sections
    assert removed_section_titles[1] not in serialized_sections
    assert "/review/reports/page" not in serialized_sections
    assert "/review/brand-reports/page" not in serialized_sections
    assert "/review/product-hypotheses/page" not in serialized_sections
    assert "/slides/page" not in serialized_sections
    assert "/presentations/page" not in serialized_sections


def test_homepage_plugin_links_are_ordered_by_group_and_locale() -> None:
    source = (ROOT / "modules" / "pdp" / "api.py").read_text(encoding="utf-8")

    expected_orders = (
        (
            '"title": "Codex for accountants"',
            ("Vera",),
        ),
        (
            '"title": "Codex for consultants"',
            ("Clara",),
        ),
        (
            '"title": "Codex per commercialisti"',
            ("Vera",),
        ),
        (
            '"title": "Codex per consulenti"',
            ("Clara",),
        ),
        (
            '"title": "Codex pour les experts-comptables"',
            ("Vera",),
        ),
        (
            '"title": "Codex pour les consultants"',
            ("Clara",),
        ),
        (
            '"title": "Codex für Steuerberaterinnen und Steuerberater"',
            ("Vera",),
        ),
        (
            '"title": "Codex für Beraterinnen und Berater"',
            ("Clara",),
        ),
    )

    for section_title, labels in expected_orders:
        start = source.index(section_title)
        positions = [source.index(label, start) for label in labels]
        assert positions == sorted(positions)


def test_vera_module_links_preserve_language_without_changing_market() -> None:
    page = (ROOT / "static" / "shared" / "vera" / "index.html").read_text(
        encoding="utf-8"
    )

    assert 'href="../new-client/index.html#journey" data-module-link' in page
    assert 'url.searchParams.set("lang", lang)' in page
    assert 'link.setAttribute("href", withLanguage' in page
    assert "window.location.replace" not in page


@pytest.mark.parametrize(
    ("page_name", "plugin_id", "install_marker"),
    (
        (
            "clara",
            "plugins_6a57b17fb5848191be710192d93fe03a",
            "data-clara-install-link",
        ),
        (
            "vera",
            "plugins_6a57ac5ce65c8191ae7bd0a51160eb7d",
            "data-vera-install-link",
        ),
    ),
)
def test_companion_install_flow_routes_login_to_same_listing(
    page_name: str, plugin_id: str, install_marker: str
) -> None:
    page = (ROOT / "static" / "shared" / page_name / "index.html").read_text(
        encoding="utf-8"
    )
    listing_url = f"https://chatgpt.com/plugins/{plugin_id}"
    login_url = f"https://chatgpt.com/auth/login?next=%2Fplugins%2F{plugin_id}"

    assert page.count(login_url) == 2
    assert listing_url not in page
    assert page.count(install_marker) == 2
    if page_name == "vera":
        assert 'data-i18n="hero.install"' in page
        assert 'data-i18n="install.button"' in page
        assert 'data-i18n="install.signed_out"' not in page
    else:
        assert 'data-i18n="install.open"' in page
        assert 'data-i18n="install.signed_out"' in page


@pytest.mark.parametrize(
    "localized_guidance",
    (
        "Not signed in? ChatGPT asks you to sign in, then opens Clara's listing.",
        "Non hai effettuato l'accesso? ChatGPT ti chiede di accedere e poi apre la pagina di Clara.",
        "Vous n'êtes pas connecté ? ChatGPT vous demande de vous connecter, puis ouvre la fiche de Clara.",
        "Noch nicht angemeldet? ChatGPT fordert Sie zur Anmeldung auf und öffnet danach Claras Eintrag.",
    ),
)
def test_clara_install_flow_localizes_logged_out_guidance(
    localized_guidance: str,
) -> None:
    page = (ROOT / "static" / "shared" / "clara" / "index.html").read_text(
        encoding="utf-8"
    )

    assert localized_guidance in page


def test_homepage_is_one_semantic_story_with_both_plugins() -> None:
    template = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "static" / "css" / "app.css").read_text(encoding="utf-8")

    narrative_markers = (
        'class="landing-opening"',
        'class="landing-harness"',
        'class="landing-open-source"',
        'class="landing-free"',
        'class="landing-security"',
        'class="landing-compliance"',
        'class="landing-bridge"',
        'class="landing-products"',
    )
    narrative_positions = [template.index(marker) for marker in narrative_markers]

    assert narrative_positions == sorted(narrative_positions)
    assert template.count("<h1") == 1
    assert 'id="main-content"' in template
    assert 'href="#{{ group.id }}"' in template
    assert 'id="{{ group.id }}"' in template
    assert "{{ group.lead }}" in template
    assert "{{ group.description }}" in template
    assert "group.responsibility" not in template
    assert "landing-grid--single" not in template
    assert "body.landing-body.landing-home" in css
    assert ".landing-home .landing-harness" in css
    assert ".landing-home .landing-open-source" in css
    design_heading_selector = (
        ".landing-home .landing-open-source h2,\n"
        ".landing-home .landing-free h2,\n"
        ".landing-home .landing-security h2,\n"
        ".landing-home .landing-compliance h2,\n"
        ".landing-home .landing-bridge h2 {"
    )
    design_heading_css = css.split(design_heading_selector, maxsplit=1)[1].split(
        "}", maxsplit=1
    )[0]
    assert "color: var(--landing-ink);" in design_heading_css
    principle_body_selector = (
        ".landing-home .landing-open-source__body > p,\n"
        ".landing-home .landing-free__body > p {"
    )
    principle_body_css = css.split(principle_body_selector, maxsplit=1)[1].split(
        "}", maxsplit=1
    )[0]
    assert "color: var(--landing-muted);" in principle_body_css
    assert "font-size: clamp(1.1rem, 1.65vw, 1.35rem);" in principle_body_css
    assert "line-height: 1.62;" in principle_body_css
    assert "letter-spacing: -0.02em;" in principle_body_css
    assert "harness.consequence" not in template
    assert "landing-harness__consequence" not in css
    assert ".landing-home .landing-bridge" in css
    assert "harness.eyebrow" not in template
    assert "bridge.eyebrow" not in template
    assert ".landing-home .landing-product" in css
    assert "@media (prefers-reduced-motion: reduce)" in css


@pytest.mark.parametrize(
    ("lang", "expected_title", "inspect_fragment"),
    (
        ("en", "Open by design.", "inspect"),
        ("it", "Aperti per scelta.", "esaminare"),
        ("fr", "Ouverts par conception.", "examiner"),
        ("de", "Offen konzipiert.", "prüfen"),
    ),
)
def test_homepage_makes_open_source_explicit(
    lang: str,
    expected_title: str,
    inspect_fragment: str,
) -> None:
    _restore_application_import_path()

    from modules.pdp import api as pdp_api

    open_source = pdp_api._get_landing_page_content(lang)["open_source"]

    assert open_source["title"] == expected_title
    assert inspect_fragment in open_source["description"].casefold()
    normalized_description = open_source["description"].casefold().replace("-", " ")
    assert "open source" in normalized_description
    assert open_source["links"][0]["href"].startswith("https://github.com/")
    assert open_source["links"][1]["href"].endswith("/LICENSE")


@pytest.mark.parametrize(
    ("lang", "expected_title", "expected_description"),
    (
        (
            "en",
            "Free by design.",
            "Vera and Clara are free to install and use. We welcome contributions "
            "to their development. Mparanza charges for consulting, implementation, "
            "and hosted services.",
        ),
        (
            "it",
            "Gratuiti per scelta.",
            "Vera e Clara si possono installare e usare gratuitamente. Accogliamo "
            "volentieri contributi al loro sviluppo. Mparanza offre a pagamento "
            "consulenza, implementazione e servizi hosted.",
        ),
        (
            "fr",
            "Gratuits par conception.",
            "Vera et Clara sont gratuites à installer et à utiliser. Nous accueillons "
            "volontiers les contributions à leur développement. Mparanza facture ses "
            "prestations de conseil et de mise en œuvre, ainsi que ses services "
            "hébergés.",
        ),
        (
            "de",
            "Kostenlos konzipiert.",
            "Vera und Clara können kostenlos installiert und genutzt werden. Wir "
            "freuen uns über Beiträge zu ihrer Weiterentwicklung. Mparanza berechnet "
            "Beratungs- und Implementierungsleistungen sowie gehostete Services.",
        ),
    ),
)
def test_homepage_makes_free_business_model_explicit(
    lang: str, expected_title: str, expected_description: str
) -> None:
    _restore_application_import_path()

    from modules.pdp import api as pdp_api

    free = pdp_api._get_landing_page_content(lang)["free"]

    assert free == {
        "id": "free",
        "title": expected_title,
        "description": expected_description,
    }


@pytest.mark.parametrize("lang", ("en", "it", "fr", "de"))
def test_homepage_sections_omit_redundant_eyebrows(lang: str) -> None:
    _restore_application_import_path()

    from modules.pdp import api as pdp_api

    content = pdp_api._get_landing_page_content(lang)

    assert "eyebrow" not in content["harness"]
    assert "eyebrow" not in content["bridge"]


def test_homepage_does_not_repeat_audience_labels_below_product_icons() -> None:
    template = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")

    identity_markup = template.split(
        '<div class="landing-product__identity">', maxsplit=1
    )[1].split("</div>", maxsplit=1)[0]

    assert "group.audience" not in identity_markup
    assert '<p class="landing-product__role">{{ group.title }}</p>' in template


def test_homepage_localizes_navigation_and_language_links() -> None:
    template = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")

    assert "copy.primary_navigation_label" in template
    assert "copy.language_selector_label" in template
    assert "copy.sign_out_button" not in template
    assert 'aria-label="{{ language_names[code] }}"' in template
    assert 'lang="{{ code }}"' in template
    assert 'hreflang="{{ code }}"' in template
    assert "data.detail" not in template


def test_homepage_tablet_header_reflows_before_mobile_breakpoint() -> None:
    css = (ROOT / "static" / "css" / "app.css").read_text(encoding="utf-8")

    tablet_start = css.index("@media (max-width: 980px)")
    mobile_start = css.index("@media (max-width: 700px)", tablet_start)
    tablet_css = css[tablet_start:mobile_start]

    assert ".landing-home .landing-header" in tablet_css
    assert "grid-template-columns: minmax(0, 1fr)" in tablet_css
    assert ".landing-home .landing-controls" in tablet_css
    assert "justify-content: space-between" in tablet_css


@pytest.mark.parametrize("lang", ("en", "it", "fr", "de"))
@pytest.mark.parametrize(
    ("group_index", "expected_group_id"), ((0, "vera"), (1, "clara"))
)
def test_homepage_content_explains_codex_harness_and_each_plugin(
    lang: str,
    group_index: int,
    expected_group_id: str,
) -> None:
    _restore_application_import_path()

    from modules.pdp import api as pdp_api

    content = pdp_api._get_landing_page_content(lang)
    groups = content["sections"][0]["groups"]
    group = groups[group_index]

    assert content["hero"]["headline"]
    assert content["hero"]["subheadline"]
    assert content["hero"]["plugins_label"]
    assert "primary_cta" not in content["hero"]
    assert "Codex" in content["hero"]["headline"]
    assert "Codex" in content["hero"]["subheadline"]
    assert content["harness"]["id"] == "codex"
    assert len(content["harness"]["layers"]) == 3
    assert "consequence" not in content["harness"]
    assert "consequence_label" not in content["harness"]
    assert content["bridge"]["id"] == "plugins"
    assert groups[0]["id"] == "vera"
    assert groups[1]["id"] == "clara"
    assert group["id"] == expected_group_id
    assert group["audience"]
    assert group["lead"]
    assert group["description"]
    assert "responsibility" not in group
    assert group["proof"]
    assert group["cta_label"]
    assert group["icon"].endswith(".svg")


@pytest.mark.parametrize(
    ("lang", "expected_opening", "expected_research", "rejected_fragment"),
    (
        (
            "en",
            "Vera works directly on the firm's files.",
            "tax and regulatory research",
            "ordinary language",
        ),
        (
            "it",
            "Vera lavora direttamente sui file dello studio.",
            "ricerche fiscali e normative",
            "parole normali",
        ),
        (
            "fr",
            "Vera travaille directement sur les fichiers du cabinet.",
            "recherches fiscales et réglementaires",
            "active le bon module",
        ),
        (
            "de",
            "Vera arbeitet direkt mit den Kanzleidateien.",
            "steuerliche und regulatorische Recherchen",
            "normalen Worten",
        ),
    ),
)
def test_homepage_vera_describes_the_task_without_literal_or_internal_language(
    lang: str,
    expected_opening: str,
    expected_research: str,
    rejected_fragment: str,
) -> None:
    _restore_application_import_path()

    from modules.pdp import api as pdp_api

    description = pdp_api._get_landing_page_content(lang)["sections"][0]["groups"][0][
        "description"
    ]

    assert description.startswith(expected_opening)
    assert expected_research in description
    assert rejected_fragment not in description


@pytest.mark.parametrize(
    (
        "lang",
        "expected_eyebrow",
        "expected_headline",
        "expected_control_term",
        "rejected_fragment",
        "rejected_consequence_fragment",
    ),
    (
        (
            "en",
            "Codex plugins for professional work",
            "AI has the power. Codex provides the control.",
            "control",
            "professional decides",
            "hallucinations",
        ),
        (
            "it",
            "Plugin Codex per il lavoro professionale",
            "La potenza viene dall'AI. Il controllo, da Codex.",
            "controllo",
            "professionista decide",
            "allucinazioni",
        ),
        (
            "fr",
            "Plugins Codex pour les professionnels",
            "L'IA apporte la puissance. Codex apporte le contrôle.",
            "contrôle",
            "professionnel décide",
            "hallucinations",
        ),
        (
            "de",
            "Codex-Plugins für professionelle Arbeit",
            "KI liefert die Leistung. Codex sorgt für Kontrolle.",
            "Kontrolle",
            "Fachperson entscheidet",
            "Halluzinationen",
        ),
    ),
)
def test_homepage_positions_control_as_the_codex_harness(
    lang: str,
    expected_eyebrow: str,
    expected_headline: str,
    expected_control_term: str,
    rejected_fragment: str,
    rejected_consequence_fragment: str,
) -> None:
    _restore_application_import_path()

    from modules.pdp import api as pdp_api

    content = pdp_api._get_landing_page_content(lang)
    serialized_content = json.dumps(content, ensure_ascii=False)

    assert content["hero"]["eyebrow"] == expected_eyebrow
    assert "Mparanza ·" not in content["hero"]["eyebrow"]
    assert content["hero"]["headline"] == expected_headline
    assert expected_control_term.casefold() in content["hero"]["headline"].casefold()
    assert content["harness"]["id"] == "codex"
    assert content["bridge"]["id"] == "plugins"
    assert rejected_fragment not in serialized_content
    assert rejected_consequence_fragment not in serialized_content
    assert '"responsibility"' not in serialized_content


@pytest.mark.parametrize(
    ("lang", "expected_description", "rejected_fragment"),
    (
        (
            "en",
            "Mparanza is Vera and Clara: two plugins that apply the same Codex "
            "harness to two different professions.",
            "first two",
        ),
        (
            "it",
            "Mparanza è Vera e Clara: due plugin che applicano lo stesso ambiente "
            "operativo Codex a due professioni diverse.",
            "primi due",
        ),
        (
            "fr",
            "Mparanza, c'est Vera et Clara : deux plugins qui appliquent le même "
            "environnement Codex à deux métiers différents.",
            "deux premiers",
        ),
        (
            "de",
            "Mparanza, das sind Vera und Clara: zwei Plugins, die dieselbe "
            "Codex-Arbeitsumgebung auf zwei Berufsgruppen ausrichten.",
            "ersten beiden",
        ),
    ),
)
def test_homepage_presents_vera_and_clara_as_the_complete_pair(
    lang: str,
    expected_description: str,
    rejected_fragment: str,
) -> None:
    _restore_application_import_path()

    from modules.pdp import api as pdp_api

    description = pdp_api._get_landing_page_content(lang)["bridge"]["description"]

    assert description == expected_description
    assert rejected_fragment not in description


@pytest.mark.parametrize(
    ("lang", "expected_blurb", "rejected_fragment"),
    (
        (
            "en",
            "A Codex plugin defines the specialist method and expected outputs.",
            "Mparanza plugin supplies",
        ),
        (
            "it",
            "Un plugin Codex definisce il metodo specialistico e i risultati da produrre.",
            "plugin Mparanza fornisce",
        ),
        (
            "fr",
            "Un plugin Codex définit la méthode spécialisée et les livrables à produire.",
            "plugin Mparanza apporte",
        ),
        (
            "de",
            "Ein Codex-Plugin bringt die fachliche Methode mit und legt die zu "
            "erstellenden Ergebnisse fest.",
            "Mparanza-Plugin liefert",
        ),
    ),
)
def test_homepage_attributes_the_specialist_method_to_codex_plugins(
    lang: str,
    expected_blurb: str,
    rejected_fragment: str,
) -> None:
    _restore_application_import_path()

    from modules.pdp import api as pdp_api

    professional_use_blurb = pdp_api._get_landing_page_content(lang)["harness"][
        "layers"
    ][2]["blurb"]

    assert professional_use_blurb == expected_blurb
    assert rejected_fragment not in professional_use_blurb


def test_homepage_app_css_link_is_cache_busted() -> None:
    base_template = (ROOT / "templates" / "base.html").read_text(encoding="utf-8")
    source = (ROOT / "modules" / "pdp" / "api.py").read_text(encoding="utf-8")

    assert "/static/css/app.css?v={{ app_css_asset_version" in base_template
    assert (
        '"app_css_asset_version": _static_asset_version("static/css/app.css")' in source
    )


def test_homepage_thesis_image_is_valid_and_cache_busted() -> None:
    from PIL import Image

    template = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    source = (ROOT / "modules" / "pdp" / "api.py").read_text(encoding="utf-8")
    image_path = ROOT / "static" / "icons" / "power_control.png"

    assert image_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    with Image.open(image_path) as image:
        image.verify()

    assert "/static/icons/power_control.png?v={{ thesis_image_asset_version" in template
    assert '"thesis_image_asset_version": _static_asset_version(' in source
