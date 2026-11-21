"""Protect focused routing without exempting backend or package changes."""

import importlib.util
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "website_checks", ROOT / "scripts/validate_static_website.py"
)
CHECKS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKS)


def match(path, pattern):
    """GitHub path wildcards used by this rule (including zero directories)."""
    expression = (
        re.escape(pattern)
        .replace(r"\*\*/", "(?:.*/)?")
        .replace(r"\*\*", ".*")
        .replace(r"\*", "[^/]*")
    )
    return re.fullmatch(expression, path) is not None


WORKFLOWS = []
for path in (ROOT / ".github/workflows").glob("*.yml"):
    data = yaml.safe_load(path.read_text())
    events = data.get("on", data.get(True, {}))
    for event in ("push", "pull_request"):
        config = events.get(event) if isinstance(events, dict) else None
        if config and "paths-ignore" in config:
            WORKFLOWS.append((path.name, event, config["paths-ignore"]))


@pytest.mark.parametrize("workflow,event,patterns", WORKFLOWS)
@pytest.mark.parametrize(
    "path",
    [
        "static/index.html",
        "static/shared/vera/index.html",
        "static/shared/vera/benchmark/con-paywall-55-dati.json",
        "static/shared/vera/benchmark/metodologia.html",
        "static/shared/style.css",
        "AGENTS.md",
    ],
)
def test_static_only_edits_do_not_run_product_suites(workflow, event, patterns, path):
    assert any(match(path, pattern) for pattern in patterns)


@pytest.mark.parametrize("workflow,event,patterns", WORKFLOWS)
@pytest.mark.parametrize(
    "path",
    [
        "plugins/vera/scripts/native_workspace.py",
        "requirements.txt",
        "static/shared/vera/downloads/vera-cowork-plugin.zip",
        "static/js/hosted-interview.js",
        ".github/workflows/plugin-runtime.yml",
    ],
)
def test_code_packages_and_workflow_changes_still_run_product_suites(
    workflow, event, patterns, path
):
    assert not any(match(path, pattern) for pattern in patterns)


def test_all_previously_broad_product_workflows_are_scoped():
    assert len({name for name, _, _ in WORKFLOWS}) == 19


def test_secret_scan_remains_enabled():
    events = yaml.safe_load((ROOT / ".github/workflows/secret-scan.yml").read_text())[
        True
    ]
    assert events["push"] is None
    assert events["pull_request"] is None


def test_valid_page(tmp_path):
    page = tmp_path / "index.html"
    page.write_text(
        '<title>Test</title><meta name="viewport" content="width=device-width"><h1 id="one">One</h1><a href="#one">Go</a>'
    )
    CHECKS.validate_page(page, tmp_path)


def test_missing_local_document_is_rejected(tmp_path):
    page = tmp_path / "index.html"
    page.write_text(
        '<title>Test</title><meta name="viewport"><a href="missing.pdf">Open</a>'
    )
    with pytest.raises(AssertionError, match="Missing local asset"):
        CHECKS.validate_page(page, tmp_path)


def test_duplicate_anchor_is_rejected(tmp_path):
    page = tmp_path / "index.html"
    page.write_text(
        '<title>Test</title><meta name="viewport"><h1 id="same">A</h1><p id="same">B</p>'
    )
    with pytest.raises(AssertionError, match="Duplicate IDs"):
        CHECKS.validate_page(page, tmp_path)


def test_published_benchmark_is_recomputable():
    CHECKS.validate_benchmark(
        ROOT / "static/shared/vera/benchmark/con-paywall-55-dati.json"
    )


@pytest.mark.parametrize("workflow,event,patterns", WORKFLOWS)
def test_mixed_html_and_backend_change_keeps_product_checks(workflow, event, patterns):
    changed = [
        "static/shared/vera/index.html",
        "plugins/vera/scripts/native_workspace.py",
    ]
    assert not all(
        any(match(path, pattern) for pattern in patterns) for path in changed
    )
