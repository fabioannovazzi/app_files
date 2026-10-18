"""Auditable usage arithmetic; feedback meaning and diagnosis remain AI-led."""

from __future__ import annotations

import hashlib
import html
import json
import re
from collections import Counter, defaultdict
from typing import Any

from modules.workflow_usage.contracts import pipeline_catalog
from modules.workflow_usage.products import Product, catalog_metadata

__all__ = ["evidence_hash", "summarize", "render_html"]


def evidence_hash(run: dict[str, Any]) -> str:
    """Hash exact retained evidence, excluding subsequent operator commentary."""
    evidence = {
        key: value
        for key, value in run.items()
        if key not in {"review", "feedback_url"}
    }
    return hashlib.sha256(
        json.dumps(
            evidence, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


def _metrics(runs: list[dict[str, Any]]) -> dict[str, Any]:
    owners = Counter(run["installation_id"] for run in runs)
    states = Counter(run["state"] for run in runs)
    ratings = Counter(str(run["feedback"]["stars"]) for run in runs if run["feedback"])
    rated = sum(ratings.values())
    terminal = sum(states[state] for state in ("completed", "failed", "cancelled"))
    return {
        "runs": len(runs),
        "installations": len(owners),
        "repeat_installations": sum(count > 1 for count in owners.values()),
        "completed": states["completed"],
        "failed": states["failed"],
        "cancelled": states["cancelled"],
        "outcome_unknown": states["unknown"],
        "observed_failed_attempts": sum(run["failure_count"] for run in runs),
        "completion_rate": states["completed"] / len(runs) if runs else None,
        "receipt_linked_runs": sum(bool(run["receipts"]) for run in runs),
        "completed_without_receipt": sum(
            run["state"] == "completed" and not run["receipts"] for run in runs
        ),
        "rated_runs": rated,
        "unrated_runs": len(runs) - rated,
        "feedback_offered": sum(run["feedback_prompted"] for run in runs),
        "response_rate_of_terminal_runs": (
            sum(bool(run["feedback"]) and run["state"] != "unknown" for run in runs)
            / terminal
            if terminal
            else None
        ),
        "stars": {str(star): ratings[str(star)] for star in range(1, 6)},
        "average_stars": (
            sum(int(star) * count for star, count in ratings.items()) / rated
            if rated
            else None
        ),
    }


def summarize(
    inventory: dict[str, Any],
    receipts: dict[str, Any] | None = None,
    *,
    product: Product = "vera",
) -> dict[str, Any]:
    """Count exact task IDs; unknown, unrated and synthetic are explicit categories."""
    runs = [run for run in inventory["runs"] if run.get("product", "vera") == product]
    real = [run for run in runs if run["sample_kind"] == "user"]
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    segments: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for run in real:
        groups[run["pipeline"]].append(run)
        segments[(run["pipeline"], run["host"], run["started_version"])].append(run)
    candidates = []
    for run in real:
        answer = run["feedback"]
        reasons = []
        if answer and answer["stars"] <= 2:
            reasons.append("low_rating")
        if answer and answer["comment"]:
            reasons.append("user_comment")
        if run["state"] == "failed":
            reasons.append("observed_failure")
        if run["state"] == "completed" and not run["receipts"]:
            reasons.append("receipt_not_linked")
        if reasons:
            candidates.append(
                {
                    "run_id": run["run_id"],
                    "product": product,
                    "installation_id": run["installation_id"],
                    "pipeline": run["pipeline"],
                    "reasons": reasons,
                    "projection_sha256": evidence_hash(run),
                    "review": run.get("review"),
                    "state": run["state"],
                    "feedback": answer,
                    "incident_report_ids": run["incident_report_ids"],
                }
            )
    linked = {item["receipt_id"] for run in runs for item in run["receipts"]}
    unattributed = [
        item
        for item in (receipts or {}).get("receipts", [])
        if item.get("product", "vera") == product and item["receipt_id"] not in linked
    ]
    metadata = catalog_metadata(product)
    minimum = tuple(
        int(part) for part in metadata["instrumented_from_version"].split(".")
    )
    current_unattributed = []
    for item in unattributed:
        version = re.fullmatch(
            r"(\d+)\.(\d+)\.(\d+)(?:[-+].*)?", item["plugin_version"]
        )
        if version and tuple(map(int, version.groups())) >= minimum:
            current_unattributed.append(item)
    return {
        "product": product,
        "receipt_inventory_complete": receipts["complete"] if receipts else None,
        "unattributed_receipts": current_unattributed,
        "legacy_unattributed_receipt_count": len(unattributed)
        - len(current_unattributed),
        "instrumented_from_version": metadata["instrumented_from_version"],
        "schema_version": 1,
        "inventory_complete": inventory["complete"],
        "inventory_total": inventory["total"],
        "included_user_runs": len(real),
        "excluded_test_runs": len(runs) - len(real),
        "totals": _metrics(real),
        "pipelines": [
            {"pipeline": identifier, "label": label, **_metrics(groups[identifier])}
            for identifier, label in pipeline_catalog(product).items()
        ],
        "segments": [
            {
                "pipeline": key[0],
                "host": key[1],
                "started_version": key[2],
                **_metrics(value),
            }
            for key, value in sorted(segments.items())
        ],
        "review_candidates": candidates,
        "limits": [
            "Installation IDs are not people or inferred computer identities.",
            "An unknown outcome is neither failure nor abandonment.",
            "No rating is not a zero-star rating.",
            "Successful execution, report receipts and satisfaction do not establish professional validation.",
            "Uninstrumented older versions and blocked delivery are not observable usage; zero received runs is not proof of zero use.",
        ],
    }


def render_html(summary: dict[str, Any]) -> str:
    """Render escaped operator evidence; comments remain untrusted text."""
    title = html.escape(summary.get("product", "vera").title())
    rows = []
    for row in summary["pipelines"]:
        average = (
            f'{row["average_stars"]:.2f}' if row["average_stars"] is not None else "—"
        )
        rows.append(
            "<tr>"
            + "".join(
                f"<td>{html.escape(str(value))}</td>"
                for value in (
                    row["label"],
                    row["runs"],
                    row["installations"],
                    row["completed"],
                    row["failed"],
                    row["cancelled"],
                    row["outcome_unknown"],
                    row["receipt_linked_runs"],
                    row["rated_runs"],
                    average,
                )
            )
            + "</tr>"
        )
    reviews = []
    for item in summary["review_candidates"]:
        answer = item["feedback"] or {}
        reviews.append(
            f'<article><h3>{html.escape(item["pipeline"])}</h3><p>{html.escape(item["run_id"])} · {html.escape(item["state"])} · {html.escape(", ".join(item["reasons"]))}</p><blockquote>{html.escape(answer.get("comment") or "Nessun commento")}</blockquote></article>'
        )
    complete = (
        "Inventario completo"
        if summary["inventory_complete"]
        else "Inventario parziale: questi numeri non sono totali"
    )
    document = (
        '<!doctype html><html lang="it"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Vera · Utilizzo e risultati</title><style>body{font-family:Instrument Sans,system-ui,sans-serif;color:#192d49;background:#fff;margin:40px auto;padding:0 24px;max-width:1200px}h1{font-weight:550}table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:10px;text-align:left;border-bottom:1px solid #dde3eb}section{overflow-x:auto}article{border-top:1px solid #dde3eb;padding:16px 0}blockquote{white-space:pre-wrap}p{line-height:1.5}</style><h1>Vera: utilizzo e risultati</h1><p>'
        + html.escape(complete)
        + f' · {summary["included_user_runs"]} attività ricevute · {summary["excluded_test_runs"]} prove escluse.</p><p>Esito sconosciuto e nessuna valutazione restano distinti da errore e insoddisfazione. Le versioni precedenti senza questa raccolta non sono misurabili.</p><section><table><thead><tr><th>Processo</th><th>Attività</th><th>Installazioni</th><th>Completate</th><th>Fallite</th><th>Annullate</th><th>Esito sconosciuto</th><th>Ricevute</th><th>Valutazioni</th><th>Stelle</th></tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table></section><h2>Evidenze da esaminare</h2>"
        + "".join(reviews)
        + "</html>"
    )
    return document.replace("<title>Vera ·", f"<title>{title} ·").replace(
        "<h1>Vera:", f"<h1>{title}:"
    )
