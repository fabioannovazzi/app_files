"""Keep teaching acceptance independent of ordinary product release checks."""

from __future__ import annotations

import subprocess
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

import pytest
import yaml

__all__: list[str] = []

ROOT = Path(__file__).resolve().parents[2]


def workflow(name: str) -> dict[str, Any]:
    """Read a workflow and normalize YAML 1.1's boolean spelling of `on`."""
    document = yaml.safe_load((ROOT / ".github" / "workflows" / name).read_text())
    if True in document:
        document["on"] = document.pop(True)
    return document


@pytest.mark.parametrize(
    ("changed_path", "runs_teaching"),
    [
        ("plugins/journal-sampling/scripts/journal_sampling_core.py", False),
        ("plugins/check-entries/scripts/check_entries_core.py", False),
        ("tests/plugins/test_journal_zero_rows.py", False),
        ("modules/operational_incidents/api.py", False),
        ("plugins/vera/assets/courses/journal-sampling/course.json", False),
        ("plugins/vera/assets/courses/index.json", False),
        ("plugins/vera/privacy/services/local-onboarding.json", False),
        ("plugins/vera/.codex-plugin/plugin.json", False),
        ("plugin_packages/vera/vera-plugin.zip", False),
        ("static/shared/vera/downloads/vera-cowork-plugin.zip", False),
        ("static/shared/vera/index.html", False),
        ("scripts/course_materials/kits_it_accounting.json", True),
        ("scripts/course_materials/inputs/budget/facts-it.md", True),
        ("scripts/course_materials/release_reviews/vera/journal-sampling.json", True),
        ("plugins/_shared/vendor/modules/courseware/execution.py", True),
        ("plugins/_shared/vendor/modules/desktop_teaching/onboarding.py", True),
        ("plugins/vera/scripts/local_teaching.py", True),
        ("plugins/clara/scripts/_desktop_teaching.py", True),
        ("plugins/vera/scripts/local_onboarding_case.py", True),
        ("plugins/vera/scripts/course_chat_mcp.cjs", True),
        ("plugins/vera/skills/learn-with-vera/SKILL.md", True),
        ("tests/plugins/test_teaching_kit_execution.py", True),
        ("tests/plugins/_business_teaching.py", True),
        ("tests/plugins/test_course_file_access.py", True),
        (".github/workflows/teaching-kits.yml", True),
    ],
)
def test_teaching_triggers_distinguish_authoring_from_generated_release_files(
    changed_path: str, runs_teaching: bool
) -> None:
    """Exercise representative paths against the actual positive glob filters."""
    filters = workflow("teaching-kits.yml")["on"]["pull_request"]["paths"]

    matched = any(fnmatchcase(changed_path, pattern) for pattern in filters)

    assert matched is runs_teaching


def test_teaching_push_and_pr_scope_match_and_manual_execution_remains_available() -> (
    None
):
    events = workflow("teaching-kits.yml")["on"]

    assert events["push"]["paths"] == events["pull_request"]["paths"]
    assert events["push"]["branches"] == ["main"]
    assert "workflow_dispatch" in events


def test_normal_runtime_ci_has_no_teaching_acceptance_dependency() -> None:
    runtime = workflow("plugin-runtime.yml")
    jobs = runtime["jobs"]
    commands = str(jobs)

    assert "paths" not in (runtime["on"]["pull_request"] or {})
    assert "paths" not in runtime["on"]["push"]
    assert "teaching-kits" not in jobs
    assert "local-teaching" not in jobs
    assert "scripts/course_materials/verify_release.py" not in commands
    assert "tests/plugins/test_teaching_release_review.py" not in commands
    assert "teaching-native.xml" not in commands
    assert "continue-on-error" not in commands


@pytest.mark.parametrize(
    "required_check",
    [
        "tests/plugins/test_check_entries_plugin.py",
        "test_vouching_kit_runs_live_sample_handoff_and_current_checks",
        "tests/plugins/test_studio_archive_file_identity.py",
        "tests/plugins/test_vera_model_data_report.py",
        "tests/plugins/test_plugin_update_notifications.py",
        "tests/plugin_attribute_reporting.coveragerc",
        "tests/plugin_costing.coveragerc",
        "tests/plugin_management_presentation.coveragerc",
        "tests/plugin_new_client.coveragerc",
        "tests/plugin_bilancio_preview.coveragerc",
        "scripts/run_bilancio_alfa_v3_acceptance.py",
        "tests/plugins/test_concordato_plan_review_plugin.py",
        "tests/plugins/test_registro_imprese_sari_plugin.py",
        "tests/plugins/test_presenza_digitale_studio.py",
        "plugins/apertura-pratica/tests/test_apertura_pratica.py",
        "tests/plugins/test_business_valuation.py",
        "tests/plugins/test_cnc_integrations.py",
        "tests/plugins/test_matter_review_presentation.py",
    ],
)
def test_product_checks_remain_in_normal_ci(required_check: str) -> None:
    commands = str(workflow("plugin-runtime.yml")["jobs"])

    assert required_check in commands


def test_teaching_acceptance_and_coverage_still_fail_on_errors() -> None:
    jobs = workflow("teaching-kits.yml")["jobs"]
    commands = str(jobs)

    assert "scripts/course_materials/verify_release.py" in commands
    assert "--junitxml=${{ runner.temp }}/teaching-native.xml" in commands
    assert "--cov-fail-under=80" in commands
    assert "continue-on-error" not in commands
    assert jobs["local-teaching"]["strategy"]["matrix"]["os"] == [
        "ubuntu-latest",
        "macos-latest",
        "windows-latest",
    ]


def committed_scope_case(root: Path, changed_path: str) -> str:
    """Create two real commits so the workflow exercises Git's path semantics."""

    def git(*args: str) -> str:
        return subprocess.check_output(
            [
                "git",
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.com",
                "-c",
                "commit.gpgsign=false",
                *args,
            ],
            cwd=root,
            text=True,
        ).strip()

    git("init", "-q")
    (root / "baseline.txt").write_text("baseline\n")
    git("add", ".")
    git("commit", "-qm", "baseline")
    base = git("rev-parse", "HEAD")
    path = root / changed_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("changed\n")
    git("add", ".")
    git("commit", "-qm", "change")
    return base


@pytest.mark.parametrize(
    ("changed_path", "event", "base_mode", "expected"),
    [
        ("scripts/course_materials/kits_it.json", "pull_request", "valid", "true"),
        (
            "scripts/course_materials/release_reviews/vera/kit.json",
            "pull_request",
            "valid",
            "true",
        ),
        (
            "plugins/vera/assets/courses/kit/course.json",
            "pull_request",
            "valid",
            "true",
        ),
        (
            "plugins/_shared/vendor/modules/courseware/execution.py",
            "pull_request",
            "valid",
            "true",
        ),
        (
            "plugins/_shared/vendor/modules/desktop_teaching/onboarding.py",
            "pull_request",
            "valid",
            "true",
        ),
        ("plugins/vera/scripts/local_teaching.py", "pull_request", "valid", "true"),
        ("plugins/clara/scripts/local_courses.py", "pull_request", "valid", "true"),
        (
            "plugins/vera/scripts/local_onboarding_case.py",
            "pull_request",
            "valid",
            "true",
        ),
        (
            "plugins/vera/scripts/onboarding_session_start.py",
            "pull_request",
            "valid",
            "true",
        ),
        ("plugins/vera/scripts/course_chat_mcp.cjs", "pull_request", "valid", "true"),
        (
            "plugins/vera/skills/learn-with-vera/SKILL.md",
            "pull_request",
            "valid",
            "true",
        ),
        (
            "tests/plugins/test_teaching_kit_execution.py",
            "pull_request",
            "valid",
            "false",
        ),
        (".github/workflows/teaching-kits.yml", "pull_request", "valid", "false"),
        ("scripts/build_product_release.py", "push", "valid", "false"),
        ("scripts/build_product_release.py", "workflow_dispatch", "valid", "true"),
        ("scripts/build_product_release.py", "push", "", "true"),
        (
            "scripts/build_product_release.py",
            "push",
            "0000000000000000000000000000000000000000",
            "true",
        ),
        ("scripts/build_product_release.py", "pull_request", "missing-base", "true"),
    ],
)
def test_editorial_scope_requires_review_for_changed_teaching_or_unknown_base(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    changed_path: str,
    event: str,
    base_mode: str,
    expected: str,
) -> None:
    base = committed_scope_case(tmp_path, changed_path)
    output = tmp_path / "github-output"
    monkeypatch.setenv("BASE_REF", base if base_mode == "valid" else base_mode)
    monkeypatch.setenv("EVENT_NAME", event)
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    steps = workflow("teaching-kits.yml")["jobs"]["teaching-kits"]["steps"]
    scope = next(step for step in steps if step.get("id") == "teaching-scope")

    subprocess.run(
        ["bash", "-e", "-c", scope["run"]],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    assert output.read_text() == f"editorial_required={expected}\n"
