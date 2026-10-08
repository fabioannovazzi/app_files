"""Execute the actual acquisition engine with the supplied fictional course source."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from tests.plugins._teaching_release import prepared_kit, record_native_check

ROOT = Path(__file__).resolve().parents[2]


@prepared_kit("vera/agenzia-acquisition")
@pytest.mark.parametrize("phase", ["demo", "practice"])
def test_agenzia_course_acquires_and_resumes_actual_outputs(
    tmp_path, monkeypatch, record_property, phase
):
    monkeypatch.syspath_prepend(str(ROOT / "plugins/_shared/vendor/modules"))
    monkeypatch.syspath_prepend(str(ROOT / "plugins/browser-automation/scripts"))
    from courseware.library import CourseLibrary

    demo = importlib.import_module("agenzia_demo")
    storage = importlib.import_module("ade_acquisition.storage")
    library = CourseLibrary(ROOT / "plugins/vera", {"agenzia-acquisition"})
    kit = library.render("agenzia-acquisition", "it", tmp_path / "kit")
    first_source = next(
        Path(name) for name in kit["source_files"] if name.endswith("demo.json")
    )
    practice_source = next(
        Path(name) for name in kit["practice_files"] if name.endswith("practice.json")
    )
    output = tmp_path / "acquisizione"
    first = demo.run_demo(first_source, output)
    first_report = storage.read_json(Path(first["run_directory"]) / "report.json")
    original = next(
        row["record"]["artifacts"][0]
        for row in first_report["invoice_results"]
        if row["status"] == "downloaded"
    )
    original_path = output / original["path"]
    original_bytes = original_path.read_bytes()
    if phase == "practice":
        result = demo.run_demo(practice_source, output)
        assert result["state"] == "complete"
        assert result["verified_existing"] == 1
        assert result["downloaded"] == 1
        assert result["run_id"] != first["run_id"]
        assert original_path.read_bytes() == original_bytes
        assert (
            storage.read_json(Path(first["run_directory"]) / "status.json")["state"]
            == "partial"
        )
    else:
        result = first
        assert result["state"] == "partial"
        assert result["downloaded"] == 1
        assert result["failed_documents"] == 1
    run = Path(result["run_directory"])
    report = storage.read_json(run / "report.json")
    assert report["stamp_duty"][0]["evidence"]["amount"] == "24.00"
    assert "12,00" in report["stamp_duty"][0]["evidence"]["payment_status"]
    expected_amounts = ["100.00", "50.00"] if phase == "practice" else ["100.00", None]
    assert [row["amount"] for row in report["cash_records"]] == expected_amounts
    assert len(report["cash_review_issues"]) == (0 if phase == "practice" else 1)
    assert "ESEMPIO DIDATTICO" in (run / "report.html").read_text()
    assert (run / "riepilogo.xlsx").is_file()
    assert (run / "fatture.csv").is_file()
    assert (run / "model_data_report.md").is_file()
    assert not list(run.glob("*.pdf"))
    record_property("agenzia_output_directory", str(run))
    record_native_check(
        record_property,
        root=ROOT,
        product="vera",
        workflow="agenzia-acquisition",
        language="it",
        phase=phase,
    )
