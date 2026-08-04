from __future__ import annotations

import importlib.util
import json
import os
import sys
import types
from pathlib import Path
from typing import Any, Callable

import pytest

# Exact plugin execution-boundary tests require a clean source tree.  Keep
# pytest and its subprocesses from creating unreceipted local bytecode during
# collection or execution.
sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests_tagging_stub import ensure_tagging_stub  # isort: skip

__all__ = []

_CANONICAL_MODULES: dict[str, types.ModuleType] = {}
_COLLECTION_ENVIRONMENT = dict(os.environ)
_RUNTIME_IMPORT_SNAPSHOTS: dict[
    str,
    tuple[dict[str, types.ModuleType], list[str], dict[str, str]],
] = {}


@pytest.fixture
def vera_workflow_workspace(
    tmp_path: Path,
) -> Callable[[str], dict[str, Any]]:
    """Build one real running v2 customer-folder context for Vera CLI tests."""

    created = 0
    engagements: dict[str, str] = {}

    ledger_path = ROOT / "plugins" / "studio-archive" / "scripts" / "client_ledger.py"
    module_name = "pytest_vera_customer_ledger"
    ledger = sys.modules.get(module_name)
    if ledger is None:
        spec = importlib.util.spec_from_file_location(module_name, ledger_path)
        assert spec is not None and spec.loader is not None
        ledger = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = ledger
        spec.loader.exec_module(ledger)

    client_root = tmp_path / "Test Client"
    client_root.mkdir(mode=0o700)
    client_id = "client_111111111111111111111111"
    ledger.create_client_manifest(client_root, client_id)

    def create(
        workflow_id: str,
        *,
        engagement_id: str | None = None,
        input_files: dict[str, str] | None = None,
        upstream_workspace: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        nonlocal created
        created += 1
        engagement_key = engagement_id or f"engagement-{created}"
        actual_engagement_id = engagements.get(engagement_key)
        if actual_engagement_id is None:
            engagement = ledger.create_engagement(
                client_root,
                client_id,
                engagement_key,
            )
            actual_engagement_id = engagement["engagement_id"]
            engagements[engagement_key] = actual_engagement_id

        input_ids: list[str] = []
        upstream_artifacts: list[dict[str, str]] = []
        if upstream_workspace is not None:
            upstream_output = Path(upstream_workspace["output_dir"])
            declarations = [
                {
                    "artifact_id": f"pytest_artifact_{index:04d}",
                    "path": path.relative_to(upstream_output).as_posix(),
                    "purpose": "Exercise the exact upstream workflow handoff.",
                    "audience": "internal",
                    "media_type": "application/octet-stream",
                }
                for index, path in enumerate(
                    sorted(
                        candidate
                        for candidate in upstream_output.rglob("*")
                        if candidate.is_file()
                    )
                )
            ]
            finalized = ledger.finalize_run(
                client_root,
                actual_engagement_id,
                upstream_workspace["run_id"],
                declarations,
            )
            upstream_artifacts = [
                {
                    "run_id": upstream_workspace["run_id"],
                    "artifact_id": artifact["artifact_id"],
                    "role": "source",
                }
                for artifact in finalized["artifact_manifest"]["artifacts"]
            ]
        else:
            supplied = input_files or {
                f"source-{created}.txt": (
                    "Ragione sociale: Beta Esempio S.r.l.\n"
                    "Codice fiscale: 01234567890\n"
                    "Certificazione Unica 2025.\n"
                )
            }
            staging = tmp_path / "fixture-sources" / str(created)
            staging.mkdir(parents=True, mode=0o700)
            for filename, content in supplied.items():
                assert Path(filename).name == filename
                source = staging / filename
                source.write_text(content, encoding="utf-8")
                imported = ledger.import_document(
                    client_root,
                    client_id,
                    actual_engagement_id,
                    source.resolve(),
                    "source",
                )
                input_ids.append(imported["receipt"]["input_id"])

        prepared = ledger.prepare_run(
            client_root,
            client_id,
            actual_engagement_id,
            workflow_id,
            "test-version",
            input_ids=input_ids,
            upstream_artifacts=upstream_artifacts,
            idempotency_key=f"pytest:{created}",
        )
        running = ledger.start_run(
            client_root,
            actual_engagement_id,
            prepared["run"]["run_id"],
        )
        context = running["context"]
        input_paths = [Path(binding["path"]) for binding in context["input_bindings"]]
        return {
            "context": context,
            "context_path": Path(running["context_path"]),
            "input_dir": Path(context["input_dir"]),
            "input_paths": input_paths,
            "input_by_name": {path.name: path for path in input_paths},
            "output_dir": Path(running["output_dir"]),
            "client_root": client_root,
            "client_id": client_id,
            "engagement_id": actual_engagement_id,
            "run_id": running["run"]["run_id"],
        }

    return create


def _drop_imported_module(name: str) -> None:
    """Remove a cached module and its matching parent-package attribute."""

    module = sys.modules.pop(name, None)
    parent_name, separator, child_name = name.rpartition(".")
    if module is None or not separator:
        return
    parent = sys.modules.get(parent_name)
    if parent is not None and getattr(parent, child_name, None) is module:
        delattr(parent, child_name)


def _canonical_module_exists(name: str) -> bool:
    """Return whether ``name`` maps to an application module in this repository."""

    root_name, separator, relative_name = name.partition(".")
    if not separator or root_name not in {"modules", "src"}:
        return False
    candidate = ROOT / root_name / Path(*relative_name.split("."))
    return candidate.with_suffix(".py").exists() or candidate.is_dir()


def _is_plugin_local_module(module: types.ModuleType) -> bool:
    """Return whether a module was imported from a plugin-local source tree."""

    module_file = getattr(module, "__file__", None)
    if not module_file:
        return False
    try:
        Path(module_file).resolve().relative_to((ROOT / "plugins").resolve())
    except (OSError, RuntimeError, ValueError):
        return False
    return True


def _discard_plugin_runtime_imports() -> None:
    """Remove process-local plugin modules and script paths between tests."""

    for name, module in list(sys.modules.items()):
        if _is_plugin_local_module(module):
            _drop_imported_module(name)

    plugins_root = (ROOT / "plugins").resolve()
    cleaned_path: list[str] = []
    for entry in sys.path:
        try:
            Path(entry).resolve().relative_to(plugins_root)
        except (OSError, RuntimeError, ValueError):
            cleaned_path.append(entry)
    sys.path[:] = cleaned_path


def _remember_canonical_modules() -> None:
    """Retain the first repository module object imported under each name."""

    for name, module in list(sys.modules.items()):
        if name != "modules" and not name.startswith(("modules.", "src.")):
            continue
        module_file = getattr(module, "__file__", None)
        if module_file:
            try:
                relative_path = Path(module_file).resolve().relative_to(ROOT.resolve())
            except (OSError, RuntimeError, ValueError):
                continue
            if not relative_path.parts or relative_path.parts[0] not in {
                "modules",
                "src",
            }:
                continue
        else:
            module_paths = getattr(module, "__path__", ())
            repository_namespace = False
            try:
                resolved_module_paths = tuple(module_paths)
            except (KeyError, RuntimeError):
                continue
            for module_path in resolved_module_paths:
                try:
                    relative_path = (
                        Path(module_path).resolve().relative_to(ROOT.resolve())
                    )
                except (OSError, RuntimeError, TypeError, ValueError):
                    continue
                if relative_path.parts and relative_path.parts[0] in {"modules", "src"}:
                    repository_namespace = True
                    break
            if not repository_namespace:
                continue
        _CANONICAL_MODULES.setdefault(name, module)


def _restore_canonical_modules(*, excluded: set[str]) -> None:
    """Restore saved module identities after collection-time test stubs."""

    for name, module in sorted(
        _CANONICAL_MODULES.items(), key=lambda item: item[0].count(".")
    ):
        if name in excluded:
            continue
        sys.modules[name] = module
        parent_name, separator, child_name = name.rpartition(".")
        if not separator:
            continue
        parent = sys.modules.get(parent_name)
        if parent is not None:
            setattr(parent, child_name, module)


def _restore_parent_attribute(name: str, module: types.ModuleType) -> None:
    """Bind ``module`` back onto its parent package when one exists."""

    parent_name, separator, child_name = name.rpartition(".")
    if not separator:
        return
    parent = sys.modules.get(parent_name)
    if parent is not None:
        setattr(parent, child_name, module)


def _reset_test_import_boundaries(next_module: Path) -> None:
    """Discard import-path and module-cache changes leaked by prior test modules."""

    _remember_canonical_modules()
    shared_vendor = (ROOT / "plugins" / "_shared" / "vendor").resolve()
    cleaned_path = []
    for entry in sys.path:
        try:
            resolved = Path(entry).resolve()
        except (OSError, RuntimeError):
            cleaned_path.append(entry)
            continue
        if resolved == shared_vendor or shared_vendor in resolved.parents:
            continue
        cleaned_path.append(entry)
    root_text = str(ROOT)
    cleaned_path = [entry for entry in cleaned_path if entry != root_text]
    sys.path[:] = [root_text, *cleaned_path]

    names_to_drop: set[str] = set()
    for name, module in sys.modules.items():
        if name != "modules" and not name.startswith(("modules.", "src.")):
            continue
        module_file = getattr(module, "__file__", None)
        if module_file:
            try:
                resolved_file = Path(module_file).resolve()
            except (OSError, RuntimeError):
                continue
            if shared_vendor == resolved_file or shared_vendor in resolved_file.parents:
                names_to_drop.add(name)
            continue
        if _canonical_module_exists(name):
            names_to_drop.add(name)

    for name in sorted(names_to_drop, key=lambda value: value.count("."), reverse=True):
        _drop_imported_module(name)
    _restore_canonical_modules(excluded=set())


def pytest_pycollect_makemodule(module_path: Path, parent: object) -> None:
    """Restore canonical import boundaries before collecting each test module."""

    del parent
    _reset_test_import_boundaries(module_path)
    return None


def pytest_collectstart(collector: object) -> None:
    """Reset again immediately before pytest imports a collected test module."""

    module_path = getattr(collector, "path", None)
    if not isinstance(module_path, Path):
        return
    try:
        relative_path = module_path.resolve().relative_to((ROOT / "tests").resolve())
    except (OSError, RuntimeError, ValueError):
        return
    if relative_path.suffix == ".py" and relative_path.name.startswith("test_"):
        _reset_test_import_boundaries(module_path)


def pytest_collection_finish(session: object) -> None:
    """Leave canonical imports active after all test modules are collected."""

    del session
    _reset_test_import_boundaries(ROOT / "tests" / "_after_collection.py")
    os.environ.clear()
    os.environ.update(_COLLECTION_ENVIRONMENT)


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item: object) -> None:
    """Snapshot imports before any test fixture can install direct stubs."""

    nodeid = getattr(item, "nodeid", None)
    if not isinstance(nodeid, str):
        return
    _discard_plugin_runtime_imports()
    _remember_canonical_modules()
    _RUNTIME_IMPORT_SNAPSHOTS[nodeid] = (
        dict(sys.modules),
        list(sys.path),
        dict(os.environ),
    )


@pytest.hookimpl(trylast=True)
def pytest_runtest_teardown(item: object) -> None:
    """Restore module identities and paths changed without monkeypatch."""

    nodeid = getattr(item, "nodeid", None)
    if not isinstance(nodeid, str):
        return
    snapshot = _RUNTIME_IMPORT_SNAPSHOTS.pop(nodeid, None)
    if snapshot is None:
        return
    prior_modules, prior_path, prior_environment = snapshot

    for name, module in list(sys.modules.items()):
        if name in prior_modules:
            continue
        if getattr(module, "__spec__", None) is None or _is_plugin_local_module(module):
            _drop_imported_module(name)

    for name, module in prior_modules.items():
        module_changed = sys.modules.get(name) is not module
        if module_changed:
            sys.modules[name] = module
        if module_changed or name == "modules" or name.startswith(("modules.", "src.")):
            _restore_parent_attribute(name, module)

    sys.path[:] = prior_path
    os.environ.clear()
    os.environ.update(prior_environment)
    _restore_canonical_modules(excluded=set())


def _ensure_jinja_stub() -> None:
    """Provide a minimal jinja2 stub so module imports remain self-contained."""

    if "jinja2" in sys.modules:
        return
    jinja2_stub = types.ModuleType("jinja2")

    def pass_context(func: Callable[..., object]) -> Callable[..., object]:
        return func

    class FileSystemLoader:
        def __init__(self, directory: object) -> None:
            self.directory = directory

    class _Template:
        def render(self, context: dict[str, object]) -> str:
            payload = {
                "preview_styles": context.get("preview_styles", []),
                "preview_scripts": context.get("preview_scripts", []),
                "preview_allowlist": context.get("preview_allowlist", []),
            }
            return (
                '<script id="slidesEditorBootstrap" type="application/json">'
                f"{json.dumps(payload)}"
                "</script>"
            )

    class Environment:
        def __init__(self, **_: object) -> None:
            self.globals: dict[str, object] = {}

        def get_template(self, _name: str) -> _Template:
            return _Template()

    jinja2_stub.pass_context = pass_context
    jinja2_stub.FileSystemLoader = FileSystemLoader
    jinja2_stub.Environment = Environment
    sys.modules["jinja2"] = jinja2_stub


def _ensure_legacy_identify_columns_ui_stub() -> None:
    """Provide the deleted legacy UI boundary required by old unit-test imports."""

    if "ui.identify_columns_ui" in sys.modules:
        return

    ui_package = sys.modules.setdefault("ui", types.ModuleType("ui"))
    ui_package.__path__ = []
    identify_columns_ui = types.ModuleType("ui.identify_columns_ui")

    class IdentifyColumnsUI:
        def show_messages(self, _messages: object) -> None:
            return None

    def show_input_data(
        df: object,
        _container: object,
        param_dict: dict[str, object],
    ) -> tuple[object, dict[str, object]]:
        return df, param_dict

    identify_columns_ui.IdentifyColumnsUI = IdentifyColumnsUI
    identify_columns_ui.show_input_data = show_input_data
    ui_package.identify_columns_ui = identify_columns_ui
    sys.modules["ui.identify_columns_ui"] = identify_columns_ui


_ensure_jinja_stub()
_ensure_legacy_identify_columns_ui_stub()
ensure_tagging_stub()
