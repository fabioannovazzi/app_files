"""Fresh processes reuse searchable evidence without reading all source files."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WORKER = r"""
import json, sys
from pathlib import Path
home, scripts, session, operation, root = sys.argv[1:]
Path.home = classmethod(lambda cls: Path(home))
sys.path.insert(0, scripts)
import archive_core as a
if operation in ('seed', 'legacy'):
    a.configure_archive(Path(root), make_studio_default=True)
    if operation == 'legacy':
        a._database_path = lambda state: state / a.DATABASE_FILENAME
    result = a.refresh_archive()
elif operation == 'refresh':
    result = a.refresh_archive()
elif operation == 'ensure':
    result = a.refresh_archive(only_if_required=True)
else:
    def forbidden(*args, **kwargs):
        raise AssertionError('Fresh search must not refresh, discover or extract files')
    a.refresh_archive = a._discover_files = a._extract_document = forbidden
    status = a.studio_archive_status()
    results = a.search_archive('dividendi concordato', scope_id=status['scopes'][0]['scope_id'])
    opened = a.open_archive_source(results['results'][0]['source_id'])
    result = {'status': status, 'search': results, 'opened': opened}
print(json.dumps(result))
"""


def call(home, session, operation, root, product="vera"):
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("VERA_STUDIO_ARCHIVE_") and k != "LUCIA_ASSURANCE_HOST"
    }
    env["VERA_STUDIO_ARCHIVE_SESSION_ID"] = session
    if product == "lucia":
        env["LUCIA_ASSURANCE_HOST"] = "1"
    process = subprocess.run(
        [
            sys.executable,
            "-c",
            WORKER,
            str(home),
            str(ROOT / "plugins/studio-archive/scripts"),
            session,
            operation,
            str(root),
        ],
        env=env,
        text=True,
        capture_output=True,
        timeout=40,
    )
    assert process.returncode == 0, process.stderr
    return json.loads(process.stdout)


@pytest.fixture
def studio(tmp_path):
    root = tmp_path / "Studio"
    scope = root / "Eutekne"
    scope.mkdir(parents=True)
    (scope / "quesito.txt").write_text(
        "Dividendi e reddito concordato: prova sintetica.", encoding="utf-8"
    )
    return root


@pytest.mark.parametrize("seed", ["seed", "legacy"])
@pytest.mark.parametrize("product", ["vera", "lucia"])
def test_new_chat_searches_and_opens_existing_index_without_refresh(
    tmp_path, studio, seed, product
):
    initial = call(tmp_path, "original-chat", seed, studio, product)
    result = call(tmp_path, "fresh-chat", "search", studio, product)
    assert result["status"]["last_refresh_at"] == initial["last_refresh_at"]
    assert result["status"]["index_requires_refresh"] is False
    assert result["opened"]["source_verified"] is True
    assert "prova sintetica" in result["opened"]["fragments"][0]["text"]
    databases = list(
        (tmp_path / ".mparanza" / f"{product}-studio-archive/profile").rglob(
            "archive.sqlite3"
        )
    )
    assert len(databases) == 1


def test_parallel_fresh_chats_migrate_the_same_legacy_snapshot(tmp_path, studio):
    initial = call(tmp_path, "original-chat", "legacy", studio)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(lambda n: call(tmp_path, f"chat-{n}", "search", studio), range(4))
        )
    assert all(
        r["status"]["last_refresh_at"] == initial["last_refresh_at"] for r in results
    )
    assert all(r["opened"]["source_verified"] for r in results)


def test_new_archive_does_not_reuse_another_roots_evidence(tmp_path, studio):
    call(tmp_path, "original-chat", "seed", studio)
    second = tmp_path / "Other Studio"
    (second / "Eutekne").mkdir(parents=True)
    (second / "Eutekne/quesito.txt").write_text(
        "Dividendi concordato: archivio diverso.", encoding="utf-8"
    )
    call(tmp_path, "second-chat", "seed", second)
    result = call(tmp_path, "fresh-chat", "search", second)
    assert "archivio diverso" in result["opened"]["fragments"][0]["text"]
    assert "prova sintetica" not in result["opened"]["fragments"][0]["text"]


def test_changed_source_is_rejected_after_cross_chat_reuse(tmp_path, studio):
    call(tmp_path, "original-chat", "seed", studio)
    (studio / "Eutekne/quesito.txt").write_text("Changed source.", encoding="utf-8")
    with pytest.raises(AssertionError, match="changed"):
        call(tmp_path, "fresh-chat", "search", studio)


def test_concurrent_refreshes_keep_a_searchable_index(tmp_path, studio):
    call(tmp_path, "original-chat", "seed", studio)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda n: call(tmp_path, f"refresh-{n}", "refresh", studio), range(2)
            )
        )
    assert all(r["unchanged_files"] == 1 for r in results)
    assert call(tmp_path, "fresh-chat", "search", studio)["opened"]["source_verified"]


def test_concurrent_recovery_refreshes_stale_shared_index_once(tmp_path, studio):
    call(tmp_path, "original-chat", "seed", studio)
    added = studio / "New client"
    added.mkdir()
    (added / "new.txt").write_text("New client source", encoding="utf-8")

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(
                lambda n: call(tmp_path, f"recover-{n}", "ensure", studio), range(4)
            )
        )

    assert sum(result.get("status") == "refreshed" for result in results) == 1
    assert sum(result.get("refreshed") is False for result in results) == 3
    assert call(tmp_path, "after-recovery", "search", studio)["opened"][
        "source_verified"
    ]
