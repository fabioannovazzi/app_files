"""Inspect Word evidence locally. Structural facts are not semantic findings."""

from __future__ import annotations

import hashlib
import posixpath
import re
import zipfile
from pathlib import Path
from typing import Any

from lxml import etree as ET

__all__ = ["inspect_docx", "paragraph_text", "parse_xml", "story_parts"]

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG = "{http://schemas.openxmlformats.org/package/2006/relationships}"
STORY = re.compile(
    r"word/(document|footnotes|endnotes|comments|header\d+|footer\d+)\.xml"
)
REVISIONS = {
    "ins",
    "del",
    "moveFrom",
    "moveTo",
    "pPrChange",
    "rPrChange",
    "tblPrChange",
    "sectPrChange",
}


def parse_xml(data: bytes) -> Any:
    """Reject entity declarations; never resolve document-controlled resources."""
    if b"<!DOCTYPE" in data.upper():
        raise ValueError("Document XML must not contain a DTD.")
    root = ET.fromstring(
        data, parser=ET.XMLParser(resolve_entities=False, no_network=True)
    )
    if root.getroottree().docinfo.doctype:
        raise ValueError("Document XML must not contain a DTD.")
    return root


def story_parts(archive: zipfile.ZipFile) -> list[str]:
    """Return ordinary Word stories, retaining stable XML paragraph anchors."""
    names = archive.namelist()
    # Fixed bounds prevent archive expansion attacks; oversize files fail explicitly.
    if len(names) != len(set(names)):
        raise ValueError("Duplicate DOCX archive entries are ambiguous.")
    if sum(info.file_size for info in archive.infolist()) > 512 * 1024 * 1024:
        raise ValueError("DOCX expands beyond the 512 MiB inspection limit.")
    if "word/document.xml" not in names:
        raise ValueError("DOCX has no main document part.")
    return sorted(name for name in names if STORY.fullmatch(name))


def paragraph_text(node: Any, view: str = "final") -> str:
    """Read one paragraph's text without mixing opposing revision views.

    Paragraph-mark/structural revisions still require the original artifact;
    this provides text-level original/final views, not Word's layout engine.
    """
    if view not in {"original", "final", "all"}:
        raise ValueError("Choose original, final or all revision text.")
    omit = {
        W + tag
        for tag in (("del", "moveFrom") if view == "final" else ("ins", "moveTo"))
    }
    pieces: list[str] = []

    def visit(element: Any) -> None:
        if element is not node and element.tag == W + "p":
            return  # Text-box paragraphs have their own anchors.
        if view != "all" and element.tag in omit:
            return
        if element.tag in {W + "t", W + "delText"}:
            pieces.append(element.text or "")
        elif element.tag == W + "tab":
            pieces.append("\t")
        elif element.tag in {W + "br", W + "cr"}:
            pieces.append("\n")
        elif element.tag == W + "noBreakHyphen":
            pieces.append("\u2011")
        elif element.tag == W + "softHyphen":
            pieces.append("\u00ad")
        else:
            for child in element:
                visit(child)

    visit(node)
    return "".join(pieces)


def _attributes(element: Any) -> dict[str, str]:
    return {ET.QName(key).localname: value for key, value in element.attrib.items()}


def _properties(parent: Any, name: str) -> list[dict[str, Any]]:
    element = parent.find(W + name)
    return (
        []
        if element is None
        else [
            {
                "property": ET.QName(child).localname,
                "attributes": _attributes(child),
                "xml": ET.tostring(child, encoding="unicode"),
            }
            for child in element
        ]
    )


def _relationships(archive: zipfile.ZipFile, part: str) -> dict[str, dict[str, str]]:
    directory, name = posixpath.split(part)
    rels = posixpath.join(directory, "_rels", name + ".rels")
    if rels not in archive.namelist():
        return {}
    return {
        element.get("Id"): dict(element.attrib)
        for element in parse_xml(archive.read(rels))
        if element.tag == PKG + "Relationship"
    }


def inspect_docx(path: Path) -> dict[str, Any]:
    """Expose text, revision views and hidden structure for model-led auditing."""
    result: dict[str, Any] = {
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "paragraphs": [],
        "comments": [],
        "styles": [],
        "numbering": [],
        "properties": {},
        "warnings": [],
        "text_view": "final",
    }
    with zipfile.ZipFile(path) as archive:
        parts = story_parts(archive)
        names = archive.namelist()
        result["signed"] = any(name.startswith("_xmlsignatures/") for name in names)
        if result["signed"]:
            result["warnings"].append(
                "Signed package: changes invalidate signatures; editing is disabled."
            )
        result["protection_enforced"] = False
        if "word/settings.xml" in names:
            settings = parse_xml(archive.read("word/settings.xml"))
            protection = settings.find(W + "documentProtection")
            if protection is not None:
                result["protection_enforced"] = protection.get(
                    W + "enforcement", "false"
                ).lower() in {"1", "true", "on"}
                if result["protection_enforced"]:
                    result["warnings"].append(
                        "Document protection is enforced; obtain an appropriate "
                        "editable source before authoring changes."
                    )
        for part in parts:
            root = parse_xml(archive.read(part))
            relationships = _relationships(archive, part)
            for number, paragraph in enumerate(root.iter(W + "p"), 1):
                anchor = f"{part}#p{number}"
                runs = []
                links = []
                revisions = []
                fields = []
                unpreserved_whitespace = []
                for node in paragraph.iter():
                    # A nested text-box paragraph is inspected independently.
                    owner = next(
                        (p for p in node.iterancestors() if p.tag == W + "p"), None
                    )
                    if node is not paragraph and owner is not paragraph:
                        continue
                    if node.tag == W + "r":
                        runs.append(
                            {
                                "text": paragraph_text(node, "all"),
                                "properties": _properties(node, "rPr"),
                                "revision_ancestors": [
                                    ET.QName(p).localname
                                    for p in node.iterancestors()
                                    if p.tag in {W + n for n in REVISIONS}
                                ],
                            }
                        )
                    elif node.tag == W + "hyperlink":
                        rid = node.get(R + "id")
                        links.append(
                            {
                                "text": paragraph_text(node),
                                "relationship_id": rid,
                                "bookmark": node.get(W + "anchor"),
                                "relationship": relationships.get(rid, {}),
                            }
                        )
                    elif node.tag in {W + n for n in REVISIONS}:
                        revisions.append(
                            {
                                "type": ET.QName(node).localname,
                                **_attributes(node),
                                "text": paragraph_text(node, "all"),
                            }
                        )
                    elif node.tag in {W + "instrText", W + "fldSimple"}:
                        fields.append(
                            {
                                "type": ET.QName(node).localname,
                                "instruction": node.get(W + "instr", node.text or ""),
                            }
                        )
                    elif node.tag in {W + "t", W + "delText"}:
                        value = node.text or ""
                        space = next(
                            (
                                parent.get(
                                    "{http://www.w3.org/XML/1998/namespace}space"
                                )
                                for parent in [node, *node.iterancestors()]
                                if parent.get(
                                    "{http://www.w3.org/XML/1998/namespace}space"
                                )
                                is not None
                            ),
                            None,
                        )
                        if value != value.strip(" \t\r\n") and space != "preserve":
                            unpreserved_whitespace.append(value)
                record = {
                    "anchor": anchor,
                    "text": paragraph_text(paragraph),
                    "original_text": paragraph_text(paragraph, "original"),
                    "runs": runs,
                    "hyperlinks": links,
                    "fields": fields,
                    "revisions": revisions,
                    "unpreserved_whitespace": unpreserved_whitespace,
                    "properties": _properties(paragraph, "pPr"),
                    "bookmarks": [
                        _attributes(n) for n in paragraph.iter(W + "bookmarkStart")
                    ],
                    "comment_ids": [
                        n.get(W + "id") for n in paragraph.iter(W + "commentReference")
                    ],
                    "in_table": any(
                        n.tag == W + "tc" for n in paragraph.iterancestors()
                    ),
                }
                result["paragraphs"].append(record)
            for comment in root.iter(W + "comment"):
                result["comments"].append(
                    {
                        **_attributes(comment),
                        "part": part,
                        "text": "\n".join(
                            paragraph_text(p) for p in comment.iter(W + "p")
                        ),
                    }
                )
            if any(
                n.tag in {W + "drawing", W + "pict", W + "object", W + "altChunk"}
                for n in root.iter()
            ):
                result["warnings"].append(
                    f"{part}: objects/images require visual inspection; their meaning is not extracted."
                )
            if any(
                n.tag
                in {
                    W + "pPrChange",
                    W + "rPrChange",
                    W + "sectPrChange",
                    W + "tblPrChange",
                }
                for n in root.iter()
            ):
                result["warnings"].append(
                    f"{part}: structural or formatting revisions require artifact inspection."
                )
            if any(
                n.tag in {W + "ins", W + "del"}
                and any(p.tag == W + "pPr" for p in n.iterancestors())
                for n in root.iter()
            ):
                result["warnings"].append(
                    f"{part}: paragraph-mark revisions affect joins/numbering; text views do not simulate layout."
                )
        for part in ("docProps/core.xml", "docProps/app.xml", "docProps/custom.xml"):
            if part in names:
                result["properties"][part] = ET.tostring(
                    parse_xml(archive.read(part)), encoding="unicode"
                )
        for part, key, tag in (
            ("word/styles.xml", "styles", "style"),
            ("word/numbering.xml", "numbering", None),
        ):
            if part in names:
                root = parse_xml(archive.read(part))
                nodes = list(root.iter(W + tag)) if tag else list(root)
                result[key] = [
                    {
                        "attributes": _attributes(node),
                        "xml": ET.tostring(node, encoding="unicode"),
                    }
                    for node in nodes
                ]
                if key == "styles":
                    defaults = root.find(W + "docDefaults")
                    result["style_defaults"] = (
                        ET.tostring(defaults, encoding="unicode")
                        if defaults is not None
                        else ""
                    )
        result["warnings"].append(
            "Text views and style metadata do not verify rendered layout, signature validity or legal correctness."
        )
    return result
