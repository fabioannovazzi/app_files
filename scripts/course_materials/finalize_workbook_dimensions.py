"""Add exact worksheet bounds omitted by the authoring tool's XLSX export.

The current Concordato reader requires this optional XLSX metadata. Values,
formulas, styles and all other package parts are preserved. This is input
authoring, not a fallback or modification of the professional pipeline.
"""

from __future__ import annotations

import argparse
import re
import zipfile
from pathlib import Path

from defusedxml.ElementTree import fromstring

__all__ = ["finalize", "main"]
NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def finalize(path: Path) -> None:
    """Declare the bounding rectangle of the cells actually in each sheet."""
    with zipfile.ZipFile(path) as archive:
        parts = [(entry, archive.read(entry.filename)) for entry in archive.infolist()]
    replacement: dict[str, bytes] = {}
    for entry, payload in parts:
        if not re.fullmatch(r"xl/worksheets/sheet\d+\.xml", entry.filename):
            continue
        sheet = fromstring(payload)
        if sheet.find(f"{{{NS}}}dimension") is not None:
            continue
        cells = [node.attrib["r"] for node in sheet.iter(f"{{{NS}}}c")]
        columns, rows = [], []
        for cell in cells:
            match = re.fullmatch(r"([A-Z]+)([1-9]\d*)", cell)
            if match is None:
                raise ValueError(f"Invalid authored cell address: {cell}")
            column = 0
            for letter in match[1]:
                column = column * 26 + ord(letter) - ord("A") + 1
            columns.append((column, match[1]))
            rows.append(int(match[2]))
        ref = (
            f"{min(columns)[1]}{min(rows)}:{max(columns)[1]}{max(rows)}"
            if cells
            else "A1"
        )
        # Add only the missing metadata bytes, preserving all existing XML bytes.
        root = re.search(rb"<([A-Za-z_][\w.-]*:)?worksheet\b[^>]*>", payload)
        if root is None or sheet.tag != f"{{{NS}}}worksheet":
            raise ValueError("Expected an authored SpreadsheetML worksheet")
        prefix = root[1] or b""
        serialized = b"<" + prefix + b'dimension ref="' + ref.encode() + b'" />'
        start = root.end()
        if sheet.find(f"{{{NS}}}sheetPr") is not None:
            closing = b"</" + prefix + b"sheetPr>"
            end = payload.find(closing)
            if end < 0:
                match = re.search(
                    b"<" + re.escape(prefix) + rb"sheetPr\b[^>]*/>", payload
                )
                if match is None:
                    raise ValueError("Cannot locate the authored sheet properties")
                start = match.end()
            else:
                start = end + len(closing)
        replacement[entry.filename] = payload[:start] + serialized + payload[start:]
    target = path.with_suffix(".dimensions.xlsx")
    with zipfile.ZipFile(target, "w") as archive:
        for entry, payload in parts:
            archive.writestr(entry, replacement.get(entry.filename, payload))
    target.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    for path in sorted(args.directory.glob("*.xlsx")):
        finalize(path)


if __name__ == "__main__":
    main()
