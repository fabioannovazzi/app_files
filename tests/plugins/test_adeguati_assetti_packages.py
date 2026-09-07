from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

from tests.plugins.test_adeguati_assetti import intelligent_case, review_for

__all__: list[str] = []

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "filename", ["vera-plugin.zip", "vera-chatgpt-upload.zip", "vera-claude-plugin.zip"]
)
def test_packaged_review_runs_with_exact_archive_context(
    tmp_path: Path, vera_workflow_workspace, filename: str
) -> None:
    workspace = vera_workflow_workspace(
        "adeguati-assetti", input_files={"evidence.txt": "Synthetic reporting evidence"}
    )
    extracted = tmp_path / "extracted"
    with ZipFile(ROOT / "plugin_packages/vera" / filename) as archive:
        script_name = next(
            name
            for name in archive.namelist()
            if name.endswith("/modules/adeguati-assetti/scripts/assetti_review.py")
            or name == "modules/adeguati-assetti/scripts/assetti_review.py"
        )
        archive.extractall(extracted)
    script = extracted / script_name
    review = review_for(
        workspace["input_paths"][0], Path(workspace["context"]["run_root"]) / "inputs"
    )
    review["intelligent_review"] = intelligent_case(tmp_path)["intelligent_review"]
    review_path = workspace["output_dir"] / "review_input.json"
    review_path.write_text(json.dumps(review))

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--client-engagement",
            str(workspace["context_path"]),
            "--review",
            str(review_path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    record_path = next(workspace["output_dir"].glob("adeguati-assetti-*.json"))
    record = json.loads(record_path.read_text())
    assert record["workflow_id"] == "adeguati-assetti"
    assert record["status"] == "draft_for_review"
    assert record["review"]["intelligent_review"] == review["intelligent_review"]
    assert (
        "Could substantiate an informal control"
        in record_path.with_suffix(".md").read_text()
    )
