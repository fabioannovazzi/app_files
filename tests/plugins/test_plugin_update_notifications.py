from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
CLARA_ROOT = ROOT / "plugins" / "clara"
VERA_ROOT = ROOT / "plugins" / "vera"
PUBLISHED_VERSIONS_PATH = ROOT / "static" / "shared" / "codex-plugin-versions.json"
UPDATE_SCRIPT_PATH = CLARA_ROOT / "scripts" / "check_for_update.py"


def load_update_checker() -> Any:
    spec = importlib.util.spec_from_file_location(
        "plugin_update_checker", UPDATE_SCRIPT_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def write_plugin_manifest(root: Path, name: str, version: str) -> None:
    manifest_path = root / ".codex-plugin" / "plugin.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(
            {
                "name": name,
                "version": version,
                "interface": {"displayName": name.title()},
            }
        ),
        encoding="utf-8",
    )


def update_manifest(name: str, version: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "plugins": {
            name: {
                "published_version": version,
                "install_url": f"https://chatgpt.com/plugins/{name}",
            }
        },
    }


@pytest.mark.parametrize(
    ("candidate", "installed", "expected"),
    [
        ("1.2.0", "1.1.9", True),
        ("1.0.0", "1.0.0", False),
        ("1.0.0+build.2", "1.0.0+build.1", False),
        ("1.0.0", "1.0.0-rc.1", True),
        ("1.0.0-rc.2", "1.0.0-rc.1", True),
    ],
)
def test_is_newer_version_uses_semver_precedence(
    candidate: str, installed: str, expected: bool
) -> None:
    checker = load_update_checker()

    result = checker.is_newer_version(candidate, installed)

    assert result is expected


def test_check_for_update_returns_message_for_new_published_version(
    tmp_path: Path,
) -> None:
    checker = load_update_checker()
    plugin_root = tmp_path / "plugin"
    write_plugin_manifest(plugin_root, "clara", "1.0.0")
    opener = lambda *_args, **_kwargs: FakeResponse(  # noqa: E731
        update_manifest("clara", "1.1.0")
    )

    result = checker.check_for_update(
        plugin_root,
        tmp_path / "data",
        now=1_000.0,
        opener=opener,
    )

    assert result == (
        "Clara update available: installed 1.0.0, published 1.1.0. "
        "Visit https://chatgpt.com/plugins/clara to get the latest published version."
    )


def test_check_for_update_uses_fresh_local_cache(tmp_path: Path) -> None:
    checker = load_update_checker()
    plugin_root = tmp_path / "plugin"
    plugin_data = tmp_path / "data"
    write_plugin_manifest(plugin_root, "vera", "1.0.0")
    plugin_data.mkdir()
    (plugin_data / "update-check.json").write_text(
        json.dumps(
            {
                "checked_at": 900.0,
                "manifest": update_manifest("vera", "1.1.0"),
            }
        ),
        encoding="utf-8",
    )

    def fail_if_called(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("A fresh cache must avoid a network request")

    result = checker.check_for_update(
        plugin_root,
        plugin_data,
        now=1_000.0,
        opener=fail_if_called,
    )

    assert result is not None
    assert "Vera update available" in result


def test_check_for_update_fails_open_when_network_is_unavailable(
    tmp_path: Path,
) -> None:
    checker = load_update_checker()
    plugin_root = tmp_path / "plugin"
    write_plugin_manifest(plugin_root, "clara", "1.0.0")

    def unavailable(*_args: object, **_kwargs: object) -> None:
        raise TimeoutError

    result = checker.check_for_update(
        plugin_root,
        tmp_path / "data",
        now=1_000.0,
        opener=unavailable,
    )

    assert result is None
    cache = json.loads(
        (tmp_path / "data" / "update-check.json").read_text(encoding="utf-8")
    )
    assert cache == {"checked_at": 1_000.0, "manifest": {}}


def test_check_for_update_suppresses_repeat_notification_within_one_day(
    tmp_path: Path,
) -> None:
    checker = load_update_checker()
    plugin_root = tmp_path / "plugin"
    plugin_data = tmp_path / "data"
    write_plugin_manifest(plugin_root, "clara", "1.0.0")
    plugin_data.mkdir()
    (plugin_data / "update-check.json").write_text(
        json.dumps(
            {
                "checked_at": 900.0,
                "manifest": update_manifest("clara", "1.1.0"),
                "last_notified_at": 950.0,
                "last_notified_version": "1.1.0",
            }
        ),
        encoding="utf-8",
    )

    def fail_if_called(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("A fresh cache must avoid a network request")

    result = checker.check_for_update(
        plugin_root,
        plugin_data,
        now=1_000.0,
        opener=fail_if_called,
    )

    assert result is None


@pytest.mark.parametrize("plugin_root", [CLARA_ROOT, VERA_ROOT])
def test_plugins_declare_trusted_session_start_update_hook(plugin_root: Path) -> None:
    manifest = json.loads(
        (plugin_root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    hooks = json.loads(
        (plugin_root / "hooks" / "hooks.json").read_text(encoding="utf-8")
    )

    assert manifest["hooks"] == "./hooks/hooks.json"
    session_hook = hooks["hooks"]["SessionStart"][0]
    assert session_hook["matcher"] == "startup|resume"
    assert session_hook["hooks"] == [
        {
            "type": "command",
            "command": 'python3 "$PLUGIN_ROOT/scripts/check_for_update.py"',
            "timeout": 8,
        }
    ]


def test_session_start_prioritizes_exact_fixed_request_message(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    checker = load_update_checker()
    plugin_root = tmp_path / "plugin"
    plugin_data = tmp_path / "data"
    write_plugin_manifest(plugin_root, "clara", "1.0.0")
    fixed_message = "The problem you reported as CR-123 is fixed. Update now?"
    monkeypatch.setenv("PLUGIN_ROOT", str(plugin_root))
    monkeypatch.setenv("PLUGIN_DATA", str(plugin_data))
    monkeypatch.setattr(
        checker,
        "_check_fixed_change_requests",
        lambda *_args: fixed_message,
    )

    result = checker.main()

    assert result == 0
    assert json.loads(capsys.readouterr().out) == {"systemMessage": fixed_message}


def test_plugin_update_scripts_stay_identical() -> None:
    clara_script = (CLARA_ROOT / "scripts" / "check_for_update.py").read_text(
        encoding="utf-8"
    )
    vera_script = (VERA_ROOT / "scripts" / "check_for_update.py").read_text(
        encoding="utf-8"
    )

    assert clara_script == vera_script


@pytest.mark.parametrize("plugin_root", [CLARA_ROOT, VERA_ROOT])
def test_published_manifest_never_advertises_unreleased_source_version(
    plugin_root: Path,
) -> None:
    checker = load_update_checker()
    source_manifest = json.loads(
        (plugin_root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    published_manifest = json.loads(PUBLISHED_VERSIONS_PATH.read_text(encoding="utf-8"))
    published_version = published_manifest["plugins"][plugin_root.name][
        "published_version"
    ]

    result = checker.is_newer_version(published_version, source_manifest["version"])

    assert result is False
