#!/usr/bin/env python3
"""Build and verify the products' downloadable Antigravity packages from canonical source."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile, ZipInfo

from build_codex_plugin_zip import (
    RUNTIME_SUPPORT_FILES,
    expected_zip_entries,
    load_bundles,
    load_packages,
    verify_packaged_mcp,
    verify_zip_entries,
)

__all__ = ["build_package", "package_entries", "verify_package", "main"]

ROOT = Path(__file__).resolve().parents[1]
PRODUCTS = ("vera", "clara", "lucia")
LOGGER = logging.getLogger(__name__)
MCP_FIELDS = {
    "command",
    "serverUrl",
    "args",
    "env",
    "cwd",
    "headers",
    "authProviderType",
    "oauth",
    "disabled",
    "disabledTools",
}
INSTALL_README = """{title} per Google Antigravity / {title} for Google Antigravity

Istruzioni / Instructions:
https://mparanza.com/static/shared/{product}/antigravity/index.html

1. Estrai tutto lo ZIP. La cartella {product} contiene plugin.json.
   Extract the entire ZIP. The {product} folder contains plugin.json.
2. Con Antigravity CLI installato, esegui nel terminale sostituendo il percorso:
   With Antigravity CLI installed, run in a terminal using your actual path:
   agy plugin install "/path/to/{product}"
3. Verifica / Verify:
   agy plugin list
   agy agent
4. Nella cartella dei tuoi documenti, avvia {title} e accedi con Google:
   From your document folder, start {title} and sign in with Google:
   agy --agent {product}

Per Antigravity desktop/IDE, puoi invece copiare la cartella {product} in
.agents/plugins/ nella cartella del progetto e riaprire Antigravity.
For Antigravity desktop/IDE, you can instead copy the {product} folder into
.agents/plugins/ inside your project folder and reopen Antigravity.

Il pacchetto include skill, agente {title}, moduli, script e server MCP.
Le integrazioni specifiche di ChatGPT, Codex e Cowork dipendono dall'host.
The package includes skills, the {title} agent, modules, scripts and MCP servers.
ChatGPT, Codex and Cowork integrations depend on the host.
"""


def _json_bytes(value: object) -> bytes:
    """Encode stable, readable metadata."""
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def package_entries(product: str = "vera") -> dict[str, bytes]:
    """Project a complete product bundle into Antigravity's plugin layout."""
    if product not in PRODUCTS:
        raise ValueError(f"Unsupported Antigravity product: {product}")
    bundle = next(
        target
        for target in [*load_packages(), *load_bundles()]
        if target.target_name == product
    )
    source = expected_zip_entries(bundle)
    prefix = f"{bundle.package_root}/plugins/{product}/"
    excluded = {".mcp.json", ".app.json", "hooks/hooks.json"}
    entries = {
        f"{product}/" + name.removeprefix(prefix): content
        for name, content in source.items()
        if name.startswith(prefix) and name.removeprefix(prefix) not in excluded
    }
    # Clara's deck helpers need these canonical files inside the installed root.
    for relative in RUNTIME_SUPPORT_FILES.get(product, ()):
        entries[f"{product}/{relative.as_posix()}"] = source[
            f"{bundle.package_root}/{relative.as_posix()}"
        ]
    manifest = json.loads(entries[f"{product}/.codex-plugin/plugin.json"])
    entries[f"{product}/plugin.json"] = _json_bytes(
        {
            "$schema": "https://antigravity.google/schemas/v1/plugin.json",
            "name": product,
            "description": manifest["description"],
        }
    )
    servers = json.loads(source.get(prefix + ".mcp.json", b'{"mcpServers": {}}'))[
        "mcpServers"
    ]
    entries[f"{product}/mcp_config.json"] = _json_bytes(
        {
            "mcpServers": {
                name: {key: value for key, value in config.items() if key in MCP_FIELDS}
                for name, config in servers.items()
            }
        }
    )
    entries[f"{product}/agents/{product}.md"] = (
        ROOT / f"plugins/{product}/agents/{product}.md"
    ).read_bytes()
    entries[f"{product}/LEGGIMI_ANTIGRAVITY.txt"] = INSTALL_README.format(
        product=product, title=product.title()
    ).encode()
    if not servers:
        entries[f"{product}/LEGGIMI_ANTIGRAVITY.txt"] = (
            entries[f"{product}/LEGGIMI_ANTIGRAVITY.txt"]
            .replace(b"moduli, script e server MCP.", b"moduli e script locali.")
            .replace(
                b"modules, scripts and MCP servers.", b"modules and local scripts."
            )
        )
    return dict(sorted(entries.items()))


def _metadata(entries: dict[str, bytes], product: str) -> bytes:
    """Use the packaged version for the website label."""
    manifest = json.loads(entries[f"{product}/.codex-plugin/plugin.json"])
    return _json_bytes({"name": product, "version": manifest["version"]})


def verify_package(
    output: Path | None = None, metadata: Path | None = None, *, product: str = "vera"
) -> None:
    """Reject stale ZIP content and exercise its actual MCP configuration."""
    output = (
        output
        or ROOT / f"static/shared/{product}/downloads/{product}-antigravity-plugin.zip"
    )
    metadata = metadata or output.with_suffix(".json")
    entries = package_entries(product)
    verify_zip_entries(output, entries)
    if metadata.read_bytes() != _metadata(entries, product):
        raise ValueError("Antigravity download version does not match the package")
    servers = json.loads(entries[f"{product}/mcp_config.json"])["mcpServers"]
    errors = (
        verify_packaged_mcp(output, [product], config_name="mcp_config.json")
        if servers
        else []
    )
    if errors:
        raise ValueError("\n".join(errors))


def build_package(
    output: Path | None = None, metadata: Path | None = None, *, product: str = "vera"
) -> None:
    """Write a reproducible ZIP and its matching website metadata."""
    output = (
        output
        or ROOT / f"static/shared/{product}/downloads/{product}-antigravity-plugin.zip"
    )
    metadata = metadata or output.with_suffix(".json")
    entries = package_entries(product)
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    metadata.write_bytes(_metadata(entries, product))
    verify_package(output, metadata, product=product)


def main(argv: list[str] | None = None) -> int:
    """Build the public download or verify it without changes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("products", nargs="*", choices=PRODUCTS)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        for product in args.products or PRODUCTS:
            if args.check:
                verify_package(product=product)
            else:
                build_package(product=product)
            LOGGER.info("[OK] %s Antigravity download", product)
    except (OSError, ValueError, BadZipFile) as exc:
        LOGGER.error("Antigravity package failed: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
