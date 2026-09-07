"""Generate honest no-model disclosures for local lifecycle test fixtures."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

__all__ = ["write_no_model_report"]


def write_no_model_report(
    output: Path,
    workflow_id: str,
    run_id: str,
    *,
    runtime_profile: str = "openai-codex",
    report_script: Path | None = None,
) -> list[dict[str, str]]:
    """Return declarations for a synthetic run that executes no model call."""

    request: dict[str, Any] = {
        "schema_version": 1,
        "workflow_id": workflow_id,
        "run_id": run_id,
        "runtime_profile": runtime_profile,
        "language": "en",
        "created_at": "2026-09-05T12:00:00+00:00",
        "professional_purpose": "Verify synthetic local workflow artifacts.",
        "phases": [
            {
                "phase_id": "fixture",
                "purpose": "Exercise local code without a model call.",
                "outcome": "no_case_data",
                "evidence_basis": "workflow_receipt",
                "source_extent": [],
                "locally_processed": [],
                "model_visible": [],
                "remained_local": [],
                "reason": "The test fixture performs no model or network call.",
                "evidence_files": [],
            }
        ],
        "improvement_assessment": {"status": "not_assessed", "candidates": []},
    }
    if report_script is not None:
        with tempfile.TemporaryDirectory(
            prefix="synthetic-model-data-request-"
        ) as folder:
            request_path = Path(folder) / "request.json"
            request_path.write_text(json.dumps(request), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-B",
                    str(report_script),
                    "build",
                    "--input",
                    str(request_path),
                    "--evidence-root",
                    str(output),
                    "--output-dir",
                    str(output),
                ],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["server_receipt"]["status"] == "not_requested"
    else:
        source = (
            Path(__file__).resolve().parents[1]
            / "plugins/vera/scripts/model_data_report.py"
        )
        spec = importlib.util.spec_from_file_location("test_disclosure_factory", source)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        report, markdown = module.build_model_data_report(request, evidence_root=output)
        (output / "model_data_report.json").write_text(
            json.dumps(report) + "\n", encoding="utf-8"
        )
        (output / "model_data_report.md").write_text(markdown, encoding="utf-8")
    return [
        {
            "artifact_id": f"disclosure.{suffix}",
            "path": f"model_data_report.{suffix}",
            "purpose": "Disclose the synthetic run's model-data boundary.",
            "audience": "review",
            "media_type": mime,
        }
        for suffix, mime in (("json", "application/json"), ("md", "text/markdown"))
    ]
