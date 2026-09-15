from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPTS = (
    Path(__file__).resolve().parents[2]
    / "plugins/clara/modules/reporting-engine/scripts"
)


def _fixture(tmp_path: Path) -> tuple[Path, list[str]]:
    source = tmp_path / "input.csv"
    source.write_text("Month,Product,Retailer\n2026-06,A,B\n", encoding="utf-8")
    component = tmp_path / "component.py"
    component.write_text(
        """import sys,time
from pathlib import Path
output=Path(sys.argv[1]); order=Path(sys.argv[2])
with order.open('a') as f: f.write(output.name+' start\\n')
time.sleep(0.2)
(output/'data.csv').write_text('Product,Value\\nA,1\\n')
with order.open('a') as f: f.write(output.name+' end\\n')
""",
        encoding="utf-8",
    )
    driver = tmp_path / "driver.py"
    driver.write_text(
        """import os,sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import render_capability as renderer
base=Path(sys.argv[2])
renderer._runner_command=lambda request, **kwargs: [sys.executable, str(base/'component.py'), str(request.output_dir), str(base/'order.log')]
if sys.argv[3]=='crash':
    original=renderer._publish_run_artifacts
    def crash(*args, **kwargs):
        original(*args, **kwargs)
        os._exit(41)
    renderer._publish_run_artifacts=crash
request=renderer.RenderRequest(capability_id='set_overlap.upset', input_file=base/'input.csv', output_dir=base/'output', artifact_mode='data_only', timeout_seconds=10, role_bindings={'set_membership_fields': {'item_column':'Product','set_column':'Retailer'}, 'period_filter': {'period_column':'Month','selected_period':'2026-06'}})
renderer.render_capability(request)
renderer.verify_render_generation(request.output_dir)
""",
        encoding="utf-8",
    )
    return tmp_path / "output", [
        sys.executable,
        str(driver),
        str(SCRIPTS),
        str(tmp_path),
    ]


def test_reporting_abrupt_publication_death_is_not_success_and_retry_completes(
    tmp_path: Path,
) -> None:
    output, command = _fixture(tmp_path)
    crashed = subprocess.run(
        [*command, "crash"], capture_output=True, text=True, timeout=20
    )
    assert crashed.returncode == 41, crashed.stderr
    assert (
        json.loads((output / "current_reporting.json").read_text())["status"]
        == "running"
    )
    stages = list(output.parent.glob(".clara-reporting-run-*"))
    assert len(stages) == 1
    assert (stages[0] / "data.csv").is_file()

    retried = subprocess.run(
        [*command, "normal"], capture_output=True, text=True, timeout=20
    )

    assert retried.returncode == 0, retried.stderr
    assert (
        json.loads((output / "current_reporting.json").read_text())["status"]
        == "completed"
    )
    assert (stages[0] / "data.csv").is_file()
    previous = list(output.glob("render_manifest.*.previous.json"))
    assert len(previous) == 1
    assert json.loads(previous[0].read_text())["status"] == "running"


def test_two_reporting_processes_serialize_and_keep_both_generations(
    tmp_path: Path,
) -> None:
    output, command = _fixture(tmp_path)
    first = subprocess.Popen(
        [*command, "normal"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    second = subprocess.Popen(
        [*command, "normal"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    try:
        _, first_error = first.communicate(timeout=20)
        _, second_error = second.communicate(timeout=20)
    finally:
        for process in (first, second):
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)

    assert first.returncode == 0, first_error
    assert second.returncode == 0, second_error
    lines = (tmp_path / "order.log").read_text().splitlines()
    first_id, second_id = lines[0].split()[0], lines[2].split()[0]
    assert first_id != second_id
    assert lines == [
        f"{first_id} start",
        f"{first_id} end",
        f"{second_id} start",
        f"{second_id} end",
    ]
    generations = list(
        (output / ".reporting-generations").glob("*/published/render_manifest.json")
    )
    assert len(generations) == 2
    assert (
        json.loads((output / "current_reporting.json").read_text())["status"]
        == "completed"
    )
