"""Build Codex and Cowork releases together from each product's canonical version."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import subprocess
import sys
from pathlib import Path
from zipfile import BadZipFile, ZipFile

__all__ = ["main", "verify_versions"]
ROOT = Path(__file__).resolve().parents[1]
PRODUCTS = ("vera", "clara", "lucia")
LOGGER = logging.getLogger(__name__)


def _archive_version(path: Path, product: str) -> str:
    versions = []
    with ZipFile(path) as archive:
        for name in archive.namelist():
            if not name.endswith(
                (".codex-plugin/plugin.json", ".claude-plugin/plugin.json")
            ):
                continue
            manifest = json.loads(archive.read(name))
            if manifest.get("name") == product:
                versions.append(manifest["version"])
    if len(versions) != 1:
        raise ValueError(f"{path}: expected one {product} manifest")
    return versions[0]


def verify_versions(root: Path, products: tuple[str, ...]) -> dict[str, str]:
    """Compare exact manifest versions and public ZIP bytes, not semantic behavior."""
    result = {}
    for product in products:
        source = root / "plugins" / product / ".codex-plugin/plugin.json"
        version = json.loads(source.read_text())["version"]
        directory = root / "plugin_packages" / product
        archives = [
            directory / f"{product}-plugin.zip",
            directory / f"{product}-chatgpt-upload.zip",
            directory / f"{product}-claude-plugin.zip",
        ]
        public = (
            root
            / "static/shared"
            / product
            / "downloads"
            / f"{product}-cowork-plugin.zip"
        )
        for path in [*archives, public]:
            actual = _archive_version(path, product)
            if actual != version:
                raise ValueError(
                    f"{path}: version {actual}; canonical version is {version}"
                )
        if (
            hashlib.sha256(public.read_bytes()).digest()
            != hashlib.sha256(archives[-1].read_bytes()).digest()
        ):
            raise ValueError(
                f"{product}: public Cowork ZIP differs from the built release"
            )
        result[product] = version
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("products", nargs="*", choices=PRODUCTS)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check source drift and version alignment without writing.",
    )
    args = parser.parse_args(argv)
    products = tuple(args.products) or PRODUCTS
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    suffix = ["--check"] if args.check else []
    commands = [["scripts/build_codex_plugin_zip.py", *products, *suffix]]
    commands.extend(
        [
            "scripts/build_codex_plugin_zip.py",
            name,
            "--chatgpt-upload",
            f"plugin_packages/{name}/{name}-chatgpt-upload.zip",
            *suffix,
        ]
        for name in products
    )
    commands.append(["scripts/build_claude_plugin_zip.py", *products, *suffix])
    try:
        for command in commands:
            subprocess.run([sys.executable, *command], cwd=ROOT, check=True)
        versions = verify_versions(ROOT, products)
    except (OSError, ValueError, BadZipFile, subprocess.CalledProcessError) as exc:
        LOGGER.error("Release alignment failed: %s", exc)
        return 1
    for name, version in versions.items():
        LOGGER.info("[OK] %s %s: Codex and Cowork packages aligned", name, version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
