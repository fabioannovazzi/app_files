from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

__all__ = [
    "BriefLine",
    "extract_brief_lines_from_docx",
    "extract_brief_lines_from_markdown",
    "normalize_numeric_text",
    "strip_markdown_line",
]

_WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


@dataclass(frozen=True, slots=True)
class BriefLine:
    line_number: int
    raw: str
    text: str
    is_heading: bool


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def normalize_numeric_text(text: str) -> str:
    normalized = (text or "").replace("−", "-")
    normalized = re.sub(r"(?<=\d),(?=\d{3}\b)", "", normalized)
    normalized = re.sub(r"(?<=\d)\s+%", "%", normalized)
    return normalized


def strip_markdown_line(line: str) -> str:
    text = (line or "").rstrip("\n")
    text = re.sub(r"^\s*#{1,6}\s*", "", text)
    text = re.sub(r"\s*#+\s*$", "", text)
    text = re.sub(r"^\s*>\s*", "", text)
    text = re.sub(r"^\s*(?:[-*+]|\d+\.)\s+", "", text)
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"~~(.*?)~~", r"\1", text)
    text = re.sub(r"(\*\*|__)(.*?)\1", r"\2", text)
    text = re.sub(r"(\*|_)(.*?)\1", r"\2", text)
    text = re.sub(r"<[^>]+>", "", text)
    return text


def extract_brief_lines_from_markdown(markdown_text: str) -> list[BriefLine]:
    lines = (markdown_text or "").splitlines()
    extracted: list[BriefLine] = []
    for line_number, raw in enumerate(lines, start=1):
        is_heading = bool(re.match(r"^\s*#{1,6}\s+", raw))
        stripped = strip_markdown_line(raw)
        extracted.append(
            BriefLine(
                line_number=line_number,
                raw=raw,
                text=_normalize_whitespace(stripped),
                is_heading=is_heading,
            )
        )
    return extracted


def extract_brief_lines_from_docx(docx_path: Path) -> list[BriefLine]:
    docx_path = Path(docx_path)
    with zipfile.ZipFile(docx_path) as archive:
        xml_bytes = archive.read("word/document.xml")

    root = etree.fromstring(xml_bytes)
    lines: list[BriefLine] = []
    line_number = 0
    for para in root.xpath(".//w:p", namespaces=_WORD_NS):
        style_vals = para.xpath("./w:pPr/w:pStyle/@w:val", namespaces=_WORD_NS)
        is_heading = bool(style_vals and style_vals[0].lower().startswith("heading"))
        chunks: list[str] = []
        for node in para.xpath(".//w:t | .//w:tab | .//w:br", namespaces=_WORD_NS):
            if node.tag.endswith("}t"):
                chunks.append(node.text or "")
            elif node.tag.endswith("}tab"):
                chunks.append(" ")
            elif node.tag.endswith("}br"):
                chunks.append(" ")
        text = _normalize_whitespace("".join(chunks))
        if not text and not is_heading:
            continue
        line_number += 1
        lines.append(
            BriefLine(
                line_number=line_number,
                raw=text,
                text=text,
                is_heading=is_heading,
            )
        )
    return lines
