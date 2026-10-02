"""Explicit installer for the optional connector, outside client workspaces."""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import venv
from pathlib import Path

__all__ = ["main", "config_text"]


def config_text(
    python: Path,
    input_dir: Path,
    output_dir: Path,
    model_dir: Path,
    engine: str = "openai",
    rizzo_port: int = 5005,
) -> str:
    """Generate a separate stdio server entry without editing the user's config."""
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
    name = {"openai": "privacy_filter", "gliner2": "gliner2_pii", "rizzo": "rizzo_pii"}[
        engine
    ]
    return (
        f"[mcp_servers.{name}]\n"
        f"command = {json.dumps(str(python))}\n"
        f"args = {json.dumps(args)}\n"
        "startup_timeout_sec = 30\n"
        "tool_timeout_sec = 3600\n"
        "enabled = true\n"
    )


def main() -> None:
    """Install declared packages and model; write a reviewable Codex config entry."""
    parser = argparse.ArgumentParser(description=__doc__)
    default_root = Path.home() / ".local" / "share" / "mparanza" / "privacy-filter"
    if sys.platform == "win32":
        default_root = Path(os.environ["LOCALAPPDATA"]) / "Mparanza" / "privacy-filter"
    parser.add_argument(
        "--engine", choices=("openai", "gliner2", "rizzo"), default="openai"
    )
    parser.add_argument("--rizzo-port", type=int, default=5005)
    parser.add_argument("--runtime-dir", type=Path)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.rizzo_port <= 65535:
        parser.error("--rizzo-port must be between 1 and 65535.")
    if sys.version_info < (3, 12):
        parser.error("Python 3.12 or newer is required.")
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
    runtime_dir.mkdir(parents=True, exist_ok=True)
    engine_file.write_text(json.dumps({"engine": args.engine}), encoding="utf-8")
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    environment = runtime_dir / "venv"
    venv.EnvBuilder(with_pip=True).create(environment)
    python = environment / (
        "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
    )
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
    config_path = runtime_dir / "codex-mcp.toml"
    config_path.write_text(
        config_text(
            python,
            input_dir,
            output_dir,
            runtime_dir / "model",
            args.engine,
            args.rizzo_port,
        ),
        encoding="utf-8",
    )
    logging.info(
        "Ready. Add the server entry from %s to your Codex config.toml.", config_path
    )
    if args.engine == "rizzo":
        logging.info(
            "Start the separately installed Rizzo app on 127.0.0.1:%s before filtering.",
            args.rizzo_port,
        )


if __name__ == "__main__":
    main()
