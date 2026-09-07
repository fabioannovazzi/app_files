"""Native acceptance of extracted plugins with no Python 3.12 or uv on PATH."""

from __future__ import annotations

import argparse
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    results = []
    with tempfile.TemporaryDirectory(prefix="shared-cold-") as temporary:
        base = Path(temporary).resolve()
        os.environ["MPARANZA_RUNTIME_ROOT"] = str(base / "runtime")
        os.environ["PATH"] = ""
        for product, component in [
            ("vera", "studio-archive"),
            ("clara", "reporting-engine"),
            ("lucia", "studio-archive"),
        ]:
            with ZipFile(
                repo / f"plugin_packages/{product}/{product}-plugin.zip"
            ) as archive:
                archive.extractall(base / "packages")
            root = base / f"packages/{product}-codex-plugin/plugins/{product}"
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
            results.append(
                {
                    "product": product,
                    "target": str(target),
                    "check": "pass",
                    "launcher": "pass",
                }
            )
        assert len({row["target"] for row in results}) == 1
        assert len(list((base / "runtime").rglob("pyvenv.cfg"))) == 1
        args.output.write_text(
            json.dumps(
                {
                    "host_python": sys.version,
                    "platform": sys.platform,
                    "path_empty": True,
                    "products": results,
                },
                indent=2,
            )
            + "\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
