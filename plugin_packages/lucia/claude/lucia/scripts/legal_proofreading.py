"""Persist and render a model-authored forensic review with exact source checks."""

from __future__ import annotations

import argparse
import html
import json
import logging
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from legal_documents import read_pack

__all__ = ["CATEGORIES", "scaffold", "validate_audit", "render_audit", "main"]

LOGGER = logging.getLogger(__name__)
CATEGORIES = (
    "definitions",
    "references",
    "consistency",
    "entities",
    "numbers",
    "language",
    "numbering",
    "formatting",
)
SEVERITIES = ("critical", "high", "medium", "low", "info")


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def scaffold(run_dir: Path) -> Path:
    """Create an explicit unreviewed audit; existence never means inspection ran."""
    pack = read_pack(run_dir)
    target = run_dir / "proofreading.json"
    audit = {
        "context": _load(run_dir / "review.json")["context"],
        "documents": {
            source["id"]: {
                "reviewed_anchors": [],
                "limitations": source["warnings"],
                "maps": {
                    name: {"entries": [], "note": ""}
                    for name in ("entities", "sections", "terms")
                },
                "passes": {
                    name: {"status": "not-reviewed", "note": ""} for name in CATEGORIES
                },
                "visual_review": {"status": "not-reviewed", "evidence": ""},
            }
            for source in pack["sources"]
        },
        "findings": [],
        "takeaways": [],
    }
    with target.open("x", encoding="utf-8") as handle:
        json.dump(audit, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return target


def validate_audit(run_dir: Path, audit: dict[str, Any]) -> dict[str, Any]:
    """Check audit shape, declared coverage and quotes, not judgment or truth."""
    pack = read_pack(run_dir)
    sources = {source["id"]: source for source in pack["sources"]}
    schema = _load(Path(__file__).with_name("legal_proofreading.schema.json"))
    errors = [
        f"{e.json_path}: {e.message}"
        for e in Draft202012Validator(schema).iter_errors(audit)
    ]
    if errors:
        return {"valid": False, "complete": False, "errors": errors, "limitations": []}
    context_schema = _load(
        Path(__file__).with_name("legal_documents_review.schema.json")
    )["properties"]["context"]
    errors.extend(
        f"context.{e.json_path}: {e.message}"
        for e in Draft202012Validator(context_schema).iter_errors(audit["context"])
    )
    documents = audit["documents"]
    limits: list[str] = []
    if set(documents) != set(sources):
        errors.append("Retain every selected document, including unreadable documents.")
    units = {
        (s["id"], u["anchor"]): u["text"] for s in sources.values() for u in s["units"]
    }

    def check_citations(citations: list[dict[str, str]], owner: str) -> None:
        for citation in citations:
            text = units.get((citation["source_id"], citation["anchor"]))
            quote = " ".join(citation["quote"].split())
            if not text or not quote or quote not in " ".join(text.split()):
                errors.append(
                    f"{owner}: quotation not found at the cited source anchor."
                )

    for source_id, document in documents.items():
        if source_id not in sources:
            continue
        source = sources[source_id]
        anchors = {unit["anchor"] for unit in source["units"]}
        reviewed = set(document["reviewed_anchors"])
        if reviewed - anchors:
            errors.append(f"{source_id}: unknown reviewed anchors.")
        if anchors - reviewed or source["error"] or not anchors:
            limits.append(f"{source_id}: source reading is incomplete or unavailable.")
        if set(document["passes"]) != set(CATEGORIES):
            errors.append(f"{source_id}: record every proofreading pass.")
        for category, review_pass in document["passes"].items():
            if review_pass["status"] != "complete":
                limits.append(f"{source_id}/{category}: {review_pass['status']}")
            if review_pass["status"] == "complete" and not review_pass["note"].strip():
                errors.append(
                    f"{source_id}/{category}: completed pass needs its findings or no-issue rationale."
                )
        if document["visual_review"]["status"] != "complete":
            limits.append(f"{source_id}: visual review not complete.")
        elif not document["visual_review"]["evidence"].strip():
            errors.append(
                f"{source_id}: completed visual review needs the inspected artifact/pages."
            )
        for name, mapping in document["maps"].items():
            if not mapping["note"].strip():
                errors.append(
                    f"{source_id}/{name}: explain the map's scope, absence or unfinished work."
                )
            for entry in mapping["entries"]:
                check_citations(entry["citations"], source_id + "/" + name)
        limits.extend(f"{source_id}: {limit}" for limit in document["limitations"])
    ids = [finding["id"] for finding in audit["findings"]]
    if len(ids) != len(set(ids)):
        errors.append("Finding IDs must be unique.")
    for finding in audit["findings"]:
        check_citations(finding["citations"], finding["id"])
    return {
        "valid": not errors,
        "complete": not errors and not limits,
        "errors": errors,
        "limitations": limits,
        "coverage_basis": "Declared by the reviewing model; not proof of its attention or legal accuracy.",
    }


def render_audit(run_dir: Path, audit_path: Path) -> Path:
    """Deliver findings, reference maps and explicit pass coverage as local HTML."""
    audit = _load(audit_path)
    validation = validate_audit(run_dir, audit)
    target = run_dir / "proofreading.html"
    if target.exists():
        number = 1
        while (run_dir / f"previous-{number}-proofreading.html").exists():
            number += 1
        target.rename(run_dir / f"previous-{number}-proofreading.html")
    (run_dir / "proofreading-validation.json").write_text(
        json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if not validation["valid"]:
        raise ValueError("Invalid audit: " + "; ".join(validation["errors"]))
    lang = audit["context"].get("language", "it")
    labels = _load(Path(__file__).with_name("legal_proofreading_labels.json"))[lang]
    esc = lambda value: html.escape(str(value), quote=True)
    findings = sorted(audit["findings"], key=lambda f: SEVERITIES.index(f["severity"]))
    rows = []
    for finding in findings:
        evidence = "<br>".join(
            f"{esc(c['source_id'])} · {esc(c['anchor'])}<blockquote>{esc(c['quote'])}</blockquote>"
            for c in finding["citations"]
        )
        rows.append(
            "<tr>"
            + "".join(
                f"<td>{cell}</td>"
                for cell in (
                    esc(finding["id"]),
                    esc(labels["severities"][finding["severity"]]),
                    esc(labels["categories"][finding["category"]]),
                    esc(labels["kinds"][finding["kind"]]),
                    evidence,
                    esc(finding["issue"]) + "<p>" + esc(finding["reason"]) + "</p>",
                    esc(finding["fix"]),
                )
            )
            + "</tr>"
        )
    context = "".join(
        f"<dt>{esc(key)}</dt><dd>{esc(value)}</dd>"
        for key, value in audit["context"].items()
    )
    sections = []
    for source_id, document in audit["documents"].items():
        pass_rows = "".join(
            f"<tr><th>{esc(labels['categories'][category])}</th><td>{esc(labels['states'][entry['status']])}</td><td>{esc(entry['note'])}</td></tr>"
            for category, entry in document["passes"].items()
        )
        maps = []
        for name, mapping in document["maps"].items():
            entries = "".join(
                f"<li><strong>{esc(entry['label'])}</strong> {esc(entry['note'])}<ul>"
                + "".join(
                    f"<li>{esc(c['anchor'])}: {esc(c['quote'])}</li>"
                    for c in entry["citations"]
                )
                + "</ul></li>"
                for entry in mapping["entries"]
            )
            maps.append(
                f"<h4>{esc(labels['maps'][name])}</h4><p>{esc(mapping['note'])}</p><ul>{entries}</ul>"
            )
        sections.append(
            f"<section><h3>{esc(source_id)}</h3><table>{pass_rows}</table><p>{esc(document['visual_review']['evidence'])}</p>{''.join(maps)}</section>"
        )
    limits = "".join(f"<li>{esc(limit)}</li>" for limit in validation["limitations"])
    takeaways = "".join(f"<li>{esc(item)}</li>" for item in audit["takeaways"])
    body = f"""<!doctype html><html lang="{lang}"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(labels['title'])}</title>
<style>body{{font:16px/1.6 'Instrument Sans',Arial,sans-serif;color:#172b4d;margin:40px auto;padding:0 24px;max-width:1200px}}h1,h2,h3{{line-height:1.2}}h1{{font-size:36px}}h2{{margin-top:40px}}table{{border-collapse:collapse;width:100%;font-size:14px}}th,td{{border:1px solid #ccd5df;text-align:left;vertical-align:top;padding:12px}}thead{{background:#edf3f8}}blockquote{{margin:8px 0;white-space:pre-wrap}}dt{{font-weight:bold}}dd{{margin:0 0 12px}}.table{{overflow:auto}}@media print{{body{{margin:0}}thead{{display:table-header-group}}tr{{break-inside:avoid}}}}</style>
<main><h1>{esc(labels['title'])}</h1><p>{esc(labels['complete'] if validation['complete'] else labels['partial'])}</p><p>{esc(labels['meaning'])}</p><ul>{takeaways}</ul>
<h2>{esc(labels['findings'])}</h2><div class="table"><table><thead><tr>{''.join('<th>'+esc(h)+'</th>' for h in labels['columns'])}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<h2>{esc(labels['coverage'])}</h2>{''.join(sections)}<h2>{esc(labels['context'])}</h2><dl>{context}</dl><h2>{esc(labels['limits'])}</h2><ul>{limits}</ul>
<h2>{esc(labels['privacy_title'])}</h2><p>{esc(labels['privacy'])}</p></main></html>"""
    target.write_text(body, encoding="utf-8")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("scaffold", "render"))
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--audit", type=Path)
    args = parser.parse_args(argv)
    try:
        result = (
            scaffold(args.run_dir)
            if args.command == "scaffold"
            else render_audit(
                args.run_dir, args.audit or args.run_dir / "proofreading.json"
            )
        )
        LOGGER.info("%s", result)
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        LOGGER.error("%s", error)
        return 2


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
