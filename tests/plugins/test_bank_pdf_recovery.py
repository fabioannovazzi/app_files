"""Bank recovery acceptance: source-backed repairs cannot bypass qualification."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest
from reportlab.pdfgen import canvas

HOST_ADAPTER = """import json, re, sys
source = json.load(sys.stdin)
lines = {}
for page in source["pages"]:
    for word in page["words"]:
        lines.setdefault((word["page"], word["row"]), []).append(word)
rows = []
for line in lines.values():
    dates = [w for w in line if re.fullmatch(r"\\d{2}/\\d{2}/\\d{4}", w["text"])]
    if not dates:
        if rows and all(190 <= float(w["x0"]) < 350 for w in line):
            rows[-1]["description"] += [w["id"] for w in line]
        continue
    amount = next(w for w in line if 430 <= float(w["x0"]) < 530)
    rows.append({
        "amount": amount["id"], "column": COLUMN,
        "date": [dates[0]["id"]], "value_date": [dates[1]["id"]],
        "description": [w["id"] for w in line if 190 <= float(w["x0"]) < 350],
        "reference": [w["id"] for w in line if 350 <= float(w["x0"]) < 430],
        "balance": next((w["id"] for w in line if 530 <= float(w["x0"])), None)
    })
CHANGE
json.dump({"rows": rows}, sys.stdout)
"""


@pytest.fixture
def bank_tools(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / "plugins/_shared/vendor/modules"))
    from vera_journal_pdf.adapter import source_inventory
    from vera_journal_pdf.bank import read_bank_pdf
    from vera_journal_pdf.recovery import recover_pdf

    return source_inventory, read_bank_pdf, recover_pdf


def bank_case(
    tmp_path, bank_tools, *, signed=False, change="", closing="980,00", totals=False
):
    """Independent two-page source with a continued description and bank controls."""
    inventory, _, _ = bank_tools
    source = tmp_path / "bank.pdf"
    pdf = canvas.Canvas(str(source), pagesize=(600, 800))
    pdf.setFont("Courier", 7)
    if not totals:
        pdf.drawString(190, 760, "OPENING BALANCE")
        pdf.drawRightString(590, 760, "1.000,00")
    pdf.drawString(22, 700, "01/01/2024")
    pdf.drawString(112, 700, "02/01/2024")
    pdf.drawString(192, 700, "PRIVATE SUPPLIER")
    pdf.drawString(352, 700, "TRANSFER-ABC")
    pdf.drawRightString(475, 700, "-30,00" if signed else "30,00")
    if not totals:
        pdf.drawRightString(590, 700, "970,00")
    pdf.drawString(192, 680, "Invoice payment")
    pdf.showPage()
    pdf.setFont("Courier", 7)
    pdf.drawString(192, 760, "continued description")
    pdf.drawString(22, 700, "03/01/2024")
    pdf.drawString(112, 700, "03/01/2024")
    pdf.drawString(192, 700, "PRIVATE CUSTOMER")
    pdf.drawString(352, 700, "TRANSFER-DEF")
    pdf.drawRightString(525, 700, "10,00")
    if totals:
        pdf.drawString(190, 660, "TOTAL DEBIT")
        pdf.drawRightString(475, 660, "30,00")
        pdf.drawString(190, 640, "TOTAL CREDIT")
        pdf.drawRightString(525, 640, "10,00")
    else:
        pdf.drawRightString(590, 700, "980,00")
        pdf.drawString(190, 640, "CLOSING BALANCE")
        pdf.drawRightString(590, 640, closing)
    pdf.save()
    layout = {
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "recovery_currency": "EUR",
        "document_kind": "bank_statement",
        "body": [20, 780],
        "columns": {
            "date": [20, 110],
            "value_date": [110, 190],
            "description": [190, 350],
            "reference": [350, 430],
            "balance": [530, 595],
            **(
                {"amount": [430, 530]}
                if signed
                else {"debit": [430, 480], "credit": [480, 530]}
            ),
        },
    }
    if signed:
        layout.update(
            negative_amount_notation="leading_minus",
            negative_amount_semantics="signed_side",
        )
    words = [
        w
        for p in inventory(source, layout, source_role="bank")["pages"]
        for w in p["words"]
    ]
    layout["statement_controls"] = {}
    control_labels = (
        (("debit_total", "DEBIT"), ("credit_total", "CREDIT"))
        if totals
        else (("opening_balance", "OPENING"), ("closing_balance", "CLOSING"))
    )
    for kind, label in control_labels:
        heading = next(w for w in words if w["text"] == label)
        line = [
            w
            for w in words
            if (w["page"], w["row"]) == (heading["page"], heading["row"])
        ]
        layout["statement_controls"][kind] = {
            "label": [w["id"] for w in line if float(w["x0"]) < 350],
            "amount": line[-1]["id"],
            "column": kind.split("_")[0] if totals else "balance",
        }
    output = tmp_path / "run"
    output.mkdir(exist_ok=True)
    script = output / "bank_adapter.py"
    column = (
        '"amount"' if signed else '("debit" if float(amount["x0"]) < 480 else "credit")'
    )
    script.write_text(HOST_ADAPTER.replace("COLUMN", column).replace("CHANGE", change))
    layout["agent_adapter"] = {
        "path": str(script),
        "sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
    }
    return source, output, layout


def test_bank_printed_movement_totals_can_independently_check_source(
    bank_tools, tmp_path
):
    _, reader, _ = bank_tools
    source, _, layout = bank_case(tmp_path, bank_tools, totals=True)

    rows, diagnostics = reader(source, layout, currency="EUR")

    assert diagnostics["accepted"] is True
    assert [r["amount"] for r in rows] == ["-30.00", "10.00"]


def test_bank_descending_statement_checks_balances_in_chronological_order(
    bank_tools, tmp_path
):
    inventory, reader, _ = bank_tools
    source, _, layout = bank_case(tmp_path, bank_tools)
    pdf = canvas.Canvas(str(source), pagesize=(600, 800))
    pdf.setFont("Courier", 7)
    pdf.drawString(190, 760, "CLOSING BALANCE")
    pdf.drawRightString(590, 760, "980,00")
    for y, date, right, amount, balance in (
        (700, "03/01/2024", 525, "10,00", "980,00"),
        (680, "01/01/2024", 475, "30,00", "970,00"),
    ):
        pdf.drawString(22, y, date)
        pdf.drawString(112, y, date)
        pdf.drawString(192, y, "Movement")
        pdf.drawRightString(right, y, amount)
        pdf.drawRightString(590, y, balance)
    pdf.drawString(190, 640, "OPENING BALANCE")
    pdf.drawRightString(590, 640, "1.000,00")
    pdf.save()
    layout["source_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    layout["transaction_order"] = "descending"
    words = inventory(source, layout, source_role="bank")["pages"][0]["words"]
    for kind, label in (("opening_balance", "OPENING"), ("closing_balance", "CLOSING")):
        heading = next(w for w in words if w["text"] == label)
        line = [w for w in words if w["row"] == heading["row"]]
        layout["statement_controls"][kind] = {
            "label": [w["id"] for w in line if float(w["x0"]) < 350],
            "amount": line[-1]["id"],
            "column": "balance",
        }

    rows, diagnostics = reader(source, layout, currency="EUR")

    assert diagnostics["accepted"] is True
    assert [r["amount"] for r in rows] == ["10.00", "-30.00"]


def test_ordinary_bank_inspection_preserves_partial_entries_and_issues(
    bank_tools, tmp_path
):
    from tests.plugins.test_journal_bank_reconciliation_plugin import (
        _save_csv,
        load_core,
    )

    bank, output, layout = bank_case(tmp_path, bank_tools, closing="981,00")
    journal = tmp_path / "journal.csv"
    _save_csv(journal, [["Date", "Amount"], ["2024-01-01", "-30.00"]])
    recipe = output / "recipe.json"
    recipe.write_text(
        json.dumps({"bank": {"files": {bank.name: {"pdf_bank_layout": layout}}}})
    )

    result = load_core().inspect_inputs(bank, journal, output, recipe)

    assert result.bank["row_count"] == 0
    assert result.bank["files"][0]["bank_diagnostics"]["readable_row_count"] == 2
    assert (
        "bank_opening_movements_closing_mismatch"
        in (output / "inspection.json").read_text()
    )
    assert "PRIVATE SUPPLIER" in (output / "readable_pdf_entries.csv").read_text()


@pytest.mark.parametrize("signed", [False, True])
def test_bank_recovery_reads_distinct_layouts_and_freezes_with_separate_history(
    bank_tools, tmp_path, signed
):
    _, reader, recover = bank_tools
    source, output, layout = bank_case(tmp_path, bank_tools, signed=signed)
    (output / "pdf_recovery").mkdir()
    (output / "pdf_recovery" / "session.json").write_text('{"journal": "unchanged"}')

    trial = recover(
        source,
        output,
        "trial",
        source_role="bank",
        currency="EUR",
        layout=layout,
        reason="Reviewed physical bank columns and continuation",
    )
    freeze = recover(
        source, output, "freeze", source_role="bank", currency="EUR", layout=layout
    )
    rows, diagnostics = reader(
        source, json.loads(Path(freeze["layout_path"]).read_text()), currency="EUR"
    )

    assert trial["status"] == "ready_to_freeze"
    assert diagnostics["accepted"] is True
    assert [r["amount"] for r in rows] == ["-30.00", "10.00"]
    assert (
        rows[0]["line_desc"] == "PRIVATE SUPPLIER Invoice payment continued description"
    )
    assert rows[0]["value_date"] == "2024-01-02"
    assert freeze["qualified"] is False
    assert freeze["population_operations_allowed"] is False
    assert Path(freeze["layout_path"]).parent.parent.name == "bank"
    assert json.loads((output / "pdf_recovery" / "session.json").read_text()) == {
        "journal": "unchanged"
    }


@pytest.mark.parametrize(
    "change,reason",
    [
        ("rows = rows[1:]", "unclaimed_source_amount"),
        ("rows.append(rows[0])", "duplicate_source_amount"),
        ('rows[0]["column"] = "credit"', "amount_outside_reviewed_side"),
        ('rows[0]["amount"] = "fabricated"', "invalid_source_reference"),
        ('rows[0]["amount_value"] = "-300.00"', "invalid_bank_movement_proposal"),
        ('rows[0]["date"] = rows[1]["date"]', "bank_date_outside_movement"),
        (
            'rows[0]["description"] += rows[1]["description"]',
            "bank_text_crosses_movement",
        ),
        ('rows[0]["balance"] = rows[1]["balance"]', "bank_balance_outside_movement"),
    ],
)
def test_incorrect_bank_corrections_retain_readable_rows_but_block_population(
    bank_tools, tmp_path, change, reason
):
    _, reader, _ = bank_tools
    source, _, layout = bank_case(tmp_path, bank_tools, change=change)

    rows, diagnostics = reader(source, layout, currency="EUR")

    assert rows == []
    assert diagnostics["accepted"] is False
    assert diagnostics["readable_row_count"] >= 1
    assert reason in {i["reason"] for i in diagnostics["unresolved_issues"]}


def test_wrong_bank_closing_balance_cannot_be_repaired_by_model_values(
    bank_tools, tmp_path
):
    _, _, recover = bank_tools
    source, output, layout = bank_case(tmp_path, bank_tools, closing="981,00")

    trial = recover(
        source,
        output,
        "trial",
        source_role="bank",
        currency="EUR",
        layout=layout,
        reason="Investigate printed closing balance",
    )

    assert trial["status"] == "revise_layout"
    assert trial["readable_row_count"] == 2
    retained = json.loads(Path(trial["readable_entries_path"]).read_text())
    assert retained["population_operations_allowed"] is False
    assert "bank_opening_movements_closing_mismatch" in {
        i["reason"] for i in retained["unresolved_issues"]
    }
    assert "unqualified_requires_review" in Path(trial["readable_csv_path"]).read_text()


def test_missing_bank_controls_preserve_reading_without_qualifying_statement(
    bank_tools, tmp_path
):
    _, reader, _ = bank_tools
    source, _, layout = bank_case(tmp_path, bank_tools)
    layout.pop("statement_controls")

    rows, diagnostics = reader(source, layout, currency="EUR")

    assert rows == []
    assert diagnostics["readable_row_count"] == 2
    assert "bank_requires_independent_printed_controls" in {
        i["reason"] for i in diagnostics["unresolved_issues"]
    }


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("document_kind", "payment_receipt", "bank_statement"),
        ("source_sha256", "0" * 64, "exact PDF"),
        ("recovery_currency", "CHF", "currency differs"),
    ],
)
def test_bank_recovery_rejects_wrong_source_role_or_binding(
    bank_tools, tmp_path, field, value, message
):
    _, reader, _ = bank_tools
    source, _, layout = bank_case(tmp_path, bank_tools)
    layout[field] = value

    with pytest.raises(ValueError, match=message):
        reader(source, layout, currency="EUR")


def test_bank_adapter_code_change_invalidates_frozen_replay(bank_tools, tmp_path):
    _, reader, _ = bank_tools
    source, _, layout = bank_case(tmp_path, bank_tools)
    Path(layout["agent_adapter"]["path"]).write_text("raise RuntimeError('changed')")

    with pytest.raises(ValueError, match="adapter changed"):
        reader(source, layout, currency="EUR")


def test_bank_wrong_running_balance_is_rejected_even_with_valid_closing(
    bank_tools, tmp_path
):
    _, reader, _ = bank_tools
    source, _, layout = bank_case(tmp_path, bank_tools)
    layout["transaction_order"] = "descending"

    rows, diagnostics = reader(source, layout, currency="EUR")

    assert rows == []
    assert "bank_running_balance_mismatch" in {
        i["reason"] for i in diagnostics["unresolved_issues"]
    }


def test_bank_inventory_and_inspection_use_selected_source_history(
    bank_tools, tmp_path
):
    _, _, recover = bank_tools
    source, output, layout = bank_case(tmp_path, bank_tools)

    result = recover(
        source, output, "inventory", source_role="bank", currency="EUR", layout=layout
    )

    assert result["source_role"] == "bank"
    assert result["page_count"] == 2
    assert Path(result["inventory_path"]).parent.parent.name == "bank"


def test_bank_recovery_reaches_reconciliation_only_after_mapping_review(
    bank_tools, tmp_path
):
    from tests.plugins.test_journal_bank_reconciliation_plugin import (
        _attach_current_mapping_receipt,
        _save_csv,
        _seal_relationship_recipe,
        load_core,
    )

    _, _, recover = bank_tools
    bank, output, layout = bank_case(tmp_path, bank_tools)
    recover(
        bank,
        output,
        "trial",
        source_role="bank",
        currency="EUR",
        layout=layout,
        reason="Read bank source tokens",
    )
    frozen = recover(
        bank, output, "freeze", source_role="bank", currency="EUR", layout=layout
    )
    exact = json.loads(Path(frozen["layout_path"]).read_text())
    journal = tmp_path / "journal.csv"
    _save_csv(
        journal,
        [
            ["Date", "Amount", "Description"],
            ["2024-01-01", "-30.00", "Supplier"],
            ["2024-01-03", "10.00", "Customer"],
        ],
    )
    recipe_path = output / "recipe.json"
    recipe_path.write_text(
        json.dumps({"bank": {"files": {bank.name: {"pdf_bank_layout": exact}}}})
    )
    core = load_core()
    inspection = output / "inspection"
    unreviewed = core.inspect_inputs(bank, journal, inspection, recipe_path)
    recipe_path = inspection / "suggested_recipe.json"
    recipe = json.loads(recipe_path.read_text())
    receipts = json.loads((inspection / "input_receipts.json").read_text())["receipts"]
    _attach_current_mapping_receipt(
        core,
        recipe,
        receipts,
        side="bank",
        source_path=bank,
        decision_id="decision.bank.recovery",
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
        bank,
        journal,
        tmp_path / "reconciled",
        sealed,
        tolerance="0",
        date_window_days=0,
    )

    assert unreviewed.bank["row_count"] == 0
    assert unreviewed.bank["files"][0]["bank_diagnostics"]["accepted"] is True
    assert result.matches.height == 2
    assert result.unmatched_bank.height == 0
    assert result.unmatched_journal.height == 0

    changed = json.loads(sealed.read_text())
    changed["bank"]["files"][bank.name]["pdf_bank_layout"]["body"][0] = 21
    sealed.write_text(json.dumps(changed))
    stale = core.inspect_inputs(bank, journal, output / "stale", sealed)
    assert stale.bank["row_count"] == 0
    assert stale.bank["files"][0]["qualification_status"] == "needs_review"
    assert stale.bank["files"][0]["bank_diagnostics"]["accepted"] is True


@pytest.mark.parametrize("host", ["source", "codex", "cowork"])
def test_bank_recovery_managed_command_selects_bank_then_seals_and_reconciles(
    bank_tools, tmp_path, host
):
    from tests.plugins.test_journal_bank_reconciliation_plugin import (
        _load_customer_ledger,
        _save_csv,
    )
    from tests.plugins.test_journal_bank_review_receipts import (
        _decisions,
        _runtime_environment,
    )

    repo = Path(__file__).resolve().parents[2]
    root = repo / "plugins/vera"
    if host != "source":
        archive = (
            repo
            / "plugin_packages/vera"
            / ("vera-plugin.zip" if host == "codex" else "vera-claude-plugin.zip")
        )
        with ZipFile(archive) as bundle:
            bundle.extractall(tmp_path / "package")
        root = next(
            (tmp_path / "package").rglob("scripts/managed_python_runtime.py")
        ).parents[1]
    environment = _runtime_environment(root, tmp_path)
    environment["MPARANZA_INCIDENT_DELIVERY"] = "local-only"
    bank, _, layout = bank_case(tmp_path, bank_tools)
    journal = tmp_path / "journal.csv"
    _save_csv(
        journal,
        [
            ["Date", "Description", "Reference", "Amount", "Balance", "Currency"],
            ["2024-01-01", "Supplier", "TRANSFER-ABC", "-30.00", "970.00", "EUR"],
            ["2024-01-03", "Customer", "TRANSFER-DEF", "10.00", "980.00", "EUR"],
        ],
    )
    ledger = _load_customer_ledger()
    client = tmp_path / "client"
    client.mkdir()
    client_id = "client_555555555555555555555555"
    ledger.create_client_manifest(client, client_id)
    engagement = ledger.create_engagement(client, client_id, "Synthetic bank recovery")
    inputs = [
        ledger.import_document(
            client, client_id, engagement["engagement_id"], path, role
        )["receipt"]["input_id"]
        for path, role in ((bank, "source"), (journal, "journal"))
    ]
    prepared = ledger.prepare_run(
        client,
        client_id,
        engagement["engagement_id"],
        "journal-bank-reconciliation",
        "synthetic-test",
        input_ids=inputs,
    )
    case = ledger.start_run(
        client, engagement["engagement_id"], prepared["run"]["run_id"]
    )
    output = Path(case["output_dir"])
    sources = {
        item["role"]: Path(item["path"]) for item in case["context"]["input_bindings"]
    }
    adapter = output / "bank_adapter.py"
    adapter.write_bytes(Path(layout["agent_adapter"]["path"]).read_bytes())
    layout["agent_adapter"]["path"] = str(adapter)
    recipe = output / "recipe.json"
    recipe.write_text(
        json.dumps(
            {"bank": {"files": {sources["source"].name: {"pdf_bank_layout": layout}}}}
        )
    )

    def run(script, *arguments):
        return subprocess.run(
            [
                sys.executable,
                str(root / "scripts/managed_python_runtime.py"),
                "--module",
                "journal-bank-reconciliation",
                "run",
                f"scripts/{script}",
                "--client-engagement",
                case["context_path"],
                *map(str, arguments),
            ],
            capture_output=True,
            text=True,
            cwd=root,
            env=environment,
            timeout=90,
            check=False,
        )

    base = (sources["source"], sources["journal"], "--output-dir", output)
    initial = run("inspect_inputs.py", *base)
    assert initial.returncode == 0, initial.stderr
    inventory = run(
        "inspect_inputs.py",
        sources["source"].parent,
        sources["journal"],
        "--output-dir",
        output,
        "--recipe",
        recipe,
        "--pdf-side",
        "bank",
        "--pdf-source",
        sources["source"],
        "--pdf-currency",
        "EUR",
        "--pdf-recovery",
        "inventory",
    )
    assert inventory.returncode == 0, inventory.stderr
    assert '"status": "evidence_only"' in inventory.stderr
    trial = run(
        "inspect_inputs.py",
        *base,
        "--recipe",
        recipe,
        "--pdf-side",
        "bank",
        "--pdf-source",
        sources["source"],
        "--pdf-currency",
        "EUR",
        "--pdf-recovery",
        "trial",
        "--pdf-reason",
        "Reviewed bank source columns",
    )
    assert trial.returncode == 0, trial.stderr
    assert '"status": "ready_to_freeze"' in trial.stderr
    frozen = run(
        "inspect_inputs.py",
        *base,
        "--recipe",
        recipe,
        "--pdf-side",
        "bank",
        "--pdf-currency",
        "EUR",
        "--pdf-recovery",
        "freeze",
    )
    assert frozen.returncode == 0, frozen.stderr
    assert not (output / "pdf_recovery/session.json").exists()
    inspected = run("inspect_inputs.py", *base, "--recipe", recipe)
    assert inspected.returncode == 0, inspected.stderr
    recipe = output / "suggested_recipe.json"
    choices = _decisions(json.loads(recipe.read_text()))
    choices["bank"]["files"][sources["source"].name].update(
        pdf_bank_layout=layout, excluded_monetary_columns=[]
    )
    choices["journal"]["files"][sources["journal"].name]["csv_field_delimiter"] = ","
    decisions = output / "decisions.json"
    decisions.write_text(json.dumps(choices))
    sealed = run(
        "seal_review_receipts.py",
        "--output-dir",
        output,
        "--recipe",
        recipe,
        "--decisions",
        decisions,
    )
    assert sealed.returncode == 0, sealed.stderr

    reconciled = run(
        "run_reconciliation.py",
        sources["source"],
        sources["journal"],
        "--output-dir",
        output / "reconciliation",
        "--recipe",
        recipe,
        "--tolerance",
        "0",
        "--date-window-days",
        "0",
    )

    assert reconciled.returncode == 0, reconciled.stderr
    assert "matched=2" in reconciled.stderr
    assert (output / "reconciliation/material_value_ledger.json").is_file()
    rejected = run(
        "inspect_inputs.py",
        *base,
        "--pdf-side",
        "bank",
        "--pdf-source",
        sources["journal"],
        "--pdf-currency",
        "EUR",
        "--pdf-recovery",
        "inspect",
    )
    assert rejected.returncode != 0
    assert "differs from the bound source file" in rejected.stderr
