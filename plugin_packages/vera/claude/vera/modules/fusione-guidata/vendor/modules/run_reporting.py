"""Create selected Vera reports at the Archive artifact-sealing boundary."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_COMPONENT = Path(__file__).resolve().parents[1]
for _scripts in (
    Path(__file__).resolve().parent,
    _COMPONENT.parent.parent / "scripts",
    _COMPONENT.parent / "vera/scripts",
    _COMPONENT.parent / "_shared/reporting-runtime",
    _COMPONENT / "vendor/modules",
):
    if (_scripts / "selective_reporting.py").is_file():
        if str(_scripts) not in sys.path:
            sys.path.insert(0, str(_scripts))
        break
from selective_reporting import report_pipeline

__all__ = [
    "begin_report",
    "finish_report",
    "report_declarations",
    "retain_artifact_manifest",
    "selective_reporting_enabled",
]


def selective_reporting_enabled() -> bool:
    """Keep other products' existing report contract when Archive is bundled."""
    for parent in Path(__file__).resolve().parents:
        registry = parent / "privacy/registry.json"
        if registry.is_file():
            return json.loads(registry.read_text(encoding="utf-8"))["product"] == "vera"
    return True  # The standalone repository component is Vera's Archive.


def begin_report(loaded: Mapping[str, Any]) -> dict[str, Any]:
    """Start measurement at Archive's durable start write, without agent input."""
    if not selective_reporting_enabled():
        return {"status": "legacy_required"}
    if report_pipeline(loaded["run"]["workflow_id"]) is None:
        return {"status": "not_applicable", "reason": "pipeline_not_selected"}
    from archive_reporting import begin_run

    return begin_run(loaded)


def finish_report(loaded: Mapping[str, Any]) -> dict[str, Any]:
    """Snapshot at review; close and stamp at the terminal Archive write."""
    if not selective_reporting_enabled():
        return {"status": "legacy_required"}
    if report_pipeline(loaded["run"]["workflow_id"]) is None:
        return {"status": "not_applicable", "reason": "pipeline_not_selected"}
    from archive_reporting import finish_run

    return finish_run(loaded)


def report_declarations(output: Path) -> list[dict[str, str]]:
    """Declare generated report artifacts without exposing case data to the model."""
    result = []
    for name, mime in (
        ("model_data_report_input.json", "application/json"),
        ("model_data_report_options.json", "application/json"),
        ("model_data_report.json", "application/json"),
        ("model_data_report.md", "text/markdown"),
        ("privacy_contract.json", "application/json"),
        ("model_data_receipt_request.json", "application/json"),
        ("model_data_receipt.json", "application/json"),
        ("model_data_receipt.html", "text/html"),
    ):
        if (output / name).is_file():
            result.append(
                {
                    "artifact_id": "disclosure." + name.replace("_", "-"),
                    "path": name,
                    "purpose": "Record this Archive run's measured model-data boundary.",
                    "audience": (
                        "internal"
                        if name.endswith(("_input.json", "_options.json"))
                        else "review"
                    ),
                    "media_type": mime,
                }
            )
    return result


def retain_artifact_manifest(root: Path, manifest: dict[str, Any]) -> None:
    """Keep the receipt used by existing handoffs when delivery labels change."""
    from archive_report_seal import retain_manifest

    retain_manifest(root, manifest)
