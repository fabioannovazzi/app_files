from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "installed_product", ROOT / "scripts/check_installed_product.py"
)
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


def entry(*, version="0.1.253", marketplace="openai-curated-remote", enabled=True):
    return {
        "name": "vera",
        "pluginId": f"vera@{marketplace}",
        "version": version,
        "installed": True,
        "enabled": enabled,
        "source": {
            "source": "remote" if marketplace == "openai-curated-remote" else "local"
        },
    }


@pytest.mark.parametrize(
    "installed",
    [
        [],
        [entry(enabled=False)],
        [entry(version="0.1.219")],
        [entry(marketplace="mp-vera")],
        [entry(), entry(marketplace="mp-vera")],
    ],
)
def test_rejects_missing_disabled_stale_local_and_duplicate_installations(installed):
    assert checker.inspect_installation({"installed": installed}, "vera", "0.1.253")


def test_accepts_one_official_version_and_ignores_disabled_old_installation():
    inventory = {"installed": [entry(), entry(marketplace="mp-vera", enabled=False)]}
    assert checker.inspect_installation(inventory, "vera", "0.1.253") == []


def test_missing_inventory_is_not_a_pass():
    assert checker.inspect_installation({}, "vera", "0.1.253")


@pytest.mark.parametrize("version,valid", [("0.1.219", False), ("0.1.253", True)])
def test_checks_the_exposed_skill_even_when_a_newer_cache_exists(
    tmp_path, version, valid
):
    root = tmp_path / version
    skill = root / "skills/vera/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("Vera")
    manifest = root / ".codex-plugin/plugin.json"
    manifest.parent.mkdir()
    manifest.write_text(json.dumps({"name": "vera", "version": version}))
    assert (checker.inspect_skill(skill, "vera", "0.1.253") == []) is valid


def test_deleted_skill_requires_a_fresh_conversation(tmp_path):
    assert (
        "fresh conversation"
        in checker.inspect_skill(tmp_path / "old/SKILL.md", "vera", "0.1.253")[0]
    )
