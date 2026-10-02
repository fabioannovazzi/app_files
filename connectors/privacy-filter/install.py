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
    if engine not in ("openai", "gliner2"):
        raise ValueError("unsupported_engine")
    if engine == "gliner2":
        args.extend(("--engine", "gliner2"))
    name = "gliner2_pii" if engine == "gliner2" else "privacy_filter"
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
    parser.add_argument("--engine", choices=("openai", "gliner2"), default="openai")
    parser.add_argument("--runtime-dir", type=Path)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if sys.version_info < (3, 12):
        parser.error("Python 3.12 or newer is required.")
    input_dir = args.input_dir.expanduser().resolve(strict=True)
    if not input_dir.is_dir():
        parser.error("The input directory must exist.")
    if args.engine == "gliner2":
        default_root = default_root.with_name("gliner2-pii")
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
            parser.error("Choose an empty runtime directory for GLiNER2-PII.")
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
    logging.info("Installing the separate %s runtime and model.", args.engine)
    subprocess.run(  # nosec B603
        [
            str(python),
            "-m",
            "pip",
            "install",
            "-r",
            str(
                source
                / (
                    "requirements-gliner2.txt"
                    if args.engine == "gliner2"
                    else "requirements-model.txt"
                )
            ),
            str(source),
        ],
        check=True,
    )
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
        config_text(python, input_dir, output_dir, runtime_dir / "model", args.engine),
        encoding="utf-8",
    )
    logging.info(
        "Ready. Add the server entry from %s to your Codex config.toml.", config_path
    )


if __name__ == "__main__":
    main()
