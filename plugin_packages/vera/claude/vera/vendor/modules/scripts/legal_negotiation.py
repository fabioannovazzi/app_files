"""Inventory Word revisions and account for model-authored negotiating positions."""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import html
import json
import logging
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from legal_documents import read_pack
from legal_docx import W, paragraph_text, parse_xml, story_parts
from lxml import etree as ET

__all__ = [
    "inventory_changes",
    "scaffold",
    "validate_positions",
    "render_positions",
    "verify_delivery",
    "main",
]
LOGGER = logging.getLogger(__name__)
REVISION_TAGS = frozenset(
    {
        "ins",
        "del",
        "moveFrom",
        "moveTo",
        "cellIns",
        "cellDel",
        "cellMerge",
        "pPrChange",
        "rPrChange",
        "tblPrChange",
        "tblPrExChange",
        "tblGridChange",
        "trPrChange",
        "tcPrChange",
        "sectPrChange",
        "numberingChange",
        "customXmlPrChange",
        "conflictIns",
        "conflictDel",
        "moveFromRangeStart",
        "moveFromRangeEnd",
        "moveToRangeStart",
        "moveToRangeEnd",
        "customXmlInsRangeStart",
        "customXmlInsRangeEnd",
        "customXmlDelRangeStart",
        "customXmlDelRangeEnd",
        "customXmlMoveFromRangeStart",
        "customXmlMoveFromRangeEnd",
        "customXmlMoveToRangeStart",
        "customXmlMoveToRangeEnd",
    }
)


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _font_css() -> str:
    """Embed the already bundled font without adding a network dependency."""
    script = Path(__file__).resolve()
    candidates = (
        script.parent.parent
        / "vendor/modules/courseware/assets/InstrumentSans-Regular.ttf",
        script.parent.parent / "courseware/assets/InstrumentSans-Regular.ttf",
        script.parents[2]
        / "_shared/vendor/modules/courseware/assets/InstrumentSans-Regular.ttf",
    )
    for path in candidates:
        if path.is_file():
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            return (
                "@font-face{font-family:'Instrument Sans';src:url(data:font/ttf;base64,"
                + encoded
                + ") format('truetype');font-weight:100 900;font-style:normal}"
            )
    return ""


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: Any, *, exclusive: bool = False) -> None:
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError("Negotiation outputs must be ordinary local files.")
    with path.open("x" if exclusive else "w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def inventory_changes(run_dir: Path, source_id: str) -> dict[str, Any]:
    """Read every revision record in Word XML parts; never classify legal effect.

    XML identities, byte hashes and exact counts are mechanical evidence.
    Insertion/deletion records and move/range endpoints remain distinct units;
    they are not a count of user actions or legal negotiating positions.
    """
    pack = read_pack(run_dir)
    source = next((s for s in pack["sources"] if s["id"] == source_id), None)
    if source is None or source["error"]:
        raise ValueError("Choose an accessible source from this evidence pack.")
    path = run_dir / source["snapshot"]
    if path.suffix.lower() != ".docx":
        raise ValueError("Negotiation inventory requires the original tracked DOCX.")
    changes: list[dict[str, Any]] = []
    comments: list[dict[str, Any]] = []
    parts: list[str] = []
    limits = list(source["warnings"])
    with zipfile.ZipFile(path) as archive:
        story_parts(archive)  # Reuse duplicate-entry and expansion protection.
        for part in sorted(
            n
            for n in archive.namelist()
            if n.startswith("word/") and n.endswith(".xml")
        ):
            root = parse_xml(archive.read(part))
            tree = root.getroottree()
            parts.append(part)
            anchors = {p: f"{part}#p{i}" for i, p in enumerate(root.iter(W + "p"), 1)}
            for node in root.iter():
                if not isinstance(node.tag, str):
                    continue
                tag = ET.QName(node).localname
                attributes = {ET.QName(k).localname: v for k, v in node.attrib.items()}
                owner = next(
                    (p for p in [node, *node.iterancestors()] if p.tag == W + "p"), None
                )
                locator = part + "#" + tree.getpath(node)
                if node.tag == W + "comment":
                    cid = attributes.get("id", "")
                    comments.append(
                        {
                            "id": f"M{len(comments) + 1:05}",
                            "word_id": cid,
                            "locator": locator,
                            "attributes": attributes,
                            "text": "\n".join(
                                paragraph_text(p, "all") for p in node.iter(W + "p")
                            ),
                            "anchors": [],
                        }
                    )
                    continue
                is_word = ET.QName(node).namespace in {
                    W[1:-1],
                    "http://schemas.microsoft.com/office/word/2010/wordml",
                    "http://schemas.microsoft.com/office/word/2012/wordml",
                }
                # w15:person is contact metadata for comment/revision authors,
                # not a revision record (MS Open XML CT_Person).
                if (
                    node.tag
                    == "{http://schemas.microsoft.com/office/word/2012/wordml}person"
                ):
                    continue
                if not is_word or not (
                    tag in REVISION_TAGS
                    or ("author" in attributes and tag != "comment")
                ):
                    continue
                known = tag in REVISION_TAGS
                if not known:
                    limits.append(
                        f"{locator}: unrecognised revision-bearing element {tag}; inspect the original."
                    )
                changes.append(
                    {
                        "id": f"C{len(changes) + 1:05}",
                        "kind": tag,
                        "locator": locator,
                        "paragraph_anchor": anchors.get(owner, ""),
                        "attributes": attributes,
                        "text": paragraph_text(node, "all"),
                        "original_context": (
                            paragraph_text(owner, "original")
                            if owner is not None
                            else ""
                        ),
                        "final_context": (
                            paragraph_text(owner, "final") if owner is not None else ""
                        ),
                        "xml": ET.tostring(node, encoding="unicode"),
                        "known_markup": known,
                    }
                )
        # Retain complete comment ranges, including paragraphs without a reference.
        for part in parts:
            root = parse_xml(archive.read(part))
            active: set[str] = set()
            for i, paragraph in enumerate(root.iter(W + "p"), 1):
                owner_ids = set(active)
                for node in paragraph.iter():
                    if node.tag == W + "commentRangeStart":
                        active.add(node.get(W + "id", ""))
                        owner_ids.update(active)
                    elif node.tag in {W + "commentReference", W + "commentRangeEnd"}:
                        owner_ids.add(node.get(W + "id", ""))
                        if node.tag == W + "commentRangeEnd":
                            active.discard(node.get(W + "id", ""))
                for comment in comments:
                    if comment["word_id"] in owner_ids:
                        comment["anchors"].append(f"{part}#p{i}")
    return {
        "schema_version": 1,
        "source_id": source_id,
        "source_sha256": source["sha256"],
        "source_name": source["name"],
        "parts": parts,
        "changes": changes,
        "comments": comments,
        "limitations": list(dict.fromkeys(limits)),
        "count_basis": "Word revision records and range markers, not user actions or legal significance.",
    }


def scaffold(
    run_dir: Path, source_id: str, previous_review: Path | None = None
) -> Path:
    """Persist an unreviewed inventory and optional selected earlier-round snapshot."""
    targets = [
        run_dir / n
        for n in (
            "negotiation-inventory.json",
            "negotiation-inventory.sha256",
            "negotiation.json",
            "negotiation-prior.json",
        )
    ]
    if any(p.exists() for p in targets):
        raise ValueError(
            "Negotiation state already exists; resume it instead of replacing it."
        )
    inventory = inventory_changes(run_dir, source_id)
    if not inventory["changes"]:
        raise ValueError(
            "No tracked revisions found. Use ordinary document comparison or supply the marked-up DOCX."
        )
    inventory["previous"] = None
    if previous_review is not None:
        previous = _load(previous_review)
        schema = _load(Path(__file__).with_name("legal_negotiation.schema.json"))
        if list(Draft202012Validator(schema).iter_errors(previous)):
            raise ValueError("The selected earlier review has an invalid structure.")
        _write(run_dir / "negotiation-prior.json", previous, exclusive=True)
        inventory["previous"] = {
            "snapshot": "negotiation-prior.json",
            "sha256": _hash((run_dir / "negotiation-prior.json").read_bytes()),
            "provenance": "Selected earlier review; its source accuracy and approval are not automatically established.",
        }
    _write(targets[0], inventory, exclusive=True)
    digest = _hash(targets[0].read_bytes())
    targets[1].write_text(digest + "\n", encoding="utf-8")
    review = {
        "schema_version": 1,
        "inventory_sha256": digest,
        "context": _load(run_dir / "review.json")["context"],
        "response_mode": "blank",
        "response_request": "",
        "original_inspected": False,
        "visual_review": {"status": "pending", "evidence": ""},
        "positions": [],
        "other_changes": [],
        "comment_reviews": [],
        "round_comparison": [],
        "limitations": [],
    }
    _write(targets[2], review, exclusive=True)
    return targets[2]


def _read_inventory(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "negotiation-inventory.json"
    digest = _hash(path.read_bytes())
    if digest != (run_dir / "negotiation-inventory.sha256").read_text().strip():
        raise ValueError("Negotiation inventory changed; prepare a new evidence run.")
    inventory = _load(path)
    current = inventory_changes(run_dir, inventory["source_id"])
    retained = {key: value for key, value in inventory.items() if key != "previous"}
    if current != retained:
        raise ValueError("Negotiation inventory does not match the selected original.")
    if inventory["previous"] is not None:
        prior = run_dir / "negotiation-prior.json"
        if (
            inventory["previous"]["snapshot"] != prior.name
            or _hash(prior.read_bytes()) != inventory["previous"]["sha256"]
        ):
            raise ValueError("Earlier-round snapshot changed; prepare a new run.")
    return inventory


def validate_positions(run_dir: Path, review: dict[str, Any]) -> dict[str, Any]:
    """Enforce exact identity/coverage and quotes, never grouping or legal judgment."""
    inventory = _read_inventory(run_dir)
    schema = _load(Path(__file__).with_name("legal_negotiation.schema.json"))
    errors = [
        f"{e.json_path}: {e.message}"
        for e in Draft202012Validator(schema).iter_errors(review)
    ]
    if errors:
        return {
            "valid": False,
            "accounted": False,
            "errors": errors,
            "limitations": inventory["limitations"],
        }
    if review["inventory_sha256"] != _hash(
        (run_dir / "negotiation-inventory.json").read_bytes()
    ):
        errors.append("Review is bound to a different inventory.")
    context_schema = _load(
        Path(__file__).with_name("legal_documents_review.schema.json")
    )["properties"]["context"]
    errors.extend(
        f"context.{e.json_path}: {e.message}"
        for e in Draft202012Validator(context_schema).iter_errors(review["context"])
    )
    position_ids = [p["id"] for p in review["positions"]]
    if len(position_ids) != len(set(position_ids)):
        errors.append("Position IDs must be unique.")
    assigned = [cid for p in review["positions"] for cid in p["change_ids"]]
    assigned.extend(item["change_id"] for item in review["other_changes"])
    expected = {c["id"] for c in inventory["changes"]}
    counts = Counter(assigned)
    missing = sorted(expected - set(counts))
    unknown = sorted(set(counts) - expected)
    repeated = sorted(cid for cid, n in counts.items() if n != 1)
    if missing or unknown or repeated:
        errors.append(
            f"Every revision must be assigned exactly once: missing={missing}, unknown={unknown}, repeated={repeated}."
        )
    comment_ids = [item["comment_id"] for item in review["comment_reviews"]]
    if Counter(comment_ids) != Counter(c["id"] for c in inventory["comments"]):
        errors.append(
            "Review every comment exactly once, including unanchored comments."
        )
    for item in review["comment_reviews"]:
        if set(item["position_ids"]) - set(position_ids):
            errors.append(f"{item['comment_id']}: unknown position reference.")
    units = {
        (s["id"], u["anchor"]): u["text"]
        for s in read_pack(run_dir)["sources"]
        for u in s["units"]
    }
    for position in review["positions"]:
        if review["response_mode"] == "blank" and position["response"]:
            errors.append(
                f"{position['id']}: leave the response blank unless requested by the user."
            )
        for citation in position["citations"]:
            text = units.get((citation["source_id"], citation["anchor"]), "")
            quote = " ".join(citation["quote"].split())
            if not quote or quote not in " ".join(text.split()):
                errors.append(
                    f"{position['id']}: quotation not found at its source anchor."
                )
    if (
        review["response_mode"] == "user_requested"
        and not review["response_request"].strip()
    ):
        errors.append("Record the user's response instruction.")
    if inventory["previous"] is None:
        if review["round_comparison"]:
            errors.append("Round comparison needs a selected earlier review.")
    else:
        prior = _load(run_dir / "negotiation-prior.json")
        old = [
            pid
            for row in review["round_comparison"]
            for pid in row["previous_position_ids"]
        ]
        new = [
            pid
            for row in review["round_comparison"]
            for pid in row["current_position_ids"]
        ]
        if Counter(old) != Counter(p["id"] for p in prior["positions"]) or Counter(
            new
        ) != Counter(position_ids):
            errors.append(
                "Round comparison must retain every earlier and current position exactly once."
            )
    limits = list(inventory["limitations"]) + review["limitations"]
    if not review["original_inspected"]:
        limits.append("Original inspection is not declared complete.")
    if review["visual_review"]["status"] != "complete":
        limits.append(
            "Visual review is pending; counts do not establish layout or legal effect."
        )
    elif not review["visual_review"]["evidence"].strip():
        errors.append("Completed visual review needs the inspected file/pages.")
    if inventory["previous"] is not None:
        limits.append(inventory["previous"]["provenance"])
    return {
        "valid": not errors,
        "accounted": not errors,
        "errors": errors,
        "limitations": list(dict.fromkeys(limits)),
        "counts": {
            "revisions": len(expected),
            "positions": len(position_ids),
            "position_revisions": sum(
                len(p["change_ids"]) for p in review["positions"]
            ),
            "other_revisions": len(review["other_changes"]),
            "unaccounted": len(missing),
            "comments": len(inventory["comments"]),
        },
        "meaning": "Exact declared accounting of retained Word markup; not proof of legal correctness, model attention or professional approval.",
    }


def _withdraw(run_dir: Path) -> None:
    names = (
        "negotiation.html",
        "negotiation.xlsx",
        "negotiation.csv",
        "negotiation-receipt.json",
        "negotiation-reviewed.json",
    )
    version = 1
    while any((run_dir / f"previous-{version}-{name}").exists() for name in names):
        version += 1
    for name in names:
        path = run_dir / name
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ValueError("Negotiation outputs must be ordinary local files.")
        if path.exists():
            path.rename(run_dir / f"previous-{version}-{name}")


def render_positions(run_dir: Path, review_path: Path, product: str = "Lucia") -> Path:
    """Render a concise position table plus the complete revision/comment ledger."""
    _withdraw(run_dir)
    _write(
        run_dir / "negotiation-validation.json",
        {
            "valid": False,
            "accounted": False,
            "errors": ["Current review has not completed validation."],
            "limitations": [],
        },
    )
    review = _load(review_path)
    validation = validate_positions(run_dir, review)
    _write(run_dir / "negotiation-validation.json", validation)
    if not validation["valid"]:
        raise ValueError(
            "Negotiation accounting failed: " + "; ".join(validation["errors"])
        )
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font

    language = review["context"].get("language", "it")
    labels = _load(Path(__file__).with_name("legal_negotiation_labels.json"))[language]
    inventory = _read_inventory(run_dir)
    esc = lambda value: html.escape(str(value), quote=True)
    columns = [
        labels[k] for k in ("position", "effect", "clauses", "count", "response")
    ]
    rows = [
        [
            p["title"] + "\n" + p["grouping_reason"],
            p["effect"],
            "\n".join(
                f"{c['source_id']} · {c['anchor']} · {c['quote']}"
                for c in p["citations"]
            ),
            len(p["change_ids"]),
            p["response"],
        ]
        for p in review["positions"]
    ]
    assignments = {cid: p["id"] for p in review["positions"] for cid in p["change_ids"]}
    assignments.update(
        {
            c["change_id"]: labels["other"] + ": " + c["reason"]
            for c in review["other_changes"]
        }
    )
    ledger = [
        [
            c["id"],
            c["kind"],
            c["paragraph_anchor"] or c["locator"],
            c["attributes"].get("author", ""),
            c["attributes"].get("date", c["attributes"].get("dateUtc", "")),
            c["text"],
            assignments[c["id"]],
        ]
        for c in inventory["changes"]
    ]
    comment_review = {c["comment_id"]: c for c in review["comment_reviews"]}
    comments = [
        [
            c["id"],
            c["attributes"].get("author", ""),
            "\n".join(c["anchors"]),
            c["text"],
            comment_review[c["id"]]["analysis"],
            ", ".join(comment_review[c["id"]]["position_ids"]),
        ]
        for c in inventory["comments"]
    ]
    rounds = [
        [
            ", ".join(r["previous_position_ids"]),
            ", ".join(r["current_position_ids"]),
            r["status"],
            r["analysis"],
        ]
        for r in review["round_comparison"]
    ]
    counts = validation["counts"]
    summary = labels["summary"].format(**counts)

    def table(headers: list[str], values: list[list[Any]]) -> str:
        heading = "".join(f"<th scope='col'>{esc(c)}</th>" for c in headers)
        body = "".join(
            "<tr>" + "".join(f"<td>{esc(v)}</td>" for v in row) + "</tr>"
            for row in values
        )
        return f"<div class='table-scroll'><table><thead><tr>{heading}</tr></thead><tbody>{body}</tbody></table></div>"

    sections = f"<h2>{esc(labels['positions'])}</h2>" + table(columns, rows)
    sections += f"<h2>{esc(labels['ledger'])}</h2>" + table(
        [
            labels[k]
            for k in ("id", "kind", "anchor", "author", "date", "text", "assignment")
        ],
        ledger,
    )
    sections += f"<h2>{esc(labels['comments'])}</h2>" + table(
        [labels[k] for k in ("id", "author", "anchor", "text", "analysis", "position")],
        comments,
    )
    if inventory["previous"] is not None:
        sections += f"<h2>{esc(labels['rounds'])}</h2>" + table(
            [labels[k] for k in ("previous", "current", "status", "analysis")], rounds
        )
    sections += (
        f"<h2>{esc(labels['limits'])}</h2><ul>"
        + "".join(f"<li>{esc(v)}</li>" for v in validation["limitations"])
        + "</ul>"
    )
    sections += f"<p>{esc(labels['meaning'])}</p>"
    source_name = inventory["source_name"]
    page = f"""<!doctype html><html lang='{esc(language)}'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'><title>{esc(labels['title'])}</title>
<style>{_font_css()}body{{margin:0;background:#fff;color:#172b4d;font:16px/1.55 'Instrument Sans',sans-serif}}main{{max-width:1200px;margin:auto;padding:clamp(24px,5vw,64px)}}header{{border-bottom:1px solid #ccd5df;padding-bottom:24px}}h1{{font-size:clamp(28px,4vw,42px);line-height:1.15;max-width:26ch}}h2{{margin-top:40px;font-size:22px}}.source{{color:#46556a;overflow-wrap:anywhere}}.table-scroll{{overflow:auto}}table{{width:100%;border-collapse:collapse;font-size:14px}}th,td{{padding:14px 12px;border-bottom:1px solid #d5dde5;text-align:left;vertical-align:top;white-space:pre-wrap;min-width:110px;overflow-wrap:anywhere}}th{{border-top:1px solid #9baec2;font-weight:600}}@media print{{main{{padding:0}}.table-scroll{{overflow:visible}}table{{font-size:10px}}th,td{{min-width:0;padding:8px}}}}</style></head>
<body><main><header><p>{esc(product)}</p><h1>{esc(labels['title'])}</h1><p class='source'>{esc(source_name)}</p><p>{esc(summary)}</p></header>{sections}</main></body></html>"""
    workbook = Workbook()
    workbook.remove(workbook.active)
    sheets = [
        (labels["positions"], columns, rows),
        (
            labels["ledger"],
            [
                labels[k]
                for k in (
                    "id",
                    "kind",
                    "anchor",
                    "author",
                    "date",
                    "text",
                    "assignment",
                )
            ],
            ledger,
        ),
        (
            labels["comments"],
            [
                labels[k]
                for k in ("id", "author", "anchor", "text", "analysis", "position")
            ],
            comments,
        ),
    ]
    if inventory["previous"] is not None:
        sheets.append(
            (
                labels["rounds"],
                [labels[k] for k in ("previous", "current", "status", "analysis")],
                rounds,
            )
        )
    sheets.append(
        (
            labels["limits"],
            [labels["source"], labels["analysis"]],
            [
                [source_name, summary],
                [inventory["source_sha256"], labels["meaning"]],
                *[["", v] for v in validation["limitations"]],
            ],
        )
    )
    for title, headers, values in sheets:
        sheet = workbook.create_sheet(title[:31])
        sheet.append(headers)
        for row in values:
            sheet.append(row)
        for row in sheet:
            for cell in row:
                if isinstance(cell.value, str):
                    cell.data_type = (
                        "s"  # Document text must never become an Excel formula.
                    )
                cell.font = Font(name="Instrument Sans", size=11, bold=cell.row == 1)
                cell.alignment = Alignment(vertical="top", wrap_text=True)
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for column in sheet.columns:
            sheet.column_dimensions[column[0].column_letter].width = 35
    workbook.save(run_dir / "negotiation.xlsx")
    with (run_dir / "negotiation.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        for row in rows:
            writer.writerow(
                [
                    (
                        "'" + v
                        if isinstance(v, str)
                        and v.lstrip().startswith(("=", "+", "-", "@"))
                        else v
                    )
                    for v in row
                ]
            )
    target = run_dir / "negotiation.html"
    target.write_text(page, encoding="utf-8")
    (run_dir / "negotiation-reviewed.json").write_bytes(review_path.read_bytes())
    _write(
        run_dir / "negotiation-receipt.json",
        {
            "review_sha256": _hash(review_path.read_bytes()),
            "inventory_sha256": review["inventory_sha256"],
            "outputs": {
                n: _hash((run_dir / n).read_bytes())
                for n in (
                    "negotiation.html",
                    "negotiation.xlsx",
                    "negotiation.csv",
                    "negotiation-reviewed.json",
                )
            },
        },
    )
    return target


def verify_delivery(run_dir: Path) -> dict[str, Any]:
    """Recheck the delivered review and exact retained output bytes."""
    receipt = _load(run_dir / "negotiation-receipt.json")
    required = {
        "negotiation.html",
        "negotiation.xlsx",
        "negotiation.csv",
        "negotiation-reviewed.json",
    }
    if set(receipt["outputs"]) != required:
        raise ValueError("Negotiation delivery has incomplete output bindings.")
    for name, digest in receipt["outputs"].items():
        if _hash((run_dir / name).read_bytes()) != digest:
            raise ValueError(f"Negotiation delivery changed: {name}")
    reviewed = run_dir / "negotiation-reviewed.json"
    if _hash(reviewed.read_bytes()) != receipt["review_sha256"]:
        raise ValueError("Negotiation review snapshot changed.")
    review = _load(reviewed)
    if review["inventory_sha256"] != receipt["inventory_sha256"]:
        raise ValueError("Negotiation delivery has a foreign inventory binding.")
    validation = validate_positions(run_dir, review)
    if not validation["valid"]:
        raise ValueError("Retained negotiation review no longer passes accounting.")
    return validation


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("scaffold")
    prepare.add_argument("--run-dir", type=Path, required=True)
    prepare.add_argument("--source", required=True)
    prepare.add_argument("--previous-review", type=Path)
    render = sub.add_parser("render")
    render.add_argument("--run-dir", type=Path, required=True)
    render.add_argument("--review", type=Path, required=True)
    render.add_argument("--product", choices=("Vera", "Lucia"), default="Lucia")
    verify = sub.add_parser("verify")
    verify.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        if args.command == "verify":
            validation = verify_delivery(args.run_dir)
            LOGGER.info("%s", json.dumps(validation, ensure_ascii=False))
            return 0
        path = (
            scaffold(args.run_dir, args.source, args.previous_review)
            if args.command == "scaffold"
            else render_positions(args.run_dir, args.review, args.product)
        )
    except (OSError, ValueError, zipfile.BadZipFile, ET.XMLSyntaxError) as error:
        LOGGER.error("Negotiation review failed: %s", error)
        return 1
    LOGGER.info("%s", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
