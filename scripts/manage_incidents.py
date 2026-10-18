"""Operate the error queue and publish diagnosed, structured recovery remedies."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from zipfile import ZipFile

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.operational_incidents.contracts import Remedy
from modules.operational_incidents.store import IncidentStore
from modules.utilities.secrets_loader import load_env_from_secrets_file
from modules.workflow_usage.products import Product, product_name

__all__ = ["main", "verify_update_release"]


def verify_update_release(root: Path, product: Product, version: str) -> None:
    """Bind an update to both published host packages of the report's product."""
    product = product_name(product)
    for package, suffix in (
        (
            root / f"static/shared/{product}/downloads/{product}-cowork-plugin.zip",
            ".claude-plugin/plugin.json",
        ),
        (
            root / f"plugin_packages/{product}/{product}-plugin.zip",
            ".codex-plugin/plugin.json",
        ),
    ):
        with ZipFile(package) as archive:
            manifests = [
                json.loads(archive.read(name))
                for name in archive.namelist()
                if name.endswith(suffix)
            ]
            matching = [
                manifest for manifest in manifests if manifest.get("name") == product
            ]
            if len(matching) != 1 or matching[0]["version"] != version:
                raise ValueError(
                    f"Required version is not the deployed downloadable {product.title()} release on both hosts"
                )


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
    remedy.add_argument(
        "--input", type=Path, required=True, help="Remedy JSON file, or - for stdin"
    )
    remedy.add_argument("--expected-revision", type=int)
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
        value = Remedy.model_validate_json(
            sys.stdin.read()
            if str(args.input) == "-"
            else args.input.read_text(encoding="utf-8")
        )
        if value.kind == "update":
            reports = store.show(args.incident_id)["reports"]
            target = next(
                (
                    report
                    for report in reports
                    if report["report_id"] == str(value.target_report_id)
                ),
                None,
            )
            if target is None or value.required_version is None:
                parser.error("An update requires an exact original report and version")
            try:
                verify_update_release(
                    Path(__file__).resolve().parents[1],
                    product_name(target["product"]),
                    value.required_version,
                )
            except ValueError as exc:
                parser.error(str(exc))
        result = store.remedy(
            args.incident_id, value, expected_revision=args.expected_revision
        )
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
