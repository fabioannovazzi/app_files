from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import zipfile
from dataclasses import asdict, replace
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = ROOT / "plugins" / "clara" / "scripts"


def _load_module(name: str, path: Path) -> Any:
    scripts_path = str(SCRIPTS_ROOT)
    inserted = scripts_path not in sys.path
    if inserted:
        sys.path.insert(0, scripts_path)
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        if inserted:
            sys.path.remove(scripts_path)


PARSER = _load_module(
    "clara_commercial_general_journal_parser_test",
    SCRIPTS_ROOT / "parse_commercial_general_journal.py",
)


def _reviewed_row_sha256(cells: dict[int, str]) -> str:
    return PARSER.canonical_general_journal_row_sha256(cells)


def _bind_amountless_exclusions(
    rows: dict[int, dict[int, str]],
    contract: Any,
) -> Any:
    return replace(
        contract,
        reviewed_amountless_exclusions=tuple(
            replace(
                exclusion,
                canonical_row_sha256=_reviewed_row_sha256(rows[exclusion.row_number]),
            )
            for exclusion in contract.reviewed_amountless_exclusions
        ),
    )


def _column_name(column: int) -> str:
    result = ""
    value = column
    while value:
        value, remainder = divmod(value - 1, 26)
        result = chr(ord("A") + remainder) + result
    return result


def _worksheet_xml(rows: dict[int, dict[int, str]]) -> str:
    row_nodes: list[str] = []
    for row_number in sorted(rows):
        cell_nodes = []
        for column, value in sorted(rows[row_number].items()):
            reference = f"{_column_name(column)}{row_number}"
            cell_nodes.append(
                f'<c r="{reference}" t="inlineStr"><is>'
                f'<t xml:space="preserve">{escape(value)}</t>'
                "</is></c>"
            )
        row_nodes.append(f'<row r="{row_number}">{"".join(cell_nodes)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/'
        'spreadsheetml/2006/main"><sheetData>'
        f'{"".join(row_nodes)}'
        "</sheetData></worksheet>"
    )


def _write_xlsx(
    path: Path,
    rows: dict[int, dict[int, str]],
    *,
    sheet_name: str = "Reviewed journal",
    worksheet_xml: str | None = None,
    worksheet_target: str = "worksheets/sheet1.xml",
) -> str:
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/'
        'spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/'
        '2006/relationships"><sheets>'
        f'<sheet name="{escape(sheet_name)}" sheetId="1" r:id="rId1"/>'
        "</sheets></workbook>"
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/'
        'package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/'
        '2006/relationships/worksheet" '
        f'Target="{escape(worksheet_target)}"/>'
        "</Relationships>"
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/'
        'package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/'
        '2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/'
        '2006/content-types">'
        '<Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.'
        'relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.'
        'spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.'
        'spreadsheetml.worksheet+xml"/>'
        "</Types>"
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            worksheet_xml or _worksheet_xml(rows),
        )
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rows() -> dict[int, dict[int, str]]:
    return {
        1: {1: "Synthetic fixture metadata"},
        2: {1: "Data registrazione"},
        3: {
            3: "Riga",
            6: "Conto",
            10: "Dare",
            14: "Avere",
        },
        4: {1: "2023-01-31 00:00:00"},
        5: {
            3: "1",
            6: "10 / 1 / 1",
            10: "100.25",
        },
        6: {
            3: "2",
            6: "20 / 1 / 1",
            14: "100.25",
        },
        7: {1: ("28/02/2023\n" "3 30 / 1 / 1 60,00 D\n" "4 40 / 1 / 1 60,00 C")},
        8: {2: "Data registrazione"},
        9: {
            2: "Riga",
            5: "Conto",
            9: "Dare",
            13: "Avere",
        },
        10: {2: "2023-03-31 00:00:00"},
        11: {
            2: "5",
            5: "50 / 1 / 1",
            9: "50",
        },
        12: {
            2: "6",
            5: "60 / 1 / 1",
            13: "50",
        },
        13: {1: "Totale generale 210,25 210,25"},
    }


def _contract() -> Any:
    return PARSER.GeneralJournalLayoutContract(
        contract_version="clara.commercial_general_journal_layout.v5",
        review_status="reviewed",
        sheet_name="Reviewed journal",
        date_header_label="Data registrazione",
        line_header_label="Riga",
        account_header_label="Conto",
        debit_header_label="Dare",
        credit_header_label="Avere",
        page_layouts=(
            PARSER.PageLayout(
                layout_id="layout-a",
                date_header_column=1,
                line_header_column=3,
                account_header_column=6,
                debit_header_column=10,
                credit_header_column=14,
                date_columns=(1, 2, 3, 4, 5),
                line_id_columns=(1, 2, 3, 4, 5),
                account_columns=(6,),
                debit_amount_columns=(9, 10, 11),
                credit_amount_columns=(13, 14, 15),
                physical_first_line_columns=(6,),
            ),
            PARSER.PageLayout(
                layout_id="layout-b",
                date_header_column=2,
                line_header_column=2,
                account_header_column=5,
                debit_header_column=9,
                credit_header_column=13,
                date_columns=(1, 2, 3, 4),
                line_id_columns=(1, 2, 3, 4),
                account_columns=(5,),
                debit_amount_columns=(8, 9, 10),
                credit_amount_columns=(12, 13, 14),
                physical_first_line_columns=(5,),
            ),
        ),
        date_patterns=(
            PARSER.DatePattern(
                pattern=(r"^(?P<date>[0-9]{4}-[0-9]{2}-[0-9]{2}) " r"00:00:00$"),
                strptime_format="%Y-%m-%d",
            ),
            PARSER.DatePattern(
                pattern=(r"^(?P<date>[0-9]{2}/[0-9]{2}/[0-9]{4})(?:\s|$)"),
                strptime_format="%d/%m/%Y",
            ),
        ),
        account_code_pattern=r"[0-9]+\s*/\s*[0-9]+\s*/\s*[0-9]+",
        logical_candidate_pattern=(
            r"^\s*[1-9][0-9]*\s+" r"[0-9]+\s*/\s*[0-9]+\s*/\s*[0-9]+"
        ),
        logical_movement_patterns=(
            PARSER.LogicalMovementPattern(
                layout_ids=("layout-a", "layout-b"),
                pattern=(
                    r"^\s*(?P<line_id>[1-9][0-9]*)\s+"
                    r"(?P<account>[0-9]+\s*/\s*[0-9]+\s*/\s*[0-9]+)"
                    r"\s+(?:(?P<debit>"
                    r"(?:0|[1-9][0-9]{0,2}(?:\.[0-9]{3})*),[0-9]{2})"
                    r"\s+D|(?P<credit>"
                    r"(?:0|[1-9][0-9]{0,2}(?:\.[0-9]{3})*),[0-9]{2})"
                    r"\s+C)\s*$"
                ),
                amount_format="italian_grouped_2",
            ),
        ),
        physical_embedded_amount_patterns=(),
        reviewed_amount_pairs=(),
        reviewed_amountless_exclusions=(),
        physical_amount_format="canonical_dot",
        amount_sign_policy="nonnegative",
        control_pattern=(
            r"^Totale generale\s+"
            r"(?P<debit>(?:0|[1-9][0-9]{0,2}(?:\.[0-9]{3})*),[0-9]{2})"
            r"\s+"
            r"(?P<credit>(?:0|[1-9][0-9]{0,2}(?:\.[0-9]{3})*),[0-9]{2})"
            r"$"
        ),
        control_amount_format="italian_grouped_2",
        reviewed_final_debit_total="210.25",
        reviewed_final_credit_total="210.25",
    )


def _reviewed_amount_locator(
    *,
    row_number: int,
    column: int,
    line_index: int,
    layout_id: str = "layout-b",
    amount_format: str = "italian_grouped_2",
) -> Any:
    amount_pattern = r"(?P<amount>(?:0|[1-9][0-9]{0,2}" r"(?:\.[0-9]{3})*),[0-9]{2})"
    if amount_format == "canonical_dot":
        amount_pattern = r"(?P<amount>[+-]?(?:0|[1-9][0-9]*)" r"(?:\.[0-9]+)?)"
    return PARSER.ReviewedAmountLocator(
        layout_id=layout_id,
        row_number=row_number,
        column=column,
        line_index=line_index,
        pattern=f"^{amount_pattern}$",
        amount_format=amount_format,
    )


def _reviewed_pair_contract_fixture() -> tuple[
    dict[int, dict[int, str]],
    Any,
]:
    rows = _rows()
    rows[13] = {2: "7", 5: "70 / 1 / 1"}
    rows[14] = {2: "8", 5: "80 / 1 / 1"}
    rows[15] = {1: "25,00\n25,00"}
    rows[16] = {1: "Totale generale 235,25 235,25"}
    pair = PARSER.ReviewedAmountPair(
        debit=PARSER.ReviewedAmountPairMember(
            movement_layout_id="layout-b",
            movement_row_number=13,
            movement_line_id=7,
            amount_locator=_reviewed_amount_locator(
                row_number=15,
                column=1,
                line_index=0,
            ),
        ),
        credit=PARSER.ReviewedAmountPairMember(
            movement_layout_id="layout-b",
            movement_row_number=14,
            movement_line_id=8,
            amount_locator=_reviewed_amount_locator(
                row_number=15,
                column=1,
                line_index=1,
            ),
        ),
    )
    contract = replace(
        _contract(),
        reviewed_amount_pairs=(pair,),
        reviewed_final_debit_total="235.25",
        reviewed_final_credit_total="235.25",
    )
    return rows, contract


def _reviewed_amountless_exclusion_fixture() -> tuple[
    dict[int, dict[int, str]],
    Any,
]:
    rows = _rows()
    rows[13] = {2: "7", 5: "70 / 1 / 1"}
    rows[14] = {1: "Totale generale 210,25 210,25"}
    exclusion = PARSER.ReviewedAmountlessExclusion(
        layout_id="layout-b",
        row_number=13,
        line_id=7,
        nonempty_columns=(2, 5),
        residual_columns=(),
        canonical_row_sha256=_reviewed_row_sha256(rows[13]),
    )
    contract = replace(
        _contract(),
        reviewed_amountless_exclusions=(exclusion,),
    )
    return rows, contract


def _parse(
    tmp_path: Path,
    *,
    rows: dict[int, dict[int, str]] | None = None,
    contract: Any | None = None,
    digest: str | None = None,
) -> Any:
    source = tmp_path / "synthetic.xlsx"
    actual_digest = _write_xlsx(source, rows or _rows())
    return PARSER.parse_commercial_general_journal(
        source,
        expected_source_sha256=digest or actual_digest,
        layout_contract=contract or _contract(),
    )


def test_parser_returns_exact_in_memory_model_and_sanitized_counts(
    tmp_path: Path,
) -> None:
    result = _parse(tmp_path)

    assert len(result.movements) == 6
    assert result.debit_total == Decimal("210.25")
    assert result.credit_total == Decimal("210.25")
    assert result.source_control_debit_total == Decimal("210.25")
    assert result.source_control_credit_total == Decimal("210.25")
    assert result.first_posting_date.isoformat() == "2023-01-31"
    assert result.last_posting_date.isoformat() == "2023-03-31"
    assert result.physical_movement_count == 4
    assert result.logical_movement_count == 2
    assert result.line_id_gap_count == 0
    assert dict(result.layout_page_counts) == {"layout-a": 1, "layout-b": 1}
    assert result.sanitized_counts() == {
        "movement_count": 6,
        "physical_movement_count": 4,
        "logical_movement_count": 2,
        "excluded_amountless_count": 0,
        "page_header_count": 2,
        "line_id_gap_count": 0,
        "layout_variant_count": 2,
        "first_posting_date": "2023-01-31",
        "last_posting_date": "2023-03-31",
    }


def test_parser_sums_many_high_digit_movements_independent_of_ambient_precision(
    tmp_path: Path,
) -> None:
    amount = "9999999999999999999999999999.99"
    expected_total = "319999999999999999999999999999.68"
    rows = {
        1: {1: "Data registrazione"},
        2: {
            3: "Riga",
            6: "Conto",
            10: "Dare",
            14: "Avere",
        },
        3: {1: "2023-01-31 00:00:00"},
    }
    for line_id in range(1, 65):
        amount_column = 10 if line_id <= 32 else 14
        rows[line_id + 3] = {
            3: str(line_id),
            6: "10 / 1 / 1",
            amount_column: amount,
        }
    rows[68] = {
        1: (
            "Totale generale "
            "319.999.999.999.999.999.999.999.999.999,68 "
            "319.999.999.999.999.999.999.999.999.999,68"
        )
    }
    contract = replace(
        _contract(),
        reviewed_final_debit_total=expected_total,
        reviewed_final_credit_total=expected_total,
    )

    with localcontext() as context:
        context.prec = 8
        result = _parse(tmp_path, rows=rows, contract=contract)

    assert result.debit_total == Decimal(expected_total)
    assert result.credit_total == Decimal(expected_total)
    assert len(result.movements) == 64


@pytest.mark.parametrize(
    "amount_column",
    [
        pytest.param(9, id="debit"),
        pytest.param(13, id="credit"),
    ],
)
def test_parser_rejects_zero_physical_movement_without_side_provenance(
    tmp_path: Path,
    amount_column: int,
) -> None:
    rows = _rows()
    rows[13] = {
        2: "7",
        5: "70 / 1 / 1",
        amount_column: "0",
    }
    rows[14] = {1: "Totale generale 210,25 210,25"}

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="exactly one nonzero debit or credit amount",
    ):
        _parse(tmp_path, rows=rows)


@pytest.mark.parametrize(
    "logical_line",
    [
        pytest.param("3 30 / 1 / 1 0,00 D", id="debit"),
        pytest.param("3 30 / 1 / 1 0,00 C", id="credit"),
    ],
)
def test_parser_rejects_zero_logical_movement_without_side_provenance(
    tmp_path: Path,
    logical_line: str,
) -> None:
    rows = _rows()
    rows[7][1] = f"28/02/2023\n{logical_line}"

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="exactly one nonzero debit or credit amount",
    ):
        _parse(tmp_path, rows=rows)


@pytest.mark.parametrize(
    "embedded_pattern",
    [
        pytest.param(
            (
                r"^description "
                r"(?P<debit>(?:0|[1-9][0-9]{0,2}"
                r"(?:\.[0-9]{3})*),[0-9]{2})"
                r"(?P<credit>(?!))?$"
            ),
            id="debit",
        ),
        pytest.param(
            (
                r"^description "
                r"(?P<debit>(?!))?"
                r"(?P<credit>(?:0|[1-9][0-9]{0,2}"
                r"(?:\.[0-9]{3})*),[0-9]{2})$"
            ),
            id="credit",
        ),
    ],
)
def test_parser_rejects_zero_embedded_movement_without_side_provenance(
    tmp_path: Path,
    embedded_pattern: str,
) -> None:
    rows = _rows()
    del rows[5][10]
    rows[5][8] = "description 0,00"
    contract = replace(
        _contract(),
        physical_embedded_amount_patterns=(
            PARSER.PhysicalEmbeddedAmountPattern(
                layout_ids=("layout-a",),
                column=8,
                pattern=embedded_pattern,
                amount_format="italian_grouped_2",
            ),
        ),
    )

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="exactly one nonzero debit or credit amount",
    ):
        _parse(tmp_path, rows=rows, contract=contract)


def test_parser_rejects_wrong_format_amount_only_row(tmp_path: Path) -> None:
    rows = _rows()
    rows[13] = {9: "1,00"}
    rows[14] = {1: "Totale generale 210,25 210,25"}

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="not an exact canonical-dot Decimal",
    ):
        _parse(tmp_path, rows=rows)


def test_parser_rejects_extra_wrong_format_amount_on_valid_movement(
    tmp_path: Path,
) -> None:
    rows = _rows()
    rows[5][11] = "1,00"

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="not an exact canonical-dot Decimal",
    ):
        _parse(tmp_path, rows=rows)


def test_parser_rejects_wrong_format_amount_beside_final_control(
    tmp_path: Path,
) -> None:
    rows = _rows()
    rows[13][9] = "1,00"

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="control row also contains a movement signal",
    ):
        _parse(tmp_path, rows=rows)


def test_parser_rejects_registered_amount_beside_multiline_final_control(
    tmp_path: Path,
) -> None:
    rows = _rows()
    rows[13] = {
        2: "7",
        5: "70 / 1 / 1\nTotale generale 210,25 210,25",
        9: "1.00",
    }

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="control row also contains a movement signal",
    ):
        _parse(tmp_path, rows=rows)


def test_parser_rejects_multiline_registered_amount_cell_before_partition(
    tmp_path: Path,
) -> None:
    rows = _rows()
    rows[13] = {9: "1.00\nnarrative continuation"}
    rows[14] = {1: "Totale generale 210,25 210,25"}

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="not an exact canonical-dot Decimal",
    ):
        _parse(tmp_path, rows=rows)


def test_parser_rejects_control_row_with_additional_physical_movement(
    tmp_path: Path,
) -> None:
    rows = _rows()
    rows[13].update(
        {
            2: "7",
            5: "70 / 1 / 1",
            9: "1.00",
        }
    )

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="control row also contains a movement signal",
    ):
        _parse(tmp_path, rows=rows)


def test_parser_rejects_multiple_control_lines_in_one_physical_row(
    tmp_path: Path,
) -> None:
    rows = _rows()
    rows[13][2] = rows[13][1]

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="multiple reviewed control lines",
    ):
        _parse(tmp_path, rows=rows)


def test_parser_rejects_unlisted_physical_blank_amount_line(
    tmp_path: Path,
) -> None:
    rows = _rows()
    rows[13] = {
        2: "7",
        5: "70 / 1 / 1",
    }
    rows[14] = {1: "Totale generale 210,25 210,25"}

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="ambiguous or missing amount",
    ):
        _parse(tmp_path, rows=rows)


def test_parser_excludes_exact_reviewed_amountless_row_without_zero_movement(
    tmp_path: Path,
) -> None:
    rows, contract = _reviewed_amountless_exclusion_fixture()

    result = _parse(tmp_path, rows=rows, contract=contract)

    assert tuple(movement.line_id for movement in result.movements) == (
        1,
        2,
        3,
        4,
        5,
        6,
    )
    assert result.debit_total == Decimal("210.25")
    assert result.credit_total == Decimal("210.25")
    assert result.physical_movement_count == 4
    assert result.logical_movement_count == 2
    assert result.excluded_amountless_count == 1
    assert result.sanitized_counts()["excluded_amountless_count"] == 1


def test_parser_counts_interleaved_excluded_line_id_in_gap_reconciliation(
    tmp_path: Path,
) -> None:
    rows = _rows()
    rows[12] = {2: "6", 5: "60 / 1 / 1"}
    rows[13] = {2: "7", 5: "70 / 1 / 1", 13: "50"}
    rows[14] = {1: "Totale generale 210,25 210,25"}
    contract = replace(
        _contract(),
        reviewed_amountless_exclusions=(
            PARSER.ReviewedAmountlessExclusion(
                layout_id="layout-b",
                row_number=12,
                line_id=6,
                nonempty_columns=(2, 5),
                residual_columns=(),
                canonical_row_sha256=_reviewed_row_sha256(rows[12]),
            ),
        ),
    )

    result = _parse(tmp_path, rows=rows, contract=contract)

    assert tuple(movement.line_id for movement in result.movements[-2:]) == (
        5,
        7,
    )
    assert result.line_id_gap_count == 0
    assert result.excluded_amountless_count == 1


@pytest.mark.parametrize(
    "cells",
    (
        {2: "7", 5: "Cafe\u0301\ncontinuation"},
        {5: "Cafe\u0301\ncontinuation", 2: "7"},
    ),
)
def test_canonical_reviewed_row_sha256_has_stable_domain_separated_vector(
    cells: dict[int, str],
) -> None:
    digest = PARSER.canonical_general_journal_row_sha256(cells)

    assert digest == "84dedfb7e989dff1f27355c1674fec3a4365cc2ffa0aff73628b7a38bee764b9"


@pytest.mark.parametrize(
    "replacement",
    (
        "résidual",
        " residual",
        "residual ",
        "re\u0301sidual",
        "residual\ncontinuation",
    ),
)
def test_parser_rejects_amountless_exclusion_exact_text_mutation_before_use(
    tmp_path: Path,
    replacement: str,
) -> None:
    rows, contract = _reviewed_amountless_exclusion_fixture()
    rows[13][7] = "residual"
    exclusion = replace(
        contract.reviewed_amountless_exclusions[0],
        nonempty_columns=(2, 5, 7),
        residual_columns=(7,),
    )
    contract = _bind_amountless_exclusions(
        rows,
        replace(contract, reviewed_amountless_exclusions=(exclusion,)),
    )
    rows[13][7] = replacement

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="canonical row fingerprint changed",
    ):
        _parse(tmp_path, rows=rows, contract=contract)


def test_parser_rejects_amountless_exclusion_column_swap_before_use(
    tmp_path: Path,
) -> None:
    rows, contract = _reviewed_amountless_exclusion_fixture()
    rows[13][7] = "residual"
    exclusion = replace(
        contract.reviewed_amountless_exclusions[0],
        nonempty_columns=(2, 5, 7),
        residual_columns=(7,),
    )
    contract = _bind_amountless_exclusions(
        rows,
        replace(contract, reviewed_amountless_exclusions=(exclusion,)),
    )
    rows[13][5], rows[13][7] = rows[13][7], rows[13][5]

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="canonical row fingerprint changed",
    ):
        _parse(tmp_path, rows=rows, contract=contract)


@pytest.mark.parametrize(
    "replacement_row",
    (
        {2: "7"},
        {2: "7", 5: "70 / 1 / 1", 7: "added"},
        {2: "7", 6: "70 / 1 / 1"},
    ),
)
def test_parser_rejects_amountless_exclusion_column_shape_mutation_before_use(
    tmp_path: Path,
    replacement_row: dict[int, str],
) -> None:
    rows, contract = _reviewed_amountless_exclusion_fixture()
    rows[13] = replacement_row

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="nonempty columns changed",
    ):
        _parse(tmp_path, rows=rows, contract=contract)


def test_parser_rejects_amountless_exclusion_contract_hash_tamper(
    tmp_path: Path,
) -> None:
    rows, contract = _reviewed_amountless_exclusion_fixture()
    exclusion = replace(
        contract.reviewed_amountless_exclusions[0],
        canonical_row_sha256="0" * 64,
    )
    contract = replace(
        contract,
        reviewed_amountless_exclusions=(exclusion,),
    )

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="canonical row fingerprint changed",
    ):
        _parse(tmp_path, rows=rows, contract=contract)


def test_parser_rejects_missing_reviewed_amountless_exclusion_row(
    tmp_path: Path,
) -> None:
    rows, contract = _reviewed_amountless_exclusion_fixture()
    del rows[13]

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="amountless exclusion row is missing",
    ):
        _parse(tmp_path, rows=rows, contract=contract)


def test_parser_rejects_changed_reviewed_amountless_exclusion_line_id(
    tmp_path: Path,
) -> None:
    rows, contract = _reviewed_amountless_exclusion_fixture()
    rows[13][2] = "8"
    contract = _bind_amountless_exclusions(rows, contract)

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="amountless exclusion line ID changed",
    ):
        _parse(tmp_path, rows=rows, contract=contract)


def test_parser_rejects_ambiguous_reviewed_amountless_exclusion_line_id(
    tmp_path: Path,
) -> None:
    rows, contract = _reviewed_amountless_exclusion_fixture()
    rows[13][3] = "8"
    exclusion = contract.reviewed_amountless_exclusions[0]
    contract = replace(
        contract,
        reviewed_amountless_exclusions=(
            replace(
                exclusion,
                nonempty_columns=(2, 3, 5),
                residual_columns=(3,),
            ),
        ),
    )
    contract = _bind_amountless_exclusions(rows, contract)

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="line ID is ambiguous or missing",
    ):
        _parse(tmp_path, rows=rows, contract=contract)


def test_parser_rejects_reviewed_amountless_exclusion_layout_change(
    tmp_path: Path,
) -> None:
    rows, contract = _reviewed_amountless_exclusion_fixture()
    exclusion = contract.reviewed_amountless_exclusions[0]
    contract = replace(
        contract,
        reviewed_amountless_exclusions=(replace(exclusion, layout_id="layout-a"),),
    )

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="amountless exclusion layout does not match",
    ):
        _parse(tmp_path, rows=rows, contract=contract)


@pytest.mark.parametrize(
    "replacement_row",
    (
        {2: "7"},
        {2: "7", 5: "70 / 1 / 1", 7: "extra"},
    ),
)
def test_parser_rejects_changed_amountless_exclusion_nonempty_columns(
    tmp_path: Path,
    replacement_row: dict[int, str],
) -> None:
    rows, contract = _reviewed_amountless_exclusion_fixture()
    rows[13] = replacement_row

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="amountless exclusion nonempty columns changed",
    ):
        _parse(tmp_path, rows=rows, contract=contract)


@pytest.mark.parametrize("amount_column", (9, 13))
def test_parser_rejects_standalone_amount_on_amountless_exclusion(
    tmp_path: Path,
    amount_column: int,
) -> None:
    rows, contract = _reviewed_amountless_exclusion_fixture()
    rows[13][amount_column] = "1"
    exclusion = contract.reviewed_amountless_exclusions[0]
    contract = replace(
        contract,
        reviewed_amountless_exclusions=(
            replace(
                exclusion,
                nonempty_columns=tuple(sorted((2, 5, amount_column))),
                residual_columns=(amount_column,),
            ),
        ),
    )
    contract = _bind_amountless_exclusions(rows, contract)

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="amountless exclusion contains an amount",
    ):
        _parse(tmp_path, rows=rows, contract=contract)


def test_parser_rejects_embedded_amount_on_amountless_exclusion(
    tmp_path: Path,
) -> None:
    rows, contract = _reviewed_amountless_exclusion_fixture()
    rows[13][7] = "embedded 1,00"
    exclusion = contract.reviewed_amountless_exclusions[0]
    contract = replace(
        contract,
        reviewed_amountless_exclusions=(
            replace(
                exclusion,
                nonempty_columns=(2, 5, 7),
                residual_columns=(7,),
            ),
        ),
        physical_embedded_amount_patterns=(
            PARSER.PhysicalEmbeddedAmountPattern(
                layout_ids=("layout-b",),
                column=7,
                pattern=(
                    r"^embedded (?P<debit>(?:0|[1-9][0-9]{0,2}"
                    r"(?:\.[0-9]{3})*),[0-9]{2})"
                    r"(?P<credit>(?!))?$"
                ),
                amount_format="italian_grouped_2",
            ),
        ),
    )
    contract = _bind_amountless_exclusions(rows, contract)

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="amountless exclusion contains an amount",
    ):
        _parse(tmp_path, rows=rows, contract=contract)


def test_parser_accepts_exact_residual_columns_on_amountless_exclusion(
    tmp_path: Path,
) -> None:
    rows, contract = _reviewed_amountless_exclusion_fixture()
    rows[13][7] = "residual"
    exclusion = contract.reviewed_amountless_exclusions[0]
    contract = replace(
        contract,
        reviewed_amountless_exclusions=(
            replace(
                exclusion,
                nonempty_columns=(2, 5, 7),
                residual_columns=(7,),
            ),
        ),
    )
    contract = _bind_amountless_exclusions(rows, contract)

    result = _parse(tmp_path, rows=rows, contract=contract)

    assert result.excluded_amountless_count == 1
    assert len(result.movements) == 6


def test_parser_reconciles_multiple_exact_amountless_exclusions(
    tmp_path: Path,
) -> None:
    rows = _rows()
    rows[13] = {2: "7", 5: "70 / 1 / 1", 7: "residual-a"}
    rows[14] = {2: "8", 5: "80 / 1 / 1", 7: "residual-b"}
    rows[15] = {1: "Totale generale 210,25 210,25"}
    contract = replace(
        _contract(),
        reviewed_amountless_exclusions=(
            PARSER.ReviewedAmountlessExclusion(
                layout_id="layout-b",
                row_number=13,
                line_id=7,
                nonempty_columns=(2, 5, 7),
                residual_columns=(7,),
                canonical_row_sha256=_reviewed_row_sha256(rows[13]),
            ),
            PARSER.ReviewedAmountlessExclusion(
                layout_id="layout-b",
                row_number=14,
                line_id=8,
                nonempty_columns=(2, 5, 7),
                residual_columns=(7,),
                canonical_row_sha256=_reviewed_row_sha256(rows[14]),
            ),
        ),
    )

    result = _parse(tmp_path, rows=rows, contract=contract)

    assert result.excluded_amountless_count == 2
    assert len(result.movements) == 6
    assert result.line_id_gap_count == 0


def test_parser_rejects_changed_residual_column_ownership(
    tmp_path: Path,
) -> None:
    rows, contract = _reviewed_amountless_exclusion_fixture()
    rows[13][7] = "residual"
    exclusion = contract.reviewed_amountless_exclusions[0]
    contract = replace(
        contract,
        reviewed_amountless_exclusions=(
            replace(
                exclusion,
                nonempty_columns=(2, 5, 7),
                residual_columns=(5,),
            ),
        ),
    )
    contract = _bind_amountless_exclusions(rows, contract)

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="amountless exclusion residual columns changed",
    ):
        _parse(tmp_path, rows=rows, contract=contract)


def test_parser_rejects_logical_amount_signal_in_residual_column(
    tmp_path: Path,
) -> None:
    rows, contract = _reviewed_amountless_exclusion_fixture()
    rows[13][7] = "8 80 / 1 / 1 1,00 D"
    exclusion = contract.reviewed_amountless_exclusions[0]
    contract = replace(
        contract,
        reviewed_amountless_exclusions=(
            replace(
                exclusion,
                nonempty_columns=(2, 5, 7),
                residual_columns=(7,),
            ),
        ),
    )
    contract = _bind_amountless_exclusions(rows, contract)

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="amountless exclusion contains a logical amount",
    ):
        _parse(tmp_path, rows=rows, contract=contract)


def test_contract_rejects_residual_column_outside_nonempty_shape(
    tmp_path: Path,
) -> None:
    rows, contract = _reviewed_amountless_exclusion_fixture()
    exclusion = contract.reviewed_amountless_exclusions[0]
    contract = replace(
        contract,
        reviewed_amountless_exclusions=(replace(exclusion, residual_columns=(7,)),),
    )

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="residual columns must be a subset",
    ):
        _parse(tmp_path, rows=rows, contract=contract)


def test_parser_rejects_multiline_text_on_amountless_exclusion(
    tmp_path: Path,
) -> None:
    rows, contract = _reviewed_amountless_exclusion_fixture()
    rows[13][5] = "70 / 1 / 1\ncontinuation"
    contract = _bind_amountless_exclusions(rows, contract)

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="amountless exclusion contains multiline text",
    ):
        _parse(tmp_path, rows=rows, contract=contract)


def test_parser_rejects_duplicate_reviewed_amountless_exclusion(
    tmp_path: Path,
) -> None:
    rows, contract = _reviewed_amountless_exclusion_fixture()
    exclusion = contract.reviewed_amountless_exclusions[0]
    contract = replace(
        contract,
        reviewed_amountless_exclusions=(exclusion, exclusion),
    )

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="amountless exclusion rows must be unique",
    ):
        _parse(tmp_path, rows=rows, contract=contract)


def test_contract_rejects_duplicate_amountless_exclusion_line_id(
    tmp_path: Path,
) -> None:
    rows, contract = _reviewed_amountless_exclusion_fixture()
    exclusion = contract.reviewed_amountless_exclusions[0]
    contract = replace(
        contract,
        reviewed_amountless_exclusions=(
            exclusion,
            replace(
                exclusion,
                row_number=14,
                nonempty_columns=(1,),
            ),
        ),
    )

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="amountless exclusion line IDs must be unique",
    ):
        _parse(tmp_path, rows=rows, contract=contract)


def test_contract_rejects_amountless_exclusion_pair_row_overlap(
    tmp_path: Path,
) -> None:
    rows, contract = _reviewed_pair_contract_fixture()
    contract = replace(
        contract,
        reviewed_amountless_exclusions=(
            PARSER.ReviewedAmountlessExclusion(
                layout_id="layout-b",
                row_number=13,
                line_id=9,
                nonempty_columns=(2, 5),
                residual_columns=(),
                canonical_row_sha256=_reviewed_row_sha256(rows[13]),
            ),
        ),
    )

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="must not overlap reviewed amount pair rows",
    ):
        _parse(tmp_path, rows=rows, contract=contract)


def test_contract_rejects_amountless_exclusion_pair_line_id_overlap(
    tmp_path: Path,
) -> None:
    rows, contract = _reviewed_pair_contract_fixture()
    contract = replace(
        contract,
        reviewed_amountless_exclusions=(
            PARSER.ReviewedAmountlessExclusion(
                layout_id="layout-b",
                row_number=16,
                line_id=7,
                nonempty_columns=(1,),
                residual_columns=(),
                canonical_row_sha256=_reviewed_row_sha256(rows[16]),
            ),
        ),
    )

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="must not overlap reviewed amount pair line IDs",
    ):
        _parse(tmp_path, rows=rows, contract=contract)


def test_contract_rejects_amountless_exclusion_pair_locator_row_overlap(
    tmp_path: Path,
) -> None:
    rows, contract = _reviewed_pair_contract_fixture()
    contract = replace(
        contract,
        reviewed_amountless_exclusions=(
            PARSER.ReviewedAmountlessExclusion(
                layout_id="layout-b",
                row_number=15,
                line_id=9,
                nonempty_columns=(1,),
                residual_columns=(),
                canonical_row_sha256=_reviewed_row_sha256(rows[15]),
            ),
        ),
    )

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="must not overlap reviewed amount locator rows",
    ):
        _parse(tmp_path, rows=rows, contract=contract)


def test_parser_rejects_unlisted_blank_beside_exact_amountless_exclusion(
    tmp_path: Path,
) -> None:
    rows, contract = _reviewed_amountless_exclusion_fixture()
    rows[14] = {2: "8", 5: "80 / 1 / 1"}
    rows[15] = {1: "Totale generale 210,25 210,25"}

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="ambiguous or missing amount",
    ):
        _parse(tmp_path, rows=rows, contract=contract)


def test_parser_rejects_amountless_exclusion_line_id_on_other_physical_row(
    tmp_path: Path,
) -> None:
    rows, contract = _reviewed_amountless_exclusion_fixture()
    rows[12][1] = "7"

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="amountless exclusion line ID appeared on the wrong row",
    ):
        _parse(tmp_path, rows=rows, contract=contract)


def test_parser_rejects_amountless_exclusion_line_id_in_logical_line(
    tmp_path: Path,
) -> None:
    rows, contract = _reviewed_amountless_exclusion_fixture()
    rows[14] = {1: "continuation\n7 80 / 1 / 1 1,00 D"}
    rows[15] = {1: "Totale generale 210,25 210,25"}

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="amountless exclusion line ID appeared in a logical line",
    ):
        _parse(tmp_path, rows=rows, contract=contract)


def test_parser_uses_equal_reviewed_amount_pair_locators(
    tmp_path: Path,
) -> None:
    rows, contract = _reviewed_pair_contract_fixture()

    result = _parse(tmp_path, rows=rows, contract=contract)

    assert result.movements[-2].debit == Decimal("25.00")
    assert result.movements[-2].credit == Decimal(0)
    assert result.movements[-1].debit == Decimal(0)
    assert result.movements[-1].credit == Decimal("25.00")
    assert result.physical_movement_count == 6
    assert result.logical_movement_count == 2


def test_parser_uses_reviewed_pair_role_instead_of_ordinary_amount_side(
    tmp_path: Path,
) -> None:
    rows, contract = _reviewed_pair_contract_fixture()
    rows[13][9] = "25.00"
    rows[14][9] = "25.00"
    del rows[15]
    contract = replace(
        contract,
        reviewed_amount_pairs=(
            PARSER.ReviewedAmountPair(
                debit=replace(
                    contract.reviewed_amount_pairs[0].debit,
                    amount_locator=_reviewed_amount_locator(
                        row_number=13,
                        column=9,
                        line_index=0,
                        amount_format="canonical_dot",
                    ),
                ),
                credit=replace(
                    contract.reviewed_amount_pairs[0].credit,
                    amount_locator=_reviewed_amount_locator(
                        row_number=14,
                        column=9,
                        line_index=0,
                        amount_format="canonical_dot",
                    ),
                ),
            ),
        ),
    )

    result = _parse(tmp_path, rows=rows, contract=contract)

    assert result.movements[-2].debit == Decimal("25.00")
    assert result.movements[-1].credit == Decimal("25.00")


def test_parser_rejects_missing_reviewed_amount_locator(
    tmp_path: Path,
) -> None:
    rows, contract = _reviewed_pair_contract_fixture()
    del rows[15][1]

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="amount locator (row|column) is missing",
    ):
        _parse(tmp_path, rows=rows, contract=contract)


def test_parser_rejects_changed_reviewed_amount_locator(
    tmp_path: Path,
) -> None:
    rows, contract = _reviewed_pair_contract_fixture()
    rows[15][1] = "25,00\nchanged"

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="amount locator content changed",
    ):
        _parse(tmp_path, rows=rows, contract=contract)


def test_parser_rejects_reviewed_pair_line_id_conflict(
    tmp_path: Path,
) -> None:
    rows, contract = _reviewed_pair_contract_fixture()
    rows[13][2] = "9"

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="pair movement line ID changed",
    ):
        _parse(tmp_path, rows=rows, contract=contract)


def test_parser_rejects_reviewed_pair_movement_row_conflict(
    tmp_path: Path,
) -> None:
    rows, contract = _reviewed_pair_contract_fixture()
    rows[17] = rows.pop(13)

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="pair movement row is missing",
    ):
        _parse(tmp_path, rows=rows, contract=contract)


def test_parser_rejects_reviewed_pair_movement_layout_conflict(
    tmp_path: Path,
) -> None:
    rows, contract = _reviewed_pair_contract_fixture()
    pair = contract.reviewed_amount_pairs[0]
    contract = replace(
        contract,
        reviewed_amount_pairs=(
            replace(
                pair,
                debit=replace(
                    pair.debit,
                    movement_layout_id="layout-a",
                ),
            ),
        ),
    )

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="pair movement layout does not match",
    ):
        _parse(tmp_path, rows=rows, contract=contract)


def test_parser_rejects_reviewed_pair_locator_layout_conflict(
    tmp_path: Path,
) -> None:
    rows, contract = _reviewed_pair_contract_fixture()
    pair = contract.reviewed_amount_pairs[0]
    contract = replace(
        contract,
        reviewed_amount_pairs=(
            replace(
                pair,
                debit=replace(
                    pair.debit,
                    amount_locator=replace(
                        pair.debit.amount_locator,
                        layout_id="layout-a",
                    ),
                ),
            ),
        ),
    )

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="amount locator layout does not match",
    ):
        _parse(tmp_path, rows=rows, contract=contract)


def test_parser_rejects_unequal_reviewed_amount_pair(
    tmp_path: Path,
) -> None:
    rows, contract = _reviewed_pair_contract_fixture()
    rows[15][1] = "25,00\n24,00"

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="pair values must be exactly equal",
    ):
        _parse(tmp_path, rows=rows, contract=contract)


def test_contract_rejects_duplicate_reviewed_amount_locator(
    tmp_path: Path,
) -> None:
    rows, contract = _reviewed_pair_contract_fixture()
    pair = contract.reviewed_amount_pairs[0]
    contract = replace(
        contract,
        reviewed_amount_pairs=(
            replace(
                pair,
                credit=replace(
                    pair.credit,
                    amount_locator=pair.debit.amount_locator,
                ),
            ),
        ),
    )

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="amount locators must be globally unique",
    ):
        _parse(tmp_path, rows=rows, contract=contract)


def test_parser_rejects_unconsumed_reviewed_amount_locator(
    tmp_path: Path,
) -> None:
    rows, contract = _reviewed_pair_contract_fixture()
    rows[14] = {1: "Narrative continuation\nwithout registered signals"}

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="amount locators were not consumed exactly once",
    ):
        _parse(tmp_path, rows=rows, contract=contract)


def test_parser_rejects_ordinary_amount_on_reviewed_pair_row(
    tmp_path: Path,
) -> None:
    rows, contract = _reviewed_pair_contract_fixture()
    rows[13][9] = "25.00"

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="undeclared ordinary amount",
    ):
        _parse(tmp_path, rows=rows, contract=contract)


def test_parser_rejects_ordinary_movement_using_pair_owned_locator(
    tmp_path: Path,
) -> None:
    rows, contract = _reviewed_pair_contract_fixture()
    pair = contract.reviewed_amount_pairs[0]
    contract = replace(
        contract,
        reviewed_amount_pairs=(
            PARSER.ReviewedAmountPair(
                debit=replace(
                    pair.debit,
                    amount_locator=_reviewed_amount_locator(
                        row_number=5,
                        column=10,
                        line_index=0,
                        layout_id="layout-a",
                        amount_format="canonical_dot",
                    ),
                ),
                credit=replace(
                    pair.credit,
                    amount_locator=_reviewed_amount_locator(
                        row_number=6,
                        column=14,
                        line_index=0,
                        layout_id="layout-a",
                        amount_format="canonical_dot",
                    ),
                ),
            ),
        ),
    )

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="locator reached ordinary physical extraction",
    ):
        _parse(tmp_path, rows=rows, contract=contract)


def test_parser_rejects_unlisted_blank_with_reviewed_pairs(
    tmp_path: Path,
) -> None:
    rows, contract = _reviewed_pair_contract_fixture()
    rows[17] = rows.pop(16)
    rows[16] = {2: "9", 5: "90 / 1 / 1"}

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="ambiguous or missing amount",
    ):
        _parse(tmp_path, rows=rows, contract=contract)


def test_parser_rejects_source_digest_mismatch(tmp_path: Path) -> None:
    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="exact reviewed digest",
    ):
        _parse(tmp_path, digest="0" * 64)


def test_parser_accepts_package_absolute_openpyxl_worksheet_target(
    tmp_path: Path,
) -> None:
    source = tmp_path / "synthetic.xlsx"
    digest = _write_xlsx(
        source,
        _rows(),
        worksheet_target="/xl/worksheets/sheet1.xml",
    )

    result = PARSER.parse_commercial_general_journal(
        source,
        expected_source_sha256=digest,
        layout_contract=_contract(),
    )

    assert len(result.movements) == 6
    assert result.debit_total == Decimal("210.25")


@pytest.mark.parametrize(
    "worksheet_target",
    (
        "//xl/worksheets/sheet1.xml",
        "../worksheets/sheet1.xml",
        "https://example.invalid/sheet1.xml",
    ),
)
def test_parser_rejects_unsafe_internal_worksheet_target(
    tmp_path: Path,
    worksheet_target: str,
) -> None:
    source = tmp_path / "synthetic.xlsx"
    digest = _write_xlsx(
        source,
        _rows(),
        worksheet_target=worksheet_target,
    )

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="relationship target is unsafe",
    ):
        PARSER.parse_commercial_general_journal(
            source,
            expected_source_sha256=digest,
            layout_contract=_contract(),
        )


def test_parser_rejects_lexical_source_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target.xlsx"
    digest = _write_xlsx(target, _rows())
    source = tmp_path / "source.xlsx"
    source.symlink_to(target)

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="must not be a symlink",
    ):
        PARSER.parse_commercial_general_journal(
            source,
            expected_source_sha256=digest,
            layout_contract=_contract(),
        )


def test_parser_rejects_hard_linked_source(tmp_path: Path) -> None:
    target = tmp_path / "target.xlsx"
    digest = _write_xlsx(target, _rows())
    source = tmp_path / "source.xlsx"
    os.link(target, source)

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="must not be hard linked",
    ):
        PARSER.parse_commercial_general_journal(
            source,
            expected_source_sha256=digest,
            layout_contract=_contract(),
        )


def test_parser_rejects_path_swapped_to_same_inode_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.xlsx"
    digest = _write_xlsx(source, _rows())
    moved = tmp_path / "moved.xlsx"
    original_lstat = PARSER.Path.lstat
    source_lstat_calls = 0

    def swap_on_final_lstat(path: Path) -> Any:
        nonlocal source_lstat_calls
        if path == source:
            source_lstat_calls += 1
            if source_lstat_calls == 2:
                source.rename(moved)
                source.symlink_to(moved)
        return original_lstat(path)

    monkeypatch.setattr(PARSER.Path, "lstat", swap_on_final_lstat)

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="changed to a symlink",
    ):
        PARSER.parse_commercial_general_journal(
            source,
            expected_source_sha256=digest,
            layout_contract=_contract(),
        )


def test_parser_rejects_unreviewed_layout_contract(tmp_path: Path) -> None:
    contract = replace(_contract(), review_status="pending")

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="explicitly reviewed",
    ):
        _parse(tmp_path, contract=contract)


def test_parser_rejects_unknown_page_layout(tmp_path: Path) -> None:
    rows = _rows()
    rows[9][12] = rows[9].pop(13)

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="exactly one reviewed layout",
    ):
        _parse(tmp_path, rows=rows)


def test_parser_rejects_unparsed_physical_movement_candidate(
    tmp_path: Path,
) -> None:
    rows = _rows()
    del rows[5][10]

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="ambiguous or missing amount",
    ):
        _parse(tmp_path, rows=rows)


@pytest.mark.parametrize(
    ("candidate_row", "expected_message"),
    [
        pytest.param({2: "7"}, "ambiguous or missing account", id="line-only"),
        pytest.param(
            {5: "70 / 1 / 1"},
            "ambiguous or missing line ID",
            id="account-only",
        ),
        pytest.param({9: "1.00"}, "ambiguous or missing line ID", id="debit-only"),
        pytest.param({13: "1.00"}, "ambiguous or missing line ID", id="credit-only"),
        pytest.param(
            {2: "7", 5: "70 / 1 / 1"},
            "ambiguous or missing amount",
            id="line-account",
        ),
        pytest.param(
            {2: "7", 9: "1.00"},
            "ambiguous or missing account",
            id="line-debit",
        ),
        pytest.param(
            {5: "70 / 1 / 1", 9: "1.00"},
            "ambiguous or missing line ID",
            id="account-debit",
        ),
        pytest.param(
            {2: "7", 13: "1.00"},
            "ambiguous or missing account",
            id="line-credit",
        ),
        pytest.param(
            {5: "70 / 1 / 1", 13: "1.00"},
            "ambiguous or missing line ID",
            id="account-credit",
        ),
    ],
)
def test_parser_rejects_each_incomplete_standalone_physical_signal_combination(
    tmp_path: Path,
    candidate_row: dict[int, str],
    expected_message: str,
) -> None:
    rows = _rows()
    rows[13] = candidate_row
    rows[14] = {1: "Totale generale 210,25 210,25"}

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match=expected_message,
    ):
        _parse(tmp_path, rows=rows)


@pytest.mark.parametrize(
    ("candidate_row", "expected_message"),
    [
        pytest.param(
            {7: "embedded 1,00"},
            "ambiguous or missing line ID",
            id="embedded-only",
        ),
        pytest.param(
            {2: "7", 7: "embedded 1,00"},
            "ambiguous or missing account",
            id="line-embedded",
        ),
        pytest.param(
            {5: "70 / 1 / 1", 7: "embedded 1,00"},
            "ambiguous or missing line ID",
            id="account-embedded",
        ),
    ],
)
def test_parser_rejects_each_incomplete_embedded_physical_signal_combination(
    tmp_path: Path,
    candidate_row: dict[int, str],
    expected_message: str,
) -> None:
    rows = _rows()
    rows[13] = candidate_row
    rows[14] = {1: "Totale generale 210,25 210,25"}
    contract = replace(
        _contract(),
        physical_embedded_amount_patterns=(
            PARSER.PhysicalEmbeddedAmountPattern(
                layout_ids=("layout-b",),
                column=7,
                pattern=(
                    r"^embedded "
                    r"(?P<debit>(?:0|[1-9][0-9]{0,2}"
                    r"(?:\.[0-9]{3})*),[0-9]{2})"
                    r"(?P<credit>(?!))?$"
                ),
                amount_format="italian_grouped_2",
            ),
        ),
    )

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match=expected_message,
    ):
        _parse(tmp_path, rows=rows, contract=contract)


def test_parser_ignores_physical_row_without_any_registered_signal(
    tmp_path: Path,
) -> None:
    rows = _rows()
    rows[13] = {
        7: "Narrative continuation without a registered signal.",
        16: "Reviewer note.",
    }
    rows[14] = {1: "Totale generale 210,25 210,25"}

    result = _parse(tmp_path, rows=rows)

    assert len(result.movements) == 6
    assert result.debit_total == Decimal("210.25")
    assert result.credit_total == Decimal("210.25")


def test_parser_rejects_unparsed_logical_movement_candidate(
    tmp_path: Path,
) -> None:
    rows = _rows()
    rows[7][1] = "28/02/2023\n" "3 30 / 1 / 1 not-an-amount\n" "4 40 / 1 / 1 60,00 C"

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="logical movement candidate",
    ):
        _parse(tmp_path, rows=rows)


def test_parser_rejects_duplicate_global_line_id(tmp_path: Path) -> None:
    rows = _rows()
    rows[6][3] = "1"

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="duplicate global line ID",
    ):
        _parse(tmp_path, rows=rows)


def test_parser_rejects_decreasing_global_line_id(tmp_path: Path) -> None:
    rows = _rows()
    rows[7][1] = "28/02/2023\n" "3 30 / 1 / 1 60,00 D\n" "6 40 / 1 / 1 60,00 C"
    rows[11][2] = "5"
    rows[12][2] = "7"

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="strictly increasing",
    ):
        _parse(tmp_path, rows=rows)


def test_parser_reports_but_does_not_interpret_line_id_gap(
    tmp_path: Path,
) -> None:
    rows = _rows()
    rows[11][2] = "6"
    rows[12][2] = "7"

    result = _parse(tmp_path, rows=rows)

    assert result.line_id_gap_count == 1


def test_parser_rejects_decreasing_posting_date(tmp_path: Path) -> None:
    rows = _rows()
    rows[10][2] = "2023-01-01 00:00:00"

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="nondecreasing",
    ):
        _parse(tmp_path, rows=rows)


def test_parser_rejects_physical_amount_ambiguity(tmp_path: Path) -> None:
    rows = _rows()
    rows[5][14] = "100.25"

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="ambiguous or missing amount",
    ):
        _parse(tmp_path, rows=rows)


def test_parser_uses_reviewed_physical_embedded_debit_amount(
    tmp_path: Path,
) -> None:
    rows = _rows()
    del rows[5][10]
    rows[5][8] = "description 100,25"
    contract = replace(
        _contract(),
        physical_embedded_amount_patterns=(
            PARSER.PhysicalEmbeddedAmountPattern(
                layout_ids=("layout-a",),
                column=8,
                pattern=(
                    r"^description "
                    r"(?P<debit>(?:0|[1-9][0-9]{0,2}"
                    r"(?:\.[0-9]{3})*),[0-9]{2})"
                    r"(?P<credit>(?!))?$"
                ),
                amount_format="italian_grouped_2",
            ),
        ),
    )

    result = _parse(tmp_path, rows=rows, contract=contract)

    assert result.movements[0].debit == Decimal("100.25")
    assert result.movements[0].credit == Decimal(0)


def test_parser_rejects_standalone_and_embedded_amount_ambiguity(
    tmp_path: Path,
) -> None:
    rows = _rows()
    rows[5][8] = "description 100,25"
    contract = replace(
        _contract(),
        physical_embedded_amount_patterns=(
            PARSER.PhysicalEmbeddedAmountPattern(
                layout_ids=("layout-a",),
                column=8,
                pattern=(
                    r"^description "
                    r"(?P<debit>(?:0|[1-9][0-9]{0,2}"
                    r"(?:\.[0-9]{3})*),[0-9]{2})"
                    r"(?P<credit>(?!))?$"
                ),
                amount_format="italian_grouped_2",
            ),
        ),
    )

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="ambiguous or missing amount",
    ):
        _parse(tmp_path, rows=rows, contract=contract)


def test_parser_uses_reviewed_account_prefix_when_description_contains_code_shape(
    tmp_path: Path,
) -> None:
    rows = _rows()
    rows[5][6] = "10 / 1 / 1 description 99 / 9 / 9"
    contract = replace(
        _contract(),
        account_code_pattern=r"^\s*[0-9]+\s*/\s*[0-9]+\s*/\s*[0-9]+",
    )

    result = _parse(tmp_path, rows=rows, contract=contract)

    assert result.movements[0].account_code == "10/1/1"


def test_parser_preserves_reviewed_physical_first_line_from_multiline_cell(
    tmp_path: Path,
) -> None:
    rows = _rows()
    rows[5][6] = "10 / 1 / 1 description\nnon-movement continuation"
    contract = replace(
        _contract(),
        account_code_pattern=r"^\s*[0-9]+\s*/\s*[0-9]+\s*/\s*[0-9]+",
    )

    result = _parse(tmp_path, rows=rows, contract=contract)

    assert result.movements[0].account_code == "10/1/1"
    assert result.movements[0].debit == Decimal("100.25")


def test_parser_rejects_source_control_mismatch_to_review(
    tmp_path: Path,
) -> None:
    contract = replace(
        _contract(),
        reviewed_final_debit_total="210.26",
    )

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="source final controls",
    ):
        _parse(tmp_path, contract=contract)


def test_parser_rejects_movement_total_mismatch_to_control(
    tmp_path: Path,
) -> None:
    rows = _rows()
    rows[5][10] = "99.25"

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="parsed movements do not reconcile",
    ):
        _parse(tmp_path, rows=rows)


def test_parser_rejects_missing_reviewed_sheet(tmp_path: Path) -> None:
    contract = replace(_contract(), sheet_name="Different reviewed sheet")

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="exactly one worksheet",
    ):
        _parse(tmp_path, contract=contract)


def test_parser_does_not_write_outputs(tmp_path: Path) -> None:
    result = _parse(tmp_path)

    assert len(result.movements) == 6
    assert sorted(path.name for path in tmp_path.iterdir()) == ["synthetic.xlsx"]


def test_contract_mapping_constructor_rejects_unexpected_field() -> None:
    value = asdict(_contract())
    value["entity"] = "synthetic"

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="unexpected fields",
    ):
        PARSER.general_journal_layout_contract_from_mapping(value)


def test_contract_mapping_constructor_rejects_removed_reviewed_zero_field() -> None:
    value = asdict(_contract())
    value["reviewed_zero_amount_line_ids"] = []

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="unexpected fields",
    ):
        PARSER.general_journal_layout_contract_from_mapping(value)


def test_contract_mapping_constructor_rejects_boolean_column() -> None:
    value = json.loads(json.dumps(asdict(_contract())))
    value["page_layouts"][0]["date_header_column"] = True

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="must be an integer",
    ):
        PARSER.general_journal_layout_contract_from_mapping(value)


def test_contract_mapping_constructor_rejects_unexpected_exclusion_field() -> None:
    value = json.loads(json.dumps(asdict(_contract())))
    value["reviewed_amountless_exclusions"] = [
        {
            "layout_id": "layout-b",
            "row_number": 13,
            "line_id": 7,
            "nonempty_columns": [2, 5],
            "residual_columns": [],
            "canonical_row_sha256": "0" * 64,
            "reason": "not part of the strict schema",
        }
    ]

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="contains unexpected fields",
    ):
        PARSER.general_journal_layout_contract_from_mapping(value)


def test_contract_mapping_constructor_rejects_boolean_exclusion_line_id() -> None:
    value = json.loads(json.dumps(asdict(_contract())))
    value["reviewed_amountless_exclusions"] = [
        {
            "layout_id": "layout-b",
            "row_number": 13,
            "line_id": True,
            "nonempty_columns": [2, 5],
            "residual_columns": [],
            "canonical_row_sha256": "0" * 64,
        }
    ]

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="line_id must be an integer",
    ):
        PARSER.general_journal_layout_contract_from_mapping(value)


def test_contract_mapping_constructor_requires_residual_columns() -> None:
    value = json.loads(json.dumps(asdict(_contract())))
    value["reviewed_amountless_exclusions"] = [
        {
            "layout_id": "layout-b",
            "row_number": 13,
            "line_id": 7,
            "nonempty_columns": [2, 5],
            "canonical_row_sha256": "0" * 64,
        }
    ]

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="is missing fields",
    ):
        PARSER.general_journal_layout_contract_from_mapping(value)


def test_contract_mapping_constructor_requires_exclusion_row_sha256() -> None:
    value = json.loads(json.dumps(asdict(_contract())))
    value["reviewed_amountless_exclusions"] = [
        {
            "layout_id": "layout-b",
            "row_number": 13,
            "line_id": 7,
            "nonempty_columns": [2, 5],
            "residual_columns": [],
        }
    ]

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="is missing fields",
    ):
        PARSER.general_journal_layout_contract_from_mapping(value)


@pytest.mark.parametrize("invalid_sha256", ("A" * 64, "g" * 64))
def test_contract_mapping_constructor_rejects_invalid_exclusion_row_sha256(
    invalid_sha256: str,
) -> None:
    value = json.loads(json.dumps(asdict(_contract())))
    value["reviewed_amountless_exclusions"] = [
        {
            "layout_id": "layout-b",
            "row_number": 13,
            "line_id": 7,
            "nonempty_columns": [2, 5],
            "residual_columns": [],
            "canonical_row_sha256": invalid_sha256,
        }
    ]

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="canonical row SHA-256 must be lowercase hexadecimal",
    ):
        PARSER.general_journal_layout_contract_from_mapping(value)


def test_contract_loader_round_trips_exact_digest_bound_json(
    tmp_path: Path,
) -> None:
    path = tmp_path / "layout-contract.json"
    payload = (json.dumps(asdict(_contract()), indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    path.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()

    loaded = PARSER.load_general_journal_layout_contract(
        path,
        expected_contract_sha256=digest,
    )

    assert loaded == _contract()


def test_contract_loader_rejects_duplicate_json_field(tmp_path: Path) -> None:
    path = tmp_path / "layout-contract.json"
    payload = json.dumps(asdict(_contract()), sort_keys=True)
    duplicate = (
        '{"contract_version":"clara.commercial_general_journal_layout.v5",'
        + payload[1:]
    ).encode("utf-8")
    path.write_bytes(duplicate)
    digest = hashlib.sha256(duplicate).hexdigest()

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="duplicate field",
    ):
        PARSER.load_general_journal_layout_contract(
            path,
            expected_contract_sha256=digest,
        )


def test_contract_loader_rejects_digest_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "layout-contract.json"
    path.write_text(
        json.dumps(asdict(_contract()), sort_keys=True),
        encoding="utf-8",
    )

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="exact reviewed digest",
    ):
        PARSER.load_general_journal_layout_contract(
            path,
            expected_contract_sha256="0" * 64,
        )


def test_parser_enforces_decompressed_member_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        PARSER,
        "MAX_XLSX_MEMBER_UNCOMPRESSED_BYTES",
        200,
    )

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="decompressed byte limit",
    ):
        _parse(tmp_path)


def test_parser_enforces_worksheet_row_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(PARSER, "MAX_WORKSHEET_ROWS", 5)

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="row-count limit",
    ):
        _parse(tmp_path)


def test_parser_enforces_worksheet_cell_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(PARSER, "MAX_WORKSHEET_CELLS", 10)

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="total cell-count limit",
    ):
        _parse(tmp_path)


def test_parser_rejects_worksheet_dtd_and_entity_declaration(
    tmp_path: Path,
) -> None:
    source = tmp_path / "synthetic.xlsx"
    worksheet_xml = _worksheet_xml(_rows()).replace(
        "?>",
        '?>\n<!DOCTYPE worksheet [<!ENTITY injected "not parsed">]>',
        1,
    )
    digest = _write_xlsx(
        source,
        _rows(),
        worksheet_xml=worksheet_xml,
    )

    with pytest.raises(
        PARSER.GeneralJournalParseError,
        match="forbidden DTD or entity declaration",
    ):
        PARSER.parse_commercial_general_journal(
            source,
            expected_source_sha256=digest,
            layout_contract=_contract(),
        )
