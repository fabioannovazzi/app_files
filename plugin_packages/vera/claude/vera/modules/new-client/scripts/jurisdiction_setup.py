"""Geneva professional setup adapter within the existing New Client workflow."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for vendor in (
    ROOT / "vendor/modules",
    ROOT.parent.parent / "vendor/modules",
    ROOT.parent / "_shared/vendor/modules",
):
    if (vendor / "vera_assurance").is_dir():
        sys.path.insert(0, str(vendor))
        break

from vera_assurance.jurisdiction import citations, run, seal, text, validate_envelope

__all__ = ["build_record", "render_memo"]

DOMAINS = {"identity", "mandate", "ownership", "aml_applicability", "privacy_roles"}


def build_record(
    payload: dict[str, Any], *, input_root: Path, client_id: str, engagement_id: str
) -> dict[str, Any]:
    """Keep setup evidence, requirements and unreceived documents distinct."""
    payload = validate_envelope(payload, input_root)
    if payload["language"] not in {"fr", "en"}:
        raise ValueError("This presentation adapter supports fr and en")
    text(payload.get("client_name"), "client name")
    text(payload.get("mandate"), "mandate")
    source_ids = {source["id"] for source in payload["sources"]}
    reviews = payload.get("domain_reviews", [])
    if (
        not isinstance(reviews, list)
        or len(reviews) != len(DOMAINS)
        or {r.get("domain") for r in reviews} != DOMAINS
    ):
        raise ValueError(
            "Review identity, mandate, ownership, AML applicability and privacy roles"
        )
    unresolved = []
    for review in reviews:
        if review.get("status") not in {"supported", "unresolved", "not_applicable"}:
            raise ValueError("Invalid domain review status")
        text(review.get("title"), "domain title")
        text(review.get("assessment"), "domain assessment")
        citations(review.get("citations"), source_ids)
        if review["status"] == "unresolved":
            unresolved.append(review["domain"])
    documents = payload.get("document_plan")
    if not isinstance(documents, list):
        raise ValueError("Provide a document plan, including an explicit empty plan")
    seen = set()
    for document in documents:
        identity = text(document.get("id"), "document ID")
        if identity in seen:
            raise ValueError("Duplicate document ID")
        seen.add(identity)
        for key in ("title", "purpose", "next_action"):
            text(document.get(key), key)
        if document.get("status") not in {
            "received",
            "requested",
            "missing",
            "not_applicable",
        }:
            raise ValueError("Invalid document evidence status")
        if document["status"] == "received":
            citations(document.get("citations"), source_ids)
        elif document.get("citations"):
            citations(document["citations"], source_ids)
    results = {
        "unresolved_domains": unresolved,
        "outstanding_document_ids": [
            d["id"] for d in documents if d["status"] in {"requested", "missing"}
        ],
        "italian_aml_scoring_applied": False,
        "engagement_accepted": False,
    }
    return seal(
        payload,
        results,
        workflow_id="new-client",
        client_id=client_id,
        engagement_id=engagement_id,
    )


def render_memo(record: dict[str, Any]) -> str:
    """Render the complete authored review and document state for the professional."""
    case = record["review"]
    fr = case["language"] == "fr"
    lines = [
        "# " + ("Ouverture du dossier client" if fr else "New client setup"),
        "",
        case["client_name"],
        "",
        "CH-GE · " + case["as_of"],
        "",
        case["mandate"],
        "",
        (
            ("Projet à examiner" if fr else "Draft for professional review")
            if not case.get("professional_decision")
            else case["professional_decision"]["conclusion"]
        ),
        "",
        case["jurisdiction_basis"],
    ]
    for review in case["domain_reviews"]:
        lines.extend(
            [
                "",
                "## " + review["title"],
                "",
                review["status"],
                "",
                review["assessment"],
                "",
                "; ".join(
                    c["source_id"] + ": " + c["locator"] for c in review["citations"]
                ),
            ]
        )
    lines.extend(
        [
            "",
            "## "
            + ("Pièces et prochaines actions" if fr else "Documents and next actions"),
        ]
    )
    for document in case["document_plan"]:
        lines.extend(
            [
                "",
                "### " + document["title"],
                "",
                document["status"],
                "",
                document["purpose"],
                "",
                document["next_action"],
            ]
        )
    lines.extend(
        [
            "",
            "## " + ("Sources et limites" if fr else "Sources and limitations"),
            "",
            case["limitations"],
        ]
    )
    for source in case["legal_basis"]:
        lines.append(
            f'\n{source["title"]} · {source["url"]} · {source["locator"]} · {source["applicability"]}'
        )
    for source in case["sources"]:
        lines.append(
            f'\n{source["id"]}: {source["title"]} · SHA-256 {source["sha256"]}'
        )
    lines.extend(
        [
            "",
            (
                "L’acceptation du mandat reste une décision du professionnel."
                if fr
                else "Engagement acceptance remains the professional's decision."
            ),
            "",
            record["record_sha256"],
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(run("new-client", build_record, render_memo))
