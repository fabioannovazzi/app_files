from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("host", ["codex", "chatgpt-upload", "claude"])
def test_release_index_matches_every_final_host_projected_byte(host):
    filename = "vera-plugin.zip" if host == "codex" else f"vera-{host}-plugin.zip"
    if host == "chatgpt-upload":
        filename = "vera-chatgpt-upload.zip"
    with ZipFile(ROOT / "plugin_packages/vera" / filename) as archive:
        indexes = [
            name for name in archive.namelist() if name.endswith("execution-files.json")
        ]
        assert len(indexes) == 1
        index = indexes[0]
        prefix = index.removesuffix("execution-files.json")
        manifest = json.loads(archive.read(index))
        expected = {
            name.removeprefix(prefix): hashlib.sha256(archive.read(name)).hexdigest()
            for name in archive.namelist()
            if name.startswith(prefix) and name != index and not name.endswith("/")
        }

    assert manifest["schema_version"] == 1
    assert manifest["files"] == expected
    assert "scripts/verified_execution.py" in expected
    assert "skills/vera/references/execution-recovery.md" in expected


@pytest.mark.parametrize("host", ["codex", "chatgpt-upload", "claude"])
def test_packaged_preflight_recovers_host_cache_hardlinks_without_manual_repair(
    tmp_path, host
):
    filenames = {
        "codex": "vera-plugin.zip",
        "chatgpt-upload": "vera-chatgpt-upload.zip",
        "claude": "vera-claude-plugin.zip",
    }
    installed = tmp_path / "installed"
    aliases = tmp_path / "host-cache"
    aliases.mkdir()
    with ZipFile(ROOT / "plugin_packages/vera" / filenames[host]) as archive:
        index = next(
            name for name in archive.namelist() if name.endswith("execution-files.json")
        )
        prefix = index.removesuffix("execution-files.json")
        # These are release-test archives generated from inspected repo source.
        for name in archive.namelist():
            if not name.startswith(prefix) or name.endswith("/"):
                continue
            relative = Path(name.removeprefix(prefix))
            assert not relative.is_absolute() and ".." not in relative.parts
            path = installed / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(archive.read(name))
            alias = aliases / relative
            alias.parent.mkdir(parents=True, exist_ok=True)
            alias.hardlink_to(path)

    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            str(installed / "scripts/verified_execution.py"),
            "--module",
            "journal-bank-reconciliation",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    prepared = Path(json.loads(completed.stdout)["execution_root"])
    try:
        assert prepared != installed
        relative = "modules/journal-bank-reconciliation/scripts/inspect_inputs.py"
        assert (prepared / relative).stat().st_nlink == 1
        assert (installed / relative).stat().st_nlink == 2
        assert (aliases / relative).read_bytes() == (prepared / relative).read_bytes()
        help_result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(
                    prepared
                    / "modules/journal-bank-reconciliation/scripts/check_dependencies.py"
                ),
                "--help",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert help_result.returncode == 0, help_result.stderr
    finally:
        shutil.rmtree(prepared)
