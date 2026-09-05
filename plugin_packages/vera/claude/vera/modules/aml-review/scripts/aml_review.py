"""Persist model-authored AML reviews; fixed checks protect evidence lineage."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
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
    return date.fromisoformat(_text(value, label)).isoformat()


def _references(rows: Any, sources: dict[str, Any]) -> None:
    if not isinstance(rows, list) or not rows:
        raise ValueError("Each evidence-backed item needs citations")
    for row in rows:
        if row["source_id"] not in sources:
            raise ValueError("Citation refers to an unknown source")
        _text(row["locator"], "citation locator")


def build_record(
    review: dict[str, Any], *, input_root: Path, client_id: str, engagement_id: str
) -> dict[str, Any]:
    """Validate exact references, not the truth or quality of AML judgments."""
    review = copy.deepcopy(review)
    if review["schema_version"] != 1 or review["jurisdiction"] != "IT":
        raise ValueError("Expected version 1 Italian AML review")
    for field in ("scope", "assessment", "limitations"):
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
            previous_record.get("workflow_id") != "aml-review"
            or previous_record.get("schema_version") != 1
        ):
            raise ValueError("Previous source is not an AML review record")
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
        _text(review["changes_since_previous"], "changes since previous review")
    calculation = None
    if review.get("calculation_source_id") is not None:
        # Reuse the complete existing validator before arithmetic, not a new rule engine.
        path = ROOT.parent / "new-client" / "scripts" / "new_client_core.py"
        spec = importlib.util.spec_from_file_location("aml_new_client", path)
        if spec is None or spec.loader is None:
            raise ValueError("New Client arithmetic module is unavailable")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        intake = module.validate_new_client_input(
            json.loads(source_paths[review["calculation_source_id"]].read_text())
        )
        calculation = module.calculate_aml(intake["aml"])
    proposal = {k: v for k, v in review.items() if k != "professional_decision"}
    proposal_hash = digest(proposal)
    decision = review.get("professional_decision")
    if decision is not None:
        if decision["proposal_sha256"] != proposal_hash:
            raise ValueError("Decision is not bound to this exact proposal")
        for field in ("reviewer_ref", "conclusion", "review_date_reason"):
            _text(decision[field], field)
        _date(decision["reviewed_at"], "reviewed_at")
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
        "workflow_id": "aml-review",
        "client_id": client_id,
        "engagement_id": engagement_id,
        "status": "professional_decision_recorded" if decision else "draft_for_review",
        "proposal_sha256": proposal_hash,
        "previous_record_sha256": previous_hash,
        "review": review,
        "calculation": calculation,
        "assurance_limit": "Hashes establish record integrity, not evidence truth, reviewer identity or AML compliance.",
    }
    record["record_sha256"] = digest(record)
    return record


def render_memo(record: dict[str, Any]) -> str:
    """Render every finding and decision without silently clearing open issues."""
    review = record["review"]
    lines = [
        "# AML review / Revisione antiriciclaggio",
        "",
        str(review["as_of"]),
        "",
        record["status"],
        "",
        review["scope"],
        "",
        review["assessment"],
        "",
        "## Findings / Osservazioni",
        "",
    ]
    for item in review["findings"]:
        lines.extend([f"### {item['id']}", ""])
        for field in ("observation", "interpretation", "alternatives", "follow_up"):
            lines.extend([f"**{field}:** {item[field]}", ""])
        lines.extend([f"- {c['source_id']}: {c['locator']}" for c in item["citations"]])
        lines.append("")
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
    if record["calculation"] is not None:
        lines.extend(
            [
                "",
                "## Calculation / Calcolo",
                "",
                "```json",
                json.dumps(record["calculation"], ensure_ascii=False, indent=2),
                "```",
            ]
        )
    if review.get("professional_decision") is not None:
        lines.extend(
            [
                "",
                "## Recorded decision / Decisione registrata",
                "",
                "```json",
                json.dumps(
                    review["professional_decision"], ensure_ascii=False, indent=2
                ),
                "```",
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
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = output / f"aml-review-{record['record_sha256']}.json"
    content = json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if path.exists():
        if path.read_text() != content:
            raise ValueError("Existing review differs from its digest")
    else:
        with path.open("x", encoding="utf-8") as handle:
            path.chmod(0o600)
            handle.write(content)
    memo = path.with_suffix(".md")
    rendered = render_memo(record)
    if memo.exists():
        if memo.read_text() != rendered:
            raise ValueError("Existing memo differs from its record")
    else:
        with memo.open("x", encoding="utf-8") as handle:
            memo.chmod(0o600)
            handle.write(rendered)
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
        expected_workflow_id="aml-review",
        input_paths=[args.review],
    )
    if context["schema_version"] != "vera.client_workflow_context.v2":
        raise ValueError("AML review requires a portable v2 client run")
    review = json.loads(args.review.read_text())
    input_root = Path(context["run_root"]) / "inputs"
    paths = [input_root / row["path"] for row in review["sources"]]
    context = load_client_engagement_context_file(
        args.client_engagement, expected_workflow_id="aml-review", input_paths=paths
    )
    record = build_record(
        review,
        input_root=input_root,
        client_id=context["client_id"],
        engagement_id=context["engagement_id"],
    )
    save_record(record, Path(context["output_dir"]))
    logging.info("Saved AML review: %s", record["record_sha256"])
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
