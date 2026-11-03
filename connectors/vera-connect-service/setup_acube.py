"""Register the local A-Cube MCP for an installed Vera in Codex Desktop."""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

__all__ = ["main"]


def main() -> None:
    """Prepare the locked JS dependency tree and register a credential-free launch."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--vera-root",
        required=True,
        type=Path,
        help="Enabled Vera plugin directory containing modules/",
    )
    parser.add_argument(
        "--python",
        type=Path,
        help="Prepared Vera Python; defaults to the interpreter running this script",
    )
    parser.add_argument(
        "--environment", choices=("sandbox", "production"), default="sandbox"
    )
    parser.add_argument(
        "--vault", help="Selected 1Password vault name or ID; use with --item"
    )
    parser.add_argument("--item", help="Selected Login name or ID; use with --vault")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace a different registration of this same name",
    )
    args = parser.parse_args()
    if bool(args.vault) != bool(args.item):
        parser.error("Specify both --vault and --item, or neither.")
    root = args.vera_root.expanduser().resolve()
    if not (root / ".codex-plugin/plugin.json").is_file():
        parser.error("Select the enabled Vera plugin root.")
    components = [
        root / "modules" / mod / "scripts"
        for mod in ("studio-archive", "browser-automation")
    ]
    python = (args.python or Path(sys.executable)).expanduser().absolute()
    probe = subprocess.run(
        [
            str(python),
            "-I",
            "-c",
            "import sys; sys.path[:0] = sys.argv[1:]; import archive_core, ade_acquisition.artifacts",
            *map(str, components),
        ],
        capture_output=True,
    )
    if probe.returncode:
        parser.error(
            "The selected Vera installation and interpreter cannot load its Archive and invoice modules. Complete Vera's ordinary runtime setup."
        )
    here = Path(__file__).resolve().parent
    adapter = here / "connectors" / "vera-acube"
    if not adapter.is_dir():
        adapter = here.parent / "vera-acube"  # source checkout
    node, pnpm, codex = map(shutil.which, ("node", "pnpm", "codex"))
    if not all((node, pnpm, codex)):
        parser.error("Install Node 20+, pnpm and Codex CLI before connecting A-Cube.")
    if (
        int(
            subprocess.check_output(
                [node, "-p", "process.versions.node.split('.')[0]"], text=True
            )
        )
        < 20
    ):
        parser.error("Node 20 or newer is required.")
    name = "vera_acube" if args.environment == "sandbox" else "vera_acube_production"
    launch = [
        str(adapter / "server.mjs"),
        "--" + args.environment,
        "--vera-root",
        str(root),
        "--python",
        str(python),
    ]
    if args.vault:
        launch += ["--vault", args.vault, "--item", args.item]
    current = subprocess.run(
        [codex, "mcp", "get", name, "--json"], capture_output=True, text=True
    )
    identical = False
    if current.returncode == 0:
        cfg = json.loads(current.stdout)
        transport = cfg.get("transport", {})
        identical = (
            cfg.get("enabled") is True
            and transport.get("command") == node
            and transport.get("args") == launch
            and not transport.get("env")
            and not transport.get("env_vars")
        )
        if not identical and not args.replace:
            parser.error(
                f"{name} already has different settings. Review them locally and use --replace only for an intended change."
            )
    elif "no mcp server named" not in current.stderr.lower():
        parser.error("Could not inspect the named Codex registration.")
    subprocess.run(
        [pnpm, "install", "--frozen-lockfile", "--ignore-scripts"],
        cwd=adapter,
        check=True,
        env={**os.environ, "CI": "true"},
    )
    if not identical:
        subprocess.run([codex, "mcp", "add", name, "--", node, *launch], check=True)
    logging.info(
        "Registered %s. Check connection_status and then perform a scoped provider read.",
        name,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
