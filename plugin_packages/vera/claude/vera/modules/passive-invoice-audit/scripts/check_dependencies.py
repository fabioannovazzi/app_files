"""Check dependencies and native Luna prerequisites for this Vera workflow."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import logging
import re
import shutil
import subprocess
from pathlib import Path

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)
PLUGIN_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_IMPORTS = ("openpyxl", "xlsxwriter")
REQUIRED_CODEX_VERSION = "codex-cli 0.148.0-alpha.21"
REQUIRED_CODEX_SHA256 = (
    "5e508bd40c1bdd2d9798a269839c16935c71941e5709c097b0a527bee52977ab"
)
PACKAGE_IMPORTS = {"openpyxl": "openpyxl", "xlsxwriter": "xlsxwriter"}


def _requirement_name(line: str) -> str:
    """Return the normalized distribution name from one requirements line."""

    cleaned = line.split("#", 1)[0].strip()
    if not cleaned or cleaned.startswith(("-", "git+", "http://", "https://")):
        return ""
    match = re.match(r"([A-Za-z0-9_.-]+)", cleaned)
    return match.group(1).lower() if match else ""


def main(argv: list[str] | None = None) -> int:
    """Return zero only when deterministic and native-Claude prerequisites exist."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--requirements",
        action="append",
        type=Path,
        default=[],
        help="Explicit requirements file to validate; repeat for multiple files.",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    requirement_files = args.requirements or [PLUGIN_ROOT / "requirements.txt"]
    packages: set[str] = set()
    for requirements_path in requirement_files:
        if not requirements_path.is_file():
            LOGGER.error("Requirements file is unavailable: %s", requirements_path)
            return 1
        packages.update(
            name
            for line in requirements_path.read_text(encoding="utf-8").splitlines()
            if (name := _requirement_name(line))
        )
    imports = {
        PACKAGE_IMPORTS.get(package, package.replace("-", "_")) for package in packages
    }
    imports.update(REQUIRED_IMPORTS)
    missing = [
        name for name in sorted(imports) if importlib.util.find_spec(name) is None
    ]
    if missing:
        LOGGER.error("Missing Python dependencies: %s", ", ".join(missing))
        return 1
    from cowork_worker import configured_runtime

    if configured_runtime() == "cowork-haiku":
        LOGGER.info(
            "OK: Python dependencies available. Semantic review requires the packaged Cowork Haiku subagent; this check does not verify model availability."
        )
        return 0
    codex = shutil.which("codex")
    if not codex:
        LOGGER.error("Claude CLI is unavailable; native GPT-5.6 Luna cannot run")
        return 1
    codex_path = Path(codex).resolve()
    completed = subprocess.run(
        [str(codex_path), "--version"],
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )
    digest = hashlib.sha256(codex_path.read_bytes()).hexdigest()
    evidence = {
        "codex_path": str(codex_path),
        "codex_version": completed.stdout.strip(),
        "codex_sha256": digest,
        "required_model": "gpt-5.6-luna",
        "direct_model_api": False,
    }
    if (
        completed.returncode != 0
        or evidence["codex_version"] != REQUIRED_CODEX_VERSION
        or digest != REQUIRED_CODEX_SHA256
    ):
        LOGGER.error("Native Luna worker is not qualified: %s", json.dumps(evidence))
        return 1
    LOGGER.info("OK: %s", json.dumps(evidence))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
