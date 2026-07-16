from __future__ import annotations

import html
import json
from collections import Counter
from pathlib import Path
from typing import Any

__all__ = ["build_chart_selection_setup_audit", "main"]

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = REPO_ROOT / "runs" / "chart_selection_manifest_rebuild"
DEFAULT_SELECTION_MANIFEST = RUN_DIR / "selection_manifest.json"
DEFAULT_COMPATIBILITY_AUDITS = {
    "us_cosmetics": RUN_DIR / "us_cosmetics_dataset_profile_chart_compatibility.json",
    "hair_color_iv": RUN_DIR / "hair_color_iv_dataset_profile_chart_compatibility.json",
    "adventureworks": RUN_DIR
    / "adventureworks_dataset_profile_chart_compatibility.json",
}
DEFAULT_OUTPUT_JSON = RUN_DIR / "chart_selection_setup_audit.json"
DEFAULT_OUTPUT_MD = RUN_DIR / "chart_selection_setup_audit.md"
DEFAULT_OUTPUT_HTML = RUN_DIR / "chart_selection_setup_audit.html"

SEMANTIC_OR_PACKAGE_ISSUES = {
    "requires_semantic_or_package_metric_source",
    "requires_semantic_or_package_role",
}
DATASET_SCHEMA_ISSUES = {
    "missing_schema_role",
    "missing_source_metric_roles",
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _compatibility_by_capability(
    compatibility_audits: dict[str, dict[str, Any]],
) -> dict[str, dict[str, dict[str, Any]]]:
    return {
        dataset_id: {
            str(result["capability_id"]): result for result in audit.get("results", [])
        }
        for dataset_id, audit in compatibility_audits.items()
    }


def _manifest_contract_issues(capability: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    invocation_contract = capability.get("normalized_invocation_contract")
    if (
        isinstance(invocation_contract, dict)
        and invocation_contract.get("status") != "parameter_contract_ready"
    ):
        issues.append(
            "invocation_contract_status:"
            f"{invocation_contract.get('status', 'missing')}"
        )
    contract = capability.get("selection_contract") or {}
    requirements = contract.get("dataset_requirements") or {}
    dimensions = requirements.get("dimensions") or {}
    for role in dimensions.get("required_roles") or []:
        if role not in (dimensions.get("role_requirements") or {}):
            issues.append(f"missing_dimension_role_requirement:{role}")
    for metric_role in (requirements.get("metrics") or {}).get(
        "source_metric_roles"
    ) or []:
        if not metric_role.get("accepted_metric_classes"):
            issues.append(f"missing_metric_classes:{metric_role.get('role')}")
    return issues


def _shortcoming_labels(results_by_dataset: dict[str, dict[str, Any]]) -> list[str]:
    labels: set[str] = set()
    for result in results_by_dataset.values():
        issues = set(result.get("issues") or [])
        if issues & SEMANTIC_OR_PACKAGE_ISSUES:
            labels.add("semantic_or_package_gap")
        if issues & DATASET_SCHEMA_ISSUES:
            labels.add("dataset_schema_gap")
        if "missing_role_prerequisites" in issues:
            labels.add("profile_role_candidate_gap")
        if "missing_period_axis" in issues:
            labels.add("period_axis_gap")
        if "insufficient_dimension_columns" in issues:
            labels.add("dimension_count_gap")
    return sorted(labels)


def _overall_status(
    *,
    manifest_issues: list[str],
    results_by_dataset: dict[str, dict[str, Any]],
    shortcomings: list[str],
) -> str:
    if manifest_issues:
        return "manifest_contract_gap"
    statuses = {result.get("status") for result in results_by_dataset.values()}
    if statuses == {"mechanically_compatible"}:
        return "mechanically_ready_on_tested_profiles"
    if shortcomings == ["semantic_or_package_gap"]:
        return "blocked_by_semantic_or_package_layer"
    if shortcomings and set(shortcomings) <= {"dataset_schema_gap"}:
        return "blocked_by_dataset_schema"
    if "semantic_or_package_gap" in shortcomings:
        return "blocked_by_semantic_or_package_plus_dataset_profile"
    return "needs_profile_or_manifest_review"


def _role_resolution_digest(result: dict[str, Any]) -> list[dict[str, Any]]:
    digest = []
    for role in result.get("role_resolutions") or []:
        digest.append(
            {
                "role": role.get("role"),
                "resolution_type": role.get("resolution_type"),
                "missing_profile_roles": role.get("missing_profile_roles") or [],
                "candidate_columns": role.get("candidate_columns") or [],
                "prerequisite_matches": role.get("prerequisite_matches") or {},
                "issues": role.get("issues") or [],
            }
        )
    return digest


def _mechanical_role_match_digest(result: dict[str, Any]) -> list[dict[str, Any]]:
    digest = []
    for match in result.get("mechanical_role_matches") or []:
        digest.append(
            {
                "kind": match.get("kind"),
                "role": match.get("role"),
                "fit_status": match.get("fit_status"),
                "ambiguity_status": match.get("ambiguity_status"),
                "candidate_count": match.get("candidate_count"),
                "candidate_columns": match.get("candidate_columns") or [],
                "issue": match.get("issue"),
            }
        )
    return digest


def _capability_record(
    capability_id: str,
    capability: dict[str, Any],
    compatibility_by_dataset: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, Any]:
    results_by_dataset = {
        dataset_id: results.get(
            capability_id,
            {
                "capability_id": capability_id,
                "status": "missing",
                "issues": ["missing_compatibility_result"],
            },
        )
        for dataset_id, results in compatibility_by_dataset.items()
    }
    manifest_issues = _manifest_contract_issues(capability)
    shortcomings = _shortcoming_labels(results_by_dataset)
    return {
        "capability_id": capability_id,
        "overall_status": _overall_status(
            manifest_issues=manifest_issues,
            results_by_dataset=results_by_dataset,
            shortcomings=shortcomings,
        ),
        "manifest_contract_issues": manifest_issues,
        "family": capability.get("family"),
        "visual_grammar": capability.get("visual_grammar"),
        "selection_emphasis": capability.get("selection_emphasis"),
        "invocation_contract_status": (
            capability.get("normalized_invocation_contract") or {}
        ).get("status", "not_recorded"),
        "best_when": capability.get("best_when"),
        "avoid_when": capability.get("avoid_when"),
        "period_semantics": capability.get("period_semantics") or {},
        "metric_requirements": capability.get("selection_contract", {})
        .get("dataset_requirements", {})
        .get("metrics", {}),
        "dimension_requirements": capability.get("selection_contract", {})
        .get("dataset_requirements", {})
        .get("dimensions", {}),
        "shortcomings": shortcomings,
        "datasets": {
            dataset_id: {
                "status": result.get("status"),
                "issues": result.get("issues") or [],
                "period_candidates": result.get("period_candidates") or [],
                "source_metric_matches": result.get("source_metric_matches") or [],
                "role_resolutions": _role_resolution_digest(result),
                "mechanical_role_matches": _mechanical_role_match_digest(result),
            }
            for dataset_id, result in results_by_dataset.items()
        },
    }


def build_chart_selection_setup_audit(
    *,
    selection_manifest_path: Path = DEFAULT_SELECTION_MANIFEST,
    compatibility_audit_paths: dict[str, Path] | None = None,
    output_json_path: Path = DEFAULT_OUTPUT_JSON,
    output_md_path: Path = DEFAULT_OUTPUT_MD,
    output_html_path: Path = DEFAULT_OUTPUT_HTML,
) -> dict[str, Any]:
    manifest = _load_json(selection_manifest_path)
    audit_paths = compatibility_audit_paths or DEFAULT_COMPATIBILITY_AUDITS
    compatibility_audits = {
        dataset_id: _load_json(path) for dataset_id, path in audit_paths.items()
    }
    compatibility = _compatibility_by_capability(compatibility_audits)
    records = [
        _capability_record(capability_id, capability, compatibility)
        for capability_id, capability in sorted(
            manifest.get("capabilities", {}).items()
        )
    ]
    status_counts = dict(
        sorted(Counter(record["overall_status"] for record in records).items())
    )
    shortcoming_counts = dict(
        sorted(
            Counter(
                shortcoming
                for record in records
                for shortcoming in record["shortcomings"]
            ).items()
        )
    )
    payload = {
        "schema_version": "1.0",
        "purpose": (
            "Chart-by-chart setup audit for the future selector boundary: manifest "
            "role contract plus dataset-profile mechanical compatibility. This "
            "does not decide business semantic validity."
        ),
        "inputs": {
            "selection_manifest": str(selection_manifest_path),
            "compatibility_audits": {
                dataset_id: str(path) for dataset_id, path in audit_paths.items()
            },
        },
        "manifest_validation_issue_count": len(manifest.get("validation_issues") or []),
        "dataset_counts": {
            dataset_id: audit.get("counts", {})
            for dataset_id, audit in compatibility_audits.items()
        },
        "overall_status_counts": status_counts,
        "invocation_contract_status_counts": dict(
            sorted(
                Counter(
                    record["invocation_contract_status"] for record in records
                ).items()
            )
        ),
        "shortcoming_counts": shortcoming_counts,
        "records": records,
    }
    _write_json(output_json_path, payload)
    output_md_path.write_text(_markdown(payload), encoding="utf-8")
    output_html_path.write_text(_html_page(payload), encoding="utf-8")
    return payload


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Chart Selection Setup Audit",
        "",
        payload["purpose"],
        "",
        "## Overall Status Counts",
        "",
    ]
    for status, count in payload["overall_status_counts"].items():
        lines.append(f"- `{status}`: `{count}`")
    lines.extend(["", "## Invocation Contract Status Counts", ""])
    for status, count in payload["invocation_contract_status_counts"].items():
        lines.append(f"- `{status}`: `{count}`")
    lines.extend(["", "## Shortcoming Counts", ""])
    for shortcoming, count in payload["shortcoming_counts"].items():
        lines.append(f"- `{shortcoming}`: `{count}`")
    lines.extend(["", "## Dataset Counts", ""])
    for dataset_id, counts in payload["dataset_counts"].items():
        count_text = ", ".join(f"`{key}`={value}" for key, value in counts.items())
        lines.append(f"- `{dataset_id}`: {count_text}")
    lines.extend(["", "## Capability Results", ""])
    for record in payload["records"]:
        lines.append(
            f"- `{record['capability_id']}`: `{record['overall_status']}` "
            f"({record['selection_emphasis']})"
        )
        if record["shortcomings"]:
            lines.append(
                "  - Shortcomings: "
                + ", ".join(f"`{item}`" for item in record["shortcomings"])
            )
        for dataset_id, dataset in record["datasets"].items():
            issue_text = ", ".join(dataset["issues"]) or "none"
            lines.append(
                f"  - `{dataset_id}`: `{dataset['status']}` / issues `{issue_text}`"
            )
        role_lines = _role_lines(record)
        if role_lines:
            lines.extend(f"  - {line}" for line in role_lines)
    return "\n".join(lines) + "\n"


def _role_lines(record: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    first_dataset = next(iter(record["datasets"].values()), None)
    if not first_dataset:
        return lines
    for role in first_dataset.get("role_resolutions") or []:
        resolution_type = role.get("resolution_type")
        missing = ", ".join(role.get("missing_profile_roles") or []) or "none"
        candidates = ", ".join(
            f"`{column}`" for column in (role.get("candidate_columns") or [])[:5]
        )
        if not candidates:
            prerequisite_matches = role.get("prerequisite_matches") or {}
            candidate_parts = []
            for profile_role, values in prerequisite_matches.items():
                if values:
                    candidate_parts.append(
                        f"{profile_role}: "
                        + ", ".join(f"`{value}`" for value in values[:3])
                    )
            candidates = "; ".join(candidate_parts) or "none"
        lines.append(
            f"Role `{role.get('role')}`: `{resolution_type}`, "
            f"missing `{missing}`, candidates {candidates}"
        )
    return lines


def _html_page(payload: dict[str, Any]) -> str:
    summary_rows = "\n".join(
        "<tr>" f"<th>{html.escape(status)}</th>" f"<td>{count}</td>" "</tr>"
        for status, count in payload["overall_status_counts"].items()
    )
    cards = "\n".join(_html_card(record) for record in payload["records"])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Chart Selection Setup Audit</title>
  <style>
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: #17202a;
      background: #fff;
    }}
    header {{
      padding: 28px 32px 20px;
      background: #f7f8fa;
      border-bottom: 1px solid #d9dee7;
    }}
    main {{ padding: 24px 32px 48px; }}
    h1 {{ margin: 0 0 8px; font-size: 28px; letter-spacing: 0; }}
    h2 {{ margin: 0; font-size: 17px; letter-spacing: 0; }}
    p {{ line-height: 1.45; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}
    th, td {{
      text-align: left;
      vertical-align: top;
      border-top: 1px solid #d9dee7;
      padding: 7px 6px;
    }}
    th {{ color: #667085; width: 22%; }}
    .summary {{
      border: 1px solid #d9dee7;
      border-radius: 8px;
      overflow: hidden;
      margin-bottom: 22px;
    }}
    .card {{
      border: 1px solid #d9dee7;
      border-radius: 8px;
      margin-bottom: 14px;
      overflow: hidden;
    }}
    .cardHeader {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      padding: 14px 16px;
      background: #fbfcfd;
      border-bottom: 1px solid #d9dee7;
    }}
    .meta {{
      margin: 0 0 4px;
      color: #667085;
      font-size: 12px;
      font-weight: 700;
    }}
    .badge {{
      align-self: flex-start;
      border-radius: 999px;
      border: 1px solid #d9dee7;
      padding: 5px 9px;
      font-size: 12px;
      font-weight: 700;
      white-space: nowrap;
    }}
    .mechanically_ready_on_tested_profiles {{
      color: #0f766e;
      border-color: #99d0c9;
      background: #e8f6f4;
    }}
    .blocked_by_semantic_or_package_layer,
    .blocked_by_dataset_schema,
    .blocked_by_semantic_or_package_plus_dataset_profile,
    .needs_profile_or_manifest_review {{
      color: #b54708;
      border-color: #fedf89;
      background: #fffaeb;
    }}
    .manifest_contract_gap {{
      color: #b42318;
      border-color: #fecdca;
      background: #fef3f2;
    }}
    .body {{ padding: 14px 16px; }}
    code {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
    }}
    .muted {{ color: #667085; }}
  </style>
</head>
<body>
  <header>
    <h1>Chart Selection Setup Audit</h1>
    <p class="muted">{html.escape(payload["purpose"])}</p>
  </header>
  <main>
    <section class="summary"><table>{summary_rows}</table></section>
    {cards}
  </main>
</body>
</html>
"""


def _html_card(record: dict[str, Any]) -> str:
    dataset_rows = "\n".join(
        "<tr>"
        f"<th>{html.escape(dataset_id)}</th>"
        f"<td><code>{html.escape(str(dataset['status']))}</code></td>"
        f"<td>{_format_code_list(dataset['issues'])}</td>"
        "</tr>"
        for dataset_id, dataset in record["datasets"].items()
    )
    role_rows = "\n".join(
        f'<tr><th>Role</th><td colspan="2">{html.escape(line)}</td></tr>'
        for line in _role_lines(record)
    )
    shortcoming_text = _format_code_list(record["shortcomings"])
    return f"""
<article class="card">
  <div class="cardHeader">
    <div>
      <p class="meta">{html.escape(record["capability_id"])}</p>
      <h2>{html.escape(str(record["selection_emphasis"]))}</h2>
    </div>
    <span class="badge {html.escape(record["overall_status"])}">{html.escape(record["overall_status"])}</span>
  </div>
  <div class="body">
    <table>
      <tr><th>Best when</th><td colspan="2">{html.escape(str(record.get("best_when") or ""))}</td></tr>
      <tr><th>Avoid when</th><td colspan="2">{html.escape(str(record.get("avoid_when") or ""))}</td></tr>
      <tr><th>Shortcomings</th><td colspan="2">{shortcoming_text}</td></tr>
      {dataset_rows}
      {role_rows}
    </table>
  </div>
</article>
"""


def _format_code_list(values: list[Any]) -> str:
    if not values:
        return '<span class="muted">none</span>'
    return ", ".join(f"<code>{html.escape(str(value))}</code>" for value in values)


def main() -> int:
    payload = build_chart_selection_setup_audit()
    print(DEFAULT_OUTPUT_JSON)
    print(DEFAULT_OUTPUT_MD)
    print(DEFAULT_OUTPUT_HTML)
    print(json.dumps(payload["overall_status_counts"], sort_keys=True))
    print(json.dumps(payload["shortcoming_counts"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
