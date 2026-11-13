from __future__ import annotations

import json
from pathlib import Path

__all__: list[str] = []


def test_production_restart_build_command_remains_available() -> None:
    package = json.loads(Path("package.json").read_text(encoding="utf-8"))

    assert package["scripts"]["build:all"] == "sh scripts/build_public_codex_downloads.sh"
