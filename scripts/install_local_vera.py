"""Stage and serialize a verified local Vera update through supported Codex commands.

This updates only the selected local distribution. It does not publish anything.
All cooperating installers must use this entrypoint; Codex's own UI/CLI does not
participate in our transaction lock.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins/vera/scripts"))
from verified_execution import (  # noqa: E402
    execution_package_id,
    execution_store_lock,
    prepare_execution_root,
    release_execution_root,
)

__all__ = ["install", "main"]
LOGGER = logging.getLogger(__name__)


def _codex(arguments: list[str]) -> dict[str, Any]:
    result = subprocess.run(
        ["codex", "plugin", *arguments, "--json"],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return json.loads(result.stdout)


def _source(command: Callable, name: str) -> Path | None:
    entries = command(["marketplace", "list"])["marketplaces"]
    selected = [entry for entry in entries if entry["name"] == name]
    if not selected:
        return None
    if (
        len(selected) != 1
        or selected[0].get("marketplaceSource", {}).get("sourceType") != "local"
    ):
        raise ValueError("The selected marketplace is not one local source")
    return Path(selected[0]["marketplaceSource"]["source"]).resolve()


def _remove_owned_source(path: Path) -> None:
    """Remove only installer-owned code, never follow links into caller files."""
    for directory, _, files in os.walk(path):
        Path(directory).chmod(0o700)
        for name in files:
            target = Path(directory) / name
            if not target.is_symlink():
                target.chmod(0o600)
    shutil.rmtree(path)


def _recover_staging_sources(destination: Path) -> None:
    """Recover interrupted copies only when their ownership receipt still matches."""
    for source in destination.glob(".staging-*"):
        receipt = source / ".managed-source.json"
        if source.is_symlink() or not receipt.is_file() or receipt.is_symlink():
            continue
        try:
            data = json.loads(receipt.read_text())
            info = source.stat()
            if (
                set(data) == {"package_sha256", "identity"}
                and re.fullmatch("[0-9a-f]{64}", data["package_sha256"])
                and data["identity"] == [info.st_dev, info.st_ino]
            ):
                _remove_owned_source(source)
        except (OSError, ValueError, TypeError):
            LOGGER.warning("Unrecognized interrupted source retained: %s", source)


def _collect_sources(destination: Path, keep: set[Path]) -> None:
    for source in destination.iterdir():
        if (
            source in keep
            or source.is_symlink()
            or not re.fullmatch("[0-9a-f]{64}", source.name)
        ):
            continue
        receipt = source / ".managed-source.json"
        if not receipt.is_file() or receipt.is_symlink():
            continue
        data = json.loads(receipt.read_text())
        info = source.stat()
        if data == {
            "package_sha256": source.name,
            "identity": [info.st_dev, info.st_ino],
        }:
            _remove_owned_source(source)


def install(
    source: Path,
    destination: Path,
    expected_version: str,
    *,
    command: Callable = _codex,
) -> dict[str, Any]:
    """Validate before replacing registration, verify selection, roll back failures."""
    source = source.resolve()
    catalog = json.loads((source / ".agents/plugins/marketplace.json").read_text())
    if catalog["name"] != "mp-vera" or len(catalog["plugins"]) != 1:
        raise ValueError("Select the single-product mp-vera local distribution")
    plugin = catalog["plugins"][0]
    if plugin["name"] != "vera" or plugin["source"] != {
        "source": "local",
        "path": "./plugins/vera",
    }:
        raise ValueError("Local Vera source must be ./plugins/vera")
    original = source / "plugins/vera"
    metadata = json.loads((original / ".codex-plugin/plugin.json").read_text())
    if metadata["name"] != "vera" or metadata["version"] != expected_version:
        raise ValueError("The selected source is not the requested Vera version")
    with execution_store_lock("install"):
        pinned = prepare_execution_root(original, None, shared=True)
        try:
            digest = execution_package_id(pinned)
            if digest is None:
                raise ValueError("A local install requires an indexed release package")
            destination = destination.resolve()
            destination.mkdir(parents=True, exist_ok=True, mode=0o700)
            _recover_staging_sources(destination)
            staged = destination / digest
            if not staged.exists():
                temporary = Path(tempfile.mkdtemp(prefix=".staging-", dir=destination))
                try:
                    info = temporary.stat()
                    (temporary / ".managed-source.json").write_text(
                        json.dumps(
                            {
                                "package_sha256": digest,
                                "identity": [info.st_dev, info.st_ino],
                            }
                        )
                    )
                    shutil.copytree(pinned, temporary / "plugins/vera")
                    target = temporary / ".agents/plugins/marketplace.json"
                    target.parent.mkdir(parents=True)
                    target.write_text(json.dumps(catalog, indent=2) + "\n")
                    temporary.rename(staged)
                finally:
                    if temporary.exists():
                        _remove_owned_source(temporary)
            if (
                json.loads((staged / ".agents/plugins/marketplace.json").read_text())
                != catalog
            ):
                raise ValueError("Staged local catalog changed")
            verified = prepare_execution_root(
                staged / "plugins/vera", None, shared=True
            )
            release_execution_root(verified)
            if execution_package_id(staged / "plugins/vera") != digest:
                raise ValueError("Staged local package changed")
            previous = _source(command, catalog["name"])
            switched = previous != staged
            try:
                if switched:
                    if previous is not None:
                        command(["marketplace", "remove", catalog["name"]])
                    command(["marketplace", "add", str(staged)])
                if _source(command, catalog["name"]) != staged:
                    raise ValueError(
                        "Codex selected another local source; installation was not started"
                    )
                installed = command(["add", "vera@mp-vera"])
                current = command(["list"])["installed"]
                enabled = [
                    entry
                    for entry in current
                    if entry.get("name") == "vera"
                    and entry.get("enabled")
                    and entry.get("installed")
                ]
                if (
                    len(enabled) != 1
                    or enabled[0].get("pluginId") != "vera@mp-vera"
                    or enabled[0].get("version") != expected_version
                ):
                    raise ValueError(
                        "Enabled Vera installation differs from the requested release"
                    )
                if _source(command, catalog["name"]) != staged:
                    raise ValueError("Local source changed during installation")
            except (OSError, ValueError, KeyError, subprocess.SubprocessError):
                # Restore only the registration changed by this transaction. Do
                # not overwrite a third-party update that ignored this lock.
                if switched and _source(command, catalog["name"]) in {staged, None}:
                    if _source(command, catalog["name"]) is not None:
                        command(["marketplace", "remove", catalog["name"]])
                    if previous is not None:
                        command(["marketplace", "add", str(previous)])
                        command(["add", "vera@mp-vera"])
                raise
            _collect_sources(
                destination, {staged} | ({previous} if previous is not None else set())
            )
            return {
                "version": expected_version,
                "package_sha256": digest,
                "source": str(staged),
                "installation": installed,
                "active_chat_acceptance": "requires a fresh chat",
            }
        finally:
            release_execution_root(pinned)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source", type=Path, help="Extracted vera-codex-plugin distribution"
    )
    parser.add_argument(
        "--destination",
        type=Path,
        required=True,
        help="Stable directory reserved for managed local Vera sources",
    )
    parser.add_argument("--expected-version", required=True)
    args = parser.parse_args()
    result = install(args.source, args.destination, args.expected_version)
    sys.stdout.write(json.dumps(result, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
