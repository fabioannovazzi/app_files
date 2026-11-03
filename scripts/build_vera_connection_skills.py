"""Build independent Codex skill downloads, without packaging local credentials."""

from __future__ import annotations

import argparse
import io
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from validate_plugin_skills import validate_skill_entries

__all__ = ["build", "main"]
ROOT = Path(__file__).resolve().parents[1]
CONNECTORS = ROOT / "connectors"
DOWNLOADS = ROOT / "static/shared/vera-integrazioni/downloads"
LOGIN = "vera-1password"
SERVICE = "vera-connect-service"


def build(skill: str) -> bytes:
    """Return a deterministic, allowlisted ZIP with a host-discoverable root."""
    files = {"SKILL.md": CONNECTORS / skill / "SKILL.md"}
    helper = CONNECTORS / LOGIN / "login.mjs"
    if skill == LOGIN:
        files["login.mjs"] = helper
    elif skill == SERVICE:
        files["setup_acube.py"] = CONNECTORS / skill / "setup_acube.py"
        files[f"connectors/{LOGIN}/login.mjs"] = helper
        for name in (
            "README.md",
            "server.mjs",
            "archive_invoice.py",
            "package.json",
            "pnpm-lock.yaml",
        ):
            files[f"connectors/vera-acube/{name}"] = CONNECTORS / "vera-acube" / name
    else:
        raise ValueError("Unknown skill")
    files["LICENSE"] = ROOT / "LICENSE"
    entries = {
        f"{skill}/{name}": path.read_bytes().replace(b"\r\n", b"\n")
        for name, path in files.items()
    }
    validate_skill_entries(entries)
    stream = io.BytesIO()
    with ZipFile(stream, "w") as archive:
        for name, data in sorted(entries.items()):
            info = ZipInfo(name)
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, data)
    return stream.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for skill in (LOGIN, SERVICE):
        path = DOWNLOADS / f"{skill}.zip"
        expected = build(skill)
        if args.check:
            if not path.is_file() or path.read_bytes() != expected:
                parser.exit(1, f"Rebuild {path.name}\n")
        else:
            path.write_bytes(expected)


if __name__ == "__main__":
    main()
