"""Operate the error queue and publish diagnosed, structured recovery remedies."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.operational_incidents.contracts import Remedy
from modules.operational_incidents.store import IncidentStore
from modules.utilities.secrets_loader import load_env_from_secrets_file

__all__ = ["main"]


def main() -> None:
    """Require diagnosed evidence and validate published ZIPs for update remedies."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite-path", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list")
    listing.add_argument("--limit", type=int, default=100)
    show = commands.add_parser("show")
    show.add_argument("incident_id")
    installation = commands.add_parser("installation")
    installation.add_argument("installation_id")
    app = commands.add_parser("app")
    app.add_argument("app_installation_id")
    commands.add_parser("registry")
    remedy = commands.add_parser("remedy")
    remedy.add_argument("incident_id")
    remedy.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    load_env_from_secrets_file()
    store = IncidentStore(args.sqlite_path)
    result: dict[str, Any] | list[dict[str, Any]]
    if args.command == "list":
        result = store.queue(args.limit)
    elif args.command == "show":
        result = store.show(args.incident_id)
    elif args.command == "installation":
        result = store.installation(args.installation_id)
    elif args.command == "app":
        result = store.app_installation(args.app_installation_id)
    elif args.command == "registry":
        result = store.registry()
    else:
        value = Remedy.model_validate_json(args.input.read_text(encoding="utf-8"))
        if value.kind == "update":
            import zipfile

            root = Path(__file__).resolve().parents[1]
            for package, suffix in (
                (
                    root / "static/shared/vera/downloads/vera-cowork-plugin.zip",
                    ".claude-plugin/plugin.json",
                ),
                (
                    root / "plugin_packages/vera/vera-plugin.zip",
                    ".codex-plugin/plugin.json",
                ),
            ):
                with zipfile.ZipFile(package) as archive:
                    manifests = [
                        json.loads(archive.read(name))
                        for name in archive.namelist()
                        if name.endswith(suffix)
                    ]
                    product = [
                        manifest
                        for manifest in manifests
                        if manifest.get("name") == "vera"
                    ]
                    if (
                        len(product) != 1
                        or product[0]["version"] != value.required_version
                    ):
                        parser.error(
                            "Required version is not the deployed downloadable Vera release on both hosts"
                        )
        result = store.remedy(args.incident_id, value)
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
