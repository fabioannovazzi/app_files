"""Behavioral acceptance for host-authored recovery and independent checks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from reportlab.pdfgen import canvas

from tests.plugins.journal_pdf_fixtures import grid_layout, write_grid_pdf

# This is fixture-specific host code, deliberately outside the installed parser.
# It understands a header the maintained reader does not recognize.
ADAPTER = """import json, re, sys
data = json.load(sys.stdin)
rows = []
header = None
for page in data["pages"]:
    lines = {}
    for word in page["words"]:
        lines.setdefault(word["row"], []).append(word)
    for line in lines.values():
        entry = next((w for w in line if w["text"].startswith("ENTRY-")), None)
        if entry:
            header = (entry, next(w for w in line if re.fullmatch(r"\\d{2}/\\d{2}/\\d{4}", w["text"])))
            continue
        if any(w["text"] == "TOTALI" for w in line):
            continue
        amount = next((w for w in line if re.fullmatch(r"\\d+,\\d{2}", w["text"])), None)
        if amount:
            side = "debit" if float(amount["x0"]) < 486 else "credit"
            low, high = (20, 98) if side == "debit" else (98, 174)
            rows.append({"amount": amount["id"], "side": side,
                "account": [w["id"] for w in line if low <= float(w["x0"]) < high],
                "description": [w["id"] for w in line if 174 <= float(w["x0"]) < 404],
                "date": header[1]["id"], "registration": header[0]["id"]})
CHANGE
json.dump({"rows": rows}, sys.stdout)
"""


def unfamiliar_source(path: Path, *, wrong_total: bool = False) -> dict:
    """Two independently specified balanced registrations, unfamiliar headers."""
    pdf = canvas.Canvas(str(path), pagesize=(600, 800))
    pdf.setFont("Courier", 8)
    pdf.drawString(20, 750, "Journal ENTRY-7 date 01/01/2024")
    pdf.drawString(24, 720, "101")
    pdf.drawString(178, 720, "PRIVATE CUSTOMER")
    pdf.drawRightString(480, 720, "30,00")
    pdf.drawString(104, 700, "201")
    pdf.drawRightString(562, 700, "30,00")
    pdf.drawString(20, 670, "Journal ENTRY-8 date 02/01/2024")
    pdf.drawString(24, 640, "102")
    pdf.drawRightString(480, 640, "20,00")
    pdf.drawString(104, 620, "202")
    pdf.drawRightString(562, 620, "20,00")
    pdf.drawString(178, 590, "TOTALI PROGRESSIVI")
    pdf.drawRightString(480, 590, "51,00" if wrong_total else "50,00")
    pdf.drawRightString(562, 590, "50,00")
    pdf.save()
    layout = grid_layout()
    layout.pop("rule_characters")
    layout.pop("border_art")
    layout["source_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return layout


def proposed_adapter(output: Path, layout: dict, change: str = "") -> dict:
    output.mkdir(exist_ok=True)
    script = output / "local_adapter.py"
    script.write_text(ADAPTER.replace("CHANGE", change), encoding="utf-8")
    return {
        **layout,
        "agent_adapter": {
            "path": str(script),
            "sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
        },
    }


@pytest.fixture
def pdf_tools(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / "plugins/_shared/vendor/modules"))
    from vera_journal_pdf import read_registration_pdf
    from vera_journal_pdf.recovery import recover_pdf

    return read_registration_pdf, recover_pdf


def test_unfamiliar_header_recovered_and_frozen_without_changing_reader(
    pdf_tools, tmp_path
):
    reader, recover = pdf_tools
    source = tmp_path / "journal.pdf"
    layout = unfamiliar_source(source)
    output = tmp_path / "run"
    failed = recover(
        source,
        output,
        "trial",
        currency="EUR",
        layout=layout,
        reason="Unfamiliar registration header",
    )
    evidence = recover(source, output, "inventory", currency="EUR", layout=layout)
    proposal = proposed_adapter(output, layout)

    passed = recover(
        source,
        output,
        "trial",
        currency="EUR",
        layout=proposal,
        reason="Use original ENTRY header tokens",
    )
    frozen = recover(source, output, "freeze", currency="EUR", layout=proposal)
    rows, diagnostics = reader(
        source, json.loads(Path(frozen["layout_path"]).read_text())
    )

    assert failed["status"] == "revise_layout"
    assert Path(evidence["inventory_path"]).is_file()
    assert passed["diagnostics"]["accepted"] is True
    assert diagnostics["accepted"] is True
    assert [(r["account"], r["debit"], r["credit"]) for r in rows] == [
        ("101", "30.00", "0"),
        ("201", "0", "30.00"),
        ("102", "20.00", "0"),
        ("202", "0", "20.00"),
    ]
    assert frozen["qualified"] is False
    assert frozen["population_operations_allowed"] is False
    assert Path(passed["layout"]["agent_adapter"]["path"]).parent.name == "adapters"


@pytest.mark.parametrize(
    "change,reason",
    [
        ("rows = rows[2:]", "unclaimed_source_amount"),
        ("rows.append(rows[0])", "duplicate_source_amount"),
        ('rows[0]["side"] = "credit"', "amount_outside_reviewed_side"),
        ('rows[0]["amount"] = "invented"', "invalid_source_reference"),
        ('rows[0]["debit"] = "300.00"', "invalid_posting_proposal"),
        (
            'rows[0]["account"] = rows[2]["account"]',
            "account_reference_outside_posting",
        ),
        (
            'rows[2]["date"] = rows[0]["date"]; rows[2]["registration"] = rows[0]["registration"]',
            "posting_crosses_registration_header",
        ),
    ],
)
def test_plausible_wrong_corrections_are_rejected_but_readable_rows_retained(
    pdf_tools, tmp_path, change, reason
):
    reader, _ = pdf_tools
    source = tmp_path / "journal.pdf"
    layout = proposed_adapter(tmp_path / "run", unfamiliar_source(source), change)

    rows, diagnostics = reader(source, layout)

    assert rows == []
    assert diagnostics["accepted"] is False
    assert diagnostics["readable_row_count"] > 0
    assert reason in {issue["reason"] for issue in diagnostics["unresolved_issues"]}


def test_balance_does_not_override_wrong_printed_control(pdf_tools, tmp_path):
    reader, _ = pdf_tools
    source = tmp_path / "journal.pdf"
    layout = proposed_adapter(
        tmp_path / "run", unfamiliar_source(source, wrong_total=True)
    )

    rows, diagnostics = reader(source, layout)

    assert rows == []
    assert diagnostics["readable_row_count"] == 4
    assert "running_total_does_not_match_postings" in {
        i["reason"] for i in diagnostics["unresolved_issues"]
    }


def test_builtin_partial_reader_continues_after_failure_and_keeps_population_blocked(
    pdf_tools, tmp_path
):
    reader, recover = pdf_tools
    source = tmp_path / "journal.pdf"
    layout = write_grid_pdf(source, pages=3, issue="wrong_total")

    rows, diagnostics = reader(source, layout, retain_partial=True)
    trial = recover(
        source,
        tmp_path / "run",
        "trial",
        currency="EUR",
        layout=layout,
        reason="Inspect total mismatch",
    )
    readable = json.loads(Path(trial["readable_entries_path"]).read_text())

    assert rows == []
    assert diagnostics["page_count"] == 3
    assert {r["source_page"] for r in diagnostics["readable_rows"]} == {1, 2, 3}
    assert readable["rows"] == diagnostics["readable_rows"]
    assert readable["unresolved_issues"]
    assert readable["population_operations_allowed"] is False


@pytest.mark.parametrize("failure", ["decoder", "date"])
def test_unreadable_middle_page_does_not_erase_other_readable_pages(
    pdf_tools, tmp_path, monkeypatch, failure
):
    from pdfplumber.page import Page
    from pdfplumber.utils.exceptions import PdfminerException

    reader, _ = pdf_tools
    source = tmp_path / "journal.pdf"
    layout = write_grid_pdf(source, pages=3)
    extract = Page.extract_words

    def failing_page(page, **kwargs):
        if page.page_number == 2 and failure == "decoder":
            raise PdfminerException("Synthetic damaged page")
        words = extract(page, **kwargs)
        if page.page_number == 2:
            return [
                {
                    **word,
                    "text": (
                        "31/02/2024" if word["text"] == "01/01/2024" else word["text"]
                    ),
                }
                for word in words
            ]
        return words

    monkeypatch.setattr(Page, "extract_words", failing_page)

    rows, diagnostics = reader(source, layout, retain_partial=True)

    assert rows == []
    assert {row["source_page"] for row in diagnostics["readable_rows"]} == {1, 3}
    assert diagnostics["page_count"] == 3
    assert {issue["source_page"] for issue in diagnostics["unresolved_issues"]} >= {2}


def test_word_inventory_retains_surviving_pages_after_decoder_failure(
    pdf_tools, tmp_path, monkeypatch
):
    from pdfplumber.page import Page
    from pdfplumber.utils.exceptions import PdfminerException
    from vera_journal_pdf.adapter import source_inventory

    source = tmp_path / "journal.pdf"
    layout = write_grid_pdf(source, pages=3)
    extract = Page.extract_words

    def failing_page(page, **kwargs):
        if page.page_number == 2:
            raise PdfminerException("Synthetic damaged page")
        return extract(page, **kwargs)

    monkeypatch.setattr(Page, "extract_words", failing_page)

    result = source_inventory(source, layout)

    assert len(result["pages"]) == 3
    assert result["pages"][0]["words"]
    assert result["pages"][1]["words"] == []
    assert result["pages"][2]["words"]
    assert result["issues"] == [
        {"source_page": 2, "source_row": 0, "reason": "page_decode_failed"}
    ]


def test_adapter_code_change_invalidates_replay(pdf_tools, tmp_path):
    reader, _ = pdf_tools
    source = tmp_path / "journal.pdf"
    layout = proposed_adapter(tmp_path / "run", unfamiliar_source(source))
    Path(layout["agent_adapter"]["path"]).write_text("raise RuntimeError('changed')")

    with pytest.raises(ValueError, match="adapter changed"):
        reader(source, layout)


def test_recovery_currency_survives_bank_inspection_and_cannot_silently_change(
    pdf_tools, tmp_path
):
    from tests.plugins.test_journal_bank_reconciliation_plugin import (
        _save_csv,
        load_core,
    )

    reader, recover = pdf_tools
    source = tmp_path / "journal.pdf"
    output = tmp_path / "run"
    layout = proposed_adapter(output, unfamiliar_source(source))
    recover(
        source,
        output,
        "trial",
        currency="CHF",
        layout=layout,
        reason="Reviewed source currency and headers",
    )
    frozen = recover(source, output, "freeze", currency="CHF", layout=layout)
    exact = json.loads(Path(frozen["layout_path"]).read_text())

    bank = tmp_path / "bank.csv"
    _save_csv(bank, [["Date", "Amount", "Currency"], ["2024-01-01", "30.00", "CHF"]])
    recipe = output / "recipe.json"
    recipe.write_text(
        json.dumps(
            {"journal": {"files": {source.name: {"pdf_registration_layout": exact}}}}
        )
    )

    result = load_core().inspect_inputs(bank, source, output, recipe)

    assert {
        row["currency"]
        for row in result.journal["files"][0]["registration_diagnostics"][
            "readable_rows"
        ]
    } == {"CHF"}
    with pytest.raises(ValueError, match="currency differs"):
        reader(source, exact, currency="EUR")


@pytest.mark.parametrize(
    "change",
    [
        "sys.exit(2)",
        'raise ValueError("private source text")',
        'sys.stdout.write("invalid json"); sys.exit(0)',
    ],
)
def test_adapter_execution_failures_are_retained_as_failed_attempts(
    pdf_tools, tmp_path, change
):
    _, recover = pdf_tools
    source = tmp_path / "journal.pdf"
    layout = proposed_adapter(tmp_path / "run", unfamiliar_source(source), change)

    result = recover(
        source,
        tmp_path / "run",
        "trial",
        currency="EUR",
        layout=layout,
        reason="Host adapter trial",
    )

    assert result["diagnostics"]["accepted"] is False
    assert result["status"] == "revise_layout"
    assert Path(result["readable_entries_path"]).is_file()


def test_recovery_rejects_adapter_outside_run(pdf_tools, tmp_path):
    _, recover = pdf_tools
    source = tmp_path / "journal.pdf"
    layout = proposed_adapter(tmp_path / "elsewhere", unfamiliar_source(source))

    with pytest.raises(ValueError, match="workflow's output"):
        recover(
            source,
            tmp_path / "run",
            "trial",
            currency="EUR",
            layout=layout,
            reason="Invalid location",
        )


def test_adapter_reaches_reconciliation_only_after_source_mapping_review(
    pdf_tools, tmp_path
):
    from tests.plugins.test_journal_bank_reconciliation_plugin import (
        _attach_current_mapping_receipt,
        _save_csv,
        _seal_relationship_recipe,
        load_core,
    )

    _, recover = pdf_tools
    core = load_core()
    journal, bank = tmp_path / "journal.pdf", tmp_path / "bank.csv"
    output = tmp_path / "run"
    layout = proposed_adapter(output, unfamiliar_source(journal))
    recover(
        journal,
        output,
        "trial",
        currency="EUR",
        layout=layout,
        reason="Source header evidence",
    )
    freeze = recover(journal, output, "freeze", currency="EUR", layout=layout)
    frozen = json.loads(Path(freeze["layout_path"]).read_text())
    _save_csv(
        bank,
        [
            ["Date", "Amount", "Description"],
            ["2024-01-01", "30.00", "PRIVATE CUSTOMER"],
            ["2024-01-02", "20.00", "Second entry"],
        ],
    )
    proposed = output / "recipe.json"
    proposed.write_text(
        json.dumps(
            {"journal": {"files": {journal.name: {"pdf_registration_layout": frozen}}}}
        )
    )
    inspection = output / "inspection"
    unreviewed = core.inspect_inputs(bank, journal, inspection, proposed)
    recipe_path = inspection / "suggested_recipe.json"
    recipe = json.loads(recipe_path.read_text())
    receipts = json.loads((inspection / "input_receipts.json").read_text())["receipts"]
    _attach_current_mapping_receipt(
        core,
        recipe,
        receipts,
        side="journal",
        source_path=journal,
        decision_id="decision.mapping.agent_pdf",
    )
    recipe_path.write_text(json.dumps(recipe))
    sealed = _seal_relationship_recipe(
        core,
        recipe_path,
        inspection / "input_receipts.json",
        tolerance="0",
        date_window_days=0,
        policy_updates={"direction_policy": "same_sign"},
    )

    result = core.run_reconciliation(
        bank, journal, output / "results", sealed, tolerance="0", date_window_days=0
    )

    assert unreviewed.journal["row_count"] == 0
    assert result.matches.height == 2
    assert result.unmatched_journal.height == 2
    assert (inspection / "readable_pdf_entries.csv").is_file()
    assert (output / "results/material_value_ledger.json").is_file()


def test_failed_adapter_inspection_keeps_csv_but_no_reconciliation_population(
    pdf_tools, tmp_path
):
    from tests.plugins.test_journal_bank_reconciliation_plugin import (
        _save_csv,
        load_core,
    )

    core = load_core()
    journal, bank = tmp_path / "journal.pdf", tmp_path / "bank.csv"
    output = tmp_path / "run"
    layout = proposed_adapter(output, unfamiliar_source(journal), "rows = rows[2:]")
    _save_csv(bank, [["Date", "Amount"], ["2024-01-02", "20.00"]])
    proposed = output / "recipe.json"
    proposed.write_text(
        json.dumps(
            {"journal": {"files": {journal.name: {"pdf_registration_layout": layout}}}}
        )
    )

    result = core.inspect_inputs(bank, journal, output, proposed)

    assert result.journal["row_count"] == 0
    assert (
        result.journal["files"][0]["qualification_status"]
        == "unsupported_source_layout"
    )
    assert (
        result.journal["files"][0]["registration_diagnostics"]["readable_row_count"]
        == 2
    )
    assert (
        "unqualified_requires_review"
        in (output / "readable_pdf_entries.csv").read_text()
    )
