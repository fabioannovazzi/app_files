"""Explicit local reporting for repository-only package acceptance runners."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

__all__ = ["configure_reporting", "reporting_settings", "script_command"]


def reporting_settings(root: Path, output: Path) -> dict[str, str]:
    """Keep synthetic diagnostics and device identity inside the test directory."""
    return {
        "delivery": "local-only",
        "plugin_root": str(root.resolve()),
        "state_dir": str((output / "incident-state").resolve()),
        "device_dir": str((output / "device-state").resolve()),
    }


def configure_reporting(root: Path, output: Path) -> Any:
    """Bind the exact extracted reporter for an in-process runtime check."""
    spec = importlib.util.spec_from_file_location(
        "operational_incidents", root / "scripts/operational_incidents.py"
    )
    assert spec and spec.loader
    reporter = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = reporter
    spec.loader.exec_module(reporter)
    reporter.configure_settings(reporting_settings(root, output))
    return reporter


def script_command(
    python: str, root: Path, output: Path, script: str, *arguments: str
) -> list[str]:
    """Run actual package code with explicit test settings before its entry point."""
    code = (
        "import json,runpy,sys; from pathlib import Path; "
        "root,settings,target=sys.argv[1:4]; sys.argv=sys.argv[3:]; "
        "sys.path.insert(0,str(Path(root)/'scripts')); "
        "import operational_incidents; "
        "operational_incidents.configure_settings(json.loads(settings)); "
        "sys.path.insert(0,str(Path(target).resolve().parent)); "
        "runpy.run_path(target,run_name='__main__')"
    )
    return [
        python,
        "-I",
        "-B",
        "-c",
        code,
        str(root.resolve()),
        json.dumps(reporting_settings(root, output)),
        script,
        *arguments,
    ]
