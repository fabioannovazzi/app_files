#!/usr/bin/env python3
"""Build downloadable Codex plugin ZIP packages from repo source.

Plugin-owned files live under ``plugins/<plugin>``. Shared legacy runtime
modules used by multiple plugins are injected from the configured shared vendor
tree so each ZIP remains independently installable without duplicating editable
source per plugin.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
LICENSE_PATH = ROOT / "LICENSE"
DEFAULT_CONFIG = ROOT / "scripts" / "codex_plugin_packages.json"
DEFAULT_VENDOR_MODULE_CONFIG = ROOT / "scripts" / "plugin_vendor_modules.json"
INTERACTION_AUDIT_SCRIPT = ROOT / "scripts" / "audit_plugin_interaction_patterns.py"
WORKBENCH_DEMO_AUDIT_SCRIPT = (
    ROOT / "scripts" / "audit_non_plotting_review_workbench_demos.py"
)
CONTRACT_COVERAGE_AUDIT_SCRIPT = (
    ROOT / "scripts" / "audit_review_payload_contract_coverage.py"
)
SHARED_REVIEW_WORKBENCH_SERVER = ROOT / "scripts" / "serve_review_workbench.py"
FIXED_ZIP_DATE = (1980, 1, 1, 0, 0, 0)
EXCLUDED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
}
EXCLUDED_FILES = {
    ".DS_Store",
}
EXCLUDED_SUFFIXES = {
    ".pyc",
    ".pyo",
}
REQUIRED_DEPENDENCY_FILES = (
    "requirements.txt",
    "scripts/check_dependencies.py",
)
RUNTIME_SUPPORT_FILES = {
    "clara": (
        Path("docs/specs/pptx_templates/ag-style-spec.md"),
        Path("docs/specs/pptx_templates/bain-style-spec.md"),
        Path(".agents/skills/advisory-output-shaper/SKILL.md"),
    ),
}
REQUIRED_FEEDBACK_HEADING = "## Plugin Improvement Feedback"
LOCAL_FEEDBACK_SNIPPET = "Keep the improvement note local to chat or run artifacts."
TRANSMITTED_FEEDBACK_PLUGINS = frozenset({"clara", "vera"})
TRANSMITTED_FEEDBACK_SNIPPETS = (
    "Should I transmit this technical problem to the developer so we can fix it?",
    "Do not continue with a chat interview, offer a fallback, or ask any",
    "does not authorize transmission of the user's improvement suggestion.",
    "Only in a later turn, after the failure-report choice has been handled",
    "credentials, secrets, or other identifying information.",
    "obtain separate suggestion-transmission consent.",
    "Should I transmit this suggestion to the developer so we can improve",
    "scripts/change_requests.py submit-problem",
    "scripts/change_requests.py reserve-suggestion-prompt",
    "scripts/change_requests.py submit-suggestion",
    "scripts/change_requests.py start-interview",
    "Always use the generic client-free string below",
    "at most one minute",
)
GENERIC_VOICE_OPPORTUNITY_TEMPLATE = (
    'python scripts/change_requests.py start-interview --opportunity "General '
    "{display_name} improvement suggestion; no client, customer, source, run, or "
    'case details supplied." --language <language>'
)
SPECIALIST_FEEDBACK_HANDOFF_TEMPLATE = (
    "After substantive use of this workflow, read and follow the "
    "`Plugin Improvement Feedback` section in `../{plugin}/SKILL.md`."
)
REQUIRED_OUTPUT_LOCATION_SNIPPET = "Never write run outputs inside this Git workspace"
REQUIRED_INTERFACE_FIELDS = (
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
SEVERE_INTERACTION_AUDIT_SEVERITIES = {"blocker", "high", "medium"}
SEVERE_WORKBENCH_DEMO_AUDIT_SEVERITIES = {"blocker", "high", "medium"}
SEVERE_CONTRACT_COVERAGE_AUDIT_SEVERITIES = {"blocker", "high", "medium"}
CHATGPT_UPLOAD_MAX_DEFAULT_PROMPTS = 3
CHATGPT_UPLOAD_MAX_SUBTITLE_LENGTH = 30
CHATGPT_UPLOAD_UNSUPPORTED_MANIFEST_FIELDS = {"apps", "mcpServers"}
CHATGPT_UPLOAD_UNSUPPORTED_CONFIG_FILES = {".app.json", ".mcp.json"}
CHATGPT_UPLOAD_SUBTITLE_OVERRIDES = {
    "vera": "AI companion for accountants",
}


@dataclass(frozen=True)
class PluginPackage:
    plugin: str
    package_root: str
    marketplace_name: str
    marketplace_display: str
    output_zip: Path
    install_readme: Path
    category: str = "Productivity"

    @property
    def plugin_dir(self) -> Path:
        return ROOT / "plugins" / self.plugin

    @property
    def target_name(self) -> str:
        return self.plugin

    @property
    def plugin_names(self) -> list[str]:
        return [self.plugin]

    @property
    def marketplace_plugin_names(self) -> list[str]:
        return [self.plugin]


@dataclass(frozen=True)
class PluginBundle:
    name: str
    plugins: list[str]
    marketplace_plugins: list[str]
    package_root: str
    marketplace_name: str
    marketplace_display: str
    output_zip: Path
    install_readme: Path
    category: str = "Productivity"

    @property
    def target_name(self) -> str:
        return self.name

    @property
    def plugin_names(self) -> list[str]:
        return self.plugins

    @property
    def marketplace_plugin_names(self) -> list[str]:
        return self.marketplace_plugins


BuildTarget = PluginPackage | PluginBundle


@dataclass(frozen=True)
class VendorModuleSource:
    """One source tree whose paths are merged into a vendored ``modules`` tree."""

    source_root: Path
    module_roots: list[str]


@dataclass(frozen=True)
class VendorModuleConfig:
    """Shared legacy module source configuration for one plugin."""

    source_root: Path
    module_roots: list[str]
    overlays: list[VendorModuleSource]


def load_packages(config_path: Path = DEFAULT_CONFIG) -> list[PluginPackage]:
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    packages = []
    for item in payload.get("packages", []):
        packages.append(
            PluginPackage(
                plugin=item["plugin"],
                package_root=item["package_root"],
                marketplace_name=item["marketplace_name"],
                marketplace_display=item["marketplace_display"],
                output_zip=ROOT / item["output_zip"],
                install_readme=ROOT / item["install_readme"],
                category=item.get("category", "Productivity"),
            )
        )
    return packages


def load_bundles(config_path: Path = DEFAULT_CONFIG) -> list[PluginBundle]:
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    bundles = []
    for item in payload.get("bundles", []):
        bundles.append(
            PluginBundle(
                name=item["name"],
                plugins=item["plugins"],
                marketplace_plugins=item.get("marketplace_plugins", item["plugins"]),
                package_root=item["package_root"],
                marketplace_name=item["marketplace_name"],
                marketplace_display=item["marketplace_display"],
                output_zip=ROOT / item["output_zip"],
                install_readme=ROOT / item["install_readme"],
                category=item.get("category", "Productivity"),
            )
        )
    return bundles


def load_non_downloadable_plugins(
    config_path: Path = DEFAULT_CONFIG,
) -> set[str]:
    """Return source plugins intentionally excluded from every ZIP."""

    payload = json.loads(config_path.read_text(encoding="utf-8"))
    configured = payload.get("non_downloadable_plugins", [])
    if not isinstance(configured, list):
        raise ValueError("non_downloadable_plugins must be a list")
    names = {str(name).strip() for name in configured if str(name).strip()}
    if len(names) != len(configured):
        raise ValueError(
            "non_downloadable_plugins must contain unique, non-empty names"
        )
    return names


def load_vendor_module_config(
    config_path: Path = DEFAULT_VENDOR_MODULE_CONFIG,
) -> dict[str, VendorModuleConfig]:
    """Return plugin -> shared module roots to vendor into package ZIPs."""

    if not config_path.exists():
        return {}
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    default_roots = [str(item) for item in payload.get("default_module_roots", [])]
    default_source = ROOT / str(
        payload.get("source_root", "plugins/_shared/vendor/modules")
    )
    plugin_roots: dict[str, VendorModuleConfig] = {}
    for plugin, config in (payload.get("plugins") or {}).items():
        roots = config.get("module_roots", default_roots)
        source_root = ROOT / str(config.get("source_root", default_source))
        overlays = [
            VendorModuleSource(
                source_root=ROOT / str(overlay["source_root"]),
                module_roots=[str(item) for item in overlay.get("module_roots", [])],
            )
            for overlay in config.get("overlays", [])
        ]
        plugin_roots[str(plugin)] = VendorModuleConfig(
            source_root=source_root,
            module_roots=[str(item) for item in roots],
            overlays=overlays,
        )
    return plugin_roots


def discover_plugin_dirs(plugins_root: Path = ROOT / "plugins") -> list[Path]:
    if not plugins_root.exists():
        return []
    return sorted(
        path.parent.parent for path in plugins_root.glob("*/.codex-plugin/plugin.json")
    )


def embedded_plugin_names(plugin_dir: Path) -> list[str]:
    """Return component plugin names embedded by an umbrella plugin."""

    components_path = plugin_dir / "components.json"
    if not components_path.exists():
        return []
    payload = json.loads(components_path.read_text(encoding="utf-8"))
    names = payload.get("plugins")
    if payload.get("schema_version") != 1 or not isinstance(names, list):
        raise ValueError(f"Invalid component configuration: {components_path}")
    normalized = [str(name) for name in names]
    if not normalized or len(normalized) != len(set(normalized)):
        raise ValueError(
            f"Component names must be non-empty and unique: {components_path}"
        )
    if plugin_dir.name in normalized:
        raise ValueError(f"Umbrella plugin cannot embed itself: {components_path}")
    return normalized


def _load_interaction_audit_module():
    spec = importlib.util.spec_from_file_location(
        "audit_plugin_interaction_patterns", INTERACTION_AUDIT_SCRIPT
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {INTERACTION_AUDIT_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_workbench_demo_audit_module():
    spec = importlib.util.spec_from_file_location(
        "audit_non_plotting_review_workbench_demos", WORKBENCH_DEMO_AUDIT_SCRIPT
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {WORKBENCH_DEMO_AUDIT_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_contract_coverage_audit_module():
    spec = importlib.util.spec_from_file_location(
        "audit_review_payload_contract_coverage", CONTRACT_COVERAGE_AUDIT_SCRIPT
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {CONTRACT_COVERAGE_AUDIT_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def validate_plugin_interaction_patterns(plugin_dir: Path) -> list[str]:
    """Return severe OpenAI-pattern interaction errors for one plugin."""

    if not INTERACTION_AUDIT_SCRIPT.exists():
        return []
    report = _load_interaction_audit_module().audit_plugin(plugin_dir)
    return [
        f"{plugin_dir.name}: interaction pattern {issue.code}: {issue.message}"
        for issue in report.issues
        if issue.severity in SEVERE_INTERACTION_AUDIT_SEVERITIES
    ]


def validate_plugin_workbench_demo(plugin_dir: Path) -> list[str]:
    """Return severe shared-workbench demo-payload errors for one plugin."""

    adapter_path = plugin_dir / "assets" / "review-workbench-adapter.json"
    if not WORKBENCH_DEMO_AUDIT_SCRIPT.exists() or not adapter_path.exists():
        return []
    report = _load_workbench_demo_audit_module().audit_adapter(
        adapter_path, root=plugin_dir.parent
    )
    return [
        f"{plugin_dir.name}: workbench demo {issue.code}: {issue.message}"
        for issue in report.issues
        if issue.severity in SEVERE_WORKBENCH_DEMO_AUDIT_SEVERITIES
    ]


def _audit_root_for_plugin_dir(plugin_dir: Path) -> Path:
    return (
        plugin_dir.parent.parent
        if plugin_dir.parent.name == "plugins"
        else plugin_dir.parent
    )


def validate_plugin_contract_coverage(plugin_dir: Path) -> list[str]:
    """Return severe generated review-payload contract coverage errors."""

    adapter_path = plugin_dir / "assets" / "review-workbench-adapter.json"
    if not CONTRACT_COVERAGE_AUDIT_SCRIPT.exists() or not adapter_path.exists():
        return []
    root = _audit_root_for_plugin_dir(plugin_dir)
    test_roots = (
        root / "tests" / "plugins",
        root / "plugins" / "client-file-preparation" / "tests",
    )
    reports = _load_contract_coverage_audit_module().audit_contract_coverage(
        root,
        plugins=(plugin_dir.name,),
        test_roots=test_roots,
    )
    return [
        f"{plugin_dir.name}: review payload contract coverage {issue.code}: {issue.message}"
        for report in reports
        for issue in report.issues
        if issue.severity in SEVERE_CONTRACT_COVERAGE_AUDIT_SEVERITIES
    ]


def validate_plugin_source(plugin_dir: Path) -> list[str]:
    errors: list[str] = []
    plugin_name = plugin_dir.name
    if not plugin_dir.exists():
        return [f"{plugin_name}: plugin source does not exist: {plugin_dir}"]
    manifest_path = plugin_dir / ".codex-plugin" / "plugin.json"
    if not manifest_path.exists():
        errors.append(f"{plugin_name}: missing .codex-plugin/plugin.json")
    else:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for field in (
            "name",
            "version",
            "description",
            "author",
            "homepage",
            "repository",
            "license",
            "keywords",
            "skills",
        ):
            if not manifest.get(field):
                errors.append(f"{plugin_name}: missing manifest field {field}")
        if manifest.get("name") != plugin_name:
            errors.append(f"{plugin_name}: manifest.name must match plugin directory")
        if manifest.get("skills") != "./skills/":
            errors.append(f"{plugin_name}: manifest.skills must be ./skills/")
        has_mcp_config = (plugin_dir / ".mcp.json").exists()
        if has_mcp_config and manifest.get("mcpServers") != "./.mcp.json":
            errors.append(
                f"{plugin_name}: plugins with .mcp.json must declare manifest.mcpServers as ./.mcp.json"
            )
        if manifest.get("mcpServers") is not None and not has_mcp_config:
            errors.append(f"{plugin_name}: manifest.mcpServers requires .mcp.json")
        if has_mcp_config and manifest.get("apps") != "./.app.json":
            errors.append(
                f"{plugin_name}: plugins with MCP widgets must declare manifest.apps as ./.app.json"
            )
        if manifest.get("apps") is not None:
            if manifest.get("apps") != "./.app.json":
                errors.append(f"{plugin_name}: manifest.apps must be ./.app.json")
            app_manifest_path = plugin_dir / ".app.json"
            if not app_manifest_path.exists():
                errors.append(f"{plugin_name}: manifest.apps requires .app.json")
            else:
                try:
                    app_manifest = json.loads(
                        app_manifest_path.read_text(encoding="utf-8")
                    )
                except json.JSONDecodeError as exc:
                    errors.append(f"{plugin_name}: invalid .app.json: {exc}")
                else:
                    if not isinstance(app_manifest, dict):
                        errors.append(f"{plugin_name}: .app.json must be a JSON object")
                    elif set(app_manifest) != {"apps"}:
                        errors.append(
                            f"{plugin_name}: .app.json must contain only an apps object"
                        )
                    elif not isinstance(app_manifest.get("apps"), dict):
                        errors.append(
                            f"{plugin_name}: .app.json apps must be a JSON object"
                        )
        interface = manifest.get("interface", {})
        for field in REQUIRED_INTERFACE_FIELDS:
            if not interface.get(field):
                errors.append(f"{plugin_name}: missing interface.{field}")
        composer_icon = interface.get("composerIcon")
        logo = interface.get("logo")
        if composer_icon != logo:
            errors.append(f"{plugin_name}: interface icons must use the same asset")
        if not isinstance(composer_icon, str) or not composer_icon.startswith(
            "./assets/icon."
        ):
            errors.append(
                f"{plugin_name}: interface icons must use ./assets/icon.<extension>"
            )
        elif not (plugin_dir / composer_icon.removeprefix("./")).is_file():
            errors.append(f"{plugin_name}: missing {composer_icon.removeprefix('./')}")

    for rel_path in REQUIRED_DEPENDENCY_FILES:
        if not (plugin_dir / rel_path).exists():
            errors.append(f"{plugin_name}: missing {rel_path}")

    try:
        components = embedded_plugin_names(plugin_dir)
    except (json.JSONDecodeError, ValueError) as exc:
        errors.append(f"{plugin_name}: {exc}")
        components = []
    for component in components:
        component_dir = plugin_dir.parent / component
        if not component_dir.is_dir():
            errors.append(
                f"{plugin_name}: embedded plugin source does not exist: {component}"
            )

    skill_files = sorted((plugin_dir / "skills").glob("*/SKILL.md"))
    if not skill_files:
        errors.append(f"{plugin_name}: missing skills/*/SKILL.md")
    else:
        combined_skill_text = "\n".join(
            path.read_text(encoding="utf-8") for path in skill_files
        )
        if "check_dependencies.py" not in combined_skill_text:
            errors.append(
                f"{plugin_name}: skill instructions must tell Codex to run scripts/check_dependencies.py"
            )
        if "requirements" not in combined_skill_text.lower():
            errors.append(
                f"{plugin_name}: skill instructions must mention requirements/dependency handling"
            )
        feedback_snippets = (
            (
                REQUIRED_FEEDBACK_HEADING,
                *TRANSMITTED_FEEDBACK_SNIPPETS,
                GENERIC_VOICE_OPPORTUNITY_TEMPLATE.format(
                    display_name=plugin_name.title()
                ),
            )
            if plugin_name in TRANSMITTED_FEEDBACK_PLUGINS
            else (REQUIRED_FEEDBACK_HEADING, LOCAL_FEEDBACK_SNIPPET)
        )
        for snippet in feedback_snippets:
            if snippet not in combined_skill_text:
                errors.append(
                    f"{plugin_name}: skill instructions must include plugin improvement feedback policy"
                )
                break
        if plugin_name in TRANSMITTED_FEEDBACK_PLUGINS:
            # Specialists can trigger without the main skill. Requiring its exact
            # relative path makes the post-run handoff mechanically resolvable.
            specialist_handoff = SPECIALIST_FEEDBACK_HANDOFF_TEMPLATE.format(
                plugin=plugin_name
            )
            for skill_path in skill_files:
                if skill_path.parent.name == plugin_name:
                    continue
                if specialist_handoff not in skill_path.read_text(encoding="utf-8"):
                    relative_path = skill_path.relative_to(plugin_dir)
                    errors.append(
                        f"{plugin_name}: {relative_path} must hand off plugin improvement feedback to the main skill"
                    )
        if REQUIRED_OUTPUT_LOCATION_SNIPPET not in combined_skill_text:
            errors.append(
                f"{plugin_name}: skill instructions must include the run output location policy"
            )
        errors.extend(validate_plugin_interaction_patterns(plugin_dir))

    errors.extend(validate_plugin_workbench_demo(plugin_dir))
    errors.extend(validate_plugin_contract_coverage(plugin_dir))

    eval_path = plugin_dir / "evals" / "trigger_fixtures.json"
    if not eval_path.exists():
        errors.append(f"{plugin_name}: missing evals/trigger_fixtures.json")
    else:
        try:
            eval_payload = json.loads(eval_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{plugin_name}: invalid trigger fixture JSON: {exc}")
        else:
            if eval_payload.get("plugin") != plugin_name:
                errors.append(f"{plugin_name}: trigger fixture plugin mismatch")
            if not eval_payload.get("should_trigger"):
                errors.append(f"{plugin_name}: trigger fixture has no positive cases")
            if not eval_payload.get("should_not_trigger"):
                errors.append(f"{plugin_name}: trigger fixture has no negative cases")

    return errors


def validate_package_config(
    packages: list[PluginPackage],
    bundles: list[PluginBundle],
    config_path: Path = DEFAULT_CONFIG,
) -> list[str]:
    present_plugins = {path.name for path in discover_plugin_dirs()}
    downloadable_plugins = {package.plugin for package in packages}
    for bundle in bundles:
        downloadable_plugins.update(bundle.plugin_names)
    embedded_plugins: set[str] = set()
    for plugin in downloadable_plugins:
        embedded_plugins.update(embedded_plugin_names(ROOT / "plugins" / plugin))
    non_downloadable_plugins = load_non_downloadable_plugins(config_path)
    configured_plugins = (
        downloadable_plugins | embedded_plugins | non_downloadable_plugins
    )
    errors: list[str] = []
    for plugin in sorted(
        non_downloadable_plugins & (downloadable_plugins | embedded_plugins)
    ):
        errors.append(f"{plugin}: non-downloadable plugin is also included in a ZIP")
    for plugin in sorted(present_plugins - configured_plugins):
        errors.append(
            f"{plugin}: plugin exists under plugins/ but is missing from {DEFAULT_CONFIG.relative_to(ROOT)}"
        )
    for plugin in sorted(configured_plugins - present_plugins):
        errors.append(
            f"{plugin}: configured in {DEFAULT_CONFIG.relative_to(ROOT)} but no plugin source exists"
        )
    return errors


def validate_bundle_config(bundles: list[PluginBundle]) -> list[str]:
    present_plugins = {path.name for path in discover_plugin_dirs()}
    errors: list[str] = []
    for bundle in bundles:
        if not bundle.plugins:
            errors.append(f"{bundle.name}: bundle has no plugins")
        if not bundle.marketplace_plugins:
            errors.append(f"{bundle.name}: bundle has no marketplace plugins")
        missing = sorted(set(bundle.plugins) - present_plugins)
        for plugin in missing:
            errors.append(
                f"{bundle.name}: configured bundle plugin does not exist: {plugin}"
            )
        hidden_missing = sorted(set(bundle.marketplace_plugins) - set(bundle.plugins))
        for plugin in hidden_missing:
            errors.append(
                f"{bundle.name}: marketplace plugin is not packaged in bundle: {plugin}"
            )
    return errors


def should_skip(path: Path) -> bool:
    if any(part in EXCLUDED_DIRS for part in path.parts):
        return True
    if path.name in EXCLUDED_FILES:
        return True
    return path.suffix in EXCLUDED_SUFFIXES


def source_files(
    plugin_dir: Path, *, exclude_vendor_modules: bool = False
) -> list[Path]:
    return sorted(
        path
        for path in plugin_dir.rglob("*")
        if path.is_file()
        and not should_skip(path.relative_to(plugin_dir))
        and not (
            exclude_vendor_modules
            and len(path.relative_to(plugin_dir).parts) >= 2
            and path.relative_to(plugin_dir).parts[:2] == ("vendor", "modules")
        )
    )


def _vendor_module_source_files(source: VendorModuleSource) -> list[Path]:
    """Return files selected from one vendored module source tree."""

    if not source.module_roots:
        return []
    modules_root = source.source_root
    paths: list[Path] = []
    init_path = modules_root / "__init__.py"
    if init_path.exists():
        paths.append(init_path)
    for module_root in source.module_roots:
        candidate = modules_root / module_root
        if candidate.is_file():
            paths.append(candidate)
        elif candidate.is_dir():
            paths.extend(
                path
                for path in candidate.rglob("*")
                if path.is_file() and not should_skip(path.relative_to(modules_root))
            )
        else:
            raise FileNotFoundError(
                f"Shared vendor module source does not exist: {candidate}"
            )
    return sorted(set(paths))


def shared_vendor_module_entries(
    config: VendorModuleConfig | None,
) -> dict[str, Path]:
    """Return relative package paths for a base vendor tree plus overlays."""

    if config is None:
        return {}
    sources = [
        VendorModuleSource(config.source_root, config.module_roots),
        *config.overlays,
    ]
    entries: dict[str, Path] = {}
    for source in sources:
        for path in _vendor_module_source_files(source):
            entries[path.relative_to(source.source_root).as_posix()] = path
    return dict(sorted(entries.items()))


def review_workbench_server_entry(plugin_dir: Path) -> bytes | None:
    """Return the shared local review server when a plugin needs injection."""

    if not (plugin_dir / "assets" / "review-workbench-adapter.json").exists():
        return None
    if (plugin_dir / "scripts" / "review_server.py").exists():
        return None
    if not SHARED_REVIEW_WORKBENCH_SERVER.exists():
        raise FileNotFoundError(
            f"Shared review workbench server does not exist: {SHARED_REVIEW_WORKBENCH_SERVER}"
        )
    return SHARED_REVIEW_WORKBENCH_SERVER.read_bytes()


def marketplace_payload(package: BuildTarget) -> bytes:
    payload = {
        "name": package.marketplace_name,
        "interface": {"displayName": package.marketplace_display},
        "plugins": [
            {
                "name": plugin,
                "source": {
                    "source": "local",
                    "path": f"./plugins/{plugin}",
                },
                "policy": {
                    "installation": "AVAILABLE",
                    "authentication": "ON_INSTALL",
                },
                "category": package.category,
            }
            for plugin in package.marketplace_plugin_names
        ],
    }
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def expected_zip_entries(package: BuildTarget) -> dict[str, bytes]:
    plugin_dirs = [ROOT / "plugins" / plugin for plugin in package.plugin_names]
    vendor_module_config = load_vendor_module_config()
    hidden_missing = sorted(
        set(package.marketplace_plugin_names) - set(package.plugin_names)
    )
    if hidden_missing:
        raise ValueError(
            "Marketplace plugin is not packaged in target: " + ", ".join(hidden_missing)
        )
    for plugin_dir in plugin_dirs:
        if not plugin_dir.exists():
            raise FileNotFoundError(f"Plugin source does not exist: {plugin_dir}")
        source_errors = validate_plugin_source(plugin_dir)
        if source_errors:
            raise ValueError(
                "Plugin source validation failed:\n  - " + "\n  - ".join(source_errors)
            )
    if not package.install_readme.exists():
        raise FileNotFoundError(
            f"Install readme does not exist: {package.install_readme}"
        )
    if not LICENSE_PATH.exists():
        raise FileNotFoundError(f"Repository license does not exist: {LICENSE_PATH}")

    root = package.package_root
    entries = {
        f"{root}/LICENSE": LICENSE_PATH.read_bytes(),
        f"{root}/LEGGIMI_INSTALLAZIONE.txt": package.install_readme.read_bytes(),
        f"{root}/.agents/plugins/marketplace.json": marketplace_payload(package),
    }
    for relative_path in RUNTIME_SUPPORT_FILES.get(package.target_name, ()):
        source_path = ROOT / relative_path
        if not source_path.is_file():
            raise FileNotFoundError(
                f"Runtime support file does not exist: {source_path}"
            )
        entries[f"{root}/{relative_path.as_posix()}"] = source_path.read_bytes()
    for plugin_dir in plugin_dirs:
        plugin_root = f"{root}/plugins/{plugin_dir.name}"
        vendor_config = vendor_module_config.get(plugin_dir.name)
        for path in source_files(
            plugin_dir,
            exclude_vendor_modules=vendor_config is not None,
        ):
            rel = path.relative_to(plugin_dir).as_posix()
            entries[f"{plugin_root}/{rel}"] = path.read_bytes()
        for rel, path in shared_vendor_module_entries(vendor_config).items():
            entries[f"{plugin_root}/vendor/modules/{rel}"] = path.read_bytes()
        server_entry = review_workbench_server_entry(plugin_dir)
        if server_entry is not None:
            entries[f"{plugin_root}/scripts/review_server.py"] = server_entry
        for component_name in embedded_plugin_names(plugin_dir):
            component_dir = ROOT / "plugins" / component_name
            if not component_dir.exists():
                raise FileNotFoundError(
                    f"Embedded plugin source does not exist: {component_dir}"
                )
            component_errors = validate_plugin_source(component_dir)
            if component_errors:
                raise ValueError(
                    "Embedded plugin source validation failed:\n  - "
                    + "\n  - ".join(component_errors)
                )
            component_root = f"{plugin_root}/modules/{component_name}"
            component_vendor = vendor_module_config.get(component_name)
            for path in source_files(
                component_dir,
                exclude_vendor_modules=component_vendor is not None,
            ):
                rel = path.relative_to(component_dir).as_posix()
                entries[f"{component_root}/{rel}"] = path.read_bytes()
            for rel, path in shared_vendor_module_entries(component_vendor).items():
                entries[f"{component_root}/vendor/modules/{rel}"] = path.read_bytes()
            component_server = review_workbench_server_entry(component_dir)
            if component_server is not None:
                entries[f"{component_root}/scripts/review_server.py"] = component_server
    return dict(sorted(entries.items()))


def project_chatgpt_manifest(content: bytes) -> bytes:
    """Project a source manifest onto OpenAI's current skills-only surface."""

    manifest = json.loads(content.decode("utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("ChatGPT upload manifest must be a JSON object")
    for field in CHATGPT_UPLOAD_UNSUPPORTED_MANIFEST_FIELDS:
        manifest.pop(field, None)

    interface = manifest.get("interface")
    if interface is not None and not isinstance(interface, dict):
        raise ValueError("ChatGPT upload manifest interface must be a JSON object")
    if isinstance(interface, dict):
        subtitle_override = CHATGPT_UPLOAD_SUBTITLE_OVERRIDES.get(
            str(manifest.get("name", ""))
        )
        if subtitle_override is not None:
            interface["shortDescription"] = subtitle_override
        subtitle = interface.get("shortDescription")
        if not isinstance(subtitle, str):
            raise ValueError("ChatGPT upload shortDescription must be a string")
        if len(subtitle) > CHATGPT_UPLOAD_MAX_SUBTITLE_LENGTH:
            raise ValueError(
                "ChatGPT upload interface.shortDescription must contain at most "
                f"{CHATGPT_UPLOAD_MAX_SUBTITLE_LENGTH} characters; found "
                f"{len(subtitle)}"
            )
        prompts = interface.get("defaultPrompt")
        if prompts is not None and not isinstance(prompts, list):
            raise ValueError("ChatGPT upload defaultPrompt must be a JSON array")
        if (
            isinstance(prompts, list)
            and len(prompts) > CHATGPT_UPLOAD_MAX_DEFAULT_PROMPTS
        ):
            raise ValueError(
                "ChatGPT upload interface.defaultPrompt must contain at most "
                f"{CHATGPT_UPLOAD_MAX_DEFAULT_PROMPTS} prompts; found {len(prompts)}"
            )

    return (json.dumps(manifest, indent=2) + "\n").encode("utf-8")


def chatgpt_upload_entries(package: BuildTarget) -> dict[str, bytes]:
    """Return one source-derived, skills-only tree for OpenAI Platform."""

    if len(package.plugin_names) != 1:
        raise ValueError("ChatGPT upload ZIPs must contain exactly one root plugin")
    plugin_name = package.plugin_names[0]
    prefix = f"{package.package_root}/plugins/{plugin_name}/"
    entries: dict[str, bytes] = {"LICENSE": LICENSE_PATH.read_bytes()}
    for packaged_name, content in expected_zip_entries(package).items():
        if not packaged_name.startswith(prefix):
            continue
        name = packaged_name.removeprefix(prefix)
        path_parts = name.split("/")
        if path_parts[-1] in CHATGPT_UPLOAD_UNSUPPORTED_CONFIG_FILES:
            continue
        if "mcp" in path_parts:
            continue
        if name == ".codex-plugin/plugin.json":
            content = project_chatgpt_manifest(content)
        entries[name] = content
    if ".codex-plugin/plugin.json" not in entries:
        raise ValueError("ChatGPT upload ZIP is missing .codex-plugin/plugin.json")
    return dict(sorted(entries.items()))


def write_entry(archive: ZipFile, name: str, content: bytes) -> None:
    info = ZipInfo(name, FIXED_ZIP_DATE)
    info.compress_type = ZIP_DEFLATED
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    archive.writestr(info, content)


def write_entries_to_directory(root: Path, entries: dict[str, bytes]) -> None:
    for name, content in entries.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        target.chmod(0o644)


def verify_zip_entries(zip_path: Path, entries: dict[str, bytes]) -> None:
    with ZipFile(zip_path) as archive:
        actual_names = {name for name in archive.namelist() if not name.endswith("/")}
        expected_names = set(entries)
        if actual_names != expected_names:
            missing = sorted(expected_names - actual_names)
            extra = sorted(actual_names - expected_names)
            details = []
            if missing:
                details.append(f"missing={missing}")
            if extra:
                details.append(f"extra={extra}")
            raise ValueError("Temporary ZIP entry mismatch: " + "; ".join(details))
        for name, content in entries.items():
            if archive.read(name) != content:
                raise ValueError(f"Temporary ZIP verification failed: {name}")


def write_system_zip(
    zip_path: Path, entries: dict[str, bytes], package_root: str
) -> None:
    zip_executable = shutil.which("zip")
    if zip_executable is None:
        with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as archive:
            for name, content in entries.items():
                write_entry(archive, name, content)
        return

    with tempfile.TemporaryDirectory(
        prefix=".codex-plugin-stage.", dir=zip_path.parent
    ) as staging_name:
        staging = Path(staging_name)
        write_entries_to_directory(staging, entries)
        if zip_path.exists():
            zip_path.unlink()
        subprocess.run(
            [zip_executable, "-q", "-r", "-X", str(zip_path), package_root],
            cwd=staging,
            check=True,
        )


def build_package(package: BuildTarget) -> Path:
    entries = expected_zip_entries(package)
    output = package.output_zip
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{output.name}.",
            suffix=".tmp",
            dir=output.parent,
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
        write_system_zip(temp_path, entries, package.package_root)
        verify_zip_entries(temp_path, entries)
        temp_path.chmod(0o644)
        temp_path.replace(output)
        output.chmod(0o644)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
    return package.output_zip


def build_chatgpt_upload(package: BuildTarget, output: Path) -> Path:
    """Build an OpenAI Platform upload ZIP without changing the install ZIP."""

    entries = chatgpt_upload_entries(package)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{output.name}.",
            suffix=".tmp",
            dir=output.parent,
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
        with ZipFile(temp_path, "w", compression=ZIP_DEFLATED) as archive:
            for name, content in entries.items():
                write_entry(archive, name, content)
        verify_zip_entries(temp_path, entries)
        temp_path.chmod(0o644)
        temp_path.replace(output)
        output.chmod(0o644)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
    return output


def verify_chatgpt_upload(package: BuildTarget, output: Path) -> list[str]:
    """Return source-drift errors for an OpenAI Platform upload ZIP."""

    if not output.exists():
        return [f"ZIP missing: {output}"]
    expected = chatgpt_upload_entries(package)
    errors: list[str] = []
    with ZipFile(output) as archive:
        actual_names = {name for name in archive.namelist() if not name.endswith("/")}
        expected_names = set(expected)
        for name in sorted(expected_names - actual_names):
            errors.append(f"Missing from ZIP: {name}")
        for name in sorted(actual_names - expected_names):
            errors.append(f"Unexpected in ZIP: {name}")
        for name in sorted(expected_names & actual_names):
            if archive.read(name) != expected[name]:
                errors.append(f"Content differs: {name}")
    return errors


def verify_package(package: BuildTarget) -> list[str]:
    for plugin in package.plugin_names:
        source_errors = validate_plugin_source(ROOT / "plugins" / plugin)
        if source_errors:
            return source_errors
    expected = expected_zip_entries(package)
    if not package.output_zip.exists():
        return [f"ZIP missing: {package.output_zip}"]

    errors: list[str] = []
    with ZipFile(package.output_zip) as archive:
        actual_names = {name for name in archive.namelist() if not name.endswith("/")}
        expected_names = set(expected)
        for name in sorted(expected_names - actual_names):
            errors.append(f"Missing from ZIP: {name}")
        for name in sorted(actual_names - expected_names):
            errors.append(f"Unexpected in ZIP: {name}")
        for name in sorted(expected_names & actual_names):
            actual = archive.read(name)
            if actual != expected[name]:
                errors.append(f"Content differs: {name}")
    return errors


def select_packages(
    packages: list[PluginPackage],
    bundles: list[PluginBundle],
    selected: list[str],
) -> list[BuildTarget]:
    all_targets: list[BuildTarget] = [*packages, *bundles]
    if not selected or selected == ["all"]:
        return all_targets

    package_by_name = {package.plugin: package for package in packages}
    bundle_by_name = {bundle.name: bundle for bundle in bundles}
    containers_by_plugin: dict[str, list[BuildTarget]] = {}
    for target in all_targets:
        for plugin in target.plugin_names:
            containers_by_plugin.setdefault(plugin, []).append(target)
            plugin_dir = ROOT / "plugins" / plugin
            for component in embedded_plugin_names(plugin_dir):
                containers_by_plugin.setdefault(component, []).append(target)
    selected_targets: list[BuildTarget] = []
    selected_keys: set[tuple[str, Path]] = set()

    def append_target(target: BuildTarget) -> None:
        key = (target.package_root, target.output_zip)
        if key not in selected_keys:
            selected_keys.add(key)
            selected_targets.append(target)

    missing = []
    for name in selected:
        matched = False
        if name in package_by_name:
            matched = True
            append_target(package_by_name[name])
        for container in containers_by_plugin.get(name, []):
            matched = True
            append_target(container)
        if name in bundle_by_name:
            matched = True
            append_target(bundle_by_name[name])
        if not matched:
            missing.append(name)
    if missing:
        raise SystemExit(f"Unknown plugin package(s): {', '.join(missing)}")
    return selected_targets


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "plugins", nargs="*", help="Plugin name(s) to build, or omit for all."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--check", action="store_true", help="Verify ZIPs without rebuilding."
    )
    parser.add_argument(
        "--chatgpt-upload",
        type=Path,
        metavar="PATH",
        help="Build or verify one plugin ZIP for OpenAI Platform upload.",
    )
    args = parser.parse_args(argv)

    all_packages = load_packages(args.config)
    all_bundles = load_bundles(args.config)
    packages = select_packages(all_packages, all_bundles, args.plugins)
    if args.chatgpt_upload is not None:
        if len(packages) != 1:
            parser.error("--chatgpt-upload requires exactly one selected package")
        package = packages[0]
        try:
            if args.check:
                errors = verify_chatgpt_upload(package, args.chatgpt_upload)
                if errors:
                    print(
                        f"[FAIL] {package.target_name}: {args.chatgpt_upload}",
                        file=sys.stderr,
                    )
                    for error in errors:
                        print(f"  - {error}", file=sys.stderr)
                    return 1
                print(f"[OK] {package.target_name}: {args.chatgpt_upload}")
                return 0
            output = build_chatgpt_upload(package, args.chatgpt_upload)
            print(f"[BUILT] {package.target_name}: {output}")
            return 0
        except (BadZipFile, OSError, RuntimeError, ValueError) as exc:
            print(
                f"[FAIL] {package.target_name}: {exc}",
                file=sys.stderr,
            )
            return 1
    failed = False
    if not args.plugins or args.plugins == ["all"]:
        config_errors = validate_package_config(all_packages, all_bundles, args.config)
        config_errors.extend(validate_bundle_config(all_bundles))
        if config_errors:
            failed = True
            print("[FAIL] plugin package configuration", file=sys.stderr)
            for error in config_errors:
                print(f"  - {error}", file=sys.stderr)
    for package in packages:
        try:
            if args.check:
                errors = verify_package(package)
                if errors:
                    failed = True
                    print(
                        f"[FAIL] {package.target_name}: {package.output_zip}",
                        file=sys.stderr,
                    )
                    for error in errors:
                        print(f"  - {error}", file=sys.stderr)
                else:
                    print(f"[OK] {package.target_name}: {package.output_zip}")
            else:
                output = build_package(package)
                errors = verify_package(package)
                if errors:
                    failed = True
                    print(f"[FAIL] {package.target_name}: {output}", file=sys.stderr)
                    for error in errors:
                        print(f"  - {error}", file=sys.stderr)
                else:
                    print(f"[BUILT] {package.target_name}: {output}")
        except Exception as exc:
            failed = True
            print(f"[FAIL] {package.target_name}: {exc}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
