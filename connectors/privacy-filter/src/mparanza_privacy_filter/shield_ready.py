"""Verify prepared engine files before allowing upstream bootstrap to run offline."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

__all__ = ["snapshot", "ready"]


def snapshot(root: Path) -> dict[str, str]:
    """Hash installed assets so a broken cache cannot trigger runtime installation."""
    result = {}
    for directory in (root / "upstream/models", root / "upstream/deps/installs"):
        for path in directory.rglob("*"):
            if path.is_file():
                result[path.relative_to(root).as_posix()] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
    config = json.loads((root / "shield.json").read_text())
    cli = Path(config["cli"])
    if not cli.resolve().is_relative_to(root) or not result:
        raise ValueError("invalid_prepared_shield")
    result[cli.relative_to(root).as_posix()] = hashlib.sha256(
        cli.read_bytes()
    ).hexdigest()
    return result


def ready(root: Path) -> bool:
    """Check fixed version and every installed asset; never download or initialize NER."""
    try:
        receipt = json.loads((root / "shield-ready.json").read_text())
        return bool(
            receipt["version"] == "2.2.0" and receipt["files"] == snapshot(root)
        )
    except (OSError, ValueError, KeyError, TypeError):
        return False
