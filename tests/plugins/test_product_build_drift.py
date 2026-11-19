"""A deferred sibling build cannot hide source or released-package drift."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import check_product_build_drift as gate


@pytest.mark.parametrize(
    ("changed", "bumped", "drift", "expected"),
    [
        ([], "lucia", "plugin_packages/clara/claude/file.py", []),
        (
            [],
            "lucia",
            "plugin_packages/lucia/claude/file.py",
            ["plugin_packages/lucia/claude/file.py"],
        ),
        (
            [],
            "lucia",
            "plugins/clara/scripts/helper.py",
            ["plugins/clara/scripts/helper.py"],
        ),
        (
            ["plugin_packages/clara/claude/file.py"],
            None,
            "plugin_packages/clara/claude/file.py",
            ["plugin_packages/clara/claude/file.py"],
        ),
        ([], "lucia", "static/shared/clara/downloads/clara-cowork-plugin.zip", []),
        (
            [],
            "lucia",
            "static/shared/clara/index.html",
            ["static/shared/clara/index.html"],
        ),
        (
            [],
            "lucia",
            "static/shared/lucia/downloads/lucia-cowork-plugin.zip",
            ["static/shared/lucia/downloads/lucia-cowork-plugin.zip"],
        ),
    ],
)
def test_drift_preserves_sources_and_released_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, changed, bumped, drift, expected
):
    for product in gate.PRODUCTS:
        manifest = tmp_path / f"plugins/{product}/.codex-plugin/plugin.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(json.dumps({"version": "2" if product == bumped else "1"}))

    def git(_root, *args):
        if args[0] == "show":
            return '{"version": "1"}'
        if len(args) == 4:
            return "\n".join(changed)
        return drift

    monkeypatch.setattr(gate, "_git", git)
    assert gate.check_drift(tmp_path, "base") == expected
