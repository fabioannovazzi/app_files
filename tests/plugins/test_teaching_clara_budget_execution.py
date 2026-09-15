"""Replay prepared Clara reports through the owning workflow, including commentary.

The prose is host-authored fictional source interpretation, not learner feedback
or professional approval. Native commands perform all calculations and rendering.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest
from openpyxl import load_workbook

from tests.plugins._teaching_release import prepared_kit, record_native_check
from tests.plugins.test_teaching_kit_execution import ROOT, _read, _run, _write
from tests.plugins.test_teaching_management_execution import _recipe

__all__: list[str] = []

SCRIPT = "plugins/clara/modules/reporting-engine/scripts/budget_report.py"
SUMMARY = {
    "it": "Sintesi",
    "en": "Summary",
    "fr": "Synthèse",
    "de": "Zusammenfassung",
    "es": "Resumen",
}


def _snapshot(root: Path) -> dict[str, str]:
    """Pin every file so practice cannot silently replace the first report."""
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def _execute_clara_budget(
    root: Path, kit: dict[str, Any], language: str, phase: str
) -> Path:
    """Run inspection, calculation and the source-bound explained delivery."""
    root.mkdir(parents=True)
    prose = _read(ROOT / "tests/fixtures/teaching_reviews/clara_budget.json")[language]
    source = next(
        path
        for path in kit["source_files" if phase == "demo" else "practice_files"]
        if path.endswith(".xlsx")
    )
    _run(SCRIPT, "inspect", "--input", source, "--output-dir", root / "inspection")
    inventory = _read(root / "inspection/inspection.json")
    recipe = _recipe(inventory, language, phase, prose["entity"])
    recipe["audience"] = "internal"
    _write(root / "recipe.json", recipe)
    args = ["run", "--input", source, "--recipe", root / "recipe.json"]
    _run(SCRIPT, *args, "--output-dir", root / "calculated")
    calculated = _snapshot(root / "calculated")
    context = _read(root / "calculated/model_context.json")
    assert {control["status"] for control in context["controls"]} == {"passed"}
    metrics = {item["metric_id"]: item["value"] for item in context["metrics"]}
    assert metrics["pnl.total.ebitda"] == ("53000" if phase == "demo" else "85000")
    assert metrics["budget.total.ebitda_variance"] == (
        "6000" if phase == "demo" else "8000"
    )
    commentary = _read(root / "calculated/commentary_template.json")
    commentary.update(prose[phase])
    commentary["limitations"] = prose["limitations"]
    commentary_path = root / "authored_commentary.json"
    _write(commentary_path, commentary)
    explained = root / "explained"
    _run(
        SCRIPT,
        *args,
        "--commentary",
        commentary_path,
        "--output-dir",
        explained,
    )
    assert _snapshot(root / "calculated") == calculated
    assert _read(explained / "management_control_pack.json") == _read(
        root / "calculated/management_control_pack.json"
    )
    saved = _read(explained / "management_commentary.json")
    assert saved["status"] == "draft_pending_professional_review"
    assert saved["pack_sha256"] == context["pack_sha256"]
    first = prose[phase]["observations"][0]["text"]
    report = (explained / "management_control_report.md").read_text()
    assert first in report
    assert first in (explained / "management_control_dashboard.html").read_text()
    assert prose["limitations"][0]["text"] in report
    assert (
        f'<html lang="{language}">'
        in (explained / "management_control_dashboard.html").read_text()
    )
    workbook = load_workbook(explained / "management_control_pack.xlsx", data_only=True)
    summary = workbook[SUMMARY[language]]
    assert summary["C12"].value == (53000 if phase == "demo" else 85000)
    workbook.close()
    receipt = _read(explained / "execution_receipt.json")
    assert (
        receipt["commentary_source"]["sha256"]
        == hashlib.sha256(commentary_path.read_bytes()).hexdigest()
    )
    for item in receipt["outputs"]:
        assert (
            hashlib.sha256((explained / item["path"]).read_bytes()).hexdigest()
            == item["sha256"]
        )
    return explained


@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
@pytest.mark.parametrize("phase", ["demo", "practice"])
@prepared_kit("clara/reporting-engine")
def test_clara_reporting_kit_delivers_explained_report_and_preserves_prior_version(
    tmp_path, monkeypatch, record_property, language, phase
):
    monkeypatch.syspath_prepend(str(ROOT / "plugins/_shared/vendor/modules"))
    from courseware.library import CourseLibrary

    kit = CourseLibrary(ROOT / "plugins/clara", {"reporting-engine"}).render(
        "reporting-engine", language, tmp_path / "lesson"
    )
    _execute_clara_budget(tmp_path / "demo", kit, language, "demo")
    if phase == "practice":
        previous = _snapshot(tmp_path / "demo")
        _execute_clara_budget(tmp_path / "practice", kit, language, "practice")
        assert _snapshot(tmp_path / "demo") == previous
    record_native_check(
        record_property,
        root=ROOT,
        product="clara",
        workflow="reporting-engine",
        language=language,
        phase=phase,
    )
