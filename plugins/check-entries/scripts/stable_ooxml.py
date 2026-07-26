"""Deterministic OOXML serialization for receipted Check Entries workbooks."""

from __future__ import annotations

import re
import tempfile
import zipfile
from collections.abc import Callable
from io import BytesIO
from pathlib import Path

__all__ = ["write_stable_xlsx"]

_OOXML_TIMESTAMP = b"2000-01-01T00:00:00Z"
_CORE_TIMESTAMP_RE = re.compile(
    rb"(<dcterms:(created|modified)\b[^>]*>).*?(</dcterms:\2>)",
    flags=re.DOTALL,
)


def _stable_member_payload(name: str, payload: bytes) -> bytes:
    """Remove package timestamps whose values do not describe workbook facts."""

    if name == "docProps/core.xml":
        return _CORE_TIMESTAMP_RE.sub(
            lambda match: match.group(1) + _OOXML_TIMESTAMP + match.group(3),
            payload,
        )
    return payload


def _stable_zip_bytes(path: Path) -> bytes:
    """Return canonical ZIP bytes for one already-written OOXML workbook."""

    destination = BytesIO()
    with zipfile.ZipFile(path, "r") as source:
        members = source.infolist()
        names = [member.filename for member in members]
        if len(names) != len(set(names)):
            raise ValueError("OOXML workbook contains duplicate member names.")
        with zipfile.ZipFile(
            destination,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as target:
            for member in sorted(members, key=lambda value: value.filename):
                info = zipfile.ZipInfo(member.filename, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 0
                info.external_attr = 0
                info.flag_bits = 0
                target.writestr(
                    info,
                    _stable_member_payload(member.filename, source.read(member)),
                )
    return destination.getvalue()


def write_stable_xlsx(
    path: Path,
    writer: Callable[[Path], None],
) -> None:
    """Generate twice, canonicalize, and persist only byte-identical OOXML.

    Workbook byte equality is mechanically testable and is required because the
    resulting receipt is later used as audit evidence. Semantic workbook layout
    remains the responsibility of the caller.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="check-entries-ooxml-") as temp_name:
        temp_root = Path(temp_name)
        first_path = temp_root / "first.xlsx"
        second_path = temp_root / "second.xlsx"
        writer(first_path)
        writer(second_path)
        first = _stable_zip_bytes(first_path)
        second = _stable_zip_bytes(second_path)
        if first != second:
            raise ValueError(
                "Check Entries XLSX generation is not reproducible across two runs."
            )
        path.write_bytes(first)
