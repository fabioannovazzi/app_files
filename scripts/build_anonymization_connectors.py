"""Build the separate connector download from an explicit, reproducible file set."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import tomllib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

__all__ = ["build_bytes", "main"]

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "connectors/privacy-filter"
OUTPUT = ROOT / "static/shared/vera-integrazioni/downloads/anonymization-connectors.zip"
FILES = (
    "install.py",
    "Install.command",
    "Install.cmd",
    "pyproject.toml",
    "requirements.txt",
    "requirements-model.txt",
    "requirements-gliner2.txt",
    "SETUP.md",
    "README.md",
    "GLINER2.md",
    "RIZZO.md",
)


def build_bytes() -> bytes:
    """Package only source and guides; fixed metadata makes byte parity verifiable."""
    entries = {name: SOURCE / name for name in FILES}
    entries.update(
        {
            path.relative_to(SOURCE).as_posix(): path
            for path in (SOURCE / "src/mparanza_privacy_filter").glob("*.py")
        }
    )
    entries["LICENSE"] = ROOT / "LICENSE"
    stream = io.BytesIO()
    with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
        for name, path in sorted(entries.items()):
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"Package input must be a regular file: {name}")
            info = ZipInfo(
                "mparanza-anonymization-connectors/" + name, (1980, 1, 1, 0, 0, 0)
            )
            info.compress_type = ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (
                0o100755 if name == "Install.command" else 0o100644
            ) << 16
            # All allowlisted inputs are UTF-8 text; normalize checkout line endings.
            archive.writestr(info, path.read_text(encoding="utf-8").encode("utf-8"))
    return stream.getvalue()


def main() -> None:
    """Build or check the public download and its version/checksum metadata."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    data = build_bytes()
    metadata = (
        json.dumps(
            {
                "version": tomllib.loads((SOURCE / "pyproject.toml").read_text())[
                    "project"
                ]["version"],
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
                "engines": ["openai", "gliner2", "rizzo"],
                "hosts": ["codex", "cowork", "antigravity"],
            },
            indent=2,
        )
        + "\n"
    )
    for path, content in (
        (OUTPUT, data),
        (OUTPUT.with_suffix(".json"), metadata.encode()),
    ):
        if args.check:
            if not path.is_file() or path.read_bytes() != content:
                parser.exit(1, f"Rebuild connector download: {path}\n")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    logging.info("Connector download matches source (%s bytes).", len(data))


if __name__ == "__main__":
    main()
