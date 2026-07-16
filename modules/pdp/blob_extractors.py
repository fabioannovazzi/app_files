from __future__ import annotations

import json
from json import JSONDecodeError
from typing import Iterable, Sequence

from bs4 import BeautifulSoup  # type: ignore[import]
from bs4 import FeatureNotFound  # type: ignore[import]
from json_repair import repair_json  # type: ignore[import]

from .models import EvidenceBlob
from .profile import BlobSource, PDPProfile


def _parse_json_candidates(raw: str) -> tuple:
    text = raw.strip()
    if not text:
        return ()

    def parse(snippet: str) -> tuple:
        try:
            return (json.loads(snippet),)
        except JSONDecodeError:
            try:
                repaired = repair_json(snippet)
            except Exception:
                return ()
            if not repaired:
                return ()
            try:
                return (json.loads(repaired),)
            except JSONDecodeError:
                return ()

    candidates: list = []
    candidates.extend(parse(text))
    if candidates:
        return tuple(candidates)

    if "{" in text and "}" in text:
        start = text.find("{")
        end = text.rfind("}")
        if end >= start:
            candidates.extend(parse(text[start : end + 1]))
            if candidates:
                return tuple(candidates)

    if "[" in text and "]" in text:
        start = text.find("[")
        end = text.rfind("]")
        if end >= start:
            candidates.extend(parse(text[start : end + 1]))
            if candidates:
                return tuple(candidates)

    return tuple(candidates)


def extract_blobs_from_html(html: str, sources: Sequence[BlobSource]) -> tuple[EvidenceBlob, ...]:
    """Extract JSON-like blobs according to the configured sources."""

    try:
        soup = BeautifulSoup(html, "lxml")
    except FeatureNotFound:
        # Fallback if lxml parser is not available in the environment.
        soup = BeautifulSoup(html, "html.parser")
    blobs: list[EvidenceBlob] = []

    for source_position, source in enumerate(sources):
        elements = soup.select(source.selector)
        if source.type.startswith("script"):
            for element_index, element in enumerate(elements):
                text = element.string or element.get_text()
                if not text:
                    continue
                for candidate_index, payload in enumerate(_parse_json_candidates(text)):
                    blobs.append(
                        EvidenceBlob(
                            source=source.type,
                            selector=source.selector,
                            index=len(blobs),
                            payload=payload,
                        )
                    )
        elif source.type == "dom_fallback":
            blobs.append(
                EvidenceBlob(
                    source=source.type,
                    selector=source.selector,
                    index=len(blobs),
                    payload=None,
                )
            )
        else:
            # Unknown source types are ignored, but keep a placeholder for traceability.
            blobs.append(
                EvidenceBlob(
                    source=source.type,
                    selector=source.selector,
                    index=len(blobs),
                    payload=None,
                )
            )
    return tuple(blobs)


def extract_primary_blobs(html: str, profile: PDPProfile) -> tuple[EvidenceBlob, ...]:
    return extract_blobs_from_html(html, profile.blob_sources)


__all__ = ["extract_blobs_from_html", "extract_primary_blobs"]
