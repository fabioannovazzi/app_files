#!/usr/bin/env python3
"""Build and verify Vera's downloadable Antigravity package from canonical source."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile, ZipInfo

from build_codex_plugin_zip import (
    expected_zip_entries,
    load_bundles,
    verify_packaged_mcp,
    verify_zip_entries,
)

__all__ = ["build_package", "package_entries", "verify_package", "main"]

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "static/shared/vera/downloads/vera-antigravity-plugin.zip"
METADATA = OUTPUT.with_suffix(".json")
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
INSTALL_README = """Vera per Google Antigravity / Vera for Google Antigravity

Istruzioni / Instructions:
https://mparanza.com/static/shared/vera/antigravity/index.html

1. Estrai tutto lo ZIP. La cartella vera contiene plugin.json.
   Extract the entire ZIP. The vera folder contains plugin.json.
2. Con Antigravity CLI installato, esegui nel terminale sostituendo il percorso:
   With Antigravity CLI installed, run in a terminal using your actual path:
   agy plugin install "/path/to/vera"
3. Verifica / Verify:
   agy plugin list
   agy agent
4. Nella cartella dei tuoi documenti, avvia Vera e accedi con Google:
   From your document folder, start Vera and sign in with Google:
   agy --agent vera

Per Antigravity desktop/IDE, puoi invece copiare la cartella vera in
.agents/plugins/ nella cartella del progetto e riaprire Antigravity.
For Antigravity desktop/IDE, you can instead copy the vera folder into
.agents/plugins/ inside your project folder and reopen Antigravity.

Il pacchetto include skill, agente Vera, moduli, script e server MCP.
Le integrazioni specifiche di ChatGPT, Codex e Cowork dipendono dall'host.
The package includes skills, the Vera agent, modules, scripts and MCP servers.
ChatGPT, Codex and Cowork integrations depend on the host.
"""


def _json_bytes(value: object) -> bytes:
    """Encode stable, readable metadata."""
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def package_entries() -> dict[str, bytes]:
    """Project the complete Vera bundle into Antigravity's plugin layout."""
    bundle = next(bundle for bundle in load_bundles() if bundle.name == "vera")
    source = expected_zip_entries(bundle)
    prefix = f"{bundle.package_root}/plugins/vera/"
    excluded = {".mcp.json", ".app.json", "hooks/hooks.json"}
    entries = {
        "vera/" + name.removeprefix(prefix): content
        for name, content in source.items()
        if name.startswith(prefix) and name.removeprefix(prefix) not in excluded
    }
    manifest = json.loads(entries["vera/.codex-plugin/plugin.json"])
    entries["vera/plugin.json"] = _json_bytes(
        {
            "$schema": "https://antigravity.google/schemas/v1/plugin.json",
            "name": "vera",
            "description": manifest["description"],
        }
    )
    servers = json.loads(source[prefix + ".mcp.json"])["mcpServers"]
    entries["vera/mcp_config.json"] = _json_bytes(
        {
            "mcpServers": {
                name: {key: value for key, value in config.items() if key in MCP_FIELDS}
                for name, config in servers.items()
            }
        }
    )
    entries["vera/agents/vera.md"] = (ROOT / "plugins/vera/agents/vera.md").read_bytes()
    entries["vera/LEGGIMI_ANTIGRAVITY.txt"] = INSTALL_README.encode()
    return dict(sorted(entries.items()))


def _metadata(entries: dict[str, bytes]) -> bytes:
    """Use the packaged version for the website label."""
    manifest = json.loads(entries["vera/.codex-plugin/plugin.json"])
    return _json_bytes({"name": "vera", "version": manifest["version"]})


def verify_package(output: Path = OUTPUT, metadata: Path = METADATA) -> None:
    """Reject stale ZIP content and exercise its actual MCP configuration."""
    entries = package_entries()
    verify_zip_entries(output, entries)
    if metadata.read_bytes() != _metadata(entries):
        raise ValueError("Antigravity download version does not match the package")
    errors = verify_packaged_mcp(output, ["vera"], config_name="mcp_config.json")
    if errors:
        raise ValueError("\n".join(errors))


def build_package(output: Path = OUTPUT, metadata: Path = METADATA) -> None:
    """Write a reproducible ZIP and its matching website metadata."""
    entries = package_entries()
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    metadata.write_bytes(_metadata(entries))
    verify_package(output, metadata)


def main(argv: list[str] | None = None) -> int:
    """Build the public download or verify it without changes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        if args.check:
            verify_package()
        else:
            build_package()
    except (OSError, ValueError, BadZipFile) as exc:
        LOGGER.error("Antigravity package failed: %s", exc)
        return 1
    LOGGER.info("[OK] %s", OUTPUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
