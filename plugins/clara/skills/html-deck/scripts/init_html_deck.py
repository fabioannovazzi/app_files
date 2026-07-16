#!/usr/bin/env python3
"""Initialize editable sources for a Clara standalone HTML deck."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

SCHEMA_VERSION = "clara.html_deck_work.v1"
LEDGER_SCHEMA_VERSION = "clara.html_deck_ledger.v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--title", required=True)
    parser.add_argument("--subtitle", default="")
    parser.add_argument("--author", default="")
    parser.add_argument("--eyebrow", default="Presentation")
    parser.add_argument("--language", default="it")
    parser.add_argument("--description", default="")
    parser.add_argument("--theme-color", default="#141817")
    return parser.parse_args()


def require_empty_target(path: Path) -> None:
    if path.exists():
        if not path.is_dir():
            raise ValueError(f"Work path is not a directory: {path}")
        if any(path.iterdir()):
            raise ValueError(f"Work directory is not empty: {path}")
    path.mkdir(parents=True, exist_ok=True)


def main() -> int:
    args = parse_args()
    try:
        work_dir = args.work_dir.expanduser().resolve()
        require_empty_target(work_dir)
        engine_dir = Path(__file__).resolve().parents[1] / "assets" / "deck-engine"
        starter = engine_dir / "starter-slides.html"
        starter_plan = (
            Path(__file__).resolve().parents[1]
            / "assets"
            / "layout-library"
            / "starter-deck-plan.json"
        )
        if not starter.is_file():
            raise FileNotFoundError(f"Missing starter slides: {starter}")
        if not starter_plan.is_file():
            raise FileNotFoundError(f"Missing starter deck plan: {starter_plan}")

        metadata = {
            "schema_version": SCHEMA_VERSION,
            "title": args.title.strip(),
            "subtitle": args.subtitle.strip(),
            "author": args.author.strip(),
            "eyebrow": args.eyebrow.strip(),
            "language": args.language.strip() or "it",
            "description": args.description.strip()
            or args.subtitle.strip()
            or args.title.strip(),
            "robots": "noindex,nofollow,noarchive",
            "theme_color": args.theme_color.strip() or "#141817",
        }
        if not metadata["title"]:
            raise ValueError("Deck title cannot be empty")

        (work_dir / "deck.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        shutil.copyfile(starter, work_dir / "slides.html")
        shutil.copyfile(starter_plan, work_dir / "deck-plan.json")
        plan_payload = json.loads(starter_plan.read_text(encoding="utf-8"))
        slide_ids = [
            str(slide.get("id", "")).strip()
            for slide in plan_payload.get("slides", [])
            if isinstance(slide, dict)
        ]
        if not slide_ids:
            raise ValueError("Starter deck plan has no stable slide IDs")
        ledger = {
            "schema_version": LEDGER_SCHEMA_VERSION,
            "sources": [],
            "slides": [
                {
                    "slide_id": slide_id,
                    "basis_status": "not-applicable",
                    "basis_note": "Template example; replace with the actual evidence basis before delivery.",
                    "claims": [],
                }
                for slide_id in slide_ids
            ],
        }
        (work_dir / "content-ledger.json").write_text(
            json.dumps(ledger, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (work_dir / "custom.css").write_text(
            "/* Add only deck-specific semantic layouts here. Keep the shared engine intact. */\n",
            encoding="utf-8",
        )
        result = {
            "schema_version": SCHEMA_VERSION,
            "work_dir": str(work_dir),
            "metadata": str(work_dir / "deck.json"),
            "deck_plan": str(work_dir / "deck-plan.json"),
            "slides": str(work_dir / "slides.html"),
            "custom_css": str(work_dir / "custom.css"),
            "content_ledger": str(work_dir / "content-ledger.json"),
            "next": (
                "Edit deck-plan.json and content-ledger.json, compose with "
                "compose_html_deck.py --force, then build."
            ),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
