"""Readable views of native Plan CSVs; no calculation or source mutation."""

from __future__ import annotations

import csv
import html
import io


def _esc(value):
    return html.escape(str(value), quote=True)


def _number(value, language):
    raw = str(value or "")
    # Format native decimal strings without changing precision or rounding.
    sign = raw[:1] if raw[:1] in "+-" else ""
    unsigned = raw[len(sign) :]
    whole, dot, fraction = unsigned.partition(".")
    if not whole.isdigit() or (dot and not fraction.isdigit()):
        return _esc(raw)
    decimal, separator = (
        (".", ",")
        if language == "en"
        else (",", "." if language in {"it", "de", "es"} else "\u202f")
    )
    grouped = f"{int(whole):,}".replace(",", separator)
    return _esc(sign + grouped + (decimal + fraction if dot else ""))


def sales_plan_body(name: str, text: str, ui: dict, language: str) -> str:
    rows = list(csv.DictReader(io.StringIO(text)))
    labels = ui["sales_plan"]
    metrics = labels["metrics"]
    blocks = []
    if name == "scenario_summary.csv":
        groups = {}
        for row in rows:
            key = (row["summary_level"], row["dimension_name"], row["dimension_value"])
            groups.setdefault(key, []).append(row)
        for (level, dimension, value), members in sorted(
            groups.items(), key=lambda item: item[0][0] != "total"
        ):
            title = (
                labels["total"]
                if level == "total"
                else labels.get(dimension, dimension) + ": " + value
            )
            heads = [
                labels[k]
                for k in ["metric", "unit", "actual", "plan", "delta", "percent"]
            ]
            body = []
            for row in members:
                values = [
                    _esc(metrics.get(row["metric"], row["metric"])),
                    _esc(labels.get(row["unit"], row["unit"])),
                ]
                values.extend(
                    _number(row[k], language)
                    for k in ["actual", "plan", "delta", "delta_pct_rounded_4dp"]
                )
                body.append("<tr>" + "".join(f"<td>{v}</td>" for v in values) + "</tr>")
            blocks.append(f"<h3>{_esc(title)}</h3>" + _table(heads, body))
    else:
        groups = {}
        for row in rows:
            groups.setdefault(row["assumption_id"], []).append(row)
        for assumption, members in groups.items():
            heads = [
                labels[k]
                for k in [
                    "source",
                    "period",
                    "driver",
                    "before",
                    "after",
                    "percent",
                    "status",
                ]
            ]
            body = []
            for row in members:
                values = [
                    _esc(row["source_row_id"]),
                    _esc(row["target_period"]),
                    _esc(metrics.get(row["driver"], row["driver"])),
                ]
                values.extend(
                    _number(row[k], language)
                    for k in ["before_value", "after_value", "change_pct"]
                )
                values.append(_esc(labels.get(row["status"], row["status"])))
                body.append("<tr>" + "".join(f"<td>{v}</td>" for v in values) + "</tr>")
            blocks.append(
                f"<h3>{_esc(labels['assumption'])}: {_esc(assumption)}</h3>"
                + _table(heads, body)
            )
    return "".join(blocks)


def _table(heads, body):
    return (
        "<div class='table-scroll' tabindex='0'><table><thead><tr>"
        + "".join(f"<th scope='col'>{_esc(h)}</th>" for h in heads)
        + "</tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table></div>"
    )
