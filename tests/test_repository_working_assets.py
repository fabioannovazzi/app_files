from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROCESS_EXCEL_FIXTURE_SHA256 = (
    "1873ff5eb24f71dac52052cc5ff1602fd61cc649063e13b6a7a86b936e10708c"
)


def test_reporting_visual_reference_assets_match_manifest() -> None:
    manifest = json.loads(
        (ROOT / "docs" / "visual_reporting_references.json").read_text(encoding="utf-8")
    )
    local_assets = [
        ROOT / example["local_asset"]
        for example in manifest["examples"]
        if example.get("local_asset")
    ]

    assert len(local_assets) == 27
    assert all(path.is_file() for path in local_assets)


def test_process_excel_pdf_fixture_remains_available() -> None:
    fixture_path = ROOT / "tmp_test.pdf"

    assert (
        hashlib.sha256(fixture_path.read_bytes()).hexdigest()
        == PROCESS_EXCEL_FIXTURE_SHA256
    )


def test_codex_tool_scope_lists_are_tracked_with_current_paths() -> None:
    modules_scope = (ROOT / "tools" / "modules_to_scan.txt").read_text(encoding="utf-8")
    tests_scope = (ROOT / "tools" / "tests_to_scan.txt").read_text(encoding="utf-8")

    assert modules_scope.splitlines() == ["modules/", "src/"]
    assert tests_scope.splitlines() == ["tests/"]
