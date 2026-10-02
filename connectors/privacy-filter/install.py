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
    python: Path, input_dir: Path, output_dir: Path, model_dir: Path
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
        "--model-dir",
        str(model_dir),
    ]
    return (
        "[mcp_servers.privacy_filter]\n"
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
    parser.add_argument("--runtime-dir", type=Path, default=default_root)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if sys.version_info < (3, 12):
        parser.error("Python 3.12 or newer is required.")
    input_dir = args.input_dir.expanduser().resolve(strict=True)
    if not input_dir.is_dir():
        parser.error("The input directory must exist.")
    runtime_dir = args.runtime_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    environment = runtime_dir / "venv"
    venv.EnvBuilder(with_pip=True).create(environment)
    python = environment / (
        "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
    )
    source = Path(__file__).resolve().parent
    logging.basicConfig(level=logging.INFO)
    logging.info("Installing the separate Privacy Filter runtime and model.")
    subprocess.run(  # nosec B603
        [
            str(python),
            "-m",
            "pip",
            "install",
            "-r",
            str(source / "requirements-model.txt"),
            str(source),
        ],
        check=True,
    )
    subprocess.run(  # nosec B603
        [
            str(python),
            "-I",
            "-m",
            "mparanza_privacy_filter.prepare",
            "--model-dir",
            str(runtime_dir / "model"),
        ],
        check=True,
    )
    config_path = runtime_dir / "codex-mcp.toml"
    config_path.write_text(
        config_text(python, input_dir, output_dir, runtime_dir / "model"),
        encoding="utf-8",
    )
    logging.info(
        "Ready. Add the server entry from %s to your Codex config.toml.", config_path
    )


if __name__ == "__main__":
    main()
