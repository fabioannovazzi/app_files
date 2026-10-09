"""Saved report delivery over the actual source MCP, using fictional cases only."""

from __future__ import annotations

import base64
import hashlib

import pytest

from tests.plugins.test_vera_model_data_report import _load_module
from tests.plugins.test_vera_native_archive_lifecycle import rpc_program
from tests.plugins.test_vera_native_fusion import (
    PROGRAM,
    api,
    case,
    merger,
)

__all__ = []


def saved_export(env: dict) -> dict:
    """Prepare one actual public export, separately from subsequent read actions."""
    return rpc_program(
        env,
        PROGRAM
        + "const p=setup(),f=fields('export');execute(prepare(p,f,'readable-report'));const result=setup();",
    )


@pytest.mark.parametrize("role", ["REVIEWER", "VIEWER"])
def test_saved_report_reopens_exact_markdown_without_rewriting_export(merger, role):
    env, store, _, _ = merger
    saved_export(env)
    env["VERA_WORKSPACE_ROLES"] = role
    history = store.report()["history"]
    report_paths = sorted((store.root / "exports").glob("*/model_data_report.*"))
    before = {
        p: (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
        for p in report_paths
    }

    result = rpc_program(
        env,
        PROGRAM
        + "const first=setup(),item=first.data.exports[0],artifact=payload(call('vera_workspace_fusion_artifact',{work_ref:first.work_ref,revision:first.revision,source_ref:first.source_ref,export_ref:item.export_ref,artifact_ref:'model_data_report.md'}));const result={first,second:setup(),artifact};",
    )

    export = result["first"]["data"]["exports"][0]
    markdown = export["model_report_markdown"]
    json_path = next(p for p in report_paths if p.suffix == ".json")
    assert markdown == _load_module().show_model_data_report(json_path)
    assert markdown == base64.b64decode(result["artifact"]["base64"]).decode()
    assert export == result["second"]["data"]["exports"][0]
    assert export["model_report"]["phases"][0]["outcome"] == "not_measurable"
    assert export["model_report"]["phases"][0]["model_visible"] == []
    assert "cannot observe" in markdown
    assert result["first"]["can_write"] is (role == "REVIEWER")
    assert store.report()["history"] == history
    assert {
        p: (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
        for p in report_paths
    } == before


@pytest.mark.parametrize("variant", ["changed_markdown", "linked_markdown"])
def test_saved_report_refuses_changed_or_linked_markdown(merger, tmp_path, variant):
    env, store, _, _ = merger
    saved_export(env)
    markdown = next((store.root / "exports").glob("*/model_data_report.md"))
    if variant == "changed_markdown":
        markdown.write_text("# Fabricated exposure claim\n", encoding="utf-8")
    else:
        other = tmp_path / "same-report.md"
        other.write_bytes(markdown.read_bytes())
        markdown.unlink()
        markdown.symlink_to(other)
    history = store.report()["history"]

    result = rpc_program(
        env,
        "const result=call('vera_workspace_fusion_setup',{work_ref:'fictional-merger'});",
    )

    assert result["isError"] is True
    assert (
        "workspace" not in result.get("_meta", {})
        or "data" not in result["_meta"]["workspace"]
    )
    assert store.report()["history"] == history
