"""Create selected Vera reports at the Archive artifact-sealing boundary."""

from __future__ import annotations

import importlib.util
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
    _COMPONENT / "vendor/modules",
):
    if (_scripts / "selective_reporting.py").is_file():
        if str(_scripts) not in sys.path:
            sys.path.insert(0, str(_scripts))
        break
from selective_reporting import bind_report_run, has_comparison, report_pipeline

__all__ = ["finish_report", "report_declarations", "selective_reporting_enabled"]


def selective_reporting_enabled() -> bool:
    """Keep other products' existing report contract when Archive is bundled."""
    for parent in Path(__file__).resolve().parents:
        registry = parent / "privacy/registry.json"
        if registry.is_file():
            return json.loads(registry.read_text(encoding="utf-8"))["product"] == "vera"
    return True  # The standalone repository component is Vera's Archive.


def _builder():
    component = Path(__file__).resolve().parents[1]
    candidates = (
        Path(__file__).resolve().parent / "model_data_report.py",
        component.parent.parent / "scripts/model_data_report.py",
        component.parent / "vera/scripts/model_data_report.py",
        component / "vendor/modules/model_data_report.py",
    )
    path = next((path for path in candidates if path.is_file()), None)
    if path is None:
        raise ValueError("The bundled model-data report builder is unavailable")
    spec = importlib.util.spec_from_file_location("_archive_report_builder", path)
    if spec is None or spec.loader is None:
        raise ValueError("Cannot load the bundled report builder")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def finish_report(loaded: Mapping[str, Any]) -> dict[str, Any]:
    """Build once from recorded evidence; never invent missing exposure counts."""
    if not selective_reporting_enabled():
        return {"status": "legacy_required"}
    run = loaded["run"]
    pipeline = report_pipeline(run["workflow_id"])
    if pipeline is None:
        return {"status": "not_applicable", "reason": "pipeline_not_selected"}
    output = Path(loaded["output_dir"])
    target = output / "model_data_report.json"
    if target.is_file():
        # Existing signed bytes remain immutable, including on idempotent replay.
        bind_report_run(output, run["workflow_id"], run["run_id"])
        builder = _builder()
        report = builder.validate_model_data_report(
            json.loads(target.read_text(encoding="utf-8")), evidence_root=output
        )
        if (
            report["run_id"] != run["run_id"]
            or report["workflow_id"] != run["workflow_id"]
        ):
            raise ValueError("Report belongs to another Archive run")
        state_path = output.parent / "model_data_reporting.json"
        if state_path.is_symlink():
            raise ValueError("Report state must not be a symbolic link")
        previous = (
            json.loads(state_path.read_text(encoding="utf-8"))
            if state_path.is_file()
            else {}
        )
        receipt = (
            previous.get("server_receipt", {"status": "unknown"})
            if previous.get("report_id") == report["report_id"]
            else {"status": "unknown"}
        )
        return {
            "status": "available",
            "pipeline": pipeline,
            "report_id": report["report_id"],
            "display_markdown": builder.render_model_data_report(report),
            "server_receipt": receipt,
        }
    evidence = output / "model_data_report_input.json"
    if evidence.is_symlink():
        raise ValueError("Report evidence must not be a symbolic link")
    if not evidence.is_file():
        return {
            "status": "unavailable",
            "reason": "execution_evidence_missing",
            "pipeline": pipeline,
        }
    request = json.loads(evidence.read_text(encoding="utf-8"))
    if not isinstance(request, dict):
        raise ValueError("Report evidence must be an object")
    if (
        request.get("run_id") != run["run_id"]
        or request.get("workflow_id") != run["workflow_id"]
    ):
        raise ValueError("Report evidence belongs to another Archive run")
    bind_report_run(output, run["workflow_id"], run["run_id"])
    builder = _builder()
    # Validate even a non-reportable record; malformed evidence is not a skip.
    report, markdown = builder.build_model_data_report(request, evidence_root=output)
    if any(phase["outcome"] == "not_measurable" for phase in request["phases"]):
        return {
            "status": "unavailable",
            "reason": "execution_evidence_incomplete",
            "pipeline": pipeline,
        }
    if not has_comparison(request):
        return {
            "status": "not_applicable",
            "reason": "no_measured_local_remainder",
            "pipeline": pipeline,
        }
    options_path = output / "model_data_report_options.json"
    if options_path.is_symlink():
        raise ValueError("Report options must not be a symbolic link")
    options = (
        json.loads(options_path.read_text(encoding="utf-8"))
        if options_path.is_file()
        else {}
    )
    if (
        not isinstance(options, dict)
        or set(options) - {"local_only"}
        or type(options.get("local_only", False)) is not bool
    ):
        raise ValueError("Report options accept only a boolean local_only value")
    builder._write_once_or_identical(target, builder._canonical_bytes(report))
    builder._write_once_or_identical(
        output / "model_data_report.md", markdown.encode("utf-8")
    )
    if report["schema_version"] == 2:
        root = builder._installed_product_root()
        binding = report["privacy_contract"]
        contract = root / f"privacy/contracts/{binding['workstream']}.json"
        builder._write_once_or_identical(
            output / "privacy_contract.json", contract.read_bytes()
        )
    receipt = {"status": "not_requested", "reason": "local_only"}
    root = builder._installed_product_root()
    if root is not None and not options.get("local_only", False):
        if str(root / "scripts") not in sys.path:
            sys.path.insert(0, str(root / "scripts"))
        from notarized_run_receipt import (
            NotarizedRunReceiptError,
            stamp_model_data_report,
        )

        try:
            receipt = stamp_model_data_report(
                target, output_dir=output, plugin_root=root
            )
        except NotarizedRunReceiptError as exc:
            receipt = {"status": "pending", "reason": str(exc)}
    return {
        "status": "created",
        "pipeline": pipeline,
        "report_id": report["report_id"],
        "display_markdown": markdown,
        "server_receipt": receipt,
    }


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
