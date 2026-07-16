from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

__all__ = ["build_chart_question_png_review", "main"]

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = REPO_ROOT / "runs" / "chart_selection_manifest_rebuild"
PROOF_PATH = RUN_DIR / "us_cosmetics_adversarial_chart_proof.json"
SELECTION_MANIFEST_PATH = RUN_DIR / "selection_manifest.json"
COMPATIBILITY_AUDIT_PATH = (
    RUN_DIR / "us_cosmetics_dataset_profile_chart_compatibility.json"
)
RENDERED_ASSETS_MANIFEST_PATH = (
    RUN_DIR / "cosmetics_question_png_assets" / "manifest.json"
)
GALLERY_MANIFEST_PATH = (
    REPO_ROOT / "static" / "shared" / "png-gallery" / "manifest.json"
)
OUTPUT_PATH = RUN_DIR / "question_png_review.html"

REVIEW_CAPABILITIES = [
    "period_comparison.trend",
    "period_comparison.by_period",
    "period_comparison.multitier_column",
    "period_comparison.comparison_table",
    "period_comparison.time_series_table",
    "period_comparison.horizontal_waterfall",
    "period_comparison.dot",
    "period_comparison.slope",
    "mix.multitier_bar",
    "mix.bar",
    "mix.column",
    "mix.column_overlay",
    "mix.stacked_bar",
    "mix.stacked_bar_overlay",
    "mix.timeline",
    "mix.area",
    "mix.barmekko",
    "mix.marimekko",
    "mix.pareto",
    "mix.stacked_pareto",
    "mix.stacked_column",
    "mix.like_for_like_column",
    "mix.like_for_like_stacked_column",
    "mix.cohort_since_stacked_column",
    "mix.cohort_lost_stacked_column",
    "scatter.scatter",
    "scatter.bubble",
    "distribution.histogram",
    "set_overlap.upset_small_multiples",
    "variance.scenario_bridge",
    "variance.total_by_dimension_bridge",
    "variance.exploded_variance_bridge",
    "variance.root_cause_exploded_bridge",
    "variance.price_volume_mix",
    "variance.root_cause_total_bridge",
    "variance.root_cause_component_bridge",
]

PREFERRED_OUTPUT_BY_CAPABILITY = {
    "mix.multitier_bar": "mix_comparison__multitier_bar_two_dimension.png",
    "period_comparison.dot": "period__year_over_year_dot.png",
    "period_comparison.slope": "period__year_over_year_slope.png",
    "period_comparison.horizontal_waterfall": "period__year_over_year_waterfall.png",
    "mix.stacked_column": "mix_comparison__mix_regular__stacked_column.png",
    "mix.bar": "mix_comparison__bar.png",
    "scatter.bubble": "scatter__scatter_bubble__bubble.png",
    "distribution.histogram": "distribution__histogram.png",
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _proof_cases_by_capability() -> dict[str, dict[str, Any]]:
    proof = _load_json(PROOF_PATH)
    return {case["capability_id"]: case for case in proof["results"]}


def _capabilities() -> dict[str, dict[str, Any]]:
    manifest = _load_json(SELECTION_MANIFEST_PATH)
    return manifest["capabilities"]


def _gallery_items_by_capability() -> dict[str, list[dict[str, Any]]]:
    gallery = _load_json(GALLERY_MANIFEST_PATH)
    items_by_capability: dict[str, list[dict[str, Any]]] = {}
    for item in gallery.get("items", []):
        capability_id = (item.get("artifact_contract") or {}).get("capability_id")
        if not capability_id:
            continue
        items_by_capability.setdefault(capability_id, []).append(item)
    return items_by_capability


def _rendered_items_by_capability() -> dict[str, dict[str, Any]]:
    if not RENDERED_ASSETS_MANIFEST_PATH.exists():
        return {}
    manifest = _load_json(RENDERED_ASSETS_MANIFEST_PATH)
    return {
        str(item["capability_id"]): item
        for item in manifest.get("outputs", [])
        if item.get("status") == "written" and item.get("capability_id")
    }


def _compatibility_by_capability() -> dict[str, dict[str, Any]]:
    audit = _load_json(COMPATIBILITY_AUDIT_PATH)
    return {result["capability_id"]: result for result in audit["results"]}


def _select_gallery_item(
    capability_id: str, items_by_capability: dict[str, list[dict[str, Any]]]
) -> dict[str, Any] | None:
    items = items_by_capability.get(capability_id, [])
    preferred = PREFERRED_OUTPUT_BY_CAPABILITY.get(capability_id)
    if preferred:
        for item in items:
            if item.get("output") == preferred:
                return item
    return items[0] if items else None


def _format_params(params: dict[str, Any]) -> str:
    rows = []
    for key, value in params.items():
        rows.append(
            "<tr>"
            f"<th>{html.escape(str(key))}</th>"
            f"<td><code>{html.escape(json.dumps(value, ensure_ascii=False))}</code></td>"
            "</tr>"
        )
    return "\n".join(rows)


def _format_list(values: list[Any], *, limit: int = 10) -> str:
    if not values:
        return "<code>none</code>"
    rendered = ", ".join(
        f"<code>{html.escape(str(value))}</code>" for value in values[:limit]
    )
    if len(values) > limit:
        rendered += f' <span class="muted">+{len(values) - limit} more</span>'
    return rendered


def _format_compatibility(compatibility: dict[str, Any] | None) -> str:
    if not compatibility:
        return '<div class="missing">No dataset compatibility audit entry.</div>'
    metric_rows = []
    for match in compatibility.get("source_metric_matches") or []:
        metric_rows.append(
            "<tr>"
            f"<th>{html.escape(str(match['role']))}</th>"
            f"<td>{_format_list(match.get('candidate_columns') or [], limit=8)}</td>"
            "</tr>"
        )
    derived_roles = compatibility.get("derived_metric_roles") or []
    special_matches = compatibility.get("special_dimension_matches") or {}
    special_rows = []
    for role, candidates in special_matches.items():
        special_rows.append(
            "<tr>"
            f"<th>{html.escape(str(role))}</th>"
            f"<td>{_format_list(candidates or [], limit=8)}</td>"
            "</tr>"
        )
    issues = compatibility.get("issues") or []
    status = html.escape(str(compatibility.get("status", "unknown")))
    issue_text = _format_list(issues, limit=6) if issues else "<code>none</code>"
    metric_table = "\n".join(metric_rows) or (
        "<tr><th>source metrics</th><td><code>none required</code></td></tr>"
    )
    special_table = "\n".join(special_rows)
    special_section = (
        f"<h4>Special dimension roles</h4><table>{special_table}</table>"
        if special_rows
        else ""
    )
    return f"""
      <div class="compat">
        <dl>
          <dt>Compatibility status</dt><dd><code>{status}</code></dd>
          <dt>Compatibility issues</dt><dd>{issue_text}</dd>
          <dt>Period candidates</dt><dd>{_format_list(compatibility.get("period_candidates") or [], limit=6)}</dd>
          <dt>Derived metric roles</dt><dd>{_format_list(derived_roles, limit=8)}</dd>
        </dl>
        <h4>Source metric candidates</h4>
        <table>{metric_table}</table>
        <h4>Dimension candidates sample</h4>
        <p>{_format_list(compatibility.get("dimension_candidates_sample") or [], limit=10)}</p>
        {special_section}
      </div>
"""


def _card(
    capability_id: str,
    proof_case: dict[str, Any],
    capability: dict[str, Any],
    rendered_item: dict[str, Any] | None,
    gallery_item: dict[str, Any] | None,
    compatibility: dict[str, Any] | None,
) -> str:
    question = html.escape(proof_case["question"])
    chart = html.escape(str(proof_case.get("plugin_chart")))
    verification_artifact = proof_case.get("verification_artifact")
    verification_row = (
        "<dt>Verification artifact</dt>"
        f"<dd><code>{html.escape(str(verification_artifact))}.json</code></dd>"
        if verification_artifact
        else ""
    )
    chart_identity = proof_case.get("chart_identity") or {}
    chart_identity_status = chart_identity.get("status")
    chart_identity_row = (
        "<dt>Chart identity check</dt>"
        f"<dd><code>{html.escape(str(chart_identity_status))}</code></dd>"
        if chart_identity_status
        else ""
    )
    verdict = html.escape(str(proof_case.get("verdict")))
    best_when = html.escape(str(capability.get("best_when", "")))
    avoid_when = html.escape(str(capability.get("avoid_when", "")))
    roles = {
        "axis_roles": capability.get("axis_roles", {}),
        "period_semantics": capability.get("period_semantics", {}),
        "display_metric_roles": capability.get("display_metric_roles", []),
        "metric_requirements": capability.get("metric_requirements", {}),
        "dimension_roles": capability.get("dimension_roles", []),
    }
    dimension_contract = capability.get("dimension_contract")
    if dimension_contract is not None:
        roles["dimension_contract"] = dimension_contract
    role_json = html.escape(json.dumps(roles, indent=2, ensure_ascii=False))
    params = _format_params(proof_case.get("params") or {})
    if rendered_item:
        image_href = "cosmetics_question_png_assets/" + str(
            rendered_item["png_relative_path"]
        )
        image = (
            f'<a href="{html.escape(image_href)}">'
            f'<img src="{html.escape(image_href)}" alt="{capability_id} PNG">'
            "</a>"
        )
        source_path = rendered_item.get("source_path", "")
        renderer = rendered_item.get("renderer", "")
        image_note = html.escape(
            f"Cosmetics dataset render | {renderer} | {source_path}"
        )
    elif gallery_item:
        image_href = "../../static/shared/png-gallery/" + str(gallery_item["output"])
        image = (
            f'<a href="{html.escape(image_href)}">'
            f'<img src="{html.escape(image_href)}" alt="{capability_id} PNG">'
            "</a>"
        )
        title_lines = (gallery_item.get("title_context") or {}).get("lines") or []
        image_note = html.escape(" | ".join(str(line) for line in title_lines))
    else:
        image = '<div class="missing">No PNG found in the static gallery.</div>'
        image_note = ""

    return f"""
<article class="card">
  <div class="cardHeader">
    <div>
      <p class="capability">{html.escape(capability_id)}</p>
      <h2>{question}</h2>
    </div>
    <span class="verdict">{verdict}</span>
  </div>
  <div class="grid">
    <section class="visual">
      {image}
      <p class="imageNote">{image_note}</p>
    </section>
    <section class="details">
      <dl>
        <dt>Selected chart</dt><dd><code>{chart}</code></dd>
        {verification_row}
        {chart_identity_row}
        <dt>Best when</dt><dd>{best_when}</dd>
        <dt>Avoid when</dt><dd>{avoid_when}</dd>
      </dl>
      <h3>Parameters from the proof case</h3>
      <table>{params}</table>
      <h3>Dataset compatibility</h3>
      {_format_compatibility(compatibility)}
      <h3>Manifest role contract</h3>
      <pre>{role_json}</pre>
    </section>
  </div>
</article>
"""


def build_chart_question_png_review(output_path: Path = OUTPUT_PATH) -> Path:
    proof_cases = _proof_cases_by_capability()
    capabilities = _capabilities()
    rendered_items = _rendered_items_by_capability()
    gallery_items = _gallery_items_by_capability()
    compatibility = _compatibility_by_capability()
    cards = []
    missing = []
    for capability_id in REVIEW_CAPABILITIES:
        proof_case = proof_cases[capability_id]
        capability = capabilities[capability_id]
        rendered_item = rendered_items.get(capability_id)
        gallery_item = _select_gallery_item(capability_id, gallery_items)
        if rendered_item is None and gallery_item is None:
            missing.append(capability_id)
        cards.append(
            _card(
                capability_id,
                proof_case,
                capability,
                rendered_item,
                gallery_item,
                compatibility.get(capability_id),
            )
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        _page("\n".join(cards), missing),
        encoding="utf-8",
    )
    return output_path


def _page(cards: str, missing: list[str]) -> str:
    missing_note = (
        "Missing rendered and gallery PNGs: "
        + ", ".join(html.escape(item) for item in missing)
        if missing
        else "All selected capabilities have a cosmetics-rendered PNG or gallery fallback."
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Chart Question PNG Review</title>
  <style>
    :root {{
      --ink: #1f2933;
      --muted: #667085;
      --line: #d9dee7;
      --panel: #f7f8fa;
      --accent: #0f766e;
      --warn: #b54708;
    }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: #ffffff;
    }}
    header {{
      padding: 28px 32px 18px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 28px;
      line-height: 1.15;
      letter-spacing: 0;
    }}
    .intro {{
      margin: 0;
      max-width: 1040px;
      color: var(--muted);
      font-size: 15px;
      line-height: 1.45;
    }}
    main {{
      padding: 24px 32px 48px;
    }}
    .card {{
      border: 1px solid var(--line);
      border-radius: 8px;
      margin: 0 0 24px;
      overflow: hidden;
      background: #ffffff;
    }}
    .cardHeader {{
      display: flex;
      gap: 16px;
      align-items: flex-start;
      justify-content: space-between;
      padding: 18px 20px;
      border-bottom: 1px solid var(--line);
      background: #fbfcfd;
    }}
    .capability {{
      margin: 0 0 6px;
      font-size: 12px;
      color: var(--accent);
      font-weight: 700;
      text-transform: uppercase;
    }}
    h2 {{
      margin: 0;
      font-size: 20px;
      line-height: 1.25;
      letter-spacing: 0;
    }}
    .verdict {{
      white-space: nowrap;
      border: 1px solid #a7d8d1;
      color: #075e56;
      background: #e8f6f4;
      border-radius: 999px;
      padding: 5px 9px;
      font-size: 12px;
      font-weight: 700;
    }}
    .grid {{
      display: grid;
      grid-template-columns: minmax(420px, 1.3fr) minmax(320px, 0.7fr);
      gap: 20px;
      padding: 20px;
    }}
    img {{
      display: block;
      width: 100%;
      height: auto;
      border: 1px solid var(--line);
      background: #fff;
    }}
    .imageNote {{
      color: var(--muted);
      font-size: 12px;
      line-height: 1.35;
      margin: 8px 0 0;
    }}
    .details {{
      min-width: 0;
    }}
    dl {{
      margin: 0 0 16px;
    }}
    dt {{
      font-size: 12px;
      color: var(--muted);
      font-weight: 700;
      margin-top: 10px;
    }}
    dd {{
      margin: 3px 0 0;
      line-height: 1.4;
    }}
    h3 {{
      font-size: 14px;
      margin: 16px 0 8px;
      letter-spacing: 0;
    }}
    h4 {{
      font-size: 13px;
      margin: 12px 0 6px;
      letter-spacing: 0;
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
      padding: 6px 4px;
    }}
    th {{
      width: 34%;
      color: var(--muted);
      font-weight: 700;
    }}
    code, pre {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
    }}
    pre {{
      overflow: auto;
      background: #f3f5f7;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px;
      line-height: 1.35;
    }}
    .compat {{
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px;
      background: #fbfcfd;
    }}
    .compat p {{
      margin: 0;
      line-height: 1.45;
    }}
    .muted {{
      color: var(--muted);
      font-size: 12px;
    }}
    .missing {{
      padding: 24px;
      border: 1px solid var(--line);
      background: #fff7ed;
      color: var(--warn);
      font-weight: 700;
    }}
    footer {{
      padding: 16px 32px 28px;
      color: var(--muted);
      border-top: 1px solid var(--line);
      font-size: 13px;
    }}
    @media (max-width: 960px) {{
      header, main, footer {{
        padding-left: 16px;
        padding-right: 16px;
      }}
      .grid {{
        grid-template-columns: 1fr;
        padding: 16px;
      }}
      .cardHeader {{
        flex-direction: column;
      }}
      .verdict {{
        white-space: normal;
      }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Chart Question PNG Review</h1>
    <p class="intro">Each card pairs a plain-English analytical question from the adversarial proof with the manifest-selected chart, the parameters the caller would need to pass, dataset compatibility evidence, and a PNG rendered from the cosmetics dataset where available.</p>
  </header>
  <main>
    {cards}
  </main>
  <footer>{missing_note}</footer>
</body>
</html>
"""


def main() -> int:
    path = build_chart_question_png_review()
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
