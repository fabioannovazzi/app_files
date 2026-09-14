"""Prepare local PDF text/pages and image evidence without inferring fields."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import fitz
from invoice_workflow import _context, _json, _regular, _within, _write_new, digest

__all__ = ["prepare_source_evidence", "main"]


def prepare_source_evidence(
    selection: list[dict[str, str]], *, input_root: Path, output_dir: Path
) -> Path:
    """Retain every selected page; extraction completeness never implies truth."""
    if not selection:
        raise ValueError("Select at least one bound source")
    captured = []
    ids: set[str] = set()
    for source in selection:
        if source["id"] in ids:
            raise ValueError("Duplicate source ID")
        ids.add(source["id"])
        path = _within(input_root, source["path"])
        payload = _regular(path)
        suffix = path.suffix.lower()
        if suffix not in {
            ".pdf",
            ".png",
            ".jpg",
            ".jpeg",
            ".webp",
            ".json",
            ".txt",
        }:
            raise ValueError(
                "Unsupported source format; preserve it and request readable evidence"
            )
        captured.append(
            (dict(source, sha256=hashlib.sha256(payload).hexdigest()), payload, suffix)
        )
    sources = [source for source, _, _ in captured]
    folder = _within(output_dir, f"intake-{digest(sources)}")
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    material = []
    for source, payload, suffix in captured:
        key = source["sha256"]
        views = []
        if suffix == ".pdf":
            with fitz.open(stream=payload, filetype="pdf") as document:
                if document.needs_pass or document.page_count > 100:
                    raise ValueError(
                        "Encrypted or over-100-page PDF; select a bounded readable document"
                    )
                for index, page in enumerate(document):
                    if page.rect.width * page.rect.height * 2.25 > 25_000_000:
                        raise ValueError(
                            "Oversized PDF page; select a bounded readable document"
                        )
                    text_name = f"{key}-page-{index + 1}.txt"
                    image_name = f"{key}-page-{index + 1}.png"
                    _write_new(folder / text_name, page.get_text().encode())
                    _write_new(
                        folder / image_name,
                        page.get_pixmap(
                            matrix=fitz.Matrix(1.5, 1.5), alpha=False
                        ).tobytes("png"),
                    )
                    views.append(
                        {"page": index + 1, "text": text_name, "image": image_name}
                    )
        else:
            name = key + suffix
            _write_new(folder / name, payload)
            views.append(
                {
                    "page": 1,
                    "image" if suffix not in {".txt", ".json"} else "text": name,
                }
            )
        material.append({"source_id": source["id"], "views": views})
    _write_new(
        folder / "source_evidence.json",
        _json(
            {
                "schema_version": 1,
                "sources": sources,
                "material": material,
                "interpretation_status": "awaiting_model_extraction",
                "model_visibility": "Record pages actually read in the run-level model-data report; this inventory does not prove model exposure.",
            }
        ),
    )
    return folder


def main(argv: list[str] | None = None) -> int:
    """Prepare evidence only inside the selected Studio Archive run."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-engagement", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    args = parser.parse_args(argv)
    context = _context(args.client_engagement, args.output)
    if not args.selection.resolve().is_relative_to(args.output.resolve()):
        raise ValueError("Save source selection in this run's output directory")
    result = prepare_source_evidence(
        json.loads(_regular(args.selection)),
        input_root=Path(context["input_dir"]),
        output_dir=args.output,
    )
    logging.info("Source evidence ready for interpretation: %s", result)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
