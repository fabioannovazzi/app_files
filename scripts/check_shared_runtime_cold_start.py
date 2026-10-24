"""Native acceptance of extracted plugins with no Python 3.12 or uv on PATH."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

__all__ = ["main"]


def check_scatter(root: Path, base: Path) -> None:
    """Exercise real chart preparation with identical synthetic rows on every host."""
    source = base / "scatter.csv"
    source.write_text(
        "Product,Segment,Marketing_EUR,Sales_EUR,Units\n"
        "A,North,1000,6200,120\nB,North,1500,7300,150\n"
        "C,South,2000,9800,190\nD,South,2500,10500,220\n"
    )
    recipe = base / "recipe.json"
    recipe.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "source_file": str(source),
                "language": "en",
                "mappings": {
                    "x_metric_column": "Marketing_EUR",
                    "y_metric_column": "Sales_EUR",
                    "bubble_size_metric_column": "Units",
                    "dimensions": ["Product", "Segment"],
                    "dot_dimension": "Product",
                    "color_dimension": "Segment",
                    "small_multiples_dimension": "Segment",
                    "period_column": None,
                    "date_column": None,
                },
                "options": {
                    "currency": "EUR",
                    "color_palette": "bain",
                    "charts": [],
                    "small_multiples": True,
                    "max_chart_items": 12,
                    "small_multiples_max_panels": 6,
                },
            }
        )
    )
    output = base / "scatter-output"
    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts/managed_python_runtime.py"),
            "--module",
            "scatter-bubble-analysis",
            "run",
            "scripts/run_scatter_bubble.py",
            str(source),
            "--recipe",
            str(recipe),
            "--output-dir",
            str(output),
            "--artifact-mode",
            "data_only",
        ],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    with (output / "scatter_bubble_canonical.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 4
    assert sum(float(row["Sales_EUR"]) for row in rows) == 33800
    assert sum(float(row["Marketing_EUR"]) for row in rows) == 7000


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--host-package", choices=("codex", "cowork"), default="codex")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    suffix = "plugin" if args.host_package == "codex" else "claude-plugin"
    for product in ("vera", "clara", "lucia"):
        archive = repo / f"plugin_packages/{product}/{product}-{suffix}.zip"
        if not archive.is_file():
            parser.error(
                f"Local build artifact missing: {archive}. Build with "
                "python scripts/build_product_release.py vera lucia clara "
                "or download this commit's product-archives CI artifact first."
            )
    results = []
    with tempfile.TemporaryDirectory(prefix="shared-cold-") as temporary:
        base = Path(temporary).resolve()
        os.environ["MPARANZA_RUNTIME_ROOT"] = str(base / "runtime")
        os.environ["MPARANZA_INCIDENT_DELIVERY"] = "local-only"
        os.environ["MPARANZA_INCIDENT_STATE_DIR"] = str(base / "incident-state")
        os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
        sys.dont_write_bytecode = True
        os.environ["PATH"] = ""
        for product, component in [
            ("vera", "studio-archive"),
            ("clara", "reporting-engine"),
            ("lucia", "studio-archive"),
        ]:
            extracted = base / "packages" / product
            with ZipFile(
                repo / f"plugin_packages/{product}/{product}-{suffix}.zip"
            ) as archive:
                archive.extractall(extracted)
            root = (
                extracted / f"{product}-codex-plugin/plugins/{product}"
                if args.host_package == "codex"
                else extracted
            )
            spec = importlib.util.spec_from_file_location(
                f"cold_{product}", root / "scripts/_managed_python_runtime.py"
            )
            manager = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = manager
            spec.loader.exec_module(manager)
            # Native CI uses 3.14. Local 3.12 runs simulate only discovery's host version.
            manager.sys = SimpleNamespace(
                **{
                    name: getattr(sys, name)
                    for name in dir(sys)
                    if not name.startswith("__")
                }
            )
            manager.sys.version_info = (3, 14, 0)
            ok, target, detail = manager.ensure_runtime(root, component)
            if not ok:
                raise RuntimeError(detail)
            command = [
                sys.executable,
                str(root / "scripts/check_dependencies.py"),
                "--module",
                component,
            ]
            checked = subprocess.run(
                command, capture_output=True, text=True, timeout=180, check=False
            )
            if checked.returncode:
                raise RuntimeError(checked.stdout + checked.stderr)
            launched = subprocess.run(
                [
                    sys.executable,
                    str(root / "scripts/managed_python_runtime.py"),
                    "--module",
                    component,
                    "run",
                    "scripts/check_dependencies.py",
                    "--help",
                ],
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
            if launched.returncode:
                raise RuntimeError(launched.stdout + launched.stderr)
            receipt = json.loads((target / ".mparanza-shared-ready.json").read_text())
            if results:
                assert (
                    receipt == results[0]["receipt"]
                ), "Product handoff changed the shared environment"
            if product == "clara":
                check_scatter(root, base)
            results.append(
                {
                    "product": product,
                    "target": str(target),
                    "managed_python": subprocess.check_output(
                        [
                            str(manager.runtime_python(target)),
                            "-I",
                            "-S",
                            "-c",
                            "import sys; print(sys.version)",
                        ],
                        text=True,
                    ).strip(),
                    "check": "pass",
                    "launcher": "pass",
                    "receipt": receipt,
                    "core_lock_sha256": hashlib.sha256(
                        (root / "requirements-shared-core.lock").read_bytes()
                    ).hexdigest(),
                }
            )
        assert len({row["target"] for row in results}) == 1
        assert len(list((base / "runtime").rglob("pyvenv.cfg"))) == 1
        args.output.write_text(
            json.dumps(
                {
                    "host_python": sys.version,
                    "platform": sys.platform,
                    "host_package": args.host_package,
                    "path_empty": True,
                    "scatter_data": "pass",
                    "native_host_ui": "not_exercised",
                    "products": results,
                },
                indent=2,
            )
            + "\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
