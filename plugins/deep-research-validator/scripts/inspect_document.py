"""Inspect a Deep Research document before Codex validates it."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

__all__ = ["inspect_document_text", "read_document_text", "write_inspection"]

URL_RE = re.compile(r"https?://[^\s)\]>\"']+", re.IGNORECASE)
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
FOOTNOTE_RE = re.compile(r"^\[\^?([A-Za-z0-9_-]+)\]:\s*(.+)$", re.MULTILINE)
CITATION_RE = re.compile(r"\[(?:\^?[A-Za-z0-9_-]+|\d+(?:,\s*\d+)*)\]")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
SENTENCE_RE = re.compile(r"[^.!?\n][^.!?\n]{30,350}[.!?]")
PDF_PRINTABLE_RE = re.compile(rb"[\x09\x0a\x0d\x20-\x7e]{16,}")


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.headings: list[str] = []
        self._heading_tag = ""
        self._heading_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._heading_tag = tag
            self._heading_text = []
        if tag == "a":
            for key, value in attrs:
                if key.lower() == "href" and value:
                    self.parts.append(f" {value} ")

    def handle_endtag(self, tag: str) -> None:
        if tag == self._heading_tag:
            heading = " ".join(self._heading_text).strip()
            if heading:
                self.headings.append(heading)
            self._heading_tag = ""
            self._heading_text = []
        if tag in {"p", "div", "br", "li", "section", "article"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        text = html.unescape(data)
        self.parts.append(text)
        if self._heading_tag:
            self._heading_text.append(text)

    def text(self) -> str:
        return re.sub(r"\n{3,}", "\n\n", "".join(self.parts)).strip()


def _ordered_unique(items: list[str], *, limit: int | None = None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        cleaned = re.sub(r"\s+", " ", item.strip().strip(".,;:()[]{}<>\"'"))
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
        if limit is not None and len(out) >= limit:
            break
    return out


def _strip_trailing_url_artifacts(url: str) -> str:
    return url.rstrip(".,;:!?)\\]}>'\"")


def _extract_text_from_pdf_bytes(raw: bytes) -> str:
    chunks = [
        chunk.decode("latin-1", errors="ignore").strip()
        for chunk in PDF_PRINTABLE_RE.findall(raw)
    ]
    return "\n".join(chunk for chunk in chunks if chunk)


def read_document_text(path: Path) -> tuple[str, str]:
    """Return extracted text and parser label for a document path."""

    suffix = path.suffix.lower()
    if suffix in {".html", ".htm"}:
        extractor = _HTMLTextExtractor()
        extractor.feed(path.read_text(encoding="utf-8", errors="ignore"))
        return extractor.text(), "html_text"
    if suffix == ".pdf":
        return _extract_text_from_pdf_bytes(path.read_bytes()), "pdf_text_heuristic"
    return path.read_text(encoding="utf-8", errors="ignore"), "plain_text"


def _headings_from_text(text: str) -> list[str]:
    markdown_headings = [match.group(2) for match in HEADING_RE.finditer(text)]
    return _ordered_unique(markdown_headings, limit=40)


def _claim_candidates(text: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for index, sentence in enumerate(SENTENCE_RE.findall(text), start=1):
        sentence = re.sub(r"\s+", " ", sentence).strip()
        has_reference = bool(URL_RE.search(sentence) or CITATION_RE.search(sentence))
        has_claim_signal = bool(
            re.search(
                r"\b(is|are|was|were|must|should|therefore|because|increase|decrease|applies|equals|exceeds|results?)\b",
                sentence,
                flags=re.IGNORECASE,
            )
        )
        if has_reference or has_claim_signal:
            candidates.append(
                {
                    "candidate_index": len(candidates) + 1,
                    "text": sentence,
                    "has_reference_marker": has_reference,
                }
            )
        if len(candidates) >= 80:
            break
    return candidates


def inspect_document_text(
    text: str,
    *,
    parser: str = "plain_text",
    source_name: str = "",
) -> dict[str, Any]:
    """Build deterministic document inventory from extracted text."""

    normalized = text.strip()
    links = [
        {
            "label": match.group(1).strip(),
            "url": _strip_trailing_url_artifacts(match.group(2)),
        }
        for match in MARKDOWN_LINK_RE.finditer(normalized)
    ]
    footnotes = [
        {"id": match.group(1), "text": match.group(2).strip()}
        for match in FOOTNOTE_RE.finditer(normalized)
    ]
    urls = _ordered_unique(
        [_strip_trailing_url_artifacts(url) for url in URL_RE.findall(normalized)],
        limit=200,
    )
    citations = _ordered_unique(CITATION_RE.findall(normalized), limit=200)
    return {
        "source_name": source_name,
        "parser": parser,
        "text_hash": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        "character_count": len(normalized),
        "word_count": len(re.findall(r"\S+", normalized)),
        "headings": _headings_from_text(normalized),
        "urls": urls,
        "markdown_links": links,
        "footnotes": footnotes,
        "citation_markers": citations,
        "mechanical_claim_candidates": _claim_candidates(normalized),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_inspection(document_path: Path, output_dir: Path) -> dict[str, Path]:
    """Write document inventory and extracted text artifacts."""

    text, parser = read_document_text(document_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    inventory = inspect_document_text(
        text,
        parser=parser,
        source_name=document_path.name,
    )
    text_path = output_dir / "extracted_document.md"
    inventory_path = output_dir / "document_inventory.json"
    text_path.write_text(text.strip() + "\n", encoding="utf-8")
    _write_json(inventory_path, inventory)
    return {"extracted_document": text_path, "document_inventory": inventory_path}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document", type=Path, help="Deep Research document path.")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if not args.document.exists():
        parser.error(f"document does not exist: {args.document}")
    write_inspection(args.document, args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
