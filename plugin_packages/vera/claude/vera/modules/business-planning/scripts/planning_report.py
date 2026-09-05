"""Compile reviewable HTML from canonical numbers and typed reviewed narrative.

Exact claim/chart binding and explicit audience permissions are mechanical
contracts. Semantic accuracy, implied numeric claims and materiality still need
model-led interpretation and a named professional's review.
"""

from __future__ import annotations

import csv
import hashlib
import html
import json
import math
import re
from pathlib import Path
from typing import Any

from planning_workflow import (
    PlanningError,
    digest,
    number,
    require,
    reviewed,
    validate_plan,
)

__all__ = [
    "review_narrative",
    "build_charts",
    "compile_html",
    "write_package",
    "export_pdf",
]


def review_narrative(
    case: dict[str, Any], calculations: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Resolve typed financial claims; reject stale amounts and unsupported rubrics."""
    refs = {r["id"]: r for r in [*case["evidence"], *case["assumptions"]]}
    accepted: list[dict[str, Any]] = []
    issues: list[str] = []
    for entry in case["narrative"]:
        prefix = f"Narrative {entry['id']}"
        require(
            set(entry)
            == {
                "id",
                "kind",
                "text",
                "claims",
                "basis_ids",
                "rubric_id",
                "review",
            },
            "Unexpected narrative fields",
        )
        require(
            entry["kind"]
            in {
                "finding",
                "option",
                "risk",
                "limitation",
                "initiative",
                "capital_recommendation",
                "score",
                "benchmark",
                "kpi",
            },
            "Unknown narrative kind",
        )
        errors = []
        provisional = not reviewed(entry["review"])
        if provisional:
            issues.append(f"{prefix}: requires professional review")
        if not entry["basis_ids"] or not set(entry["basis_ids"]) <= set(refs):
            if entry["basis_ids"] or entry["kind"] != "limitation":
                errors.append("missing evidence/assumption basis")
        for rid in entry["basis_ids"]:
            if rid in refs and not reviewed(refs[rid]):
                provisional = True
                issues.append(f"{prefix}: unconfirmed narrative basis")
        tokens = re.findall(r"\{\{([a-z][a-z0-9_-]*)\}\}", entry["text"])
        claims = entry["claims"]
        if set(tokens) != set(claims):
            errors.append("claim placeholders do not match declared claims")
        prose = re.sub(r"\{\{[a-z][a-z0-9_-]*\}\}", "", entry["text"])
        if any(ch.isnumeric() for ch in prose) or "{{" in prose or "}}" in prose:
            errors.append("numeric literals must use typed claim placeholders")
        for claim in claims.values():
            if set(claim) == {"evidence_id", "value"}:
                evidence = refs.get(claim["evidence_id"])
                if evidence is None or claim["evidence_id"] not in entry["basis_ids"]:
                    errors.append("unknown source claim basis")
                elif evidence.get("value") != claim["value"] or not evidence.get(
                    "unit"
                ):
                    errors.append(
                        "source claim disagrees with evidence value or lacks units"
                    )
                elif evidence.get("claim_type") != "external_fact":
                    errors.append(
                        "source claims require an external_fact; modeled finances need calculation IDs"
                    )
                continue
            if set(claim) != {"calculation_id", "value"}:
                errors.append("invalid claim fields")
                continue
            calc = calculations.get(claim["calculation_id"])
            if calc is None or calc["value"] is None:
                errors.append(
                    "financial claim awaits an available authoritative calculation"
                )
            elif calc["value"] != claim["value"]:
                errors.append(
                    "financial number disagrees with authoritative calculation"
                )
            elif calc["metric"].startswith("reported_ebitda_"):
                errors.append(
                    "reported source EBITDA cannot replace an authoritative narrative figure"
                )
        if provisional and entry["kind"] in {
            "score",
            "benchmark",
            "kpi",
            "capital_recommendation",
        }:
            errors.append("professional acceptance required for this claim")
        if entry["kind"] in {"score", "benchmark", "kpi"}:
            rubric = refs.get(entry["rubric_id"])
            if rubric is None or not reviewed(rubric) or not rubric.get("rubric"):
                errors.append(
                    "reviewed rubric or labelled professional hypothesis required"
                )
        elif entry["rubric_id"] is not None:
            errors.append("rubric supplied to non-rubric narrative")
        if entry["kind"] == "capital_recommendation":
            # Amount must be the last period's full-horizon accepted funding gap.
            valid_claims = [
                calculations.get(c["calculation_id"])
                for c in claims.values()
                if "calculation_id" in c
            ]
            if (
                not valid_claims
                or any(
                    c is None
                    or c["metric"] != "funding_requirement"
                    or c["period"] != case["periods"][-1]
                    for c in valid_claims
                )
                or not reviewed(case["review"])
            ):
                errors.append(
                    "capital recommendation requires complete accepted funding model"
                )
        if errors:
            issues.extend(f"{prefix}: {message}" for message in errors)
        else:
            accepted.append({**entry, "provisional": provisional})
    return accepted, issues


def build_charts(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Declare chart series exclusively as authoritative calculation ID vectors."""
    if not plan["calculations"] or plan["statements"] is None:
        return []
    case = plan["case"]
    scenarios = plan["statements"]["scenarios"]
    charts = []

    def add(
        identifier: str,
        title: str,
        series: list[tuple[str, list[str]]],
        kind: str = "line",
    ) -> None:
        charts.append(
            {
                "id": identifier,
                "title": title,
                "kind": kind,
                "x_axis": "Month",
                "y_axis": case["reporting_currency"],
                "unit": case["reporting_currency"],
                "periods": case["periods"],
                "zero_line": True,
                "series": [
                    {
                        "label": label,
                        "points": [
                            {
                                "calculation_id": cid,
                                "value": plan["calculations"][cid]["value"],
                                "period": plan["calculations"][cid]["period"],
                                "scenario": plan["calculations"][cid]["scenario"],
                            }
                            for cid in ids
                        ],
                    }
                    for label, ids in series
                ],
            }
        )

    add(
        "ebitda-scenarios",
        "EBITDA by scenario",
        [
            (s["label"], [f"{s['id']}/{p}/ebitda" for p in case["periods"]])
            for s in scenarios
        ],
    )
    for scenario in scenarios:
        sid = scenario["id"]
        add(
            f"cash-{sid}",
            f"Monthly cash · {scenario['label']}",
            [
                (label, [f"{sid}/{p}/{metric}" for p in case["periods"]])
                for label, metric in (
                    ("Before new financing", "cash_before_financing"),
                    ("After scheduled financing", "ending_cash"),
                )
            ],
        )
        add(
            f"funding-{sid}",
            f"Cumulative funding gap · {scenario['label']}",
            [
                (label, [f"{sid}/{p}/{metric}" for p in case["periods"]])
                for label, metric in (
                    ("Required before financing", "funding_requirement"),
                    ("Remaining gap", "residual_funding_gap"),
                )
            ],
            "bar",
        )
        month = case["periods"][-1]
        movements = (
            "opening_cash",
            "operating_cash_flow",
            "capital_expenditure",
            "debt_draws",
            "debt_repayments",
            "equity_contributions",
            "dividends",
            "ending_cash",
        )
        add(
            f"sources-uses-{sid}",
            f"Sources and uses · {scenario['label']} · {month}",
            [
                (metric.replace("_", " "), [f"{sid}/{month}/{metric}"])
                for metric in movements
            ],
            "waterfall",
        )
        charts[-1]["x_axis"] = "Cash movement"
        reported = [
            c
            for c in plan["calculations"].values()
            if c["scenario"] == sid and c["metric"].startswith("reported_ebitda_")
        ]
        if reported:
            add(
                f"reported-adjusted-{sid}",
                f"Reported versus adjusted EBITDA · {scenario['label']}",
                [(c["metric"].replace("_", " "), [c["id"]]) for c in reported]
                + [
                    (
                        "Accepted model EBITDA",
                        [f"{sid}/{p}/ebitda" for p in case["periods"]],
                    )
                ],
                "bar",
            )
    channel_groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for channel in case["financial"].get("channels", []):
        channel_groups.setdefault((channel["scenario"], channel["period"]), []).append(
            channel
        )
    for (sid, period), channels in channel_groups.items():
        supported = [
            c
            for c in channels
            if plan["calculations"][
                f"{sid}/{period}/channel_{c['id']}_contribution_per_unit"
            ]["value"]
            is not None
        ]
        if not supported:
            continue
        add(
            f"unit-economics-{sid}-{period}",
            f"Channel contribution per unit · {sid} · {period}",
            [
                (
                    c["channel"],
                    [f"{sid}/{period}/channel_{c['id']}_contribution_per_unit"],
                )
                for c in supported
            ],
            "bar",
        )
        chart = charts[-1]
        chart["x_axis"] = "Channel"
        chart["x_labels"] = [c["channel"] for c in supported]
        chart["unit"] = chart["y_axis"] = (
            f"{case['reporting_currency']}/{supported[0]['unit_label']}"
        )
        for series in chart["series"]:
            series["points"][0]["x"] = series["label"]
    return charts


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    def cell(value: Any) -> str:
        return html.escape(
            json.dumps(value, ensure_ascii=False)
            if isinstance(value, (dict, list))
            else str(value)
        )

    return (
        '<div class="table-scroll"><table><thead><tr>'
        + "".join(f"<th>{cell(h)}</th>" for h in headers)
        + "</tr></thead><tbody>"
        + "".join(
            "<tr>" + "".join(f"<td>{cell(v)}</td>" for v in row) + "</tr>"
            for row in rows
        )
        + "</tbody></table></div>"
    )


def _svg(chart: dict[str, Any]) -> str:
    if chart["kind"] == "waterfall":
        return _waterfall(chart)
    points = [p for s in chart["series"] for p in s["points"]]
    values = [float(number(p["value"])) for p in points]
    lo, hi = min([0.0, *values]), max([0.0, *values])
    if hi == lo:
        hi = lo + 1
    # Readable axis ticks, not a financial threshold or benchmark.
    magnitude = 10 ** math.floor(math.log10((hi - lo) / 4))
    step = next(s * magnitude for s in (1, 2, 5, 10) if s * magnitude >= (hi - lo) / 4)
    lo = math.floor(lo / step) * step
    hi = math.ceil(hi / step) * step

    def y(value: float) -> float:
        return 270 - (value - lo) / (hi - lo) * 230

    def x(period: str) -> float:
        labels = chart.get("x_labels", chart["periods"])
        return 100 + labels.index(period) * (650 / max(1, len(labels) - 1))

    palette = [
        "#123d65",
        "#16829a",
        "#a15335",
        "#6a5485",
        "#556d40",
        "#9b4871",
        "#67634a",
        "#3e6870",
    ]
    e = html.escape
    svg = [
        f'<svg viewBox="0 0 840 330" role="img" aria-label="{e(chart["title"])}"><title>{e(chart["title"])}</title>'
    ]
    for i in range(round((hi - lo) / step) + 1):
        tick = lo + step * i
        svg.append(
            f'<line x1="80" x2="780" y1="{y(tick):.2f}" y2="{y(tick):.2f}" stroke="#e4e8eb"/><text x="70" y="{y(tick)+4:.2f}" text-anchor="end">{tick:,.0f}</text>'
        )
    svg.append(
        f'<line class="zero-line" x1="80" x2="780" y1="{y(0):.2f}" y2="{y(0):.2f}" stroke="#667681" stroke-dasharray="5 4"/>'
    )
    x_labels = chart.get("x_labels", chart["periods"])
    stride = max(1, (len(x_labels) + 7) // 8)
    for p in x_labels[::stride]:
        svg.append(f'<text x="{x(p):.2f}" y="295" text-anchor="middle">{e(p)}</text>')
    for i, series in enumerate(chart["series"]):
        color = palette[i % len(palette)]
        coords = " ".join(
            f'{x(p.get("x", p["period"])):.2f},{y(float(number(p["value"]))):.2f}'
            for p in series["points"]
        )
        if chart["kind"] == "line":
            svg.append(
                f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="2.5"/>'
            )
        for p in series["points"]:
            px, py = x(p.get("x", p["period"])), y(float(number(p["value"])))
            title = e(
                f'{series["label"]}: {p["value"]} {chart["unit"]} · {p["scenario"]} · {p["period"]} · {p["calculation_id"]}'
            )
            svg.append(
                f'<g data-calculation-id="{e(p["calculation_id"])}"><title>{title}</title>'
            )
            if chart["kind"] == "bar":
                width = min(24, 500 / (len(chart["periods"]) * len(chart["series"])))
                offset = (
                    0
                    if "x_labels" in chart
                    else (i - (len(chart["series"]) - 1) / 2) * width
                )
                svg.append(
                    f'<rect x="{px+offset-width/2:.2f}" y="{min(py,y(0)):.2f}" width="{width:.2f}" height="{max(.5,abs(py-y(0))):.2f}" fill="{color}"/>'
                )
            else:
                svg.append(
                    f'<circle cx="{px:.2f}" cy="{py:.2f}" r="4" fill="{color}"/>'
                )
            svg.append("</g>")
    svg.append(
        f'<text x="80" y="20">{e(chart["y_axis"])}</text><text x="440" y="322" text-anchor="middle">{e(chart["x_axis"])}</text></svg>'
    )
    legend = "".join(
        f'<span><i style="background:{palette[i % len(palette)]}"></i>{e(s["label"])}</span>'
        for i, s in enumerate(chart["series"])
    )
    data = _table(
        ["Series", "Scenario", "Month", chart["unit"], "Calculation ID"],
        [
            [s["label"], p["scenario"], p["period"], p["value"], p["calculation_id"]]
            for s in chart["series"]
            for p in s["points"]
        ],
    )
    return f'<figure id="{e(chart["id"])}"><h3>{e(chart["title"])}</h3>{"".join(svg)}<figcaption>{legend}</figcaption><details><summary>Chart data and calculation lineage</summary>{data}</details></figure>'


def _waterfall(chart: dict[str, Any]) -> str:
    """Draw a signed cash reconciliation, retaining original calculation IDs."""
    e = html.escape
    levels, cumulative = [], number("0")
    for index, series in enumerate(chart["series"]):
        point = series["points"][0]
        value = number(point["value"])
        total = index in {0, len(chart["series"]) - 1}
        start = number("0") if total else cumulative
        end = value if total else cumulative + value
        cumulative = end
        levels.append((series["label"], point, float(start), float(end), total))
    lo = min(0, *(min(r[2], r[3]) for r in levels))
    hi = max(0, *(max(r[2], r[3]) for r in levels))
    span = max(1, hi - lo)

    def y(value: float) -> float:
        return 260 - (value - lo + span * 0.1) / (span * 1.2) * 220

    parts = [
        f'<svg viewBox="0 0 840 345" role="img" aria-label="{e(chart["title"])}"><title>{e(chart["title"])}</title>'
    ]
    for tick in (lo, (lo + hi) / 2, hi):
        parts.append(
            f'<text x="65" y="{y(tick):.2f}" text-anchor="end">{tick:,.0f}</text>'
        )
    parts.append(
        f'<line class="zero-line" x1="80" x2="825" y1="{y(0):.2f}" y2="{y(0):.2f}" stroke="#667681" stroke-dasharray="5 4"/>'
    )
    for index, (label, point, bar_start, bar_end, total) in enumerate(levels):
        x = 95 + index * 92
        color = "#123d65" if total else "#16829a" if bar_end >= bar_start else "#a15335"
        parts.append(
            f'<g data-calculation-id="{e(point["calculation_id"])}"><title>{e(label)}: {e(point["value"])} {e(chart["unit"])} · {e(point["calculation_id"])}</title><rect x="{x}" y="{min(y(bar_start), y(bar_end)):.2f}" width="58" height="{max(.5,abs(y(bar_start)-y(bar_end))):.2f}" fill="{color}"/></g>'
        )
        for j, word in enumerate(label.split()):
            parts.append(
                f'<text x="{x+29}" y="{282+j*13}" text-anchor="middle">{e(word)}</text>'
            )
    parts.append(
        f'<text x="80" y="20">{e(chart["y_axis"])}</text><text x="440" y="339" text-anchor="middle">Cash movement</text></svg>'
    )
    table = _table(
        ["Movement", "Scenario", "Month", chart["unit"], "Calculation ID"],
        [
            [label, p["scenario"], p["period"], p["value"], p["calculation_id"]]
            for label, p, *_ in levels
        ],
    )
    return f'<figure id="{e(chart["id"])}"><h3>{e(chart["title"])}</h3>{"".join(parts)}<figcaption>Opening and closing cash are totals; intervening bars are signed cash movements.</figcaption><details><summary>Chart data and calculation lineage</summary>{table}</details></figure>'


def _check_audience(case: dict[str, Any]) -> None:
    for source in case["sources"]:
        allowed = source["confidentiality"]["allowed_audiences"]
        if (
            case["audience"] in allowed
            and case["audience"] in source["intended_audience"]
            and (
                source["confidentiality"]["classification"] != "internal_only"
                or case["audience"] == "internal"
            )
        ):
            continue
        decisions = [
            d
            for d in case["decisions"]
            if d.get("kind") == "audience_release"
            and source["id"] in d.get("source_ids", [])
            and d.get("audience") == case["audience"]
            and d.get("source_sha256") == source["sha256"]
            and reviewed(d)
        ]
        require(
            bool(decisions),
            f"Audience restriction: source {source['id']} requires an explicit reviewed audience decision",
        )


def compile_html(plan: dict[str, Any], *, source_root: Path) -> str:
    """Revalidate inputs and outputs before compiling the sole report structure."""
    validate_plan(plan, source_root=source_root)
    case = plan["case"]
    _check_audience(case)
    e = html.escape
    from planning_assessment import SECTIONS

    narrative = {n["id"]: n for n in plan["accepted_narrative"]}
    refs = {r["id"]: r for r in [*case["evidence"], *case["assumptions"]]}

    rendered_narrative: set[str] = set()

    def paragraph(identifier: str) -> str:
        if identifier in rendered_narrative:
            return ""
        rendered_narrative.add(identifier)
        n = narrative.get(identifier)
        if n is None:
            return '<p class="limitation">This conclusion is withheld pending correction of its supporting claims.</p>'
        prose = e(n["text"])
        for key, claim in n["claims"].items():
            if "calculation_id" in claim:
                c = plan["calculations"][claim["calculation_id"]]
                rendered = f'<a class="figure-ref" href="#calc-{e(c["id"])}" data-calculation-id="{e(c["id"])}">{e(c["value"])} {e(c["unit"])}</a>'
            else:
                r = refs[claim["evidence_id"]]
                rendered = f'<a href="#evidence-{e(r["id"])}" data-evidence-id="{e(r["id"])}">{e(claim["value"])} {e(r["unit"])}</a>'
            prose = prose.replace("{{" + key + "}}", rendered)
        status = (
            "Provisional interpretation — professional review pending"
            if n["provisional"]
            else "Reviewed interpretation"
        )
        basis = ", ".join(n["basis_ids"]) or "Explicit evidence gap"
        return f'<article id="narrative-{e(identifier)}"><p>{prose}</p><details><summary>Basis and review</summary><p>{e(status)}. {e(basis)}</p></details></article>'

    horizon = (
        f'{e(case["periods"][0])} — {e(case["periods"][-1])}'
        if case["periods"]
        else "Forecast horizon not yet established"
    )
    parts = [
        f'<header><p class="eyebrow">Business plan · Audience: {e(case["audience"])}</p><h1>{e(case["entity_name"])}</h1><p class="lead">{e(case["planning_objective"])}</p><p>{e(case["company_stage"])} · {e(case["reporting_currency"] or "Currency not established")} · {horizon}</p></header>'
    ]
    assessment = case.get("assessment")
    if assessment:
        parts.append(
            f'<section id="recommendation"><h2>Recommendation: {e(assessment["decision"]).capitalize()}</h2>'
        )
        parts.extend(paragraph(i) for i in assessment["recommendation"])
        if plan["status"] != "ready_for_professional_review":
            parts.append(
                '<p class="status">Provisional assessment. Material evidence or review remains open; this is not a finalized business plan.</p>'
            )
        parts.append("<h3>What this judgment depends on</h3>")
        parts.extend(paragraph(i) for i in assessment["depends_on"])
        parts.append("<h3>What would change the recommendation</h3>")
        parts.extend(paragraph(i) for i in assessment["would_change"])
        parts.append("</section>")
        for section, heading in SECTIONS.items():
            parts.append(f'<section id="{section}"><h2>{e(heading)}</h2>')
            parts.extend(paragraph(i) for i in assessment["sections"][section])
            for chart in plan["charts"]:
                if chart["section"] == section:
                    parts.append(_svg(chart))
                    parts.append(paragraph(chart["caption_id"]))
            parts.append("</section>")
    else:
        parts.append(
            "<section><h2>Business assessment incomplete</h2><p>The available calculations and notes do not yet constitute a business plan. A recommendation and the business questions still need to be addressed.</p></section>"
        )
    parts.append("<section><h2>Material uncertainties and limitations</h2><ul>")
    parts.extend(f"<li>{e(i)}</li>" for i in case["limitations"])
    parts.append(
        '</ul></section><details id="supporting-evidence"><summary>Supporting evidence, calculations and review record</summary>'
    )
    parts.append(
        f'<p>Validation status: {e(plan["status"])}. Checks establish internal consistency and file identity, not whether a business is viable.</p>'
    )
    parts.append(
        "<h2>Unresolved matters</h2><ul>"
        + "".join(f"<li>{e(i)}</li>" for i in plan["unresolved_matters"])
        + "</ul>"
    )
    if not assessment:
        parts.extend(paragraph(i) for i in narrative)
        parts.extend(_svg(c) for c in plan["charts"])
    for r in refs.values():
        parts.append(
            f'<p id="evidence-{e(r["id"])}"><strong>{e(r["id"])}</strong>: {e(r["description"])}</p>'
        )
    parts.append("<section><h2>Cross-source figure comparison</h2>")
    for c in plan["comparisons"]:
        parts.append(
            f'<h3>{e(c["calculation_id"])}</h3><p>Accepted observation: {e(str(c["accepted_observation_id"]))} · Material: {c["material"]}</p>'
        )
        parts.append(
            _table(
                ["Observation", "Source", "Value", "Unit", "Basis"],
                [
                    [r["id"], r["source_ids"], r["value"], r["unit"], r["basis"]]
                    for r in c["observations"]
                ],
            )
        )
        parts.append(f'<p>Resolution: {e(json.dumps(c["resolution"]))}</p>')
    parts.append(
        "</section><section><h2>Authoritative calculation register</h2><p>Ratios are fractions; monetary figures use the reporting currency. Minimum cash and funding gaps are cumulative through the stated month.</p>"
    )
    parts.append(
        '<div class="table-scroll"><table><thead><tr><th>Calculation ID</th><th>Value / unit</th><th>Method / limitation</th><th>Basis and sources</th></tr></thead><tbody>'
    )
    for c in plan["calculations"].values():
        parts.append(
            f'<tr id="calc-{e(c["id"])}"><td>{e(c["id"])}</td><td>{e(c["value"] if c["value"] is not None else "Unavailable")} {e(c["unit"])}</td><td>{e(c["formula"])} {e(c["unavailable_reason"] or "")}</td><td>{e(", ".join(c["basis_ids"]))}<br>{e(", ".join(c["source_ids"]))}</td></tr>'
        )
    parts.append(
        "</tbody></table></div></section><section><h2>Input and provenance manifest</h2>"
    )
    parts.append(
        _table(
            [
                "ID / file",
                "SHA-256 / version",
                "Role / review",
                "Intended audience",
                "Confidentiality",
            ],
            [
                [
                    s["id"] + " / " + s["path"],
                    s["sha256"] + " / " + s["version"],
                    s["role"] + " / " + s["review_status"],
                    s["intended_audience"],
                    s["confidentiality"],
                ]
                for s in case["sources"]
            ],
        )
    )
    parts.append("</section>")
    for title, key in (
        ("Facts and evidence", "evidence"),
        ("Assumptions and labelled hypotheses", "assumptions"),
        ("Professional decisions", "decisions"),
    ):
        parts.append(
            f"<section><h2>{title}</h2>"
            + _table(["ID", "Reviewed record"], [[r["id"], r] for r in case[key]])
            + "</section>"
        )
    parts.append(
        "<section><h2>Financial inputs and reconciliation</h2><details><summary>Opening balances, schedules and input lineage</summary><pre>"
        + e(json.dumps(case["financial"], indent=2))
        + "</pre></details><pre>"
        + e(
            json.dumps(
                (
                    plan["statements"]["reconciliation"]
                    if plan["statements"]
                    else {"status": "unavailable"}
                ),
                indent=2,
            )
        )
        + "</pre></section>"
    )
    parts.append(
        "<section><h2>Limitations</h2><ul>"
        + "".join(f"<li>{e(s)}</li>" for s in plan["limitations"])
        + "</ul></section>"
    )
    parts.append(
        f'<footer>Case SHA-256: {plan["case_sha256"]}<br>Calculation register SHA-256: {plan["calculations_sha256"]}<br>Validated structure SHA-256: {plan["content_sha256"]}</footer>'
    )
    parts.append("</details>")
    payload = (
        json.dumps(plan, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    style = """body{margin:0;background:#fff;color:#202a33;font:16px/1.6 system-ui,sans-serif}main{max-width:1120px;margin:0 auto;padding:64px 36px}header{border-top:5px solid #123d65;padding-top:24px}h1{font-size:44px;line-height:1.15;letter-spacing:-1.5px;margin:16px 0}h2{font-size:25px;line-height:1.3;margin:0 0 24px;color:#123d65}h3{font-size:18px}.lead{font-size:22px;max-width:760px}.eyebrow{font-size:13px;text-transform:uppercase;letter-spacing:1px;color:#42647d}.status{display:inline-block;border-bottom:2px solid #16829a;padding:4px 0}section{padding:36px 0;border-bottom:1px solid #dce2e6}article{max-width:800px;margin:0 0 28px}figure{margin:28px 0 44px;break-inside:avoid}svg{display:block;width:100%;height:auto}svg text{font:12px system-ui,sans-serif;fill:#50616b}figcaption{display:flex;flex-wrap:wrap;gap:8px 24px;font-size:13px}figcaption i{display:inline-block;width:14px;height:3px;margin-right:8px;vertical-align:middle}table{border-collapse:collapse;width:100%;font-size:12px;text-align:left}th{color:#123d65;background:#f5f7f8}td,th{padding:10px;border-bottom:1px solid #dce2e6;vertical-align:top;overflow-wrap:anywhere}td{min-width:90px}.table-scroll{overflow-x:auto}details{margin:16px 0}summary{cursor:pointer;color:#123d65;font-size:13px}#supporting-evidence>summary{font-size:19px;padding:24px 0}article>details{font-size:12px}article>details>summary{font-size:12px}p{max-width:850px}pre{font-size:11px;white-space:pre-wrap;overflow-wrap:anywhere}a{color:#123d65}footer{padding-top:28px;font-size:11px;overflow-wrap:anywhere}@media(max-width:600px){main{padding:28px 16px}h1{font-size:32px}.lead{font-size:18px}section{padding:28px 0}}@media print{main{padding:0;max-width:none}details>*{display:block!important}table{font-size:9px}.table-scroll{overflow:visible}header{break-after:avoid}h2,h3{break-after:avoid}tr{break-inside:avoid}}"""
    return f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{e(case["entity_name"])} · Business Planning</title><style>{style}</style></head><body><main>{"".join(parts)}</main><script type="application/json" id="validated-plan">{payload}</script></body></html>'


def export_pdf(plan: dict[str, Any], *, source_root: Path, output: Path) -> None:
    """PDF only from a freshly validated HTML structure; optional declared renderer."""
    rendered = compile_html(plan, source_root=source_root)
    require(
        plan["status"] == "ready_for_professional_review",
        "PDF export requires a complete validated report",
    )
    from playwright.sync_api import Error as BrowserError
    from playwright.sync_api import sync_playwright

    with sync_playwright() as runtime:
        try:
            browser = runtime.chromium.launch()
        except BrowserError as exc:
            raise PlanningError(
                "PDF browser could not launch; validated HTML remains available"
            ) from exc
        try:
            page = browser.new_page()
            page.route("**/*", lambda route: route.abort())
            page.set_content(rendered)
            page.locator("details").evaluate_all(
                "items => items.forEach(item => item.open = true)"
            )
            page.pdf(
                path=str(output),
                format="A4",
                print_background=True,
                margin={
                    "top": "15mm",
                    "bottom": "15mm",
                    "left": "12mm",
                    "right": "12mm",
                },
            )
        except BrowserError as exc:
            raise PlanningError(
                "PDF rendering failed; validated HTML remains available"
            ) from exc
        finally:
            browser.close()


def write_package(
    plan: dict[str, Any], *, source_root: Path, output: Path, pdf: bool = False
) -> None:
    """Compile before writing anything; all derived outputs bind the same figures."""
    rendered = compile_html(plan, source_root=source_root)
    output.mkdir(parents=True, exist_ok=True)
    require(
        not any(output.iterdir()),
        "Use a fresh run output folder; existing results must not be overwritten",
    )
    payloads = {
        "business_plan.json": plan,
        "input_manifest.json": plan["case"]["sources"],
        "calculations.json": plan["calculations"],
        "report_structure.json": plan,
        "reconciliation.json": (
            plan["statements"]["reconciliation"]
            if plan["statements"]
            else {"status": "unavailable"}
        ),
        "validation.json": {
            "status": plan["status"],
            "unresolved_matters": plan["unresolved_matters"],
            "canonical_replay": "passed",
        },
    }
    for name, payload in payloads.items():
        (output / name).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    (output / "business_plan_review.html").write_text(rendered, encoding="utf-8")
    with (output / "calculations.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "id",
                "scenario",
                "period",
                "metric",
                "value",
                "unit",
                "formula",
                "basis_ids",
                "source_ids",
                "unavailable_reason",
            ],
        )
        writer.writeheader()
        writer.writerows(plan["calculations"].values())
    pdf_error = None
    if pdf:
        try:
            export_pdf(
                plan, source_root=source_root, output=output / "business_plan.pdf"
            )
        except (PlanningError, ImportError) as exc:
            pdf_error = str(exc)
    receipt = {
        "workflow_id": "business-planning",
        "status": "partial" if pdf_error else plan["status"],
        "pdf_error": pdf_error,
        "case_sha256": plan["case_sha256"],
        "calculations_sha256": plan["calculations_sha256"],
        "outputs": [
            {
                "path": p.name,
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            }
            for p in sorted(output.iterdir())
        ],
    }
    receipt["content_sha256"] = digest(receipt)
    (output / "execution_receipt.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )
    if pdf_error:
        raise PlanningError(pdf_error)
