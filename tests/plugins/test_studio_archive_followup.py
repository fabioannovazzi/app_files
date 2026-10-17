"""Saved document-only progress survives the chat workspace and later sessions."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

CLI = (
    Path(__file__).resolve().parents[2]
    / "plugins/studio-archive/scripts/studio_archive.py"
)


def command(base: Path, session: str, *args: str) -> dict:
    environment = {
        **os.environ,
        "VERA_STUDIO_ARCHIVE_STATE_DIR": str(base / session),
        "VERA_STUDIO_ARCHIVE_PROFILE_DIR": str(base / "profile"),
        "VERA_STUDIO_ARCHIVE_SESSION_ID": session,
    }
    result = subprocess.run(
        [sys.executable, str(CLI), *args],
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def case(base: Path) -> tuple[str, str]:
    root = base / "Studio"
    root.mkdir()
    command(base, "first", "configure", "--archive-root", str(root))
    created = command(
        base, "first", "create-client", "--legal-name", "Synthetic follow-up client"
    )
    client_id = created["client"]["client_id"]
    engagement = command(
        base,
        "first",
        "create-engagement",
        "--client-id",
        client_id,
        "--engagement-label",
        "Document-only continuation",
    )
    return client_id, engagement["engagement"]["engagement_id"]


def save(base: Path, session: str, cid: str, eid: str, path: Path) -> dict:
    return command(
        base,
        session,
        "import-document",
        "--client-id",
        cid,
        "--engagement-id",
        eid,
        "--source-path",
        str(path),
        "--role",
        "support",
    )


def test_saved_followup_survives_deleted_workspace_and_fresh_session(
    tmp_path: Path,
) -> None:
    cid, eid = case(tmp_path)
    working = tmp_path / "follow-up.md"
    content = b"Vera-derived working note. Next step: verify missing due date.\n"
    working.write_bytes(content)
    saved = save(tmp_path, "first", cid, eid, working)
    working.unlink()

    recovered = command(tmp_path, "fresh", "engagements", "--client-id", cid)

    engagement = recovered["engagements"][0]
    receipt = engagement["imports"][0]
    assert engagement["engagement_id"] == eid
    assert engagement["workflow_run_count"] == 0
    assert receipt["input_id"] == saved["input_id"]
    assert receipt["role"] == "support"
    assert receipt["sha256"] == hashlib.sha256(content).hexdigest()
    assert receipt["byte_count"] == len(content)
    assert Path(receipt["path"]).read_bytes() == content
    assert not working.exists()


def test_changed_followup_preserves_previous_bytes_and_exact_retry_deduplicates(
    tmp_path: Path,
) -> None:
    cid, eid = case(tmp_path)
    working = tmp_path / "follow-up.md"
    working.write_bytes(b"Vera-derived note revision one.\n")
    previous = save(tmp_path, "first", cid, eid, working)
    working.write_bytes(b"Vera-derived note revision two; still awaiting evidence.\n")
    current = save(tmp_path, "second", cid, eid, working)

    retry = save(tmp_path, "third", cid, eid, working)

    recovered = command(tmp_path, "fourth", "engagements", "--client-id", cid)
    assert previous["input_id"] != current["input_id"]
    assert retry["status"] == "already_imported"
    assert retry["input_id"] == current["input_id"]
    assert len(recovered["engagements"][0]["imports"]) == 2
    assert recovered["engagements"][0]["workflow_run_count"] == 0
    assert (
        Path(previous["imported_path"]).read_bytes()
        == b"Vera-derived note revision one.\n"
    )
    assert Path(current["imported_path"]).read_bytes() == working.read_bytes()
