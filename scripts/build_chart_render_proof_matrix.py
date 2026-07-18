from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

__all__ = ["build_chart_render_proof_matrix", "main"]

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = REPO_ROOT / "runs" / "chart_selection_manifest_rebuild"
DEFAULT_SELECTION_MANIFEST = RUN_DIR / "selection_manifest.json"
DEFAULT_PARAMETER_AUDIT = RUN_DIR / "plugin_parameter_contract_audit.json"
DEFAULT_COMPATIBILITY_AUDIT = (
    RUN_DIR / "us_cosmetics_dataset_profile_chart_compatibility.json"
)
DEFAULT_STRESS_TEST = RUN_DIR / "chart_selection_stress_test.json"
DEFAULT_OUTPUT_JSON = RUN_DIR / "chart_render_proof_matrix.json"
DEFAULT_OUTPUT_MD = RUN_DIR / "chart_render_proof_matrix.md"

SEMANTIC_OR_PACKAGE_ISSUES = {
    "requires_semantic_or_package_metric_source",
    "requires_semantic_or_package_role",
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _optional_json(path: Path) -> dict[str, Any]:
    return _load_json(path) if path.exists() else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _by_capability(payload: dict[str, Any], key: str = "results") -> dict[str, Any]:
    return {
        str(item["capability_id"]): item
        for item in payload.get(key, [])
        if isinstance(item, dict) and item.get("capability_id")
    }


def _stress_by_capability(payload: dict[str, Any]) -> dict[str, Any]:
    return _by_capability(payload, key="records")


def _semantic_or_package_gap(compatibility: dict[str, Any]) -> bool:
    issues = set(compatibility.get("issues") or [])
    return bool(issues) and issues.issubset(SEMANTIC_OR_PACKAGE_ISSUES)


def _fixture_requirement(
    *,
    compatibility: dict[str, Any],
    stress: dict[str, Any],
    invocation_status: str,
) -> str:
    if invocation_status != "parameter_contract_ready":
        return "fix_invocation_contract"
    if _semantic_or_package_gap(compatibility):
        return "semantic_or_package_fixture"
    if compatibility.get("status") == "mechanically_incomplete":
        return "dataset_with_required_schema"
    if stress.get("status") == "works":
        png_status = (stress.get("png_evidence") or {}).get("status")
        return (
            "question_render_fixture"
            if png_status != "rendered_question_png"
            else "none"
        )
    if stress.get("status") == "dataset_gap":
        return "dataset_with_required_schema"
    return "question_or_render_fixture"


def _render_proof_status(
    *,
    compatibility: dict[str, Any],
    stress: dict[str, Any],
    invocation_status: str,
) -> str:
    if invocation_status != "parameter_contract_ready":
        return "invocation_contract_gap"
    if _semantic_or_package_gap(compatibility):
        return "semantic_or_package_gap"
    stress_status = str(stress.get("status") or "missing")
    png_status = str((stress.get("png_evidence") or {}).get("status") or "missing")
    if stress_status == "works" and png_status == "rendered_question_png":
        return "dataset_rendered_png_proven"
    if stress_status == "works" and png_status == "gallery_png":
        return "gallery_png_plus_parameter_proof"
    if stress_status == "dataset_gap":
        return "correct_dataset_rejection"
    if compatibility.get("status") == "mechanically_incomplete":
        return "dataset_fixture_gap"
    return "proof_fixture_gap"


def _period_scope_record(
    capability: dict[str, Any],
    compatibility: dict[str, Any],
) -> dict[str, Any]:
    """Surface manifest/profile period-scope evidence without semantic judgment."""

    compatibility_scope = compatibility.get("period_scope") or {}
    capability_scope = capability.get("period_scope_contract") or {}
    role = str(
        compatibility_scope.get("role")
        or capability_scope.get("role")
        or (capability.get("period_semantics") or {}).get("role")
        or "none"
    )
    if compatibility_scope:
        status = str(compatibility_scope.get("status") or "not_checked")
        warning = compatibility_scope.get("pre_render_warning") or ""
        period_candidates = compatibility_scope.get("period_candidates") or []
    elif role == "none":
        status = "not_applicable"
        warning = ""
        period_candidates = []
    elif capability_scope.get("scope_required_for_render"):
        status = "not_checked_scope_required"
        warning = (
            "Manifest requires period scope before render, but compatibility "
            "audit did not provide period-scope evidence."
        )
        period_candidates = []
    else:
        status = "not_checked_scope_optional"
        warning = ""
        period_candidates = []
    return {
        "role": role,
        "status": status,
        "scope_required_for_render": bool(
            compatibility_scope.get(
                "scope_required_for_render",
                capability_scope.get("scope_required_for_render", False),
            )
        ),
        "explicit_all_data_allowed": bool(
            compatibility_scope.get(
                "explicit_all_data_allowed",
                capability_scope.get("explicit_all_data_allowed", False),
            )
        ),
        "accepted_scope_controls": list(
            compatibility_scope.get("accepted_scope_controls")
            or capability_scope.get("accepted_scope_controls")
            or []
        ),
        "period_candidates": period_candidates,
        "unscoped_default": compatibility_scope.get("unscoped_default")
        or capability_scope.get("unscoped_default"),
        "pre_render_warning": warning,
    }


def _capability_record(
    capability_id: str,
    capability: dict[str, Any],
    *,
    parameter_result: dict[str, Any],
    compatibility: dict[str, Any],
    stress: dict[str, Any],
) -> dict[str, Any]:
    invocation = capability.get("normalized_invocation_contract") or {}
    invocation_status = str(
        invocation.get("status") or parameter_result.get("status") or "missing"
    )
    render_status = _render_proof_status(
        compatibility=compatibility,
        stress=stress,
        invocation_status=invocation_status,
    )
    period_scope = _period_scope_record(capability, compatibility)
    return {
        "capability_id": capability_id,
        "family": capability.get("family"),
        "selection_emphasis": capability.get("selection_emphasis"),
        "invocation_contract_status": invocation_status,
        "parameter_audit_status": parameter_result.get("status", "missing"),
        "dataset_compatibility_status": compatibility.get("status", "missing"),
        "stress_status": stress.get("status", "missing"),
        "png_evidence_status": (stress.get("png_evidence") or {}).get(
            "status", "missing"
        ),
        "render_proof_status": render_status,
        "fixture_requirement": _fixture_requirement(
            compatibility=compatibility,
            stress=stress,
            invocation_status=invocation_status,
        ),
        "period_scope_status": period_scope["status"],
        "period_scope": period_scope,
        "mechanical_issues": compatibility.get("issues") or [],
        "missing_invocation_roles": invocation.get("missing_roles") or [],
        "artifact_labels": invocation.get("artifact_labels")
        or capability.get("example_artifact_labels")
        or [],
        "output_forms": invocation.get("output_forms") or [],
    }


def build_chart_render_proof_matrix(
    *,
    selection_manifest_path: Path = DEFAULT_SELECTION_MANIFEST,
    parameter_audit_path: Path = DEFAULT_PARAMETER_AUDIT,
    compatibility_audit_path: Path = DEFAULT_COMPATIBILITY_AUDIT,
    stress_test_path: Path = DEFAULT_STRESS_TEST,
    output_json_path: Path = DEFAULT_OUTPUT_JSON,
    output_md_path: Path = DEFAULT_OUTPUT_MD,
) -> dict[str, Any]:
    manifest = _load_json(selection_manifest_path)
    parameter_audit = _optional_json(parameter_audit_path)
    compatibility_audit = _optional_json(compatibility_audit_path)
    stress_test = _optional_json(stress_test_path)

    parameter_results = _by_capability(parameter_audit)
    compatibility_results = _by_capability(compatibility_audit)
    stress_results = _stress_by_capability(stress_test)
    records = [
        _capability_record(
            capability_id,
            capability,
            parameter_result=parameter_results.get(capability_id, {}),
            compatibility=compatibility_results.get(capability_id, {}),
            stress=stress_results.get(capability_id, {}),
        )
        for capability_id, capability in sorted(manifest["capabilities"].items())
    ]
    counts = {
        "capabilities": len(records),
        "render_proof_status": dict(
            sorted(Counter(record["render_proof_status"] for record in records).items())
        ),
        "fixture_requirement": dict(
            sorted(Counter(record["fixture_requirement"] for record in records).items())
        ),
        "period_scope_status": dict(
            sorted(Counter(record["period_scope_status"] for record in records).items())
        ),
    }
    payload = {
        "schema_version": "0.1",
        "purpose": (
            "Non-semantic render/proof matrix. It consolidates invocation "
            "contracts, dataset mechanical compatibility, stress-test proof, "
            "and PNG evidence without selecting charts for a user."
        ),
        "inputs": {
            "selection_manifest": str(selection_manifest_path),
            "parameter_audit": str(parameter_audit_path),
            "compatibility_audit": str(compatibility_audit_path),
            "stress_test": str(stress_test_path),
        },
        "counts": counts,
        "records": records,
    }
    _write_json(output_json_path, payload)
    output_md_path.write_text(_markdown(payload), encoding="utf-8")
    return payload


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Chart Render Proof Matrix",
        "",
        payload["purpose"],
        "",
        "## Counts",
        "",
        f"- `capabilities`: `{payload['counts']['capabilities']}`",
        "",
        "### Render Proof Status",
        "",
    ]
    for status, count in payload["counts"]["render_proof_status"].items():
        lines.append(f"- `{status}`: `{count}`")
    lines.extend(["", "### Fixture Requirement", ""])
    for status, count in payload["counts"]["fixture_requirement"].items():
        lines.append(f"- `{status}`: `{count}`")
    lines.extend(["", "### Period Scope Status", ""])
    for status, count in payload["counts"]["period_scope_status"].items():
        lines.append(f"- `{status}`: `{count}`")
    lines.extend(["", "## Capability Matrix", ""])
    for record in payload["records"]:
        lines.append(
            f"- `{record['capability_id']}`: "
            f"`{record['render_proof_status']}`"
            f" / fixture `{record['fixture_requirement']}`"
            f" / period scope `{record['period_scope_status']}`"
        )
        if record["mechanical_issues"]:
            lines.append(f"  - Issues: `{', '.join(record['mechanical_issues'])}`")
        warning = (record.get("period_scope") or {}).get("pre_render_warning")
        if warning:
            lines.append(f"  - Period scope: {warning}")
    lines.append("")
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--selection-manifest", type=Path, default=DEFAULT_SELECTION_MANIFEST
    )
    parser.add_argument("--parameter-audit", type=Path, default=DEFAULT_PARAMETER_AUDIT)
    parser.add_argument(
        "--compatibility-audit", type=Path, default=DEFAULT_COMPATIBILITY_AUDIT
    )
    parser.add_argument("--stress-test", type=Path, default=DEFAULT_STRESS_TEST)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    return parser


def main() -> int:
    args = _parser().parse_args()
    payload = build_chart_render_proof_matrix(
        selection_manifest_path=args.selection_manifest,
        parameter_audit_path=args.parameter_audit,
        compatibility_audit_path=args.compatibility_audit,
        stress_test_path=args.stress_test,
        output_json_path=args.output_json,
        output_md_path=args.output_md,
    )
    print(args.output_json)
    print(args.output_md)
    print(json.dumps(payload["counts"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
