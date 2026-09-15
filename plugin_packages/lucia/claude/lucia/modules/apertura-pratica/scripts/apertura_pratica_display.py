"""Localized presentation of recorded matter facts and mechanical diagnostics.

This module changes display text only. It does not decide conflicts, deadlines,
applicability or professional acceptance, and leaves unknown diagnostics visible.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

__all__ = ["labels", "matter_memo", "missing_request", "handoff", "run_review"]


@lru_cache(maxsize=5)
def labels(language: str) -> dict[str, str]:
    """Read the workflow's own supported display vocabulary."""
    path = Path(__file__).resolve().parents[1] / "references/display-labels.json"
    return json.loads(path.read_text(encoding="utf-8"))[language]


def _shown(value: Any, words: Mapping[str, str]) -> str:
    if value is None or value == "":
        return words["missing"]
    return words.get(str(value), str(value))


def _diagnostic(
    message: str, intake: Mapping[str, Any], words: Mapping[str, str]
) -> str:
    for prefix in (
        "Blocking intake items remain open: ",
        "Non-blocking intake items remain open: ",
    ):
        if message.startswith(prefix):
            descriptions = {
                row["item_id"]: row["description"] for row in intake["missing_items"]
            }
            references = message.removeprefix(prefix).split(", ")
            return words[prefix] + "; ".join(
                descriptions.get(key, key).rstrip(".") for key in references
            )
    return words.get(message, message)


def matter_memo(intake: Mapping[str, Any], report: Mapping[str, Any]) -> str:
    """Lead with the actual request and received facts, then review requirements."""
    w = labels(str(intake["language"]))
    matter = intake["matter"]
    lines = [f"# {w['memo']}", ""]
    for field, value in (
        ("client", intake["client"]["display_name"] or intake["client"]["reference"]),
        ("matter", matter["title"] or matter["reference"]),
        ("status", report["status"]),
        ("jurisdiction", matter["jurisdiction"]["primary"]),
        ("opening_mode", intake["opening_mode"]),
    ):
        # Only coded status/mode values are translated; case names remain exact.
        shown = (
            _shown(value, w)
            if field in {"status", "opening_mode", "jurisdiction"}
            else str(value)
        )
        lines.append(f"**{w[field]}:** {shown}  ")
    for field in ("objective", "requested_work", "summary"):
        lines.extend(["", f"## {w[field]}", "", matter[field] or w["missing"]])
    lines.extend(["", f"## {w['parties']}", ""])
    for party in intake["parties"]:
        roles = ", ".join(_shown(role, w) for role in party["roles"])
        lines.append(
            f"- **{party['display_name']}** — {roles}; {_shown(party['identity_status'], w)}"
        )
    conflict = intake["conflict_check"]
    lines.extend(
        [
            "",
            f"## {w['conflict']}",
            "",
            f"{w['register_scope']}: {_shown(conflict['register_scope'], w)}.",
            "",
            conflict["search_method"],
            "",
            f"{w['professional_decision']}: {_shown(conflict['professional_decision']['status'], w)}.",
            "",
            f"## {w['deadlines']}",
            "",
            intake["deadline_review"]["basis"],
            "",
            f"{w['status']}: {_shown(intake['deadline_review']['status'], w)}. "
            f"{w['candidate_count']}: {len(intake['deadline_review']['candidates'])}.",
        ]
    )
    for field in ("blockers", "warnings"):
        lines.extend(["", f"## {w[field]}", ""])
        lines.extend(
            f"- {_diagnostic(message, intake, w)}" for message in report[field]
        )
        if not report[field]:
            lines.append(w["none"])
    lines.extend(["", f"## {w['sources']}", ""])
    lines.extend(
        f"- [{row['original_name']}]({row['stored_path']})"
        for row in intake["evidence_register"]
    )
    if not intake["evidence_register"]:
        lines.append(w["none"])
    lines.extend(["", w["boundary"], ""])
    return "\n".join(lines)


def missing_request(intake: Mapping[str, Any]) -> str:
    """Group authored requests by recipient without inferring who must answer."""
    w = labels(str(intake["language"]))
    items = [row for row in intake["missing_items"] if row["status"] == "open"]
    lines = [f"# {w['missing_title']}", "", w["request_boundary"]]
    for recipient, heading in (
        ("client", "client_requests"),
        ("firm", "firm_actions"),
        ("to_confirm", "unassigned_requests"),
    ):
        group = [
            row for row in items if row.get("requested_from", "to_confirm") == recipient
        ]
        if group:
            lines.extend(["", f"## {w[heading]}", ""])
            lines.extend(f"- {row['description']}" for row in group)
    if not items:
        lines.extend(["", w["none"]])
    return "\n".join(lines) + "\n"


def handoff(language: str, status: str) -> str:
    """Explain how to continue review without declaring approval."""
    w = labels(language)
    return f"# {w['review_title']}\n\n{w['status']}: {_shown(status, w)}.\n\n{w['handoff']}\n\n{w['boundary']}\n"


def run_review(language: str, report: Mapping[str, Any]) -> str:
    """Keep a concise localized index to the full matter and review documents."""
    w = labels(language)
    return (
        f"# {w['review_title']}\n\n{w['status']}: {_shown(report['status'], w)}.\n\n"
        f"- {w['blockers']}: {len(report['blockers'])}\n"
        f"- {w['warnings']}: {len(report['warnings'])}\n\n"
        f"[{w['memo']}](matter_opening_memo.md) · [{w['missing_title']}](missing_information_request.md)\n\n"
        f"{w['handoff']}\n"
    )
