"""Persist model-authored assetti reviews; fixed checks protect evidence lineage."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Any

__all__ = ["build_record", "digest", "main", "render_memo", "save_record"]

ROOT = Path(__file__).resolve().parents[1]


def digest(value: Any) -> str:
    """Hash canonical JSON for exact proposal and predecessor binding."""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must contain text")
    return value


def _date(value: Any, label: str) -> str:
    normalized = date.fromisoformat(_text(value, label)).isoformat()
    if normalized != value:
        raise ValueError(f"{label} must use YYYY-MM-DD")
    return normalized


def _references(rows: Any, sources: dict[str, Any]) -> None:
    if not isinstance(rows, list) or not rows:
        raise ValueError("Each evidence-backed item needs citations")
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Citation must be an object")
        if row["source_id"] not in sources:
            raise ValueError("Citation refers to an unknown source")
        _text(row["locator"], "citation locator")


def _linked_ids(value: Any, known: set[str], label: str) -> None:
    """Require explicit ID arrays; their semantic relationship remains reviewed."""
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a nonempty list")
    if any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must contain string IDs")
    if len(value) != len(set(value)) or not set(value).issubset(known):
        raise ValueError(f"{label} contains duplicate or unknown IDs")


# These are presentation/record fields, never a classifier of adequacy.
_INTELLIGENT_SECTIONS = {
    "coverage": (
        "Perimetro motivato / Reasoned coverage",
        {
            "area": "Area / Area",
            "status": "Stato / Status",
            "reason": "Motivazione e limiti / Rationale and limits",
        },
    ),
    "processes": (
        "Rischi e funzionamento / Risks and operation",
        {
            "process": "Processo / Process",
            "risk": "Rischio concreto / Concrete risk",
            "responsibility": "Responsabilità effettive / Actual responsibilities",
            "control": "Controllo e frequenza / Control and frequency",
            "information_flow": "Informazioni e destinatari / Information and recipients",
            "operation": "Funzionamento e controevidenze / Operation and counterevidence",
            "gap": "Lacuna o limite / Gap or limitation",
        },
    ),
    "questions": (
        "Domande che cambiano la valutazione / Decision-relevant questions",
        {
            "question": "Domanda / Question",
            "why_it_matters": "Effetto sulla valutazione / Assessment impact",
            "evidence_needed": "Esempio da cercare / Evidence to seek",
            "status": "Risposta e incertezze / Answer and uncertainty",
        },
    ),
    "chronology": (
        "Informazioni e decisioni nel tempo / Information and decision timeline",
        {
            "event_date": "Data del fatto / Event date",
            "known_at": "Quando era conoscibile / When knowable",
            "recipient": "Destinatario / Recipient",
            "event": "Fatto / Event",
            "response": "Decisione e seguito / Decision and follow-through",
            "uncertainty": "Limiti temporali / Temporal uncertainty",
        },
    ),
}


def _intelligent_review(
    value: Any, observation_ids: set[str], action_ids: set[str]
) -> None:
    """Check links and renderable shape; the model owns all semantic decisions."""
    if (
        not isinstance(value, dict)
        or type(value.get("version")) is not int
        or value["version"] != 1
    ):
        raise ValueError("Expected intelligent_review version 1")
    for name, (_, fields) in _INTELLIGENT_SECTIONS.items():
        rows = value.get(name)
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError(f"{name} must be an array of objects")
        if name == "coverage" and not rows:
            raise ValueError("Explain assessment coverage")
        ids: set[str] = set()
        for row in rows:
            row_id = _text(row.get("id"), f"{name} ID")
            if row_id in ids:
                raise ValueError(f"Duplicate {name} ID")
            ids.add(row_id)
            for field in fields:
                _text(row.get(field), f"{name} {field}")
            if name == "coverage" and row["status"] not in {
                "assessed",
                "excluded",
                "unresolved",
            }:
                raise ValueError("Unknown coverage status")
            links = row.get("observation_ids")
            if name == "coverage" and row["status"] != "assessed" and links == []:
                continue
            _linked_ids(links, observation_ids, f"{name} observations")
    _text(value.get("decision_brief"), "decision brief")
    _text(value.get("next_review"), "next review evidence and trigger")
    if value.get("action_ids") != []:
        _linked_ids(value.get("action_ids"), action_ids, "Decision brief actions")


def build_record(
    review: dict[str, Any], *, input_root: Path, client_id: str, engagement_id: str
) -> dict[str, Any]:
    """Validate exact references, not the truth or quality of assetti judgments."""
    if not isinstance(review, dict):
        raise ValueError("Review must be an object")
    review = copy.deepcopy(review)
    _text(client_id, "client ID")
    _text(engagement_id, "engagement ID")
    for field in ("sources", "legal_basis", "observations", "findings", "actions"):
        if not isinstance(review[field], list) or any(
            not isinstance(item, dict) for item in review[field]
        ):
            raise ValueError(f"{field} must be an array of objects")
    if (
        type(review["schema_version"]) is not int
        or review["schema_version"] != 1
        or review["jurisdiction"] != "IT"
    ):
        raise ValueError("Expected version 1 Italian assetti review")
    for field in (
        "scope",
        "company_context",
        "proportionality_basis",
        "assessment",
        "limitations",
    ):
        _text(review[field], field)
    _date(review["as_of"], "as_of")
    sources: dict[str, Any] = {}
    source_paths: dict[str, Path] = {}
    for source in review["sources"]:
        source_id = _text(source["id"], "source ID")
        if source_id in sources:
            raise ValueError("Duplicate source ID")
        relative = Path(source["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Source path must be relative to the bound inputs")
        path = (input_root / relative).resolve(strict=True)
        if not path.is_relative_to(input_root.resolve()) or not path.is_file():
            raise ValueError("Source escapes the bound inputs")
        if hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
            raise ValueError("Source digest mismatch")
        _text(source["title"], "source title")
        sources[source_id] = source
        source_paths[source_id] = path
    if not sources:
        raise ValueError("At least one source is required")
    for basis in review["legal_basis"]:
        for field in ("title", "url", "locator", "applicability"):
            _text(basis[field], f"legal basis {field}")
        _date(basis["checked_at"], "source retrieval date")
    if not review["legal_basis"]:
        raise ValueError("Record the verified professional basis")
    item_ids: set[str] = set()
    for item in review["findings"]:
        item_id = _text(item["id"], "finding ID")
        if item_id in item_ids:
            raise ValueError("Duplicate finding ID")
        item_ids.add(item_id)
        for field in ("observation", "interpretation", "alternatives", "follow_up"):
            _text(item[field], field)
        _references(item["citations"], sources)
    _references(review["assessment_citations"], sources)
    previous_hash = None
    previous = review.get("previous")
    if previous is not None:
        previous_record = json.loads(source_paths[previous["source_id"]].read_text())
        if (
            previous_record.get("workflow_id") != "adeguati-assetti"
            or previous_record.get("schema_version") != 1
        ):
            raise ValueError("Previous source is not an assetti review record")
        previous_hash = previous_record["record_sha256"]
        unsigned = {k: v for k, v in previous_record.items() if k != "record_sha256"}
        if (
            previous_hash != digest(unsigned)
            or previous_hash != previous["record_sha256"]
        ):
            raise ValueError("Previous record digest mismatch")
        if (
            previous_record["client_id"] != client_id
            or previous_record["engagement_id"] != engagement_id
        ):
            raise ValueError("Previous review belongs to another client or engagement")
        if previous_record["review"]["as_of"] > review["as_of"]:
            raise ValueError("Review date precedes previous assessment")
        _text(review["changes_since_previous"], "changes since previous review")
    observation_ids: set[str] = set()
    for item in review["observations"]:
        item_id = _text(item["id"], "observation ID")
        if item_id in observation_ids:
            raise ValueError("Duplicate observation ID")
        observation_ids.add(item_id)
        for field in ("area", "description", "proportionality", "assessment"):
            _text(item[field], field)
        if item["evidence_state"] not in {
            "documented",
            "reported",
            "operating_evidence",
            "unknown",
        }:
            raise ValueError("Unknown evidence state")
        # Fixed states describe provenance, never assign adequacy from a document or ratio.
        _references(item["citations"], sources)
    if not observation_ids:
        raise ValueError("At least one scoped observation is required")
    for finding in review["findings"]:
        _linked_ids(finding["observation_ids"], observation_ids, "Finding observations")
    action_ids: set[str] = set()
    for action in review["actions"]:
        action_id = _text(action["id"], "action ID")
        if action_id in action_ids:
            raise ValueError("Duplicate action ID")
        action_ids.add(action_id)
        _linked_ids(action["finding_ids"], item_ids, "Action findings")
        for field in (
            "proposal",
            "owner",
            "timing",
            "priority_reason",
            "completion_evidence_needed",
        ):
            _text(action[field], field)
        if action["status"] not in {"proposed", "in_progress", "completed", "deferred"}:
            raise ValueError("Unknown action status")
        if action["status"] == "completed":
            _references(action["completion_citations"], sources)
            _text(action["completion_assessment"], "completion assessment")
    if previous is not None:
        prior_ids = {item["id"] for item in previous_record["review"]["actions"]}
        follow_up = review["prior_action_review"]
        if not isinstance(follow_up, dict) or set(follow_up) != prior_ids:
            raise ValueError("Address every prior action explicitly")
        for value in follow_up.values():
            if not isinstance(value, dict):
                raise ValueError("Prior action review must be a structured disposition")
            if value["status"] not in {
                "open",
                "completed",
                "deferred",
                "superseded",
                "not_assessed",
            }:
                raise ValueError("Unknown prior action status")
            _text(value["assessment"], "prior action assessment")
            if value["status"] == "completed":
                _references(value["citations"], sources)
            elif value.get("citations"):
                _references(value["citations"], sources)
            if value["status"] == "superseded" or value.get("current_action_ids"):
                _linked_ids(
                    value["current_action_ids"], action_ids, "Prior replacement actions"
                )

    if "intelligent_review" in review:
        _intelligent_review(review["intelligent_review"], observation_ids, action_ids)

    proposal = {k: v for k, v in review.items() if k != "professional_decision"}
    proposal_hash = digest(proposal)
    decision = review.get("professional_decision")
    if decision is not None:
        if decision["proposal_sha256"] != proposal_hash:
            raise ValueError("Decision is not bound to this exact proposal")
        for field in ("reviewer_ref", "conclusion", "review_date_reason"):
            _text(decision[field], field)
        _date(decision["reviewed_at"], "reviewed_at")
        if decision["reviewed_at"] < review["as_of"]:
            raise ValueError("Professional decision precedes the assessment")
        if decision.get("next_review_date") is not None:
            next_date = _date(decision["next_review_date"], "next_review_date")
            if next_date < decision["reviewed_at"]:
                raise ValueError("Next review precedes the professional decision")
        dispositions = decision["finding_dispositions"]
        if not isinstance(dispositions, dict) or set(dispositions) != item_ids:
            raise ValueError("The professional must address every finding")
        for value in dispositions.values():
            _text(value, "finding disposition")
    record = {
        "schema_version": 1,
        "workflow_id": "adeguati-assetti",
        "client_id": client_id,
        "engagement_id": engagement_id,
        "status": "professional_decision_recorded" if decision else "draft_for_review",
        "proposal_sha256": proposal_hash,
        "previous_record_sha256": previous_hash,
        "review": review,
        "assurance_limit": "Hashes establish record integrity, not evidence truth, operating effectiveness, reviewer identity or adequacy. No certification is issued.",
    }
    record["record_sha256"] = digest(record)
    return record


def render_memo(record: dict[str, Any]) -> str:
    """Render every finding and decision without silently clearing open issues."""
    labels = {
        "observation": "Osservazione / Observation",
        "interpretation": "Conseguenza e valutazione / Consequence and assessment",
        "alternatives": "Spiegazioni alternative / Alternative explanations",
        "follow_up": "Approfondimento / Follow-up",
        "finding_ids": "Rilievi collegati / Related findings",
        "owner": "Responsabile proposto / Proposed owner",
        "timing": "Tempi proposti / Proposed timing",
        "priority_reason": "Motivo della priorità / Priority rationale",
        "completion_evidence_needed": "Evidenze di attuazione richieste / Implementation evidence needed",
        "status": "Stato / Status",
        "draft_for_review": "Bozza da rivedere / Draft for professional review",
        "professional_decision_recorded": "Decisione professionale registrata / Professional decision recorded",
        "documented": "Documentato / Documented",
        "reported": "Dichiarato / Reported",
        "operating_evidence": "Evidenza di funzionamento / Operating evidence",
        "unknown": "Non verificato / Unverified",
        "proposed": "Proposto / Proposed",
        "in_progress": "In corso / In progress",
        "completed": "Attuazione documentata / Completion documented",
        "deferred": "Rinviato / Deferred",
        "open": "Aperto / Open",
        "superseded": "Sostituito / Superseded",
        "not_assessed": "Non riesaminato / Not reassessed",
    }
    review = record["review"]
    lines = [
        "# Valutazione degli assetti organizzativi, amministrativi e contabili / "
        "Assessment of organizational, administrative and accounting arrangements",
        "",
        str(review["as_of"]),
        "",
        labels[record["status"]],
        "",
        review["scope"],
        "",
        review["company_context"],
        "",
        review["proportionality_basis"],
        "",
        review["assessment"],
        "",
    ]
    if "intelligent_review" in review:
        intelligent = review["intelligent_review"]
        lines.extend(
            [
                "## Decisioni da discutere / Decisions for discussion",
                "",
                intelligent["decision_brief"],
                "",
                ", ".join(intelligent["action_ids"]),
                "",
            ]
        )
        coverage_labels = {
            "assessed": "Esaminato / Assessed",
            "excluded": "Escluso / Excluded",
            "unresolved": "Da chiarire / Unresolved",
        }
        for name, (title, fields) in _INTELLIGENT_SECTIONS.items():
            lines.extend([f"## {title}", ""])
            for row in intelligent[name]:
                lines.extend([f"### {row['id']}", ""])
                for field, label in fields.items():
                    value = row[field]
                    if name == "coverage" and field == "status":
                        value = coverage_labels[value]
                    lines.extend([f"**{label}:** {value}", ""])
                lines.extend(
                    [
                        "**Evidenze / Evidence:** " + ", ".join(row["observation_ids"]),
                        "",
                    ]
                )
        lines.extend(
            ["## Prossima verifica / Next review", "", intelligent["next_review"], ""]
        )
    lines.extend(["## Evidenze e funzionamento / Evidence and operation", ""])
    for item in review["observations"]:
        lines.extend(
            [
                f"### {item['id']}: {item['area']}",
                "",
                labels[item["evidence_state"]],
                "",
            ]
        )
        for field in ("description", "proportionality", "assessment"):
            lines.extend([item[field], ""])
        lines.extend([f"- {c['source_id']}: {c['locator']}" for c in item["citations"]])
    lines.extend(["", "## Rilievi / Findings", ""])
    for item in review["findings"]:
        lines.extend([f"### {item['id']}", "", ", ".join(item["observation_ids"]), ""])
        for field in ("observation", "interpretation", "alternatives", "follow_up"):
            lines.extend([f"**{labels[field]}:** {item[field]}", ""])
        lines.extend([f"- {c['source_id']}: {c['locator']}" for c in item["citations"]])
        lines.append("")
    lines.extend(["## Piano di miglioramento / Improvement plan", ""])
    for action in review["actions"]:
        lines.extend([f"### {action['id']}: {action['proposal']}", ""])
        for field in (
            "finding_ids",
            "owner",
            "timing",
            "priority_reason",
            "completion_evidence_needed",
            "status",
        ):
            value = action[field]
            if field == "status":
                value = labels[value]
            elif field == "finding_ids":
                value = ", ".join(value)
            lines.extend([f"**{labels[field]}:** {value}", ""])
        if action["status"] == "completed":
            lines.extend([action["completion_assessment"], ""])
            lines.extend(
                [
                    f"- {c['source_id']}: {c['locator']}"
                    for c in action["completion_citations"]
                ]
            )
    if review.get("previous") is not None:
        lines.extend(["", "## Azioni precedenti / Prior actions", ""])
        for key, value in review["prior_action_review"].items():
            lines.extend(
                [f"### {key}: {labels[value['status']]}", "", value["assessment"], ""]
            )
            if value.get("current_action_ids"):
                lines.extend([", ".join(value["current_action_ids"]), ""])
            lines.extend(
                [
                    f"- {c['source_id']}: {c['locator']}"
                    for c in value.get("citations", [])
                ]
            )

    lines.extend(["## Assessment evidence / Evidenze della valutazione", ""])
    lines.extend(
        [f"- {c['source_id']}: {c['locator']}" for c in review["assessment_citations"]]
    )
    lines.extend(["", "## Sources / Fonti", ""])
    lines.extend(
        [
            f"- {s['id']}: {s['title']} ({s['path']}); SHA-256 {s['sha256']}"
            for s in review["sources"]
        ]
    )
    lines.extend(["", "## Professional basis / Riferimenti professionali", ""])
    lines.extend(
        [
            f"- [{b['title']}]({b['url']}), {b['locator']}; {b['checked_at']}. {b['applicability']}"
            for b in review["legal_basis"]
        ]
    )
    if review.get("previous") is not None:
        lines.extend(
            ["", "## Changes / Variazioni", "", review["changes_since_previous"]]
        )
    lines.extend(["", "## Limitations / Limiti", "", review["limitations"]])
    if review.get("professional_decision") is not None:
        decision = review["professional_decision"]
        lines.extend(
            [
                "",
                "## Decisione professionale registrata / Recorded professional decision",
                "",
                f"{decision['reviewer_ref']} — {decision['reviewed_at']}",
                "",
                decision["conclusion"],
                "",
            ]
        )
        lines.extend(
            [
                f"- {key}: {value}"
                for key, value in decision["finding_dispositions"].items()
            ]
        )
        lines.extend(["", decision["review_date_reason"], ""])
        if decision.get("next_review_date"):
            lines.extend(
                [
                    f"Riesame proposto / Proposed review: {decision['next_review_date']}",
                    "",
                ]
            )
    lines.extend(
        [
            "",
            record["assurance_limit"],
            "",
            f"Record SHA-256: {record['record_sha256']}",
            "",
        ]
    )
    return "\n".join(lines)


def save_record(record: dict[str, Any], output: Path) -> Path:
    """Append without overwriting an earlier review; duplicate retry is idempotent."""
    if record["record_sha256"] != digest(
        {key: value for key, value in record.items() if key != "record_sha256"}
    ):
        raise ValueError("Record changed after validation")
    if output.is_symlink():
        raise ValueError("Output directory must not be a symlink")
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = output / f"adeguati-assetti-{record['record_sha256']}.json"
    content = json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if path.is_symlink() or path.with_suffix(".md").is_symlink():
        raise ValueError("Output files must not be symlinks")
    memo = path.with_suffix(".md")
    rendered = render_memo(record)
    for target, expected in ((path, content), (memo, rendered)):
        if target.exists() and target.read_text(encoding="utf-8") != expected:
            raise ValueError("Existing output differs from its record")
    for target, expected in ((path, content), (memo, rendered)):
        if not target.exists():
            with target.open("x", encoding="utf-8") as handle:
                target.chmod(0o600)
                handle.write(expected)
    return path


def main() -> int:
    """Run only inside a started Studio Archive client workflow."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-engagement", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    args = parser.parse_args()
    for vendor in (
        ROOT / "vendor/modules",
        ROOT.parent.parent / "vendor/modules",
        ROOT.parent / "_shared/vendor/modules",
    ):
        if (vendor / "vera_assurance").is_dir():
            sys.path.insert(0, str(vendor))
            break
    from vera_assurance import load_client_engagement_context_file

    context = load_client_engagement_context_file(
        args.client_engagement,
        expected_workflow_id="adeguati-assetti",
        input_paths=[args.review],
    )
    if context["schema_version"] != "vera.client_workflow_context.v2":
        raise ValueError("assetti review requires a portable v2 client run")
    review = json.loads(args.review.read_text())
    input_root = Path(context["run_root"]) / "inputs"
    paths = [input_root / row["path"] for row in review["sources"]]
    context = load_client_engagement_context_file(
        args.client_engagement,
        expected_workflow_id="adeguati-assetti",
        input_paths=paths,
    )
    record = build_record(
        review,
        input_root=input_root,
        client_id=context["client_id"],
        engagement_id=context["engagement_id"],
    )
    save_record(record, Path(context["output_dir"]))
    logging.info("Saved assetti review: %s", record["record_sha256"])
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
