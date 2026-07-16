from __future__ import annotations

import html
import json
from collections import Counter
from pathlib import Path
from typing import Any

__all__ = ["build_chart_selection_stress_test", "main"]

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = REPO_ROOT / "runs" / "chart_selection_manifest_rebuild"
DEFAULT_SELECTION_MANIFEST = RUN_DIR / "selection_manifest.json"
DEFAULT_COMPATIBILITY_AUDIT = (
    RUN_DIR / "us_cosmetics_dataset_profile_chart_compatibility.json"
)
DEFAULT_PROOF = RUN_DIR / "us_cosmetics_adversarial_chart_proof.json"
DEFAULT_GALLERY_MANIFEST = (
    REPO_ROOT / "static" / "shared" / "png-gallery" / "manifest.json"
)
DEFAULT_RENDERED_ASSETS = RUN_DIR / "cosmetics_question_png_assets" / "manifest.json"
DEFAULT_OUTPUT_JSON = RUN_DIR / "chart_selection_stress_test.json"
DEFAULT_OUTPUT_MD = RUN_DIR / "chart_selection_stress_test.md"
DEFAULT_OUTPUT_HTML = RUN_DIR / "chart_selection_stress_test.html"

PASSING_PROOF_VERDICTS = {"credible_data_artifact"}
CORRECT_REJECTION_VERDICTS = {"correct_rejection"}
SEMANTIC_OR_PACKAGE_GAP_ISSUES = {
    "requires_semantic_or_package_metric_source",
    "requires_semantic_or_package_role",
}

STATUS_DESCRIPTIONS = {
    "works": (
        "Question/proof exists, the plugin or derived context accepted the "
        "manifest-derived parameters, dataset compatibility is mechanically "
        "sound, and a PNG example is available for inspection."
    ),
    "manifest_unclear": (
        "The manifest entry exists, but this audit lacks a proof question and "
        "parameter exercise strong enough to show that a dumb selector can use it."
    ),
    "parameter_gap": (
        "The selector path identifies the chart, but this audit lacks enough "
        "rendering or context evidence to prove parameter-to-artifact reliability."
    ),
    "dataset_gap": (
        "The current dataset cannot exercise the chart roles, or the proof "
        "correctly rejects the chart for this dataset."
    ),
    "semantic_gap": (
        "Mechanical columns exist or could be derived, but the missing decision is "
        "semantic: which special role, cohort, signal, or business-valid split to use."
    ),
    "bad_or_duplicate": (
        "The chart appears structurally redundant or unsupported enough that it "
        "should be renamed, merged, or removed. This audit does not assign this "
        "status automatically."
    ),
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _gallery_items_by_capability(
    gallery: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    items_by_capability: dict[str, list[dict[str, Any]]] = {}
    for item in gallery.get("items", []):
        capability_id = (item.get("artifact_contract") or {}).get("capability_id")
        if capability_id:
            items_by_capability.setdefault(str(capability_id), []).append(item)
    return items_by_capability


def _proof_by_capability(proof: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item["capability_id"]): item for item in proof.get("results", [])}


def _compatibility_by_capability(audit: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item["capability_id"]): item for item in audit.get("results", [])}


def _rendered_assets_by_capability(assets: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item["capability_id"]): item
        for item in assets.get("outputs", [])
        if item.get("capability_id") and item.get("status") == "written"
    }


def _manifest_contract_issues(capability: dict[str, Any]) -> list[str]:
    issues = []
    for key in (
        "analysis_task_ids",
        "selection_emphasis",
        "best_when",
        "avoid_when",
        "axis_roles",
        "metric_requirements",
        "selection_contract",
    ):
        if not capability.get(key):
            issues.append(f"missing_{key}")
    selection_contract = capability.get("selection_contract") or {}
    dataset_requirements = selection_contract.get("dataset_requirements") or {}
    if not dataset_requirements.get("metrics"):
        issues.append("missing_selection_contract_metrics")
    if not dataset_requirements.get("dimensions"):
        issues.append("missing_selection_contract_dimensions")
    if not dataset_requirements.get("period"):
        issues.append("missing_selection_contract_period")
    return issues


def _png_evidence(
    capability_id: str,
    *,
    rendered_assets: dict[str, dict[str, Any]],
    gallery_items: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    rendered = rendered_assets.get(capability_id)
    if rendered:
        return {
            "status": "rendered_question_png",
            "path": rendered.get("png_path"),
            "relative_path": rendered.get("png_relative_path"),
            "renderer": rendered.get("renderer"),
        }
    gallery = gallery_items.get(capability_id) or []
    if gallery:
        return {
            "status": "gallery_png",
            "output": gallery[0].get("output"),
            "source": gallery[0].get("source"),
            "example_count": len(gallery),
        }
    return {"status": "missing_png"}


def _semantic_gap_from_compatibility(compatibility: dict[str, Any] | None) -> bool:
    if not compatibility:
        return False
    issues = set(compatibility.get("issues") or [])
    return bool(issues) and issues.issubset(SEMANTIC_OR_PACKAGE_GAP_ISSUES)


def _classify_capability(
    *,
    capability: dict[str, Any],
    compatibility: dict[str, Any] | None,
    proof_case: dict[str, Any] | None,
    png: dict[str, Any],
    manifest_contract_issues: list[str],
) -> tuple[str, list[str]]:
    reasons = []
    if manifest_contract_issues:
        reasons.append("manifest_contract_has_missing_fields")
    compatibility_status = (
        str(compatibility.get("status")) if compatibility else "missing_compatibility"
    )
    proof_verdict = str(proof_case.get("verdict")) if proof_case else None
    has_png = png["status"] != "missing_png"

    if proof_verdict in CORRECT_REJECTION_VERDICTS:
        reasons.append("proof_correctly_rejects_this_dataset")
        return "dataset_gap", reasons

    if compatibility_status == "mechanically_incomplete":
        reasons.extend(compatibility.get("issues") or [])
        if _semantic_gap_from_compatibility(compatibility):
            reasons.append("requires_semantic_or_profile_role_mapping")
            return "semantic_gap", reasons
        return "dataset_gap", reasons

    if compatibility_status == "missing_compatibility":
        reasons.append("missing_dataset_profile_compatibility_row")
        return "parameter_gap", reasons

    if (
        proof_verdict in PASSING_PROOF_VERDICTS
        and has_png
        and not manifest_contract_issues
    ):
        reasons.append("proof_and_png_available")
        return "works", reasons

    if proof_verdict in PASSING_PROOF_VERDICTS and not has_png:
        reasons.append("proof_passed_but_png_evidence_missing")
        return "parameter_gap", reasons

    if proof_verdict and proof_verdict not in PASSING_PROOF_VERDICTS:
        reasons.append(f"proof_verdict_{proof_verdict}")
        return "parameter_gap", reasons

    if not proof_case:
        reasons.append("missing_question_parameter_proof_case")
        if not has_png:
            reasons.append("missing_png_evidence")
        return "manifest_unclear", reasons

    return "manifest_unclear", reasons


def _capability_record(
    capability_id: str,
    capability: dict[str, Any],
    *,
    compatibility: dict[str, Any] | None,
    proof_case: dict[str, Any] | None,
    rendered_assets: dict[str, dict[str, Any]],
    gallery_items: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    manifest_contract_issues = _manifest_contract_issues(capability)
    png = _png_evidence(
        capability_id,
        rendered_assets=rendered_assets,
        gallery_items=gallery_items,
    )
    status, reasons = _classify_capability(
        capability=capability,
        compatibility=compatibility,
        proof_case=proof_case,
        png=png,
        manifest_contract_issues=manifest_contract_issues,
    )
    return {
        "capability_id": capability_id,
        "status": status,
        "reasons": reasons,
        "family": capability.get("family"),
        "visual_grammar": capability.get("visual_grammar"),
        "selection_emphasis": capability.get("selection_emphasis"),
        "analysis_task_ids": capability.get("analysis_task_ids") or [],
        "best_when": capability.get("best_when"),
        "avoid_when": capability.get("avoid_when"),
        "dimension_roles": capability.get("dimension_roles") or [],
        "dimension_contract": capability.get("dimension_contract"),
        "metric_requirements": capability.get("metric_requirements") or {},
        "period_semantics": capability.get("period_semantics") or {},
        "competitors": capability.get("competing_capability_ids") or [],
        "manifest_contract_issues": manifest_contract_issues,
        "compatibility": compatibility
        or {
            "status": "missing",
            "issues": ["missing_dataset_profile_compatibility_row"],
        },
        "proof": proof_case
        or {
            "status": "missing",
            "issues": ["missing_question_parameter_proof_case"],
        },
        "png_evidence": png,
        "example_artifact_labels": capability.get("example_artifact_labels") or [],
    }


def build_chart_selection_stress_test(
    *,
    selection_manifest_path: Path = DEFAULT_SELECTION_MANIFEST,
    compatibility_audit_path: Path = DEFAULT_COMPATIBILITY_AUDIT,
    proof_path: Path = DEFAULT_PROOF,
    gallery_manifest_path: Path = DEFAULT_GALLERY_MANIFEST,
    rendered_assets_path: Path = DEFAULT_RENDERED_ASSETS,
    output_json_path: Path = DEFAULT_OUTPUT_JSON,
    output_md_path: Path = DEFAULT_OUTPUT_MD,
    output_html_path: Path = DEFAULT_OUTPUT_HTML,
) -> dict[str, Any]:
    selection_manifest = _load_json(selection_manifest_path)
    compatibility_audit = _load_json(compatibility_audit_path)
    proof = _load_json(proof_path)
    gallery = _load_json(gallery_manifest_path)
    rendered_assets = (
        _load_json(rendered_assets_path) if rendered_assets_path.exists() else {}
    )

    compatibility = _compatibility_by_capability(compatibility_audit)
    proof_cases = _proof_by_capability(proof)
    gallery_items = _gallery_items_by_capability(gallery)
    rendered_items = _rendered_assets_by_capability(rendered_assets)

    records = [
        _capability_record(
            capability_id,
            capability,
            compatibility=compatibility.get(capability_id),
            proof_case=proof_cases.get(capability_id),
            rendered_assets=rendered_items,
            gallery_items=gallery_items,
        )
        for capability_id, capability in sorted(
            selection_manifest["capabilities"].items()
        )
    ]
    counts = dict(sorted(Counter(record["status"] for record in records).items()))
    payload = {
        "schema_version": "1.0",
        "purpose": (
            "Stress-test whether the chart-selection manifest can support a "
            "future caller using a question, dataset profile compatibility, "
            "manifest role contract, and PNG evidence."
        ),
        "status_descriptions": STATUS_DESCRIPTIONS,
        "inputs": {
            "selection_manifest": str(selection_manifest_path),
            "compatibility_audit": str(compatibility_audit_path),
            "proof": str(proof_path),
            "gallery_manifest": str(gallery_manifest_path),
            "rendered_assets": str(rendered_assets_path),
        },
        "counts": counts,
        "records": records,
    }
    _write_json(output_json_path, payload)
    output_md_path.write_text(_markdown(payload), encoding="utf-8")
    output_html_path.write_text(_html_page(payload), encoding="utf-8")
    return payload


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Chart Selection Stress Test",
        "",
        payload["purpose"],
        "",
        "## Status Counts",
        "",
    ]
    for status, count in payload["counts"].items():
        lines.append(f"- `{status}`: `{count}`")
    lines.extend(["", "## Status Meaning", ""])
    for status, description in payload["status_descriptions"].items():
        lines.append(f"- `{status}`: {description}")
    lines.extend(["", "## Capability Results", ""])
    for record in payload["records"]:
        proof = record["proof"]
        question = proof.get("question", "no proof question")
        proof_verdict = proof.get("verdict", proof.get("status"))
        png_status = record["png_evidence"]["status"]
        compatibility_status = record["compatibility"]["status"]
        lines.append(
            f"- `{record['capability_id']}`: `{record['status']}` "
            f"/ compatibility `{compatibility_status}` / proof `{proof_verdict}` "
            f"/ png `{png_status}`"
        )
        lines.append(f"  - Question: {question}")
        if record["reasons"]:
            lines.append(f"  - Reasons: `{', '.join(record['reasons'])}`")
    return "\n".join(lines) + "\n"


def _format_list(values: list[Any], *, limit: int = 8) -> str:
    if not values:
        return "<code>none</code>"
    rendered = ", ".join(
        f"<code>{html.escape(str(value))}</code>" for value in values[:limit]
    )
    if len(values) > limit:
        rendered += f' <span class="muted">+{len(values) - limit} more</span>'
    return rendered


def _html_page(payload: dict[str, Any]) -> str:
    summary_rows = "\n".join(
        "<tr>"
        f"<th>{html.escape(status)}</th>"
        f"<td>{count}</td>"
        f"<td>{html.escape(payload['status_descriptions'][status])}</td>"
        "</tr>"
        for status, count in payload["counts"].items()
    )
    cards = "\n".join(_html_card(record) for record in payload["records"])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Chart Selection Stress Test</title>
  <style>
    :root {{
      --ink: #17202a;
      --muted: #667085;
      --line: #d9dee7;
      --panel: #f7f8fa;
      --works: #0f766e;
      --gap: #b54708;
      --bad: #b42318;
    }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: #fff;
    }}
    header {{
      padding: 28px 32px 20px;
      background: var(--panel);
      border-bottom: 1px solid var(--line);
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 28px;
      line-height: 1.15;
      letter-spacing: 0;
    }}
    .intro {{
      margin: 0;
      max-width: 1100px;
      color: var(--muted);
      line-height: 1.45;
    }}
    main {{
      padding: 24px 32px 48px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}
    th, td {{
      text-align: left;
      vertical-align: top;
      border-top: 1px solid var(--line);
      padding: 7px 6px;
    }}
    th {{
      color: var(--muted);
      width: 22%;
    }}
    .summary {{
      margin: 0 0 24px;
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }}
    .card {{
      border: 1px solid var(--line);
      border-radius: 8px;
      margin: 0 0 16px;
      overflow: hidden;
    }}
    .cardHeader {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      padding: 14px 16px;
      background: #fbfcfd;
      border-bottom: 1px solid var(--line);
    }}
    h2 {{
      margin: 0;
      font-size: 17px;
      line-height: 1.3;
      letter-spacing: 0;
    }}
    .capability {{
      margin: 0 0 4px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }}
    .badge {{
      align-self: flex-start;
      border-radius: 999px;
      border: 1px solid var(--line);
      padding: 5px 9px;
      font-size: 12px;
      font-weight: 700;
      white-space: nowrap;
    }}
    .works {{ color: var(--works); border-color: #99d0c9; background: #e8f6f4; }}
    .manifest_unclear, .parameter_gap, .dataset_gap, .semantic_gap {{
      color: var(--gap);
      border-color: #fedf89;
      background: #fffaeb;
    }}
    .bad_or_duplicate {{ color: var(--bad); border-color: #fecdca; background: #fef3f2; }}
    .grid {{
      display: grid;
      grid-template-columns: minmax(280px, 0.9fr) minmax(320px, 1.1fr);
      gap: 18px;
      padding: 16px;
    }}
    img {{
      max-width: 100%;
      height: auto;
      display: block;
      border: 1px solid var(--line);
      background: white;
    }}
    .missing {{
      border: 1px solid var(--line);
      background: #fff7ed;
      color: var(--gap);
      padding: 20px;
      font-weight: 700;
    }}
    pre {{
      overflow: auto;
      background: #f3f5f7;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px;
      font-size: 12px;
      line-height: 1.35;
    }}
    code {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
    }}
    .muted {{
      color: var(--muted);
      font-size: 12px;
    }}
    @media (max-width: 920px) {{
      header, main {{ padding-left: 16px; padding-right: 16px; }}
      .cardHeader {{ flex-direction: column; }}
      .grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Chart Selection Stress Test</h1>
    <p class="intro">{html.escape(payload["purpose"])}</p>
  </header>
  <main>
    <section class="summary">
      <table>{summary_rows}</table>
    </section>
    {cards}
  </main>
</body>
</html>
"""


def _html_card(record: dict[str, Any]) -> str:
    proof = record["proof"]
    question = proof.get("question", "No question/parameter proof case yet.")
    proof_verdict = proof.get("verdict", proof.get("status"))
    chart = proof.get("plugin_chart", "not exercised")
    png = _html_png(record["png_evidence"])
    roles = {
        "analysis_task_ids": record["analysis_task_ids"],
        "period_semantics": record["period_semantics"],
        "metric_requirements": record["metric_requirements"],
        "dimension_roles": record["dimension_roles"],
        "dimension_contract": record["dimension_contract"],
        "competitors": record["competitors"],
    }
    role_json = html.escape(json.dumps(roles, indent=2, ensure_ascii=False))
    reasons = _format_list(record["reasons"], limit=10)
    compatibility = record["compatibility"]
    issues = _format_list(compatibility.get("issues") or [], limit=8)
    return f"""
<article class="card">
  <div class="cardHeader">
    <div>
      <p class="capability">{html.escape(record["capability_id"])}</p>
      <h2>{html.escape(str(question))}</h2>
    </div>
    <span class="badge {html.escape(record["status"])}">{html.escape(record["status"])}</span>
  </div>
  <div class="grid">
    <section>
      {png}
    </section>
    <section>
      <table>
        <tr><th>Selected chart</th><td><code>{html.escape(str(chart))}</code></td></tr>
        <tr><th>Proof</th><td><code>{html.escape(str(proof_verdict))}</code></td></tr>
        <tr><th>Compatibility</th><td><code>{html.escape(str(compatibility.get("status")))}</code></td></tr>
        <tr><th>Issues</th><td>{issues}</td></tr>
        <tr><th>Reasons</th><td>{reasons}</td></tr>
        <tr><th>Best when</th><td>{html.escape(str(record.get("best_when") or ""))}</td></tr>
        <tr><th>Avoid when</th><td>{html.escape(str(record.get("avoid_when") or ""))}</td></tr>
      </table>
      <pre>{role_json}</pre>
    </section>
  </div>
</article>
"""


def _html_png(png: dict[str, Any]) -> str:
    if png["status"] == "rendered_question_png":
        relative_path = html.escape(str(png.get("relative_path")))
        return (
            f'<a href="cosmetics_question_png_assets/{relative_path}">'
            f'<img src="cosmetics_question_png_assets/{relative_path}" alt="question PNG">'
            "</a>"
            f'<p class="muted">{html.escape(str(png.get("renderer")))}</p>'
        )
    if png["status"] == "gallery_png":
        output = html.escape(str(png.get("output")))
        return (
            f'<a href="../../static/shared/png-gallery/{output}">'
            f'<img src="../../static/shared/png-gallery/{output}" alt="gallery PNG">'
            "</a>"
            f'<p class="muted">gallery example; count {html.escape(str(png.get("example_count")))}</p>'
        )
    return '<div class="missing">No PNG evidence for this capability yet.</div>'


def main() -> int:
    payload = build_chart_selection_stress_test()
    print(DEFAULT_OUTPUT_JSON)
    print(DEFAULT_OUTPUT_MD)
    print(DEFAULT_OUTPUT_HTML)
    print(json.dumps(payload["counts"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
