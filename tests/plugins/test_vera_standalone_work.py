from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

__all__: list[str] = []
ROOT = Path(__file__).resolve().parents[2]
VENDOR = ROOT / "plugins" / "_shared" / "vendor" / "modules"


@pytest.fixture(autouse=True)
def assurance_imports(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(str(VENDOR))


def _create(tmp_path: Path, workflow: str = "invoice-xml") -> dict:
    from vera_assurance.contracts import create_standalone_task

    source = tmp_path / "contract.txt"
    source.write_text("Synthetic contract evidence", encoding="utf-8")
    return create_standalone_task(
        tmp_path / "task",
        workflow_id=workflow,
        sources=[source],
        label="Contract review",
        purpose="Review the selected contract",
    )


@pytest.mark.parametrize(
    "workflow", ["invoice-xml", "prompt-optimizer", "deep-research-validator"]
)
def test_standalone_context_reopens_with_exact_sources_and_no_client(
    tmp_path: Path, workflow: str
) -> None:
    from vera_assurance import (
        load_client_engagement_context_file,
        load_client_workflow_context_for_output,
    )

    context = _create(tmp_path, workflow)

    loaded = load_client_engagement_context_file(
        context["context_path"],
        expected_workflow_id=workflow,
        output_dir=context["output_dir"],
    )
    secondary = load_client_workflow_context_for_output(
        context["output_dir"], expected_workflow_id=workflow
    )

    assert loaded["run_id"] == context["run_id"] == secondary["run_id"]
    assert loaded["schema_version"] == "vera.standalone_workflow_context.v1"
    assert loaded["retention"] == "user_managed_no_archive_registration"
    assert "client_id" not in loaded
    assert not list(tmp_path.rglob("client.json"))
    assert (tmp_path / "contract.txt").read_bytes() == Path(
        loaded["input_bindings"][0]["path"]
    ).read_bytes()


@pytest.mark.parametrize(
    "violation",
    [
        "changed_source",
        "extra_source",
        "output_escape",
        "wrong_workflow",
        "symlink_output",
    ],
)
def test_standalone_context_rejects_source_and_scope_violations(
    tmp_path: Path, violation: str
) -> None:
    from vera_assurance import (
        AssuranceContractError,
        load_client_engagement_context_file,
    )

    context = _create(tmp_path)
    output = Path(context["output_dir"])
    workflow = "invoice-xml"
    if violation == "changed_source":
        Path(context["input_bindings"][0]["path"]).write_text("changed")
    elif violation == "extra_source":
        (Path(context["input_dir"]) / "extra.txt").write_text("unselected")
    elif violation == "output_escape":
        output = tmp_path
    elif violation == "wrong_workflow":
        workflow = "journal-sampling"
    else:
        output = tmp_path / "output-alias"
        output.symlink_to(Path(context["output_dir"]), target_is_directory=True)

    with pytest.raises((AssuranceContractError, ValueError)):
        load_client_engagement_context_file(
            context["context_path"], expected_workflow_id=workflow, output_dir=output
        )


def test_standalone_route_rejects_unqualified_accounting_workflow_before_writes(
    tmp_path: Path,
) -> None:
    from vera_assurance import AssuranceContractError

    with pytest.raises(AssuranceContractError, match="does not support standalone"):
        _create(tmp_path, "journal-bank-reconciliation")

    assert not (tmp_path / "task").exists()


def test_standalone_cli_runs_without_archive_configuration(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("Synthetic invoice confirmation")

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "plugins" / "vera" / "scripts" / "standalone_work.py"),
            "--destination",
            str(tmp_path / "task"),
            "--workflow",
            "invoice-xml",
            "--source",
            str(source),
            "--label",
            "Invoice",
            "--purpose",
            "Prepare one invoice",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    context = json.loads(result.stdout)
    assert Path(context["context_path"]).is_file()
    assert context["run_id"].startswith("task_")
    assert not list(tmp_path.rglob("config.json"))


@pytest.mark.parametrize(
    ("workflow", "script", "artifact"),
    [
        ("prompt-optimizer", "inspect_question.py", "question_inventory.json"),
        ("deep-research-validator", "inspect_document.py", "document_inventory.json"),
    ],
)
def test_standalone_legal_engine_inspection_uses_receipted_file_route(
    tmp_path: Path, workflow: str, script: str, artifact: str
) -> None:
    context = _create(tmp_path, workflow)
    source = context["input_bindings"][0]["path"]

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "plugins" / workflow / "scripts" / script),
            source,
            "--client-engagement",
            context["context_path"],
            "--output-dir",
            context["output_dir"],
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.returncode == 0
    assert (Path(context["output_dir"]) / artifact).is_file()
    assert not list(tmp_path.rglob("client.json"))
