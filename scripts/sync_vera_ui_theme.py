"""Synchronize the shared Vera theme into offline workflow UI resources."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

if __package__:
    from scripts import generate_non_plotting_review_widgets as widgets
    from scripts.vera_ui_theme import theme_css, theme_html
else:
    import generate_non_plotting_review_widgets as widgets
    from vera_ui_theme import theme_css, theme_html

__all__ = ["CSS_SURFACES", "HTML_SURFACES", "expected_resources", "main"]

ROOT = Path(__file__).resolve().parents[1]
LOGGER = logging.getLogger(__name__)
CSS_SURFACES = (
    "plugins/vera/ui/workspace.css",
    "plugins/vera/ui/research-sources.css",
    "plugins/browser-automation/ui/agenzia.css",
    "plugins/bilancio-xbrl-it/ui/workspace.css",
    "plugins/treasury-forecast/assets/review.css",
)
HTML_SURFACES = (
    "plugins/adeguati-assetti/assets/construction-intake.html",
    "plugins/prompt-optimizer/assets/legal-tax-model.html",
    "plugins/previdenza-inps/assets/previdenza-inps-review-widget.html",
    "plugins/registro-imprese-sari/assets/registro-imprese-sari-review-widget.html",
    # These widgets maintain specialist persistence adaptations outside the
    # generic generator. Preserve their markup and scripts byte-for-byte.
    "plugins/deep-research-validator/assets/deep-research-review-widget.html",
    "plugins/client-file-preparation/assets/client-file-preparation-review-widget.html",
    "plugins/new-client/assets/new-client-review-widget.html",
    "plugins/prompt-optimizer/assets/prompt-optimizer-review-widget.html",
)


def expected_resources() -> dict[Path, str]:
    """Render every native or specialist Vera UI from the same theme bytes."""
    resources = {}
    for name in CSS_SURFACES:
        path = ROOT / name
        resources[path] = theme_css(path.read_text(encoding="utf-8"))
    for name in HTML_SURFACES:
        path = ROOT / name
        resources[path] = theme_html(path.read_text(encoding="utf-8"))
    components = json.loads((ROOT / "plugins/vera/components.json").read_text())[
        "plugins"
    ]
    for target in widgets.TARGETS:
        if target["plugin"] in components:
            path = ROOT / "plugins" / target["plugin"] / "assets" / target["asset"]
            if path not in resources:
                resources[path] = widgets.render_target(target)
    return resources


def main() -> int:
    """Write derived styles or check that central theme changes were propagated."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    stale = []
    for path, expected in expected_resources().items():
        if path.read_text(encoding="utf-8") == expected:
            continue
        if args.check:
            stale.append(path.relative_to(ROOT).as_posix())
        else:
            path.write_text(expected, encoding="utf-8")
            LOGGER.info("Updated %s", path.relative_to(ROOT))
    if stale:
        LOGGER.error("Run python scripts/sync_vera_ui_theme.py: %s", ", ".join(stale))
        return 1
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
