"""Render current planning questions and funding assessments in the shared report."""

from __future__ import annotations

import html
from typing import Any, Callable

from planning_financing import FINANCING_SECTIONS
from planning_presentation import label, language

__all__ = ["render_cycle", "render_financing"]


def render_cycle(plan: dict[str, Any], paragraph: Callable[[str], str]) -> str:
    """Show the current question, outcome and next test; keep exact deltas inspectable."""
    case = plan["case"]
    cycle = case.get("cycle")
    if cycle is None or plan["status"] == "blocked":
        return ""
    tr = lambda text: label(text, language(case))
    e = html.escape
    parts = [
        f'<section id="planning-cycle"><h2>{tr("Current planning question")}</h2>',
        f'<p class="lead">{e(cycle["question"])}</p>',
    ]
    for key, heading in (
        ("analysis_ids", "What we learned"),
        ("decision_ids", "Decision in this round"),
        ("next_test_ids", "Next test or action"),
        ("reopen_when_ids", "When to revisit"),
    ):
        parts.append(f"<h3>{tr(heading)}</h3>")
        parts.extend(paragraph(i) for i in cycle[key])
    revision = plan["planning_cycle"]
    parts.append(
        f'<details class="planning-history"><summary>{tr("Planning history and input changes")}</summary>'
    )
    for item in revision["history"]:
        parts.append(f'<p>{e(item["id"])}: {e(item["question"])}</p>')
    for change in revision["changes"]:
        parts.append(f'<h4>{e(change["field"])}</h4>')
        # Exact changes are workpapers, not independent financial claims.
        import json

        parts.append(
            f"<pre>{e(json.dumps(change, ensure_ascii=False, indent=2))}</pre>"
        )
    parts.append("</details></section>")
    return "".join(parts)


def render_financing(plan: dict[str, Any], paragraph: Callable[[str], str]) -> str:
    """Present model reasoning separately from mechanical request completeness."""
    case = plan["case"]
    if plan["status"] == "blocked" or not case.get("financing", {}).get("assessments"):
        return ""
    tr = lambda text: label(text, language(case))
    e = html.escape
    results = {r["id"]: r for r in plan["financing_assessments"]}
    parts = [
        f'<section id="financing-assessment"><h2>{tr("Financing assessment")}</h2>'
    ]
    for assessment in case["financing"]["assessments"]:
        result = results[assessment["id"]]
        instrument = assessment["instrument"]
        heading = "Bank debt" if instrument == "bank_debt" else "Venture equity"
        parts.append(
            f'<h3>{tr(heading)} · {e(assessment["provider"] or tr("Provider not yet selected"))}</h3>'
        )
        parts.extend(paragraph(i) for i in assessment["request_ids"])
        conclusion = assessment["conclusion"]
        if not result["conclusion_available"] or (
            conclusion == "prepare_request"
            and (
                not result["request_ready"]
                or plan["status"] != "ready_for_professional_review"
            )
        ):
            parts.append(
                f'<p class="status">{tr("Financing conclusion pending evidence and review")}</p>'
            )
        else:
            headings = {
                "explore": "Explore financing",
                "prepare_request": "Prepare the request",
                "revise_request": "Revise the request",
                "not_suitable": "Requested financing is not suitable",
            }
            parts.append(f"<h4>{tr(headings[conclusion])}</h4>")
        parts.extend(paragraph(i) for i in assessment["rationale_ids"])
        for key, title in FINANCING_SECTIONS[instrument].items():
            parts.append(f"<h4>{tr(title)}</h4>")
            parts.extend(paragraph(i) for i in assessment["sections"][key])
        if not result["coverage_complete"]:
            parts.append(
                f'<p class="limitation">{tr("The forecast does not yet cover the stated repayment or funding milestone.")}</p>'
            )
        parts.append(
            f'<p class="limitation">{tr("This assessment does not establish lender or investor approval.")}</p>'
        )
    parts.append("</section>")
    return "".join(parts)
