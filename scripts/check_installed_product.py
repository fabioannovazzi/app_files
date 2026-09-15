"""Verify a live Codex installation and the skill exposed in this conversation."""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
from pathlib import Path
from typing import Any

__all__ = ["inspect_installation", "inspect_skill", "main"]
LOGGER = logging.getLogger(__name__)


def inspect_installation(
    inventory: dict[str, Any], product: str, expected_version: str
) -> list[str]:
    """Compare exact host identities, not cache directories or semantic claims."""
    if not isinstance(inventory, dict):
        return ["The host returned an invalid installed-plugin inventory."]
    installed = inventory.get("installed")
    if not isinstance(installed, list):
        return ["The host did not return an installed-plugin inventory."]
    enabled = [
        entry
        for entry in installed
        if isinstance(entry, dict)
        and entry.get("name") == product
        and entry.get("installed") is True
        and entry.get("enabled") is True
    ]
    if len(enabled) != 1:
        return [
            f"Expected one enabled {product} installation; observed {len(enabled)}."
        ]
    entry = enabled[0]
    failures = []
    source = entry.get("source")
    if (
        entry.get("pluginId") != f"{product}@openai-curated-remote"
        or not isinstance(source, dict)
        or source.get("source") != "remote"
    ):
        failures.append(
            f"{product} uses {entry.get('pluginId')}, not the official Marketplace "
            "installation. A local copy is not updated by Marketplace publication."
        )
    if entry.get("version") != expected_version:
        failures.append(
            f"Enabled {product}: {entry.get('version')}; expected {expected_version}."
        )
    return failures


def inspect_skill(skill_path: Path, product: str, expected_version: str) -> list[str]:
    """Check a path supplied from the host's current skill catalog, never discover it."""
    if not skill_path.is_file():
        return [
            "The currently exposed skill no longer exists. Start a fresh conversation."
        ]
    for parent in skill_path.resolve().parents:
        manifest = parent / ".codex-plugin/plugin.json"
        if manifest.is_file():
            data = json.loads(manifest.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return ["The exposed skill has an invalid plugin manifest."]
            if data.get("name") == product and data.get("version") == expected_version:
                return []
            return [
                f"The exposed skill belongs to {data.get('name')} "
                f"{data.get('version')}; expected {product} {expected_version}."
            ]
    return ["No installed plugin manifest owns the exposed skill path."]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("product", choices=("vera", "clara", "lucia"))
    parser.add_argument("--expected-version", required=True)
    parser.add_argument(
        "--skill-path",
        type=Path,
        required=True,
        help="Exact SKILL.md path exposed by the current host skill catalog.",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        result = subprocess.run(
            ["codex", "plugin", "list", "--json"],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        failures = inspect_installation(
            json.loads(result.stdout), args.product, args.expected_version
        )
        failures.extend(
            inspect_skill(args.skill_path, args.product, args.expected_version)
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        # CLI errors can contain service responses. Do not reproduce them in reports.
        LOGGER.error("Installation verification unavailable; this is not a pass.")
        return 1
    if failures:
        for failure in failures:
            LOGGER.error(failure)
        return 1
    LOGGER.info(
        "%s %s: one enabled official installation and matching exposed skill. "
        "User-visible behavior still requires the acceptance run.",
        args.product,
        args.expected_version,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
