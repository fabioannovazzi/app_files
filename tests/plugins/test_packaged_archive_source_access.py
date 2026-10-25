"""Execute attachment intake checks from both shipped chat-host layouts."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import pytest

__all__: list[str] = []
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module", params=["codex", "chatgpt", "claude"])
def installed_package(request, tmp_path_factory) -> tuple[Path, str]:
    """Extract our generated, source-verified ZIP; do not use repository helpers."""
    host = request.param
    suffix = {
        "codex": "plugin",
        "chatgpt": "chatgpt-upload",
        "claude": "claude-plugin",
    }[host]
    root = tmp_path_factory.mktemp(f"archive-intake-{host}")
    with ZipFile(ROOT / f"plugin_packages/vera/vera-{suffix}.zip") as archive:
        archive.extractall(root)
    if host == "codex":
        root = root / "vera-codex-plugin" / "plugins" / "vera"
    return root, host


def invoke(root: Path, private: Path, *arguments: str) -> dict[str, Any]:
    """Use the supported test interpreter and isolated state, without provisioning."""
    environment = {
        **os.environ,
        "HOME": str(private / "home"),
        "USERPROFILE": str(private / "home"),
        "VERA_STUDIO_ARCHIVE_STATE_DIR": str(private / "state"),
        "VERA_STUDIO_ARCHIVE_PROFILE_DIR": str(private / "profile"),
        "VERA_STUDIO_ARCHIVE_SESSION_ID": "packaged-intake-regression",
        "PYTHONDONTWRITEBYTECODE": "1",
        "MPARANZA_INCIDENT_DELIVERY": "local-only",
    }
    completed = subprocess.run(
        [
            sys.executable,
            str(root / "modules/studio-archive/scripts/studio_archive.py"),
            *arguments,
        ],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return json.loads(completed.stdout)


def test_packaged_chat_upload_warning_precedes_any_archive_state(
    installed_package: tuple[Path, str],
    tmp_path: Path,
) -> None:
    root, _ = installed_package
    private = tmp_path / "private"

    result = invoke(
        root,
        private,
        "check-import-sources",
        "--source-path",
        "/mnt/user-data/uploads/vera-packaged-intake-journal.csv",
        "--source-path",
        "/mnt/user-data/uploads/vera-packaged-intake-bank.csv",
    )

    assert result["ready"] is False
    assert [source["code"] for source in result["sources"]] == [
        "source_not_on_device",
        "source_not_on_device",
    ]
    assert result["archive_records_created"] is False
    assert not private.exists()


def test_packaged_reachable_inputs_continue_to_receipted_import(
    installed_package: tuple[Path, str],
    tmp_path: Path,
) -> None:
    root, _ = installed_package
    private = tmp_path / "private"
    journal = tmp_path / "journal.csv"
    bank = tmp_path / "bank.csv"
    journal.write_bytes(b"date,amount\n2026-10-01,100\n")
    bank.write_bytes(b"date,amount\n2026-10-02,100\n")
    unrelated = tmp_path / "unrelated.csv"
    unrelated.write_bytes(b"not selected\r\n")
    unrelated_second = tmp_path / "unrelated-second.csv"
    unrelated_second.write_bytes(b"also not selected\r\n")
    journal_hash = hashlib.sha256(journal.read_bytes()).hexdigest()
    bank_hash = hashlib.sha256(bank.read_bytes()).hexdigest()
    access = invoke(
        root,
        private,
        "check-import-sources",
        "--source-path",
        str(journal),
        "--source-path",
        str(bank),
        "--expected-sha256",
        journal_hash,
        "--expected-sha256",
        bank_hash,
    )
    assert access["ready"] is True
    assert not private.exists()
    studio = tmp_path / "Studio"
    studio.mkdir()
    invoke(root, private, "configure", "--archive-root", str(studio))
    client_id = invoke(
        root, private, "create-client", "--legal-name", "Synthetic Intake"
    )["client"]["client_id"]
    engagement_id = invoke(
        root,
        private,
        "create-engagement",
        "--client-id",
        client_id,
        "--engagement-label",
        "Two CSVs",
    )["engagement"]["engagement_id"]

    imports = [
        invoke(
            root,
            private,
            "import-document",
            "--client-id",
            client_id,
            "--engagement-id",
            engagement_id,
            "--source-path",
            str(source),
            "--role",
            "source",
            "--expected-sha256",
            expected,
        )
        for source, expected in ((journal, journal_hash), (bank, bank_hash))
    ]

    assert [item["status"] for item in imports] == ["imported", "imported"]
    assert [item["input_receipt"]["sha256"] for item in imports] == [
        hashlib.sha256(journal.read_bytes()).hexdigest(),
        hashlib.sha256(bank.read_bytes()).hexdigest(),
    ]
    assert [item["engagement"]["engagement_id"] for item in imports] == [
        engagement_id,
        engagement_id,
    ]
    stored = list(studio.rglob("input_*/receipt.json"))
    assert len(stored) == 2
    assert unrelated.read_bytes() == b"not selected\r\n"
    assert unrelated_second.read_bytes() == b"also not selected\r\n"


def test_packaged_intake_offers_actual_host_capabilities(
    installed_package: tuple[Path, str],
) -> None:
    root, host = installed_package
    skill_name = "mparanza-vera" if host == "claude" else "vera"
    skill = (root / f"skills/{skill_name}/SKILL.md").read_text()
    section = skill.split("## Check supplied files before starting client work\n", 1)[
        1
    ].split("\n## ", 1)[0]
    section = " ".join(section.split())

    assert "check-import-sources" in section
    assert "If the MCP tool is unavailable" in section
    assert "only when the current host offers it" in section
    assert (root / "modules/studio-archive/mcp/server.cjs").is_file()
