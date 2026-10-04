"""Run the synthetic archive-to-dossier path from each actual development ZIP."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[2]
PROBE = r"""
import json
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
import test_patent_box_workflow as fixtures

plugin = Path(sys.argv[2])
workspace = Path(sys.argv[3])
fixtures.PLUGIN = plugin
workflow = fixtures.load_module("packaged_patent_box", plugin / "scripts/patent_box_workflow.py")
run = fixtures.running_case(
    workspace,
    workflow,
    archive_script=plugin.parent / "studio-archive/scripts/archive_core.py",
)
proposal = fixtures.model_proposal(run, workflow)
digest = fixtures.reviewed(run, workflow, proposal)
outcome = workflow.calculate_draft(run["context"], digest=digest)
output = Path(outcome["output_dir"])
loaded = {
    name: str(Path(sys.modules[name].__file__).resolve())
    for name in ("patent_box", "patent_box.documents", "vera_assurance")
}
assert all(Path(path).is_relative_to(plugin.parent.parent) for path in loaded.values()), loaded
assert Path(run["archive"].__file__).is_relative_to(plugin.parent)
assert outcome["result"]["additional_deduction"] == {"income": "110000.00", "irap": "88000.00"}
assert list(output.glob("*.docx")) and list(output.glob("*.pdf"))
assert (output / "manifest.json").is_file()
print(json.dumps({"loaded": loaded, "output": str(output), "demo": True, "professional_acceptance": False}))
"""


@pytest.mark.parametrize(
    "archive_name",
    ["vera-plugin.zip", "vera-chatgpt-upload.zip", "vera-claude-plugin.zip"],
)
def test_packaged_workflow_uses_its_own_archive_contract_and_exports_dossier(
    tmp_path: Path, archive_name: str
) -> None:
    archive_path = ROOT / "plugin_packages/vera" / archive_name
    installation = tmp_path / "extracted"
    with ZipFile(archive_path) as archive:
        archive.extractall(installation)
    workflow_file = next(installation.rglob("patent_box_workflow.py"))
    plugin = workflow_file.parents[1]
    environment = {
        key: value for key, value in os.environ.items() if key != "PYTHONPATH"
    }
    environment["PYTHONNOUSERSITE"] = "1"

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            PROBE,
            str(ROOT / "tests/plugins"),
            str(plugin),
            str(tmp_path / "case"),
        ],
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["professional_acceptance"] is False
    assert Path(report["output"]).is_relative_to(tmp_path / "case")
