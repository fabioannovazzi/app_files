from __future__ import annotations

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

__all__: list[str] = []
ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "plugins" / "studio-archive" / "scripts"
WORKER = """
import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import archive_core as a
state,root=Path(sys.argv[2]),Path(sys.argv[3])
action=sys.argv[4]
if action=='configure':
    result=a.configure_archive(root,state_dir=state)
elif action=='create':
    result=a.create_studio_client('Synthetic Contract Client',email_addresses=['private-alias@example.com'],state_dir=state)
    cid=result['client']['client_id']
    e=a.create_studio_client_engagement(cid,'Contract review',state_dir=state)
    result={'client_id':cid,'engagement_id':e['engagement']['engagement_id']}
elif action=='register':
    import time
    for attempt in range(50):
        try:
            rows=a.list_studio_clients(state_dir=state)['clients']
            scope=next(row['scope_id'] for row in rows if row['display_name']==sys.argv[5])
            result=a.set_studio_client_identity(scope,legal_names=[sys.argv[6]],state_dir=state)
            break
        except a.ArchiveError as exc:
            if 'transaction unavailable' not in str(exc):
                raise
            time.sleep(0.01)
    else:
        raise RuntimeError('Concurrent identity operation did not recover')
elif action=='resolve':
    result=a.resolve_studio_client_identity('legal_name','Synthetic Contract Client',state_dir=state)
elif action=='engagements':
    result=a.list_studio_client_engagements(sys.argv[5],state_dir=state)
else:
    result=a.list_studio_clients(state_dir=state)
print(json.dumps(result))
"""


def _run(
    base: Path, session: str, action: str, root: Path, *extra: str, profile: bool = True
) -> dict:
    environment = {**os.environ, "VERA_STUDIO_ARCHIVE_SESSION_ID": session}
    environment.pop("VERA_STUDIO_ARCHIVE_PROFILE_DIR", None)
    if profile:
        environment["VERA_STUDIO_ARCHIVE_PROFILE_DIR"] = str(base / "profile")
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            WORKER,
            str(SCRIPTS),
            str(base / session),
            str(root),
            action,
            *extra,
        ],
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def test_new_session_recovers_root_identity_and_engagement_without_setup(
    tmp_path: Path,
) -> None:
    root = tmp_path / "Studio"
    root.mkdir()
    _run(tmp_path, "a", "configure", root)
    created = _run(tmp_path, "a", "create", root)

    directory = _run(tmp_path, "b", "clients", root)
    identity = _run(tmp_path, "b", "resolve", root)
    engagements = _run(tmp_path, "b", "engagements", root, created["client_id"])

    assert directory["configured"] is True
    assert directory["registered_client_count"] == 1
    assert identity["resolution_status"] == "exact_match"
    assert identity["matches"][0]["client_id"] == created["client_id"]
    assert engagements["engagement_count"] == 1
    assert engagements["engagements"][0]["engagement_id"] == created["engagement_id"]
    assert "private-alias@example.com" not in json.dumps(identity)
    assert identity["private_identity_values_returned"] is False
    assert "studio_archive.sqlite3" not in {
        p.name for p in (tmp_path / "profile").rglob("*")
    }
    config_a = json.loads((tmp_path / "a" / "config.json").read_text())
    config_b = json.loads((tmp_path / "b" / "config.json").read_text())
    assert config_a["session_id"] == "a"
    assert config_b["session_id"] == "b"


def test_approved_root_change_keeps_existing_session_pinned_and_aliases_separate(
    tmp_path: Path,
) -> None:
    root_a, root_b = tmp_path / "Studio A", tmp_path / "Studio B"
    root_a.mkdir()
    root_b.mkdir()
    _run(tmp_path, "a", "configure", root_a)
    created = _run(tmp_path, "a", "create", root_a)
    _run(tmp_path, "b", "configure", root_b)

    existing = _run(tmp_path, "a", "clients", root_a)
    fresh = _run(tmp_path, "c", "clients", root_b)
    identity = _run(tmp_path, "c", "resolve", root_b)

    assert existing["clients"][0]["client_id"] == created["client_id"]
    assert fresh["registered_client_count"] == 0
    assert identity["resolution_status"] == "no_exact_match"
    assert json.loads((tmp_path / "a" / "config.json").read_text())[
        "archive_root"
    ] == str(root_a)


def test_explicit_state_without_profile_remains_isolated(tmp_path: Path) -> None:
    root = tmp_path / "Studio"
    root.mkdir()
    _run(tmp_path, "a", "configure", root, profile=False)

    directory = _run(tmp_path, "b", "clients", root, profile=False)

    assert directory["configured"] is False
    assert directory["setup_required"] is True
    assert not (tmp_path / "profile").exists()


def test_unavailable_remembered_archive_does_not_create_client_or_choose_another_root(
    tmp_path: Path,
) -> None:
    root = tmp_path / "Studio"
    root.mkdir()
    _run(tmp_path, "a", "configure", root)
    root.rmdir()

    with pytest.raises(subprocess.CalledProcessError) as failure:
        _run(tmp_path, "b", "clients", root)

    assert "does not exist" in failure.value.stderr
    assert not (tmp_path / "b" / "config.json").exists()
    assert not root.exists()


def test_malformed_profile_is_rejected_without_new_session_configuration(
    tmp_path: Path,
) -> None:
    root = tmp_path / "Studio"
    root.mkdir()
    _run(tmp_path, "a", "configure", root)
    preference = tmp_path / "profile" / "approved-archive.json"
    preference.write_text('{"archive_root":"/unexpected"}')

    with pytest.raises(subprocess.CalledProcessError) as failure:
        _run(tmp_path, "b", "clients", root)

    assert "malformed" in failure.value.stderr
    assert not (tmp_path / "b" / "config.json").exists()


def test_current_session_registry_migrates_without_scanning_other_sessions(
    tmp_path: Path,
) -> None:
    root = tmp_path / "Studio"
    root.mkdir()
    _run(tmp_path, "a", "configure", root, profile=False)
    created = _run(tmp_path, "a", "create", root, profile=False)
    _run(tmp_path, "a", "configure", root)
    _run(tmp_path, "a", "clients", root)

    identity = _run(tmp_path, "b", "resolve", root)

    assert identity["resolution_status"] == "exact_match"
    assert identity["matches"][0]["client_id"] == created["client_id"]
    assert (tmp_path / "a" / "client-identities.json").is_file()


def test_concurrent_sessions_retain_both_confirmed_identity_profiles(
    tmp_path: Path,
) -> None:
    root = tmp_path / "Studio"
    (root / "Alpha").mkdir(parents=True)
    (root / "Beta").mkdir()
    _run(tmp_path, "a", "configure", root)
    _run(tmp_path, "b", "configure", root)

    with ThreadPoolExecutor(max_workers=2) as workers:
        alpha = workers.submit(
            _run, tmp_path, "a", "register", root, "Alpha", "Private Alpha Alias"
        )
        beta = workers.submit(
            _run, tmp_path, "b", "register", root, "Beta", "Private Beta Alias"
        )
        alpha.result()
        beta.result()
    directory = _run(tmp_path, "c", "clients", root)

    assert directory["registered_client_count"] == 2
    assert directory["candidate_only_profile_count"] == 2
    assert "Private Alpha Alias" not in json.dumps(directory)
    assert "Private Beta Alias" not in json.dumps(directory)


def test_existing_approved_session_bootstraps_private_profile_and_legacy_aliases(
    tmp_path: Path,
) -> None:
    root = tmp_path / "Studio"
    root.mkdir()
    _run(tmp_path, "old", "configure", root, profile=False)
    created = _run(tmp_path, "old", "create", root, profile=False)

    current = _run(tmp_path, "old", "clients", root)
    fresh = _run(tmp_path, "fresh", "resolve", root)

    assert current["registered_client_count"] == 1
    assert fresh["resolution_status"] == "exact_match"
    assert fresh["matches"][0]["client_id"] == created["client_id"]
    assert json.loads((tmp_path / "profile/approved-archive.json").read_text())[
        "archive_root"
    ] == str(root)
    if os.name == "posix":
        assert (tmp_path / "profile").stat().st_mode & 0o777 == 0o700


def test_legacy_session_refuses_profile_inside_sources_before_creating_it(
    tmp_path: Path,
) -> None:
    root = tmp_path / "Studio"
    root.mkdir()
    _run(tmp_path, "old", "configure", root, profile=False)
    profile = root / "private-profile"
    environment = {
        **os.environ,
        "VERA_STUDIO_ARCHIVE_PROFILE_DIR": str(profile),
        "VERA_STUDIO_ARCHIVE_SESSION_ID": "old",
    }

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            WORKER,
            str(SCRIPTS),
            str(tmp_path / "old"),
            str(root),
            "clients",
        ],
        env=environment,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "outside the source archive" in result.stderr
    assert not profile.exists()
