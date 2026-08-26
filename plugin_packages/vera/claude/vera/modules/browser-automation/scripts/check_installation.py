#!/usr/bin/env python3
"""Resolve and validate the Browser Automation installation under test."""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

__all__ = ["inspect_installation", "main", "resolve_plugin_manifest"]

LOGGER = logging.getLogger(__name__)
SUPPORTED_PLUGIN_NAMES = {"browser-automation", "vera"}
VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
REQUIRED_COMPONENT_PATHS = (
    "requirements.txt",
    "scripts/acceptance_fixture.py",
    "scripts/check_dependencies.py",
    "scripts/capability_pipeline.py",
    "scripts/capability_runtime.mjs",
    "scripts/discovery_pack.py",
    "scripts/discovery_runtime.mjs",
    "skills/browser-automation/SKILL.md",
)


def resolve_plugin_manifest(component_root: Path) -> Path:
    """Return the manifest owning this exact component without scanning caches."""

    root = component_root.resolve()
    candidates = (
        root.parent.parent / ".codex-plugin" / "plugin.json",
        root / ".codex-plugin" / "plugin.json",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise ValueError("No owning .codex-plugin/plugin.json found for this component.")


def inspect_installation(component_root: Path) -> dict[str, Any]:
    """Report compatibility from the active manifest and required local files.

    This check is deterministic because manifest parsing and required-file
    presence are mechanically verifiable. It deliberately does not compare the
    observed version with a historical release number.
    """

    root = component_root.resolve()
    manifest_path = resolve_plugin_manifest(root)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    name = manifest.get("name")
    version = manifest.get("version")
    if name not in SUPPORTED_PLUGIN_NAMES:
        raise ValueError(f"Unsupported owning plugin name: {name!r}.")
    if not isinstance(version, str) or VERSION_PATTERN.fullmatch(version) is None:
        raise ValueError("Owning plugin manifest has an invalid version.")

    missing = [
        relative_path
        for relative_path in REQUIRED_COMPONENT_PATHS
        if not (root / relative_path).is_file()
    ]
    if missing:
        raise ValueError(
            "Browser Automation installation is incomplete: " + ", ".join(missing)
        )

    return {
        "schema_version": "browser-automation-installation/v1",
        "status": "compatible",
        "plugin": {
            "name": name,
            "version": version,
            "manifest_path": str(manifest_path),
        },
        "component_root": str(root),
        "version_source": "active_plugin_manifest",
        "compatibility_basis": [
            "manifest_shape",
            "supported_plugin_name",
            "required_component_files",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    """Print one structured preflight result for the installation being run."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--component-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Browser Automation module root; defaults to this script's module.",
    )
    args = parser.parse_args(argv)
    try:
        result = inspect_installation(args.component_root)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        LOGGER.error("Browser Automation installation preflight failed: %s", error)
        return 1
    sys.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
