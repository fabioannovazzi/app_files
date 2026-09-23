"""Verify files authored by the host Documents/Word skill; never edit Word here."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

from legal_docx import PKG, W, inspect_docx, parse_xml

__all__ = ["verify_word_result", "main"]

LOGGER = logging.getLogger(__name__)


def _span(text: str, edit: dict[str, Any]) -> tuple[int, int]:
    old = edit["old"]
    start = edit.get("start")
    if start is None:
        if not old or text.count(old) != 1:
            raise ValueError(
                "An ambiguous quote or insertion needs an explicit start offset."
            )
        start = text.index(old)
    if (
        type(start) is not int
        or start < 0
        or start > len(text)
        or text[start : start + len(old)] != old
    ):
        raise ValueError("The requested edit does not match the selected paragraph.")
    return start, start + len(old)


def _revision_keys(inspection: dict[str, Any]) -> set[tuple[str, str, str]]:
    return {
        (paragraph["anchor"].split("#")[0], revision["type"], revision.get("id", ""))
        for paragraph in inspection["paragraphs"]
        for revision in paragraph["revisions"]
    }


def verify_word_result(
    original: Path, result: Path, request: dict[str, Any]
) -> dict[str, Any]:
    """Verify anchored text changes, native revisions, comments and package scope.

    Exact hashes and text round trips are mechanically verifiable contracts.
    They do not replace the document skill's rendering or the lawyer's judgment.
    """
    if original.resolve() == result.resolve():
        raise ValueError("The result must be a separate file; preserve the original.")
    before = inspect_docx(original)
    after = inspect_docx(result)
    if before["signed"]:
        raise ValueError(
            "A signed original needs a separately authorized unsigned editing source."
        )
    if before["protection_enforced"]:
        raise ValueError(
            "The original has enforced document protection; obtain an appropriate "
            "editable source instead of removing protection."
        )
    if request.get("source_sha256") != before["sha256"]:
        raise ValueError("Word request does not match the original source hash.")
    if request.get("mode") not in {"tracked", "clean"}:
        raise ValueError("Declare tracked or clean output mode.")
    edits = request.get("edits")
    if not isinstance(edits, list) or not edits:
        raise ValueError("Supply the reviewed edits or comments to verify.")
    previous = {
        p["anchor"]: p
        for p in before["paragraphs"]
        if not p["anchor"].startswith("word/comments.xml")
    }
    current = {
        p["anchor"]: p
        for p in after["paragraphs"]
        if not p["anchor"].startswith("word/comments.xml")
    }
    grouped: dict[str, list[dict[str, Any]]] = {}
    for edit in edits:
        if not isinstance(edit, dict) or edit.get("kind") not in {"replace", "comment"}:
            raise ValueError("Each edit declares replace or comment.")
        for key in ("id", "anchor", "basis"):
            if not isinstance(edit.get(key), str) or not edit[key].strip():
                raise ValueError(f"Each edit needs {key}.")
        if edit["anchor"] not in previous or not isinstance(edit.get("old"), str):
            raise ValueError("Use an original paragraph anchor and quoted old text.")
        field = "new" if edit["kind"] == "replace" else "comment"
        if not isinstance(edit.get(field), str) or (
            field == "comment" and not edit[field].strip()
        ):
            raise ValueError(f"Edit needs {field} text.")
        grouped.setdefault(edit["anchor"], []).append(edit)
    if len({e["id"] for e in edits}) != len(edits):
        raise ValueError("Edit IDs must be unique.")
    errors: list[str] = []
    checks = []
    if set(previous) != set(current):
        errors.append(
            "Paragraph structure changed. This verifier covers inline edits; a structural document edit needs a separate explicit comparison and visual review."
        )
    existing_revisions = _revision_keys(before)
    after_comments = {c["id"]: c for c in after["comments"]}
    if len(after_comments) != len(after["comments"]):
        errors.append("Duplicate Word comment identifiers.")
    revision_ids = [
        (p["anchor"].split("#")[0], r.get("id"))
        for p in after["paragraphs"]
        for r in p["revisions"]
    ]
    if any(cid is None for _, cid in revision_ids) or len(set(revision_ids)) != len(
        revision_ids
    ):
        errors.append("Missing or duplicate Word revision identifiers.")
    for anchor, paragraph in previous.items():
        actual = current.get(anchor)
        if actual is None:
            continue
        if Counter(actual["unpreserved_whitespace"]) - Counter(
            paragraph["unpreserved_whitespace"]
        ):
            errors.append(
                f"{anchor}: new edge whitespace lacks xml:space=preserve; Word may join words."
            )
        expected = paragraph["text"]
        replacements = []
        for edit in grouped.get(anchor, []):
            start, end = _span(paragraph["text"], edit)
            if edit["kind"] == "replace":
                replacements.append((start, end, edit))
            else:
                matched = any(
                    after_comments.get(cid, {}).get("text") == edit["comment"]
                    for cid in actual["comment_ids"]
                )
                checks.append({"id": edit["id"], "comment_anchored": matched})
                if not matched:
                    errors.append(
                        f"{edit['id']}: expected comment is not attached to the requested paragraph."
                    )
        last_start = len(expected) + 1
        for start, end, edit in sorted(
            replacements, key=lambda value: value[0], reverse=True
        ):
            if end > last_start or start == last_start:
                raise ValueError(
                    "Requested replacements overlap; resolve them before authoring."
                )
            last_start = start
            expected = expected[:start] + edit["new"] + expected[end:]
        if actual["text"] != expected:
            errors.append(f"{anchor}: proposed text differs from the reviewed changes.")
        if (
            request["mode"] == "tracked"
            and actual["original_text"] != paragraph["original_text"]
        ):
            errors.append(
                f"{anchor}: rejecting the new revisions does not retain the original text view."
            )
        for revision in paragraph["revisions"]:
            if revision not in actual["revisions"]:
                errors.append(
                    f"{anchor}: a pre-existing revision was changed or removed."
                )
        if request["mode"] == "tracked" and replacements:
            new_revisions = [
                r
                for r in actual["revisions"]
                if (anchor.split("#")[0], r["type"], r.get("id", ""))
                not in existing_revisions
            ]
            inserted = "".join(r["text"] for r in new_revisions if r["type"] == "ins")
            deleted = "".join(r["text"] for r in new_revisions if r["type"] == "del")
            for _, _, edit in replacements:
                matched = bool(
                    (not edit["old"] or edit["old"] in deleted)
                    and (not edit["new"] or edit["new"] in inserted)
                )
                checks.append({"id": edit["id"], "native_revision": matched})
                if not matched:
                    errors.append(
                        f"{edit['id']}: expected native insertion/deletion is missing."
                    )
    for comment in before["comments"]:
        if after_comments.get(comment["id"]) != comment:
            errors.append(f"Existing comment {comment['id']} was changed or removed.")
    allowed = {e["anchor"].split("#")[0] for e in edits} | {
        "word/settings.xml",
        "word/comments.xml",
        "word/_rels/document.xml.rels",
        "[Content_Types].xml",
        "docProps/core.xml",
        "docProps/app.xml",
    }
    with zipfile.ZipFile(original) as source, zipfile.ZipFile(result) as output:
        changed_parts = [
            name
            for name in sorted(set(source.namelist()) | set(output.namelist()))
            if name not in source.namelist()
            or name not in output.namelist()
            or source.read(name) != output.read(name)
        ]
        if after["comments"]:
            rels_name = "word/_rels/document.xml.rels"
            relationships = (
                parse_xml(output.read(rels_name))
                if rels_name in output.namelist()
                else []
            )
            wired = any(
                r.tag == PKG + "Relationship"
                and r.get("Type", "").endswith("/comments")
                and r.get("Target") in {"comments.xml", "/word/comments.xml"}
                and r.get("TargetMode") != "External"
                for r in relationships
            )
            content_types = parse_xml(output.read("[Content_Types].xml"))
            declared = any(
                r.get("PartName") == "/word/comments.xml"
                and r.get("ContentType")
                == "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"
                for r in content_types
            )
            if not wired or not declared:
                errors.append(
                    "Word comments are missing their package relationship or content type."
                )
            doc = parse_xml(output.read("word/document.xml"))
            starts = [n.get(W + "id") for n in doc.iter(W + "commentRangeStart")]
            ends = [n.get(W + "id") for n in doc.iter(W + "commentRangeEnd")]
            references = [n.get(W + "id") for n in doc.iter(W + "commentReference")]
            for comment in after["comments"]:
                cid = comment["id"]
                if (
                    starts.count(cid) != 1
                    or ends.count(cid) != 1
                    or references.count(cid) != 1
                ):
                    errors.append(
                        f"Comment {cid}: missing or duplicate range/reference anchors."
                    )
    unexpected = set(changed_parts) - allowed
    if unexpected:
        errors.append(
            "Unexpected changed package parts: " + ", ".join(sorted(unexpected))
        )
    return {
        "valid": not errors,
        "source_sha256": before["sha256"],
        "result_sha256": after["sha256"],
        "request_sha256": hashlib.sha256(
            json.dumps(request, sort_keys=True).encode()
        ).hexdigest(),
        "errors": errors,
        "checks": checks,
        "changed_parts": changed_parts,
        "requires_visual_review": True,
        "meaning": "Inline text/revision/comment contract verified only. The host Documents/Word skill must inspect formatting, layout and application behavior; Lucia and the lawyer review meaning.",
    }


def main(argv: list[str] | None = None) -> int:
    """Validate the document skill's output and save a durable verification result."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.report.resolve() in {
            args.original.resolve(),
            args.result.resolve(),
            args.request.resolve(),
        }:
            raise ValueError("Verification report must not overwrite its input.")
        report = verify_word_result(
            args.original,
            args.result,
            json.loads(args.request.read_text(encoding="utf-8")),
        )
        args.report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        LOGGER.info(
            "Word contract %s: %s",
            "passed" if report["valid"] else "failed",
            args.report,
        )
        return 0 if report["valid"] else 2
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as error:
        LOGGER.error("%s", error)
        return 2


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
