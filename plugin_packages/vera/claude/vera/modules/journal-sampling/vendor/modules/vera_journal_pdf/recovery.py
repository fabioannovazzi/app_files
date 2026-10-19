"""Persistent, bounded tools for a host-agent-led PDF layout recovery loop.

The host interprets evidence and proposes recipes. These tools never call a
model, generate parser code, infer account semantics or qualify a population.
"""

from __future__ import annotations

import hashlib
import json
import re
import stat
from pathlib import Path
from typing import Any

__all__ = ["add_recovery_args", "recover_pdf", "inspect_pdf_regions"]
MAX_ATTEMPTS = 4
MAX_INSPECTIONS = 12


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()


def _file_digest(path: Path) -> str:
    entry = path.lstat()
    if not stat.S_ISREG(entry.st_mode) or entry.st_nlink != 1:
        raise ValueError("PDF recovery inputs must be ordinary single-link files")
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _identity(source: Path, currency: str) -> dict[str, Any]:
    if source.suffix.lower() != ".pdf" or not re.fullmatch(r"[A-Z]{3}", currency):
        raise ValueError(
            "Recovery requires one PDF and an explicit three-letter currency"
        )
    return {
        "source_sha256": _file_digest(source),
        "currency": currency,
        "implementation": {
            p.name: _file_digest(p) for p in sorted(Path(__file__).parent.glob("*.py"))
        },
    }


def _save(path: Path, payload: dict[str, Any]) -> None:
    # Exclusive creation preserves every predecessor; no failed attempt is replaced.
    with path.open("x", encoding="utf-8") as stream:
        stream.write(
            json.dumps(
                payload, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False
            )
            + "\n"
        )


def inspect_pdf_regions(
    source: Path,
    pages: list[int] | None = None,
    region: list[float] | None = None,
    *,
    image_dir: Path | None = None,
) -> dict[str, Any]:
    """Return at most three requested pages, bounded words/glyphs and optional renders."""
    import pdfplumber

    with pdfplumber.open(source) as document:
        count = len(document.pages)
        selected = pages if pages is not None else sorted({1, min(2, count), count})
        if (
            not selected
            or len(selected) > 3
            or len(set(selected)) != len(selected)
            or any(type(n) is not int or not 1 <= n <= count for n in selected)
        ):
            raise ValueError("Inspect one to three distinct existing PDF pages")
        samples = []
        if image_dir is not None:
            image_dir.mkdir(exist_ok=False)
        for number in selected:
            page = document.pages[number - 1]
            cropped = None
            try:
                target = page
                if region is not None:
                    from . import _coordinate

                    if len(region) != 4:
                        raise ValueError("Region needs x0, top, x1, bottom")
                    x0, top, x1, bottom = [_coordinate(v) for v in region]
                    if not (
                        0 <= x0 < x1 <= page.width and 0 <= top < bottom <= page.height
                    ):
                        raise ValueError("Inspection region is outside the page")
                    cropped = target = page.crop((x0, top, x1, bottom))
                words = target.extract_words(x_tolerance=1, y_tolerance=2)
                chars = target.chars
                sample = {
                    "page": number,
                    "width": str(page.width),
                    "height": str(page.height),
                    "word_count": len(words),
                    "character_count": len(chars),
                    "words_truncated": len(words) > 300,
                    "characters_truncated": len(chars) > 1200,
                    "words": [
                        {
                            key: str(w[key])[:100]
                            for key in ("text", "x0", "x1", "top", "bottom")
                        }
                        for w in words[:300]
                    ],
                    "characters": [
                        {
                            key: str(c[key])[:100]
                            for key in ("text", "x0", "x1", "top", "bottom")
                        }
                        for c in chars[:1200]
                    ],
                }
                if image_dir is not None:
                    image_path = image_dir / f"page-{number}.png"
                    target.to_image(resolution=110).save(image_path)
                    sample["render"] = str(image_path)
                samples.append(sample)
            finally:
                if cropped is not None:
                    cropped.close()
                page.close()
    return {
        "page_count": count,
        "sampled_pages": samples,
        "purpose": "Layout evidence only; no qualified postings",
    }


def recover_pdf(
    source: Path,
    output_dir: Path,
    action: str,
    *,
    currency: str,
    layout: dict[str, Any] | None = None,
    pages: list[int] | None = None,
    region: list[float] | None = None,
    reason: str = "",
    render: bool = False,
) -> dict[str, Any]:
    """Inspect, retain a trial, or freeze a recipe after exact full-source replay.

    Callers validate the active Studio Archive binding before entering here.
    Artifacts live below that workflow's existing output root. Neither a trial
    nor a frozen recipe replaces the normal reviewed mapping/qualification gate.
    """
    if action not in {"inspect", "trial", "freeze"}:
        raise ValueError("Unknown PDF recovery action")
    identity = _identity(source, currency)
    root = output_dir / "pdf_recovery"
    if (
        root.is_symlink()
        or any(p.is_symlink() for p in output_dir.parents)
        or output_dir.is_symlink()
    ):
        raise ValueError("Recovery output must not traverse symlinks")
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = root / "session.json"
    manifest = {
        "schema_version": "vera.pdf_recovery.v1",
        **identity,
        "max_attempts": MAX_ATTEMPTS,
    }
    if manifest_path.exists():
        _file_digest(manifest_path)
        if json.loads(manifest_path.read_text()) != manifest:
            raise ValueError(
                "Recovery source, currency or implementation changed; session is stale"
            )
    else:
        _save(manifest_path, manifest)
    attempts = []
    previous = _digest(manifest)
    for number, path in enumerate(sorted(root.glob("attempt-*.json")), 1):
        _file_digest(path)
        event = json.loads(path.read_text())
        if (
            path.name != f"attempt-{number:02}.json"
            or event["previous_sha256"] != previous
            or event["layout_sha256"] != _digest(event["layout"])
        ):
            raise ValueError("Recovery attempt history no longer closes")
        previous = _digest(event)
        attempts.append(event)
    if action == "inspect":
        existing = sorted(root.glob("inspection-*.json"))
        if len(existing) >= MAX_INSPECTIONS:
            raise ValueError("PDF recovery inspection budget exhausted")
        try:
            evidence = inspect_pdf_regions(
                source,
                pages,
                region,
                image_dir=(root / f"render-{len(existing)+1:02}") if render else None,
            )
        except ValueError as exc:
            result = {
                "status": "invalid_inspection",
                "reason": str(exc)[:500],
                **identity,
            }
            _save(root / f"inspection-{len(existing)+1:02}.json", result)
            return result
        if _identity(source, currency) != identity:
            raise ValueError("PDF source changed during inspection")
        result = {
            "status": "evidence_only",
            "reason": reason[:2000],
            **identity,
            "evidence": evidence,
        }
        _save(root / f"inspection-{len(existing)+1:02}.json", result)
        return result
    if not isinstance(layout, dict) or not layout:
        raise ValueError("Recovery trial/freeze requires a proposed layout")
    layout = json.loads(json.dumps(layout, allow_nan=False))
    if (
        layout.get("source_sha256", identity["source_sha256"])
        != identity["source_sha256"]
    ):
        raise ValueError("Proposed PDF layout is bound to another source")
    layout["source_sha256"] = identity["source_sha256"]
    layout_digest = _digest(layout)
    frozen = root / "frozen_layout.json"
    if frozen.exists():
        _file_digest(frozen)
        if action == "freeze" and json.loads(frozen.read_text()) == layout:
            receipt_path = root / "freeze_receipt.json"
            _file_digest(receipt_path)
            receipt: dict[str, Any] = json.loads(receipt_path.read_text())
            if (
                receipt["layout_sha256"] == layout_digest
                and receipt["previous_sha256"] == previous
            ):
                return receipt
        raise ValueError("Recovery recipe is already frozen; do not overwrite it")
    if action == "trial":
        if len(attempts) >= MAX_ATTEMPTS:
            raise ValueError("PDF recovery attempt budget exhausted")
        if any(e["layout_sha256"] == layout_digest for e in attempts):
            raise ValueError(
                "Identical recovery recipe already tried; inspect evidence before revising"
            )
        if not reason.strip():
            raise ValueError("Record the evidence and reason for this recipe revision")
    elif (
        not attempts
        or not attempts[-1]["diagnostics"]["accepted"]
        or attempts[-1]["layout_sha256"] != layout_digest
    ):
        # Exact trial identity is a mechanical prerequisite, not a runtime fault.
        # Keep the source unqualified and the retained history unchanged.
        return {
            "status": "freeze_blocked",
            "reason_code": "successful_exact_trial_required",
            "reason": "Freeze requires the exact latest successful full-source trial",
            **identity,
            "layout_sha256": layout_digest,
            "previous_sha256": previous,
            "qualified": False,
        }
    from . import read_registration_pdf

    try:
        rows, diagnostics = read_registration_pdf(source, layout, currency=currency)
    except ValueError as exc:
        rows, diagnostics = [], {
            "accepted": False,
            "reason": "invalid_reviewed_layout",
            "detail": str(exc)[:500],
            "rejected_rows": [],
        }
    if _identity(source, currency) != identity:
        raise ValueError("PDF source or implementation changed during recovery")
    row_digest = _digest(rows)
    if action == "freeze":
        if (
            not diagnostics["accepted"]
            or row_digest != attempts[-1]["rows_sha256"]
            or diagnostics != attempts[-1]["diagnostics"]
        ):
            raise ValueError(
                "Fresh PDF replay differs from the successful recovery trial"
            )
        receipt = {
            "status": "frozen_requires_mapping_review",
            **identity,
            "layout_sha256": layout_digest,
            "rows_sha256": row_digest,
            "previous_sha256": previous,
            "qualified": False,
            "layout_path": str(frozen),
        }
        _save(frozen, layout)
        _save(root / "freeze_receipt.json", receipt)
        return receipt
    result = {
        "attempt": len(attempts) + 1,
        "previous_sha256": previous,
        "layout": layout,
        "layout_sha256": layout_digest,
        "rows_sha256": row_digest,
        "diagnostics": diagnostics,
        "reason": reason[:2000],
        "qualified": False,
        "status": (
            "ready_to_freeze"
            if diagnostics["accepted"]
            else ("exhausted" if len(attempts) + 1 == MAX_ATTEMPTS else "revise_layout")
        ),
    }
    _save(root / f"attempt-{len(attempts)+1:02}.json", result)
    failed = diagnostics.get("rejected_rows", [])
    if failed:
        first = max(1, int(failed[0]["source_page"]))
        # Page count comes from a bounded inspector, not another whole-document parse.
        import pdfplumber

        with pdfplumber.open(source) as document:
            count = len(document.pages)
        result = {
            **result,
            "suggested_inspection_pages": list(
                range(max(1, first - 1), min(count, first + 1) + 1)
            ),
        }
    # Keep the complete controls in the retained attempt; the host receives a
    # bounded diagnostic projection even for a thousand-page success.
    controls = diagnostics.get("running_total_controls", [])
    if len(controls) > 3:
        result = {
            **result,
            "diagnostics": {
                **diagnostics,
                "running_total_control_count": len(controls),
                "running_total_controls": controls[-3:],
                "running_total_controls_truncated": True,
            },
        }
    return result


def add_recovery_args(parser: Any) -> None:
    parser.add_argument("--pdf-recovery", choices=("inspect", "trial", "freeze"))
    parser.add_argument("--pdf-pages", nargs="+", type=int)
    parser.add_argument(
        "--pdf-region", nargs=4, type=float, metavar=("X0", "TOP", "X1", "BOTTOM")
    )
    parser.add_argument("--pdf-reason", default="")
    parser.add_argument(
        "--pdf-currency", help="Reviewed source currency, required for PDF recovery"
    )
    parser.add_argument("--pdf-render", action="store_true")
