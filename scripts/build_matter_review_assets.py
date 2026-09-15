"""Build matching localized editable and read-only matter review pages."""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

__all__ = ["build", "main"]
ROOT = Path(__file__).resolve().parents[1]


def build() -> dict[Path, str]:
    """Use one reviewed template and the workflow's own display vocabulary."""
    component = ROOT / "plugins/apertura-pratica"
    vocabulary = json.loads((component / "references/display-labels.json").read_text())
    template = (ROOT / "scripts/matter_review_template.html").read_text()
    fonts = []
    for weight, name in ((400, "Regular"), (600, "SemiBold")):
        data = (
            ROOT
            / f"plugins/_shared/vendor/modules/courseware/assets/InstrumentSans-{name}.ttf"
        ).read_bytes()
        encoded = base64.b64encode(data).decode("ascii")
        fonts.append(
            f'@font-face{{font-family:"Instrument Sans";font-style:normal;font-weight:{weight};src:url(data:font/ttf;base64,{encoded}) format("truetype");}}'
        )
    template = template.replace("__FONTS__", "\n".join(fonts)).replace(
        "__LABELS__", json.dumps(vocabulary, ensure_ascii=True)
    )
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
