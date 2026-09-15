"""Host-authored delivery capture for the reviewed fictional Sales Plan case.

This lives outside the shipped kits. It formats actual native results; the
live host still interprets the user's request and writes its own explanation.
"""

from __future__ import annotations

import csv
import json
import re
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote, unquote

__all__ = ["assumption_readback", "deliver_plan", "validate_links"]

ROOT = Path(__file__).resolve().parents[2]


def _words(language):
    return json.loads(
        (ROOT / "tests/fixtures/teaching_reviews/sales_plan.json").read_text(
            encoding="utf-8"
        )
    )[language]


def _link(label, path):
    return f"[{label}]({quote(str(path), safe='/:')})"


def _number(value, language):
    """Format a native value without changing its exact magnitude."""
    number = Decimal(value)
    rendered = f"{number:,.2f}"
    if language == "en":
        return rendered
    thousands = "\u202f" if language == "fr" else "."
    return (
        rendered.replace(",", "THOUSANDS")
        .replace(".", ",")
        .replace("THOUSANDS", thousands)
    )


def _table(headers, rows):
    lines = [
        "| " + " | ".join(headers) + " |",
        "| :--- | " + " | ".join("---:" for _ in headers[1:]) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def assumption_readback(output, source, request, language, growth):
    """Write the ordinary read-back before the synthetic review receipt exists."""
    words = _words(language)
    document = output / "assumption_readback.md"
    # These are this fixture's confirmed source members, not a scope inference.
    readback = _table(
        [words["metric"], words["delta_pct"], words["products"]],
        [[words["metrics"]["units"], f"+{growth}%", "Urban bicycle; Trekking bicycle"]],
    )
    document.write_text(
        "\n\n".join(
            [
                f"# {words['readback_title']}",
                words["readback"].format(growth=growth),
                readback,
                words["rules"],
                words["confirmation"],
                _link(words["input"], source),
                _link(words["request"], request),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return document


def deliver_plan(plan, language, growth, detail_path, prior_plan=None):
    """Capture a normal artifact card using the current pipeline's own outputs."""
    words = _words(language)
    with (plan / "scenario_summary.csv").open(encoding="utf-8", newline="") as stream:
        totals = {
            row["metric"]: row
            for row in csv.DictReader(stream)
            if row["summary_level"] == "total"
        }
    reconciliation = json.loads((plan / "reconciliation.json").read_text())
    assert reconciliation["status"] == "passed"
    assert not reconciliation["errors"] and not reconciliation["warnings"]
    assert reconciliation["report_ready"] is False
    table = _table(
        [words[key] for key in ["metric", "actual", "plan", "delta", "delta_pct"]],
        [
            [words["metrics"][metric]]
            + [
                _number(totals[metric][key], language)
                for key in ["actual", "plan", "delta"]
            ]
            + [totals[metric]["delta_pct_rounded_4dp"] + "%"]
            for metric in words["metrics"]
        ],
    )
    parts = [
        f"# {words['title']}",
        words["readback"].format(growth=growth),
        words["status"],
        f"## {words['summary']}",
        table,
        words["meaning"],
    ]
    if prior_plan is not None:
        with (prior_plan / "scenario_summary.csv").open(
            encoding="utf-8", newline=""
        ) as stream:
            previous = {
                row["metric"]: row
                for row in csv.DictReader(stream)
                if row["summary_level"] == "total"
            }
        comparison = []
        for metric in ["net_sales_reporting", "gross_margin_reporting"]:
            before, after = Decimal(previous[metric]["plan"]), Decimal(
                totals[metric]["plan"]
            )
            comparison.append(
                [
                    words["metrics"][metric],
                    _number(before, language),
                    _number(after, language),
                    _number(after - before, language),
                    _number((after - before) / before * 100, language) + "%",
                ]
            )
        parts.extend(
            [
                f"## {words['comparison']}",
                words["practice"],
                _table(
                    [
                        words[key]
                        for key in ["metric", "prior", "current", "delta", "delta_pct"]
                    ],
                    comparison,
                ),
                _link(words["previous_link"], prior_plan.parent / "artifact_card.md"),
            ]
        )
    detail = json.loads(detail_path.read_text())
    traced = {row["scenario"]: row for row in detail["rows"]}
    trace_rows = []
    for metric in words["metrics"]:
        before, after = Decimal(traced["AC"][metric]), Decimal(traced["PL"][metric])
        trace_rows.append(
            [
                words["metrics"][metric],
                _number(before, language),
                _number(after, language),
                _number(after - before, language),
                _number((after - before) / before * 100, language) + "%",
            ]
        )
    parts.extend(
        [
            f"## {words['trace_title']}",
            words["trace"],
            _table(
                [
                    words[key]
                    for key in [
                        "metric",
                        "trace_actual",
                        "trace_plan",
                        "delta",
                        "delta_pct",
                    ]
                ],
                trace_rows,
            ),
            _link(words["detail_link"], detail_path),
            _link(
                words["purposes"]["assumption_application_ledger.csv"],
                plan / "assumption_application_ledger.csv",
            ),
            f"## {words['files']}",
            "\n".join(
                f"- {_link(label, plan / name)}"
                for name, label in words["purposes"].items()
            ),
            _link(words["readback_link"], plan.parent / "assumption_readback.md"),
            _link(words["review_link"], plan.parent / "codex_run_review.md"),
            _link(words["privacy_link"], plan.parent / "model_data_report.md"),
            words["next"],
        ]
    )
    (plan.parent / "artifact_card.md").write_text(
        "\n\n".join(parts) + "\n", encoding="utf-8"
    )
    (plan.parent / "codex_run_review.md").write_text(
        f"# {words['review_link']}\n\n{words['review']}\n\n"
        f"{_link(words['purposes']['reconciliation.json'], plan / 'reconciliation.json')}\n\n"
        f"{_link(words['detail_link'], detail_path)}\n",
        encoding="utf-8",
    )


def validate_links(output):
    """Check delivery links after the normal data report has been finalized."""
    for name in ["artifact_card.md", "assumption_readback.md", "codex_run_review.md"]:
        document = output / name
        targets = re.findall(r"\]\(([^)]+)\)", document.read_text(encoding="utf-8"))
        assert targets
        assert all((output / unquote(target)).is_file() for target in targets), document
