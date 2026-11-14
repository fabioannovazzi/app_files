"""Vera and Lucia retain separate archives even inside the same host chat."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
__all__: list[str] = []
WORKER = """
import json, sys
from pathlib import Path
fixture_home, scripts, operation, root = sys.argv[1:]
Path.home = classmethod(lambda cls: Path(fixture_home))
sys.path.insert(0, scripts)
import archive_core as archive
if operation == 'configure':
    result = archive.configure_archive(Path(root), make_studio_default=True)
elif operation == 'temporary':
    result = archive.configure_archive(Path(root))
else:
    result = archive.studio_archive_status()
print(json.dumps(result))
"""


def call(tmp_path, product, operation, root, session="same-chat"):
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("VERA_STUDIO_ARCHIVE_") and key != "LUCIA_ASSURANCE_HOST"
    }
    environment["VERA_STUDIO_ARCHIVE_SESSION_ID"] = session
    if product == "lucia":
        environment["LUCIA_ASSURANCE_HOST"] = "1"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            WORKER,
            str(tmp_path),
            str(ROOT / "plugins/studio-archive/scripts"),
            operation,
            str(root),
        ],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_two_products_in_one_chat_keep_separate_defaults_and_current_roots(tmp_path):
    vera, lucia = tmp_path / "Studio Vera", tmp_path / "Studio Lucia"
    vera.mkdir()
    lucia.mkdir()
    call(tmp_path, "vera", "configure", vera)
    call(tmp_path, "lucia", "configure", lucia)

    assert call(tmp_path, "vera", "status", vera)["archive_root"] == str(vera)
    assert call(tmp_path, "lucia", "status", lucia)["archive_root"] == str(lucia)
    assert call(tmp_path, "vera", "status", vera, "fresh-chat")["archive_root"] == str(
        vera
    )
    assert call(tmp_path, "lucia", "status", lucia, "fresh-chat")[
        "archive_root"
    ] == str(lucia)
    for product, selected in (("vera", vera), ("lucia", lucia)):
        preference = (
            tmp_path
            / ".mparanza"
            / f"{product}-studio-archive/profile/approved-archive.json"
        )
        assert json.loads(preference.read_text())["archive_root"] == str(selected)


def test_lucia_does_not_adopt_veras_default_when_its_own_is_unconfigured(tmp_path):
    vera = tmp_path / "Studio Vera"
    vera.mkdir()
    call(tmp_path, "vera", "configure", vera)
    assert call(tmp_path, "lucia", "status", vera, "fresh-chat")["configured"] is False


def test_temporary_lucia_selection_cannot_replace_either_product_default(tmp_path):
    vera, lucia, temporary = [
        tmp_path / name for name in ("Vera", "Lucia", "Temporary")
    ]
    for folder in (vera, lucia, temporary):
        folder.mkdir()
    call(tmp_path, "vera", "configure", vera)
    call(tmp_path, "lucia", "configure", lucia)
    call(tmp_path, "lucia", "temporary", temporary, "test-chat")
    assert call(tmp_path, "lucia", "status", temporary, "test-chat")[
        "archive_root"
    ] == str(temporary)
    assert call(tmp_path, "vera", "status", vera, "fresh-chat")["archive_root"] == str(
        vera
    )
    assert call(tmp_path, "lucia", "status", lucia, "fresh-chat")[
        "archive_root"
    ] == str(lucia)
