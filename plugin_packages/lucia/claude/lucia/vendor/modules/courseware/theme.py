"""Apply the shared workflow appearance to lesson shells without restyling reports."""

from __future__ import annotations

from pathlib import Path

__all__ = ["theme_lesson"]


def theme_lesson(page: str, product: str, root: Path, destination: Path) -> str:
    """Copy the offline stylesheet and link it only from Clara/Lucia lessons."""
    if product not in {"clara", "lucia"}:
        return page
    source = root / "ui/theme.css"
    if not source.is_file():
        source = Path(__file__).resolve().parents[3] / "ui/vera-theme.css"
    if not source.is_file():
        return page
    (destination / "workflow-theme.css").write_bytes(source.read_bytes())
    link = '<link rel="stylesheet" href="workflow-theme.css">'
    return page.replace("</head>", link + "</head>", 1)
