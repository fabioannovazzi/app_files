"""Keep authored worksheet metadata accurate without changing the case."""

from __future__ import annotations

import zipfile

import pytest
from defusedxml.ElementTree import fromstring

from scripts.course_materials.finalize_workbook_dimensions import NS, finalize


@pytest.mark.parametrize("prefix", ["", "x:"])
@pytest.mark.parametrize(
    "properties", ["", "<PsheetPr/>", "<PsheetPr><PoutlinePr/></PsheetPr>"]
)
def test_authored_bounds_preserve_all_cell_formula_and_other_part_bytes(
    tmp_path, prefix, properties
):
    namespace = f"xmlns:{prefix[:-1]}" if prefix else "xmlns"
    props = properties.replace("<P", f"<{prefix}").replace("</P", f"</{prefix}")
    content = f'<{prefix}worksheet {namespace}="{NS}">{props}<{prefix}sheetData><{prefix}row r="3"><{prefix}c r="B3"><{prefix}v>50000</{prefix}v></{prefix}c></{prefix}row><{prefix}row r="12"><{prefix}c r="AA12"><{prefix}f>B3-70000</{prefix}f><{prefix}v>-20000</{prefix}v></{prefix}c></{prefix}row></{prefix}sheetData></{prefix}worksheet>'.encode()
    path = tmp_path / "source.xlsx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/worksheets/sheet1.xml", content)
        archive.writestr("xl/styles.xml", b"unchanged fixture styles")
    finalize(path)
    with zipfile.ZipFile(path) as archive:
        updated = archive.read("xl/worksheets/sheet1.xml")
        assert archive.read("xl/styles.xml") == b"unchanged fixture styles"
    assert (
        updated.replace(f'<{prefix}dimension ref="B3:AA12" />'.encode(), b"") == content
    )
    parsed = fromstring(updated)
    assert parsed.find(f"{{{NS}}}dimension").attrib == {"ref": "B3:AA12"}
    assert list(parsed)[1 if properties else 0].tag == f"{{{NS}}}dimension"
    first = path.read_bytes()
    finalize(path)
    assert path.read_bytes() == first
