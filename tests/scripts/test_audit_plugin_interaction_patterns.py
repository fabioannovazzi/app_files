from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "audit_plugin_interaction_patterns.py"
CATALOG_PATH = ROOT / "docs" / "openai_plugin_interaction_patterns.json"


def load_audit_module():
    spec = importlib.util.spec_from_file_location(
        "audit_plugin_interaction_patterns", SCRIPT_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_plugin(
    root: Path,
    name: str,
    skill_text: str,
    *,
    mcp_text: str = "",
    asset_text: str = "",
    workbench_adapter: bool = False,
) -> Path:
    plugin_dir = root / "plugins" / name
    manifest_dir = plugin_dir / ".codex-plugin"
    skill_dir = plugin_dir / "skills" / name
    manifest_dir.mkdir(parents=True)
    skill_dir.mkdir(parents=True)
    (manifest_dir / "plugin.json").write_text(
        json.dumps({"name": name, "version": "0.1.0"}),
        encoding="utf-8",
    )
    (skill_dir / "SKILL.md").write_text(skill_text, encoding="utf-8")
    if mcp_text:
        mcp_dir = plugin_dir / "mcp"
        mcp_dir.mkdir()
        (mcp_dir / "server.cjs").write_text(mcp_text, encoding="utf-8")
    if asset_text or workbench_adapter:
        asset_dir = plugin_dir / "assets"
        asset_dir.mkdir()
        if asset_text:
            (asset_dir / "sample-review-widget.html").write_text(
                asset_text, encoding="utf-8"
            )
        if workbench_adapter:
            (asset_dir / "review-workbench-adapter.json").write_text(
                "{}", encoding="utf-8"
            )
    return plugin_dir


def test_repo_plugins_have_no_blocking_interaction_pattern_issues() -> None:
    audit = load_audit_module()

    reports = audit.audit_plugins(ROOT)
    severe = [
        (report.plugin, issue.code)
        for report in reports
        for issue in report.issues
        if issue.severity in {"blocker", "high", "medium"}
    ]

    assert reports
    assert severe == []


def test_audit_detects_continue_theater_and_missing_approval_boundary(
    tmp_path: Path,
) -> None:
    audit = load_audit_module()
    write_plugin(
        tmp_path,
        "bad-review",
        "Ask the user to type continue before every step.",
    )

    report = audit.audit_plugins(tmp_path)[0]
    issue_codes = {issue.code for issue in report.issues}

    assert report.status == "blocker"
    assert "continue_theater" in issue_codes
    assert "approval_boundary_missing" in issue_codes


def test_stateful_review_plugin_requires_visible_decision_contract(
    tmp_path: Path,
) -> None:
    audit = load_audit_module()
    write_plugin(
        tmp_path,
        "stateful-review",
        (
            "Use local deterministic scripts. Ask only for external, destructive, "
            "approval-sensitive, or material choices."
        ),
        mcp_text=(
            "openai/outputTemplate render_stateful_review "
            "save_stateful_decisions apply_stateful_decisions ui_decisions.json"
        ),
        asset_text="<html><body>review-widget</body></html>",
    )

    report = audit.audit_plugins(tmp_path)[0]
    issue_codes = {issue.code for issue in report.issues}

    assert report.status == "needs_attention"
    assert report.mcp_review_widget is True
    assert report.stateful_decision_review is True
    assert "decision_contract_missing_in_skill" in issue_codes
    assert "visible_handoff_missing" in issue_codes


def test_main_emits_json_summary(capsys) -> None:
    audit = load_audit_module()

    exit_code = audit.main(["--format", "json", "--fail-on", "none"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    pattern_ids = {pattern["pattern_id"] for pattern in payload["patterns"]}
    coverage = {item["pattern_id"]: item for item in payload["pattern_coverage"]}
    assert exit_code == 0
    assert payload["summary"]["plugin_count"] >= 1
    assert payload["plugins"]
    assert payload["playbook_section_coverage"]
    assert payload["rejected_patterns"]
    assert "ask_material_questions_only" in pattern_ids
    assert "stateful_decision_review" in pattern_ids
    assert "local_browser_writeback" in pattern_ids
    assert any(
        "test_plugin_skills_do_not_require_continue_theater" in verifier
        for pattern in payload["patterns"]
        for verifier in pattern["verifier_paths"]
    )
    assert coverage["ask_material_questions_only"]["missing_plugins"] == []
    assert coverage["stateful_decision_review"]["missing_plugins"] == []
    assert coverage["local_browser_writeback"]["missing_plugins"] == []
    assert "clara" not in coverage["stateful_decision_review"]["applicable_plugins"]


def test_pattern_catalog_is_loaded_from_structured_artifact() -> None:
    audit = load_audit_module()

    payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    catalog_ids = [pattern.pattern_id for pattern in audit.pattern_catalog()]

    assert payload["schema_version"] == "1.0"
    assert [pattern["pattern_id"] for pattern in payload["patterns"]] == catalog_ids
    assert "ask_material_questions_only" in catalog_ids
    assert "shared_ui_with_explicit_exceptions" in catalog_ids
    assert "local_browser_writeback" in catalog_ids


def test_committed_pattern_catalog_is_formatted_and_references_real_files() -> None:
    audit = load_audit_module()
    text = CATALOG_PATH.read_text(encoding="utf-8")
    payload = json.loads(text)
    playbook_text = (ROOT / payload["source"]).read_text(encoding="utf-8")
    playbook_sections = {
        line.removeprefix("### ").strip()
        for line in playbook_text.splitlines()
        if line.startswith("### ")
    }
    adopted_principles_text = playbook_text.split("## Adopted Principles", 1)[1].split(
        "## Patterns To Reject Or Modify", 1
    )[0]
    adopted_principle_sections = {
        line.removeprefix("### ").strip()
        for line in adopted_principles_text.splitlines()
        if line.startswith("### ")
    }
    catalog_pattern_ids = {pattern["pattern_id"] for pattern in payload["patterns"]}
    adopted_principle_pattern_ids = {
        pattern["pattern_id"]
        for pattern in payload["patterns"]
        if pattern["playbook_section"] in adopted_principle_sections
    }
    coverage_sections = {
        item["section"] for item in payload["playbook_section_coverage"]
    }
    covered_pattern_ids = {
        pattern_id
        for item in payload["playbook_section_coverage"]
        for pattern_id in item["pattern_ids"]
    }
    rejected_playbook_text = playbook_text.split("## Patterns To Reject Or Modify", 1)[
        1
    ].split("## Implementation Map", 1)[0]
    rejected_bullets = []
    current_bullet = ""
    for line in rejected_playbook_text.splitlines():
        if line.startswith("- "):
            if current_bullet:
                rejected_bullets.append(current_bullet.strip())
            current_bullet = line.removeprefix("- ").strip()
        elif current_bullet and line.startswith("  "):
            current_bullet += " " + line.strip()
    if current_bullet:
        rejected_bullets.append(current_bullet.strip())
    rejected_catalog_text = {
        item["playbook_text"] for item in payload["rejected_patterns"]
    }

    assert text == json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    assert (ROOT / payload["source"]).is_file()
    assert coverage_sections == adopted_principle_sections
    assert adopted_principle_pattern_ids <= covered_pattern_ids
    assert rejected_catalog_text == set(rejected_bullets)
    for pattern in payload["patterns"]:
        assert pattern["playbook_section"] in playbook_sections
        for verifier in pattern["verifier_paths"]:
            path_text = verifier.split("::", 1)[0]
            assert (ROOT / path_text).is_file(), verifier
    for item in payload["playbook_section_coverage"]:
        assert item["section"] in playbook_sections
        assert item["coverage_mode"] in {"catalog_pattern", "contract_guidance"}
        for pattern_id in item["pattern_ids"]:
            assert pattern_id in catalog_pattern_ids
        for verifier in item["verifier_paths"]:
            path_text = verifier.split("::", 1)[0]
            assert (ROOT / path_text).is_file(), verifier
    for item in payload["rejected_patterns"]:
        assert item["local_replacement"]
        assert item["guardrail_signals"]
        for signal in item["guardrail_signals"]:
            assert signal in audit.KNOWN_PATTERN_SIGNALS
        for verifier in item["verifier_paths"]:
            path_text = verifier.split("::", 1)[0]
            assert (ROOT / path_text).is_file(), verifier


def test_pattern_catalog_loader_rejects_duplicate_ids(tmp_path: Path) -> None:
    audit = load_audit_module()
    duplicate_catalog = tmp_path / "patterns.json"
    duplicate_catalog.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "patterns": [
                    {
                        "pattern_id": "duplicate",
                        "source_pattern": "source",
                        "local_rule": "rule",
                        "playbook_section": "section",
                        "evidence_signals": ["has_no_continue_theater"],
                        "verifier_paths": ["tests/example.py"],
                        "adoption_scope": "scope",
                        "applicability_signals": [],
                        "evidence_mode": "all",
                    },
                    {
                        "pattern_id": "duplicate",
                        "source_pattern": "source",
                        "local_rule": "rule",
                        "playbook_section": "section",
                        "evidence_signals": ["has_no_continue_theater"],
                        "verifier_paths": ["tests/example.py"],
                        "adoption_scope": "scope",
                        "applicability_signals": [],
                        "evidence_mode": "all",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Duplicate interaction pattern id"):
        audit.load_pattern_catalog(duplicate_catalog)


def test_pattern_catalog_loader_rejects_unknown_signals(tmp_path: Path) -> None:
    audit = load_audit_module()
    bad_catalog = tmp_path / "patterns.json"
    bad_catalog.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "patterns": [
                    {
                        "pattern_id": "bad_signal",
                        "source_pattern": "source",
                        "local_rule": "rule",
                        "playbook_section": "section",
                        "evidence_signals": ["has_no_continue_typo"],
                        "verifier_paths": ["tests/example.py"],
                        "adoption_scope": "scope",
                        "applicability_signals": [],
                        "evidence_mode": "all",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unknown signal"):
        audit.load_pattern_catalog(bad_catalog)


def test_playbook_section_coverage_rejects_unknown_patterns(tmp_path: Path) -> None:
    audit = load_audit_module()
    bad_catalog = tmp_path / "patterns.json"
    bad_catalog.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "patterns": [
                    {
                        "pattern_id": "known",
                        "source_pattern": "source",
                        "local_rule": "rule",
                        "playbook_section": "section",
                        "evidence_signals": ["has_no_continue_theater"],
                        "verifier_paths": ["tests/example.py"],
                        "adoption_scope": "scope",
                        "applicability_signals": [],
                        "evidence_mode": "all",
                    }
                ],
                "playbook_section_coverage": [
                    {
                        "section": "section",
                        "coverage_mode": "catalog_pattern",
                        "pattern_ids": ["missing"],
                        "verifier_paths": ["tests/example.py"],
                        "note": "note",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unknown pattern id"):
        audit.load_playbook_section_coverage(bad_catalog)


def test_rejected_pattern_loader_rejects_duplicate_ids(tmp_path: Path) -> None:
    audit = load_audit_module()
    bad_catalog = tmp_path / "patterns.json"
    bad_catalog.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "patterns": [
                    {
                        "pattern_id": "known",
                        "source_pattern": "source",
                        "local_rule": "rule",
                        "playbook_section": "section",
                        "evidence_signals": ["has_no_continue_theater"],
                        "verifier_paths": ["tests/example.py"],
                        "adoption_scope": "scope",
                        "applicability_signals": [],
                        "evidence_mode": "all",
                    }
                ],
                "playbook_section_coverage": [
                    {
                        "section": "section",
                        "coverage_mode": "catalog_pattern",
                        "pattern_ids": ["known"],
                        "verifier_paths": ["tests/example.py"],
                        "note": "note",
                    }
                ],
                "rejected_patterns": [
                    {
                        "pattern_id": "duplicate",
                        "playbook_text": "reject",
                        "local_replacement": "replace",
                        "guardrail_signals": ["has_no_continue_theater"],
                        "verifier_paths": ["tests/example.py"],
                    },
                    {
                        "pattern_id": "duplicate",
                        "playbook_text": "reject",
                        "local_replacement": "replace",
                        "guardrail_signals": ["has_no_continue_theater"],
                        "verifier_paths": ["tests/example.py"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Duplicate rejected interaction pattern id"):
        audit.load_rejected_patterns(bad_catalog)


def test_rejected_pattern_loader_rejects_unknown_guardrail_signals(
    tmp_path: Path,
) -> None:
    audit = load_audit_module()
    bad_catalog = tmp_path / "patterns.json"
    bad_catalog.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "patterns": [
                    {
                        "pattern_id": "known",
                        "source_pattern": "source",
                        "local_rule": "rule",
                        "playbook_section": "section",
                        "evidence_signals": ["has_no_continue_theater"],
                        "verifier_paths": ["tests/example.py"],
                        "adoption_scope": "scope",
                        "applicability_signals": [],
                        "evidence_mode": "all",
                    }
                ],
                "playbook_section_coverage": [
                    {
                        "section": "section",
                        "coverage_mode": "catalog_pattern",
                        "pattern_ids": ["known"],
                        "verifier_paths": ["tests/example.py"],
                        "note": "note",
                    }
                ],
                "rejected_patterns": [
                    {
                        "pattern_id": "bad_signal",
                        "playbook_text": "reject",
                        "local_replacement": "replace",
                        "guardrail_signals": ["bad_signal"],
                        "verifier_paths": ["tests/example.py"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unknown signal"):
        audit.load_rejected_patterns(bad_catalog)


def test_markdown_output_includes_pattern_catalog(capsys) -> None:
    audit = load_audit_module()

    exit_code = audit.main(["--format", "markdown", "--fail-on", "none"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "## Pattern Coverage" in captured.out
    assert "## Pattern Catalog" in captured.out
    assert "## Playbook Traceability" in captured.out
    assert "## Rejected Patterns" in captured.out
    assert "ask_material_questions_only" in captured.out
    assert "stateful_decision_review" in captured.out
    assert "local_browser_writeback" in captured.out
    assert "Asking the user to type `continue`" in captured.out
    assert "continue_theater" in captured.out


def test_pattern_coverage_respects_applicability(tmp_path: Path) -> None:
    audit = load_audit_module()
    write_plugin(
        tmp_path,
        "plain-plugin",
        (
            "Use local deterministic scripts. Ask only for external, destructive, "
            "approval-sensitive, or material choices."
        ),
    )
    write_plugin(
        tmp_path,
        "stateful-review",
        (
            "Use local deterministic scripts. Ask only for external, destructive, "
            "approval-sensitive, or material choices. Persist ui_decisions.json, "
            "applied_decisions.json, and final_artifacts.json."
        ),
        mcp_text=(
            "openai/outputTemplate render_stateful_review "
            "save_stateful_decisions apply_stateful_decisions ui_decisions.json"
        ),
        workbench_adapter=True,
    )

    coverage = {
        item.pattern_id: item
        for item in audit.pattern_coverage(audit.audit_plugins(tmp_path))
    }

    assert coverage["stateful_decision_review"].applicable_plugins == (
        "stateful-review",
    )
    assert coverage["stateful_decision_review"].missing_plugins == ()
    assert coverage["local_browser_writeback"].applicable_plugins == (
        "stateful-review",
    )
    assert coverage["local_browser_writeback"].missing_plugins == ()
    assert coverage["visible_review_handoff"].missing_plugins == ("stateful-review",)
