"""Verify an explicitly selected native Clara budget dashboard for app review."""

from __future__ import annotations

import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path

__all__ = ["report_bytes"]

CLARA_ROOT = Path(__file__).resolve().parents[3]
COMPONENT = next(
    path
    for path in (
        CLARA_ROOT / "modules/management-control-pack",
        CLARA_ROOT.parent / "management-control-pack",
    )
    if (path / "assets/budget-report.js").is_file()
)
REPORT = "management_control_dashboard.html"


class _ReportScripts(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.scripts: list[str] = []
        self.in_script = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"iframe", "object", "embed", "base", "form"} or any(
            name.startswith("on") or name == "srcdoc" for name, _ in attrs
        ):
            raise ValueError("Unexpected active content in budget dashboard")
        if any(
            name in {"href", "src", "action"}
            and re.sub(r"[\x00-\x20]", "", value or "")
            .casefold()
            .startswith("javascript:")
            for name, value in attrs
        ):
            raise ValueError("Script navigation is not supported in budget dashboards")
        if tag == "script":
            if attrs or self.in_script:
                raise ValueError("Only the bundled inline report script is supported")
            self.in_script = True
            self.scripts.append("")

    def handle_data(self, data: str) -> None:
        if self.in_script:
            self.scripts[-1] += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self.in_script = False


def report_bytes(report: Path) -> bytes:
    """Verify native output identity and the exact bundled presentation script."""
    if report.name != REPORT:
        raise ValueError("Select the native management_control_dashboard.html")
    receipt = json.loads((report.parent / "execution_receipt.json").read_text())
    if (
        receipt.get("schema_version") != "vera.management_control_execution_receipt.v1"
        or receipt.get("workflow_id") != "management-control-pack"
    ):
        raise ValueError("A native budget execution receipt is required")
    entries = [row for row in receipt["outputs"] if row.get("path") == REPORT]
    content = report.read_bytes()
    if (
        len(entries) != 1
        or entries[0].get("sha256") != hashlib.sha256(content).hexdigest()
        or entries[0].get("byte_count") != len(content)
    ):
        raise ValueError("The dashboard no longer matches its native receipt")
    parser = _ReportScripts()
    parser.feed(content.decode("utf-8"))
    parser.close()
    script = (COMPONENT / "assets/budget-report.js").read_text()
    if parser.in_script or parser.scripts != [script]:
        raise ValueError("The dashboard must use the current bundled report script")
    return content
