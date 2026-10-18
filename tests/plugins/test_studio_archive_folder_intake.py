"""Folder deliveries reach the organization snapshot without manual filesystem rescue."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "plugins/studio-archive/scripts/studio_archive.py"


def command(base: Path, session: str, *args: str, check: bool = True):
    result = subprocess.run(
        [sys.executable, str(CLI), *args],
        env={
            **os.environ,
            "VERA_STUDIO_ARCHIVE_STATE_DIR": str(base / session),
            "VERA_STUDIO_ARCHIVE_PROFILE_DIR": str(base / "profile"),
            "VERA_STUDIO_ARCHIVE_SESSION_ID": session,
        },
        text=True,
        capture_output=True,
        check=check,
        timeout=30,
    )
    return json.loads(result.stdout) if result.returncode == 0 else result


def case(base: Path):
    archive = base / "Studio"
    archive.mkdir()
    command(base, "setup", "configure", "--archive-root", str(archive))
    cid = command(base, "setup", "create-client", "--legal-name", "Synthetic bakery")[
        "client"
    ]["client_id"]
    eid = command(
        base,
        "setup",
        "create-engagement",
        "--client-id",
        cid,
        "--engagement-label",
        "Organization",
    )["engagement"]["engagement_id"]
    source = base / "Mixed delivery"
    (source / "Copies").mkdir(parents=True)
    (source / "2025").mkdir()
    (source / "2026").mkdir()
    (source / "empty").mkdir()
    (source / "2025/invoice.txt").write_text("2025 SNC invoice A17 EUR1220")
    (source / "Copies/duplicate.txt").write_bytes(
        (source / "2025/invoice.txt").read_bytes()
    )
    (source / "2026/invoice.txt").write_text("2026 SNC invoice A17 EUR1342")
    (source / "foreign.txt").write_text("Similarly named SRL, different customer")
    return cid, eid, source


def copy_args(cid, eid, source, destination=None):
    args = [
        "copy-client-source-folder",
        "--client-id",
        cid,
        "--engagement-id",
        eid,
        "--source-path",
        str(source),
        "--copy-authorized",
    ]
    if destination is not None:
        args += ["--destination-name", destination]
    return args


def test_delivery_tree_is_visible_to_snapshot_and_exact_retry_survives_new_session(
    tmp_path,
):
    cid, eid, source = case(tmp_path)
    copied = command(tmp_path, "first", *copy_args(cid, eid, source))
    retry = command(tmp_path, "fresh", *copy_args(cid, eid, source))
    snapshot = command(
        tmp_path,
        "snapshot",
        "snapshot-client-folder",
        "--client-id",
        cid,
        "--engagement-id",
        eid,
    )
    destination = Path(copied["destination_path"])

    assert copied["status"] == "copied"
    assert retry["status"] == "already_copied"
    assert retry["intake_id"] == copied["intake_id"]
    assert retry["receipt_path"] == copied["receipt_path"]
    assert copied["file_count"] == 4
    assert (destination / "empty").is_dir()
    assert (destination / "2025/invoice.txt").read_bytes() == (
        source / "2025/invoice.txt"
    ).read_bytes()
    assert (destination / "Copies/duplicate.txt").read_bytes() == (
        source / "2025/invoice.txt"
    ).read_bytes()
    assert (destination / "2026/invoice.txt").read_bytes() != (
        destination / "2025/invoice.txt"
    ).read_bytes()
    assert (destination / "foreign.txt").read_bytes() == (
        source / "foreign.txt"
    ).read_bytes()
    assert str(source) not in Path(copied["receipt_path"]).read_text()
    assert not (destination / ".vera-folder-intake-pending.json").exists()
    assert "Mixed delivery/2025/invoice.txt" in json.dumps(snapshot)
    assert "Mixed delivery/2026/invoice.txt" in json.dumps(snapshot)


@pytest.mark.parametrize(
    "collision", ["preexisting", "changed_source", "changed_destination"]
)
def test_conflicting_or_changed_deliveries_never_overwrite_files(tmp_path, collision):
    cid, eid, source = case(tmp_path)
    folder = command(tmp_path, "setup", "client-folder", "--client-id", cid)[
        "client_folder"
    ]
    destination = Path(folder["client_root"]) / source.name
    if collision == "preexisting":
        destination.mkdir()
        (destination / "keep.txt").write_text("Keep this existing file")
        retained = destination / "keep.txt"
    else:
        copied = command(tmp_path, "first", *copy_args(cid, eid, source))
        retained = destination / "2025/invoice.txt"
        if collision == "changed_source":
            (source / "2025/invoice.txt").write_text("Changed delivery")
        else:
            retained.write_text("Professional edited working document")
    before = retained.read_bytes()

    rejected = command(tmp_path, "retry", *copy_args(cid, eid, source), check=False)

    assert rejected.returncode != 0
    assert retained.read_bytes() == before


def test_symlink_source_fails_before_creating_delivery(tmp_path):
    cid, eid, source = case(tmp_path)
    (source / "linked.txt").symlink_to(source / "2025/invoice.txt")

    rejected = command(tmp_path, "copy", *copy_args(cid, eid, source), check=False)

    assert rejected.returncode != 0
    folder = command(tmp_path, "copy", "client-folder", "--client-id", cid)[
        "client_folder"
    ]
    assert not (Path(folder["client_root"]) / source.name).exists()


def test_other_archive_scope_cannot_be_used_as_delivery_source(tmp_path):
    cid, eid, source = case(tmp_path)
    other = command(
        tmp_path, "setup", "create-client", "--legal-name", "Foreign client"
    )
    folder = command(
        tmp_path, "setup", "client-folder", "--client-id", other["client"]["client_id"]
    )["client_folder"]
    foreign = Path(folder["client_root"]) / "foreign"
    foreign.mkdir()
    (foreign / "document.txt").write_text("Other client")

    rejected = command(tmp_path, "copy", *copy_args(cid, eid, foreign), check=False)

    assert rejected.returncode != 0
    assert "external to the approved archive" in rejected.stdout + rejected.stderr


def test_concurrent_exact_requests_publish_one_delivery(tmp_path):
    cid, eid, source = case(tmp_path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(command, tmp_path, "one", *copy_args(cid, eid, source))
        second = pool.submit(command, tmp_path, "two", *copy_args(cid, eid, source))
        results = [first.result(), second.result()]

    assert sorted(r["status"] for r in results) == ["already_copied", "copied"]
    assert results[0]["intake_id"] == results[1]["intake_id"]


def test_interrupted_copy_blocks_snapshot_and_resumes_without_overwriting(tmp_path):
    cid, eid, source = case(tmp_path)
    program = """
import os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import archive_core as a
original=a.folder_intake.ledger._stable_copy
calls=0
def interrupted(*args,**kwargs):
    global calls
    calls+=1
    if calls==2: raise OSError("simulated interruption")
    return original(*args,**kwargs)
a.folder_intake.ledger._stable_copy=interrupted
a.copy_studio_client_source_folder(sys.argv[2],sys.argv[3],Path(sys.argv[4]),copy_authorized=True)
"""
    env = {
        **os.environ,
        "VERA_STUDIO_ARCHIVE_STATE_DIR": str(tmp_path / "interrupt"),
        "VERA_STUDIO_ARCHIVE_PROFILE_DIR": str(tmp_path / "profile"),
        "VERA_STUDIO_ARCHIVE_SESSION_ID": "interrupt",
    }
    interrupted = subprocess.run(
        [sys.executable, "-c", program, str(CLI.parent), cid, eid, str(source)],
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )
    rejected = command(
        tmp_path,
        "snapshot",
        "snapshot-client-folder",
        "--client-id",
        cid,
        "--engagement-id",
        eid,
        check=False,
    )
    recovered = command(tmp_path, "recover", *copy_args(cid, eid, source))

    assert interrupted.returncode != 0
    assert rejected.returncode != 0
    assert "intake is incomplete" in rejected.stdout + rejected.stderr
    assert recovered["status"] == "copied"
    assert recovered["file_count"] == 4
    assert not (
        Path(recovered["destination_path"]) / ".vera-folder-intake-pending.json"
    ).exists()
