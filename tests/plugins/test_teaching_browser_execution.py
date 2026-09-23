"""Actual local HTML and shipped driver regressions; not live Chrome qualification."""

from __future__ import annotations

import json
import runpy
import shutil
import subprocess
from pathlib import Path

import playwright
import pytest

from tests.plugins._teaching_release import prepared_kit, record_native_check
from tests.plugins.test_teaching_kit_execution import ROOT

__all__: list[str] = []
FIXTURE = ROOT / "tests/fixtures/teaching_browser"


@prepared_kit("vera/browser-automation")
@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
@pytest.mark.parametrize("phase", ["demo", "practice"])
def test_browser_kit_replays_actual_local_page(
    tmp_path: Path, language: str, phase: str, record_property, monkeypatch
) -> None:
    """Keep demo and practice separate while exercising actual form and driver."""
    monkeypatch.syspath_prepend(str(ROOT / "plugins/_shared/vendor/modules"))
    from courseware.library import CourseLibrary

    kit = CourseLibrary(ROOT / "plugins/vera", {"browser-automation"}).render(
        "browser-automation", language, tmp_path / "kit"
    )
    source_note = Path(kit["source_files"][0]).read_text()
    practice_note = Path(kit["practice_files"][0]).read_text()
    assert "DEMO-A" in source_note and "Invoice" in source_note
    assert "DEMO-B" in practice_note and "Credit note" in practice_note
    fixture = runpy.run_path(
        str(ROOT / "plugins/browser-automation/scripts/acceptance_fixture.py")
    )
    server, thread = fixture["_start_server"](0)
    origin = f"http://127.0.0.1:{server.server_address[1]}"
    config = {
        "origin": origin,
        "playwrightPackage": str(Path(playwright.__file__).parent / "driver/package"),
        "capabilityPath": str(FIXTURE / "capability.json"),
        "demoDirectory": str(tmp_path / "demo"),
        "practiceDirectory": (
            str(tmp_path / "practice") if phase == "practice" else None
        ),
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    try:
        result = subprocess.run(
            [shutil.which("node") or "node", str(FIXTURE / "replay.mjs"), str(path)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert result.returncode == 0, result.stderr
    execution = json.loads(result.stdout)
    assert execution["demo"]["result"] == "passed"
    output = json.loads((tmp_path / phase / "outputs.json").read_text())
    expected = "Invoice" if phase == "demo" else "Credit note"
    assert output == {"confirmation": f"Package ready: {expected}; reviewed yes"}
    demo = json.loads((tmp_path / "demo/outputs.json").read_text())
    assert demo == {"confirmation": "Package ready: Invoice; reviewed yes"}
    receipt = json.loads((tmp_path / phase / "run.receipt.json").read_text())
    assert receipt["environment"]["execution_mode"] == "unverified"
    assert execution[phase]["validation_eligible"] is False
    record_property(
        "browser_execution_scope",
        "headless local fixture; not live Chrome qualification",
    )
    record_native_check(
        record_property,
        root=ROOT,
        product="vera",
        workflow="browser-automation",
        language=language,
        phase=phase,
    )
