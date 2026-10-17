from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(
    os.environ.get(
        "STUDIO_ARCHIVE_TEST_SCRIPTS", str(ROOT / "plugins/studio-archive/scripts")
    )
)
WORKER = """
import json,sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import archive_core as a
state,root=Path(sys.argv[2]),Path(sys.argv[3])
action=sys.argv[4]
if action=='configure':
    result=a.configure_archive(root,state_dir=state)
elif action=='create':
    client=a.create_studio_client(sys.argv[5],state_dir=state)
    cid=client['client']['client_id']
    eng=a.create_studio_client_engagement(cid,'Synthetic concurrency',state_dir=state)
    result={'client_id':cid,'engagement_id':eng['engagement']['engagement_id']}
elif action=='continue':
    cid,eid,source=sys.argv[5:8]
    # Directory continuity must not require indexing unrelated documents.
    a.refresh_archive=lambda **kw: (_ for _ in ()).throw(AssertionError('full refresh'))
    folder=a.get_studio_client_folder(cid,state_dir=state)
    result=a.import_studio_client_document(cid,Path(source),'support',engagement_id=eid,state_dir=state)
    result['client_root']=folder['client_folder']['client_root']
elif action=='prepare':
    result=a.prepare_studio_client_workflow(sys.argv[5],'esg-reporting-assurance',input_ids=[sys.argv[6]],state_dir=state)
else:
    result=a.list_studio_clients(state_dir=state)
print(json.dumps(result))
"""
LOCK_WORKER = """
import sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import archive_preferences as p
print('ready',flush=True)
with p.registry_lock(Path(sys.argv[2]),Path(sys.argv[3])):
    print('acquired',flush=True)
    if sys.argv[4]=='hold': sys.stdin.readline()
"""


def _environment(base: Path, session: str) -> dict[str, str]:
    return {
        **os.environ,
        "VERA_STUDIO_ARCHIVE_PROFILE_DIR": str(base / "profile"),
        "VERA_STUDIO_ARCHIVE_SESSION_ID": session,
    }


def _run(base: Path, session: str, action: str, *args: str) -> dict:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            WORKER,
            str(SCRIPTS),
            str(base / session),
            str(base / "Studio"),
            action,
            *args,
        ],
        env=_environment(base, session),
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    return json.loads(result.stdout)


def _lock_process(base: Path, mode: str) -> subprocess.Popen:
    return subprocess.Popen(
        [
            sys.executable,
            "-u",
            "-c",
            LOCK_WORKER,
            str(SCRIPTS),
            str(base / "profile"),
            str(base / "Studio"),
            mode,
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def test_registry_contention_waits_for_owner_instead_of_failing(tmp_path: Path) -> None:
    owner = _lock_process(tmp_path, "hold")
    contender = None
    try:
        assert owner.stdout.readline().strip() == "ready"
        assert owner.stdout.readline().strip() == "acquired"
        contender = _lock_process(tmp_path, "take")
        assert contender.stdout.readline().strip() == "ready"
        time.sleep(0.15)
        assert contender.poll() is None, contender.stderr.read()
        owner.communicate("release\n", timeout=5)
        output, error = contender.communicate(timeout=5)
        assert contender.returncode == 0, error
        assert output.strip() == "acquired"
    finally:
        for process in (owner, contender):
            if process is not None and process.poll() is None:
                process.kill()
                process.communicate()


def test_other_sessions_can_create_and_resume_without_full_index_refresh(
    tmp_path: Path,
) -> None:
    (tmp_path / "Studio").mkdir()
    _run(tmp_path, "alpha", "configure")
    _run(tmp_path, "beta", "configure")
    alpha = _run(tmp_path, "alpha", "create", "Synthetic Alpha")
    beta = _run(tmp_path, "beta", "create", "Synthetic Beta")
    source = tmp_path / "note.txt"
    source.write_text("Synthetic Alpha: continuation checkpoint", encoding="utf-8")
    imported = _run(
        tmp_path,
        "alpha",
        "continue",
        alpha["client_id"],
        alpha["engagement_id"],
        str(source),
    )
    prepared = _run(
        tmp_path, "alpha", "prepare", alpha["engagement_id"], imported["input_id"]
    )
    repeated = _run(
        tmp_path,
        "alpha",
        "continue",
        alpha["client_id"],
        alpha["engagement_id"],
        str(source),
    )
    assert repeated["input_id"] == imported["input_id"]
    assert Path(imported["imported_path"]).read_bytes() == source.read_bytes()
    receipt = json.loads(
        (Path(imported["imported_path"]).parent / "receipt.json").read_text()
    )
    assert receipt["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert receipt["client_id"] == alpha["client_id"]
    assert receipt["engagement_id"] == alpha["engagement_id"]
    assert beta["client_id"] != alpha["client_id"]
    assert prepared["client_id"] == alpha["client_id"]
    assert not list((tmp_path / "alpha").glob("*.sqlite3"))


def test_four_concurrent_sessions_preserve_all_clients_and_notes(
    tmp_path: Path,
) -> None:
    (tmp_path / "Studio").mkdir()
    sessions = [f"session-{i}" for i in range(4)]
    for session in sessions:
        _run(tmp_path, session, "configure")
    with ThreadPoolExecutor(max_workers=4) as workers:
        created = list(
            workers.map(
                lambda session: _run(
                    tmp_path, session, "create", f"Synthetic {session}"
                ),
                sessions,
            )
        )
    notes = []
    for session in sessions:
        source = tmp_path / f"{session}.txt"
        source.write_text(f"Checkpoint belongs only to {session}", encoding="utf-8")
        notes.append(source)
    with ThreadPoolExecutor(max_workers=4) as workers:
        futures = [
            workers.submit(
                _run,
                tmp_path,
                session,
                "continue",
                case["client_id"],
                case["engagement_id"],
                str(note),
            )
            for session, case, note in zip(sessions, created, notes)
        ]
        imported = [future.result() for future in futures]
    assert len({case["client_id"] for case in created}) == 4
    directory = _run(tmp_path, "fresh", "clients")
    assert directory["registered_client_count"] == 4
    for note, result in zip(notes, imported):
        assert Path(result["imported_path"]).read_bytes() == note.read_bytes()


def test_concurrent_identical_imports_reuse_one_receipt(tmp_path: Path) -> None:
    (tmp_path / "Studio").mkdir()
    _run(tmp_path, "alpha", "configure")
    _run(tmp_path, "beta", "configure")
    case = _run(tmp_path, "alpha", "create", "Synthetic Alpha")
    source = tmp_path / "same-note.txt"
    source.write_text("One checkpoint, two exact concurrent retries", encoding="utf-8")
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(
            workers.map(
                lambda session: _run(
                    tmp_path,
                    session,
                    "continue",
                    case["client_id"],
                    case["engagement_id"],
                    str(source),
                ),
                ["alpha", "beta"],
            )
        )
    assert results[0]["input_id"] == results[1]["input_id"]
    assert len(list((tmp_path / "Studio").rglob("receipt.json"))) == 1
    assert Path(results[0]["imported_path"]).read_bytes() == source.read_bytes()


def test_concurrent_same_client_name_does_not_overwrite_successful_creation(
    tmp_path: Path,
) -> None:
    (tmp_path / "Studio").mkdir()
    for session in ("alpha", "beta"):
        _run(tmp_path, session, "configure")
    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = [
            workers.submit(_run, tmp_path, session, "create", "Synthetic Same")
            for session in ("alpha", "beta")
        ]
        results, failures = [], []
        for future in futures:
            try:
                results.append(future.result())
            except subprocess.CalledProcessError as exc:
                failures.append(exc)
    assert len(results) == len(failures) == 1
    assert "already has the generated client label" in failures[0].stderr
    directory = _run(tmp_path, "fresh", "clients")
    assert directory["registered_client_count"] == 1
    assert directory["clients"][0]["client_id"] == results[0]["client_id"]


def test_registry_timeout_preserves_owner_lock_and_allows_later_retry(
    tmp_path: Path,
) -> None:
    owner = _lock_process(tmp_path, "hold")
    try:
        assert owner.stdout.readline().strip() == "ready"
        assert owner.stdout.readline().strip() == "acquired"
        path = next((tmp_path / "profile").rglob(".identities.lock"))
        identity = (path.stat().st_dev, path.stat().st_ino)
        program = (
            "import sys; from pathlib import Path; sys.path.insert(0,sys.argv[1]); "
            "import archive_preferences as p; "
            "guard=p.registry_lock(Path(sys.argv[2]),Path(sys.argv[3]),timeout_seconds=.15); "
            "guard.__enter__()"
        )
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                program,
                str(SCRIPTS),
                str(tmp_path / "profile"),
                str(tmp_path / "Studio"),
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode != 0
        assert "Archive identity registry is busy" in result.stderr
        assert (path.stat().st_dev, path.stat().st_ino) == identity
        assert owner.poll() is None
        owner.communicate("release\n", timeout=5)
        retry = _lock_process(tmp_path, "take")
        output, error = retry.communicate(timeout=5)
        assert retry.returncode == 0, error
        assert output.splitlines() == ["ready", "acquired"]
    finally:
        if owner.poll() is None:
            owner.kill()
            owner.communicate()


@pytest.mark.parametrize("replacement", ["missing", "foreign", "symlink"])
def test_changed_selected_client_never_receives_a_continuation(
    tmp_path: Path,
    replacement: str,
) -> None:
    (tmp_path / "Studio").mkdir()
    _run(tmp_path, "alpha", "configure")
    alpha = _run(tmp_path, "alpha", "create", "Synthetic Alpha")
    beta = _run(tmp_path, "beta", "create", "Synthetic Beta")
    selected = tmp_path / "Studio/Synthetic Alpha"
    selected.rename(tmp_path / "removed-alpha")
    if replacement == "foreign":
        import shutil

        shutil.copytree(tmp_path / "Studio/Synthetic Beta", selected)
    elif replacement == "symlink":
        selected.symlink_to(
            tmp_path / "Studio/Synthetic Beta", target_is_directory=True
        )
    source = tmp_path / "note.txt"
    source.write_text("Never save into Beta", encoding="utf-8")
    with pytest.raises(subprocess.CalledProcessError):
        _run(
            tmp_path,
            "alpha",
            "continue",
            alpha["client_id"],
            alpha["engagement_id"],
            str(source),
        )
    assert not list((tmp_path / "Studio/Synthetic Beta").rglob("note.txt"))
    assert beta["client_id"] != alpha["client_id"]
