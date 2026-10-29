"""Build matching localized editable and read-only matter review pages."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

if __package__:
    from scripts.vera_ui_theme import theme_html
else:
    from vera_ui_theme import theme_html

__all__ = ["build", "main"]
ROOT = Path(__file__).resolve().parents[1]


def build() -> dict[Path, str]:
    """Use one reviewed template and the workflow's own display vocabulary."""
    component = ROOT / "plugins/apertura-pratica"
    vocabulary = json.loads((component / "references/display-labels.json").read_text())
    template = (ROOT / "scripts/matter_review_template.html").read_text()
    template = template.replace(
        "__LABELS__", json.dumps(vocabulary, ensure_ascii=True, indent=2)
    )
    template = theme_html(template)
    return {
        component / "assets" / name: template.replace("__EDITABLE__", editable)
        for name, editable in (
            ("apertura-pratica-review.html", "true"),
            ("apertura-pratica-review-widget.html", "false"),
        )
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for path, text in build().items():
        if args.check:
            if not path.is_file() or path.read_text() != text:
                raise ValueError(f"Regenerate matter review asset: {path}")
        else:
            path.write_text(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
