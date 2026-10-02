"""Explicit installer for the optional connector, outside client workspaces."""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import tomllib
import venv
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

__all__ = ["main", "config_text", "server_entry", "write_host_files"]

ENGINES = {
    "openai": ("privacy_filter", "OpenAI Privacy Filter"),
    "gliner2": ("gliner2_pii", "GLiNER2-PII"),
    "rizzo": ("rizzo_pii", "Rizzo PII"),
}


def server_entry(
    python: Path,
    input_dir: Path,
    output_dir: Path,
    model_dir: Path,
    engine: str = "openai",
    rizzo_port: int = 5005,
) -> tuple[str, dict[str, Any]]:
    """Use the same explicit command on each host; paths are never shell code."""
    args = [
        "-I",
        "-m",
        "mparanza_privacy_filter.server",
        "--input-dir",
        str(input_dir),
        "--output-dir",
        str(output_dir),
    ]
    if engine not in ("openai", "gliner2", "rizzo"):
        raise ValueError("unsupported_engine")
    if engine != "rizzo":
        args.extend(("--model-dir", str(model_dir)))
    if engine != "openai":
        args.extend(("--engine", engine))
    if engine == "rizzo":
        if type(rizzo_port) is not int or not 1 <= rizzo_port <= 65535:
            raise ValueError("invalid_rizzo_port")
        args.extend(("--rizzo-port", str(rizzo_port)))
    return ENGINES[engine][0], {"command": str(python), "args": args}


def config_text(
    python: Path,
    input_dir: Path,
    output_dir: Path,
    model_dir: Path,
    engine: str = "openai",
    rizzo_port: int = 5005,
) -> str:
    """Generate Codex TOML without editing or replacing existing user settings."""
    name, entry = server_entry(
        python, input_dir, output_dir, model_dir, engine, rizzo_port
    )
    return (
        f"[mcp_servers.{name}]\n"
        f"command = {json.dumps(entry['command'])}\n"
        f"args = {json.dumps(entry['args'])}\n"
        "startup_timeout_sec = 30\n"
        "tool_timeout_sec = 3600\n"
        "enabled = true\n"
    )


def write_host_files(
    runtime_dir: Path,
    python: Path,
    input_dir: Path,
    output_dir: Path,
    engine: str,
    rizzo_port: int,
) -> None:
    """Emit native host formats from one command, without changing host settings."""
    name, entry = server_entry(
        python, input_dir, output_dir, runtime_dir / "model", engine, rizzo_port
    )
    config = json.dumps({"mcpServers": {name: entry}}, indent=2) + "\n"
    (runtime_dir / "codex-mcp.toml").write_text(
        config_text(
            python, input_dir, output_dir, runtime_dir / "model", engine, rizzo_port
        ),
        encoding="utf-8",
    )
    (runtime_dir / "antigravity-mcp.json").write_text(config, encoding="utf-8")
    source = Path(__file__).resolve().parent
    version = tomllib.loads((source / "pyproject.toml").read_text())["project"][
        "version"
    ]
    title = ENGINES[engine][1]
    manifest = {
        "name": "mparanza-" + name.replace("_", "-"),
        "version": version,
        "description": f"Optional local {title} connector. Setup runs separately.",
        "author": {"name": "Mparanza", "url": "https://mparanza.com"},
        "mcpServers": "./.mcp.json",
    }
    guidance = (
        "---\nname: filter-local-documents\n"
        f"description: Use when the user explicitly asks to filter local documents with {title}.\n"
        "---\n\n"
        f"Use the {name}_status tool first. If it is not ready, follow SETUP.md.\n"
        "Pass a filename relative to the configured input directory, or its host-native\n"
        "absolute path. Cowork VM /sessions paths are not host paths. Do not open or\n"
        "attach the original in chat. Use the connector's file or batch tools to save\n"
        "a filtered .txt copy. Only read the artifact when the user requests it.\n"
        "Do not silently fall back to another engine or cloud processing.\n"
        "A successful run does not guarantee that every sensitive value was detected.\n"
    )
    with ZipFile(runtime_dir / "cowork-connector.zip", "w", ZIP_DEFLATED) as archive:
        archive.writestr(".claude-plugin/plugin.json", json.dumps(manifest, indent=2))
        archive.writestr(".mcp.json", config)
        archive.writestr("skills/filter-local-documents/SKILL.md", guidance)
        archive.writestr("SETUP.md", (source / "SETUP.md").read_bytes())
    (runtime_dir / "SETUP.md").write_bytes((source / "SETUP.md").read_bytes())
    logging.info("Ready. Connection files and instructions: %s", runtime_dir)
    logging.info("Codex: codex-mcp.toml; Antigravity: antigravity-mcp.json.")
    logging.info("Cowork: install cowork-connector.zip as an optional plugin.")


def _interactive_setup(args: argparse.Namespace) -> None:
    """Collect explicit installation choices before downloading dependencies."""
    logging.info("Mparanza · Optional anonymization connectors")
    if args.engine is None:
        logging.info("1. OpenAI Privacy Filter\n2. GLiNER2-PII\n3. Rizzo PII")
        choice = input("Choose / Scegli (1, 2, 3): ").strip()
        if choice not in ("1", "2", "3"):
            raise ValueError("Choose 1, 2 or 3 and run setup again.")
        args.engine = ("openai", "gliner2", "rizzo")[int(choice) - 1]
    default = Path.home() / "Documents" / "Mparanza" / ENGINES[args.engine][1]
    for field, label, folder in (
        ("input_dir", "Originals folder / Cartella originali", "Input"),
        ("output_dir", "Filtered copies / Copie filtrate", "Output"),
    ):
        if getattr(args, field) is None:
            answer = input(f"{label} [{default / folder}]: ").strip()
            setattr(args, field, Path(answer) if answer else default / folder)
    logging.info("Engine / Motore: %s", ENGINES[args.engine][1])
    logging.info("Input: %s\nOutput: %s", args.input_dir, args.output_dir)
    logging.info("Setup downloads only the chosen engine's declared dependencies.")
    if args.engine == "rizzo":
        logging.info("Install and start the Rizzo app separately on this computer.")
    else:
        logging.info("The model and PyTorch require several GB of disk space.")
    if input("Install / Installa? [y/N]: ").strip().lower() not in (
        "y",
        "yes",
        "s",
        "si",
        "sì",
    ):
        raise ValueError("Installation cancelled; nothing downloaded.")
    args.input_dir.expanduser().mkdir(mode=0o700, parents=True, exist_ok=True)


def main() -> None:
    """Install a chosen engine and prepare Codex, Cowork and Antigravity setup."""
    parser = argparse.ArgumentParser(description=__doc__)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    default_root = Path.home() / ".local" / "share" / "mparanza" / "privacy-filter"
    if sys.platform == "win32":
        default_root = Path(os.environ["LOCALAPPDATA"]) / "Mparanza" / "privacy-filter"
    parser.add_argument("--engine", choices=("openai", "gliner2", "rizzo"))
    parser.add_argument(
        "--setup", action="store_true", help="Guided engine and folder selection"
    )
    parser.add_argument(
        "--configure-only",
        action="store_true",
        help="Regenerate host files for an existing runtime without downloads",
    )
    parser.add_argument("--rizzo-port", type=int, default=5005)
    parser.add_argument("--runtime-dir", type=Path)
    parser.add_argument("--input-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if not 1 <= args.rizzo_port <= 65535:
        parser.error("--rizzo-port must be between 1 and 65535.")
    if sys.version_info < (3, 12):
        parser.error("Python 3.12 or newer is required.")
    if args.setup:
        try:
            _interactive_setup(args)
        except (EOFError, ValueError) as exc:
            parser.exit(2, str(exc) + "\n")
    args.engine = args.engine or "openai"
    if args.input_dir is None or args.output_dir is None:
        parser.error("Provide --input-dir and --output-dir, or use --setup.")
    input_dir = args.input_dir.expanduser().resolve(strict=True)
    if not input_dir.is_dir():
        parser.error("The input directory must exist.")
    if args.engine != "openai":
        default_root = default_root.with_name(args.engine + "-pii")
    runtime_dir = (args.runtime_dir or default_root).expanduser().resolve()
    # A selected runtime must never silently become the other engine's runtime.
    engine_file = runtime_dir / "engine.json"
    if (
        engine_file.exists()
        and json.loads(engine_file.read_text())["engine"] != args.engine
    ):
        parser.error("Choose a different runtime directory for this engine.")
    if not engine_file.exists() and (runtime_dir / "venv").exists():
        if args.engine != "openai":
            parser.error("Choose an empty runtime directory for this engine.")
    environment = runtime_dir / "venv"
    python = environment / (
        "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
    )
    if args.configure_only and (not python.is_file() or not engine_file.is_file()):
        parser.error("--configure-only requires an installed connector runtime.")
    runtime_dir.mkdir(parents=True, exist_ok=True)
    engine_file.write_text(json.dumps({"engine": args.engine}), encoding="utf-8")
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    if args.configure_only:
        write_host_files(
            runtime_dir, python, input_dir, output_dir, args.engine, args.rizzo_port
        )
        return
    venv.EnvBuilder(with_pip=True).create(environment)
    source = Path(__file__).resolve().parent
    logging.basicConfig(level=logging.INFO)
    logging.info("Installing the separate %s connector runtime.", args.engine)
    requirements = {
        "openai": "requirements-model.txt",
        "gliner2": "requirements-gliner2.txt",
        "rizzo": "requirements.txt",
    }
    subprocess.run(  # nosec B603
        [
            str(python),
            "-m",
            "pip",
            "install",
            "-r",
            str(source / requirements[args.engine]),
            str(source),
        ],
        check=True,
    )
    if args.engine != "rizzo":
        subprocess.run(  # nosec B603
            [
                str(python),
                "-I",
                "-m",
                (
                    "mparanza_privacy_filter.gliner_prepare"
                    if args.engine == "gliner2"
                    else "mparanza_privacy_filter.prepare"
                ),
                "--model-dir",
                str(runtime_dir / "model"),
            ],
            check=True,
        )
    write_host_files(
        runtime_dir, python, input_dir, output_dir, args.engine, args.rizzo_port
    )
    if args.engine == "rizzo":
        logging.info(
            "Start the separately installed Rizzo app on 127.0.0.1:%s before filtering.",
            args.rizzo_port,
        )


if __name__ == "__main__":
    main()
