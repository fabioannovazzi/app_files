"""Check Python dependencies declared by this Codex plugin."""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import re
import sys
import tempfile
import warnings
from pathlib import Path

PACKAGE_IMPORTS = {
    "pillow": "PIL",
    "python-docx": "docx",
    "python-dateutil": "dateutil",
}
PLOT_EXPORT_REQUIREMENTS = {"plotly", "kaleido"}
VENDORED_LEGACY_IMPORTS = (
    "modules.charting.draw_waterfall",
    "modules.charting.legacy_draw_waterfall",
    "modules.charting.update_layouts",
    "modules.charting.make_titles",
)


def plugin_root() -> Path:
    """Return the plugin root directory."""

    return Path(__file__).resolve().parents[1]


def requirement_name(line: str) -> str:
    """Return the package name from one requirements.txt line."""

    cleaned = line.split("#", 1)[0].strip()
    if not cleaned or cleaned.startswith(("-", "git+", "http://", "https://")):
        return ""
    match = re.match(r"([A-Za-z0-9_.-]+)", cleaned)
    return match.group(1).lower() if match else ""


def import_name(package_name: str) -> str:
    """Return the import module name for a package name."""

    return PACKAGE_IMPORTS.get(package_name.lower(), package_name.replace("-", "_"))


def selected_requirement_files(explicit_files: list[str]) -> list[Path]:
    """Return requirement files to check."""

    root = plugin_root()
    files = (
        [root / name for name in explicit_files]
        if explicit_files
        else [root / "requirements.txt"]
    )
    return [path for path in files if path.exists()]


def collect_import_warnings(module_name: str) -> list[str]:
    """Import a dependency and return warnings raised during import."""

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        importlib.import_module(module_name)
    return [f"{warning.category.__name__}: {warning.message}" for warning in caught]


def check_plotly_png_export() -> tuple[str | None, str | None]:
    """Return an export error and optional fallback warning."""

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            import plotly.graph_objects as go

            with tempfile.TemporaryDirectory() as tmp_dir:
                output = Path(tmp_dir) / "plotly_export_check.png"
                fig = go.Figure(
                    go.Waterfall(
                        orientation="h",
                        measure=["absolute", "relative", "total"],
                        y=["P0", "Variance", "P1"],
                        x=[100, 25, 125],
                    )
                )
                fig.write_image(str(output), format="png")
                if not output.exists() or output.stat().st_size == 0:
                    return "Plotly PNG export produced an empty file", None
    except (ImportError, ModuleNotFoundError, OSError, RuntimeError, ValueError) as exc:
        try:
            from PIL import Image, ImageDraw

            with tempfile.TemporaryDirectory() as tmp_dir:
                output = Path(tmp_dir) / "fallback_export_check.png"
                image = Image.new("RGB", (120, 80), "#FFFFFF")
                draw = ImageDraw.Draw(image)
                draw.rectangle((10, 25, 100, 55), fill="#343434")
                image.save(output, format="PNG")
                if output.exists() and output.stat().st_size > 0:
                    return None, (
                        "Plotly/Kaleido PNG export failed; "
                        f"Pillow fallback is available: {exc}"
                    )
        except (ImportError, ModuleNotFoundError, OSError, RuntimeError, ValueError):
            pass
        return str(exc), None
    return None, None


def check_vendored_legacy_imports() -> list[tuple[str, str]]:
    """Return vendored legacy import failures."""

    vendor_root = plugin_root() / "vendor"
    repo_shared_root = plugin_root().parent / "_shared" / "variance" / "vendor"
    legacy_root = (
        repo_shared_root
        if (repo_shared_root / "modules" / "__init__.py").exists()
        else vendor_root
    )
    legacy_text = str(legacy_root)
    if legacy_text not in sys.path:
        sys.path.insert(0, legacy_text)
    failures: list[tuple[str, str]] = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for module_name in VENDORED_LEGACY_IMPORTS:
            try:
                importlib.import_module(module_name)
            except (ImportError, ModuleNotFoundError) as exc:
                failures.append((module_name, str(exc)))
    return failures


def main() -> int:
    """Run dependency checks."""

    parser = argparse.ArgumentParser(
        description="Check this Codex plugin's Python dependencies."
    )
    parser.add_argument(
        "--requirements",
        action="append",
        default=[],
        help="Specific requirements file under the plugin root. May be passed more than once.",
    )
    args = parser.parse_args()

    files = selected_requirement_files(args.requirements)
    if not files:
        print(
            "MISSING_REQUIREMENTS_FILE: no requirements file found in this plugin package"
        )
        return 1

    missing: list[tuple[str, str, str]] = []
    import_failures: list[tuple[str, str, str, str]] = []
    dependency_warnings: list[tuple[str, str, str, str]] = []
    requested_packages: set[str] = set()
    for requirements_file in files:
        for line in requirements_file.read_text(encoding="utf-8").splitlines():
            package = requirement_name(line)
            if not package:
                continue
            requested_packages.add(package)
            module_name = import_name(package)
            if importlib.util.find_spec(module_name) is None:
                missing.append((requirements_file.name, package, module_name))
                continue
            try:
                warning_messages = collect_import_warnings(module_name)
            except (ImportError, ModuleNotFoundError) as exc:
                import_failures.append(
                    (requirements_file.name, package, module_name, str(exc))
                )
                continue
            for message in warning_messages:
                dependency_warnings.append(
                    (requirements_file.name, package, module_name, message)
                )

    plotly_export_error: str | None = None
    plotly_export_warning: str | None = None
    if PLOT_EXPORT_REQUIREMENTS <= requested_packages and not (
        missing or import_failures
    ):
        plotly_export_error, plotly_export_warning = check_plotly_png_export()
    legacy_import_failures = check_vendored_legacy_imports()

    if missing or import_failures or legacy_import_failures:
        print("MISSING_DEPENDENCIES")
        for source_file, package, module_name in missing:
            print(f"- {package} ({module_name}) from {source_file}")
        for source_file, package, module_name, detail in import_failures:
            print(
                f"- {package} ({module_name}) from {source_file}: "
                f"import failed: {detail}"
            )
        for module_name, detail in legacy_import_failures:
            print(f"- vendored legacy module {module_name}: import failed: {detail}")
        install_files = " ".join(f"-r {path.name}" for path in files)
        print(
            f"Suggested install from plugin directory: python -m pip install {install_files}"
        )
        return 1

    if plotly_export_error:
        print("DEPENDENCY_EXPORT_FAILURE")
        print(f"- plotly/kaleido PNG export failed: {plotly_export_error}")
        print(
            "Suggested install from plugin directory: "
            "python -m pip install -r requirements.txt"
        )
        return 1

    if dependency_warnings:
        print("DEPENDENCY_WARNINGS")
        for source_file, package, module_name, message in dependency_warnings:
            print(f"- {package} ({module_name}) from {source_file}: {message}")
    if plotly_export_warning:
        print("OPTIONAL_EXPORT_FALLBACK")
        print(f"- plotly/kaleido export: {plotly_export_warning}")

    print("OK: all selected plugin dependencies are importable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
