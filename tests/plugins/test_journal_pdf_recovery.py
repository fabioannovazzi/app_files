"""Regression tests for opt-in recovery, with a pinned pre-change reader oracle."""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

from tests.plugins.journal_pdf_fixtures import write_grid_pdf, write_negative_grid_pdf

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def reader(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "plugins/_shared/vendor/modules"))
    from vera_journal_pdf import read_registration_pdf

    return read_registration_pdf


@pytest.fixture
def recovery(reader):
    from vera_journal_pdf.recovery import recover_pdf

    return recover_pdf


@pytest.mark.parametrize(
    "notation,amount", [("leading_minus", "-25,88"), ("trailing_minus", "25,88-")]
)
@pytest.mark.parametrize(
    "semantics,expected",
    [
        ("signed_side", [("-25.88", "0"), ("0", "-25.88")]),
        ("opposite_side", [("0", "25.88"), ("25.88", "0")]),
    ],
)
def test_reviewed_negatives_preserve_accounts_and_source_totals(
    reader, tmp_path, notation, amount, semantics, expected
):
    source = tmp_path / "reversal.pdf"
    layout = write_negative_grid_pdf(source, amount=amount)
    layout.update(
        negative_amount_notation=notation, negative_amount_semantics=semantics
    )

    rows, diag = reader(source, layout)

    assert diag["accepted"], diag
    assert [(r["debit"], r["credit"]) for r in rows] == expected
    assert [r["account"] for r in rows] == ["1.01.001", "2.01.001"]
    assert rows[0]["line_desc"] == "OPS! SRLS"
    assert rows[0]["source_amount_text"] == amount
    assert rows[0]["source_amount_side"] == "debit"
    assert rows[0]["negative_amount_semantics"] == semantics
    assert diag["running_total_basis"] == "signed_source_sides"
    assert diag["running_total_controls"][0]["recomputed"] == {
        "debit": "74.12",
        "credit": "74.12",
    }
    assert diag["running_total_controls"][0]["matched"] is True


@pytest.mark.parametrize(
    "amount,notation,reason",
    [
        ("25,88-", None, "unsupported_negative_amount_notation"),
        ("-25,88", None, "negative_amount_side_requires_review"),
        ("(25,88)", None, "unsupported_negative_amount_notation"),
        ("-25,88", "trailing_minus", "unsupported_negative_amount_notation"),
        ("25,88-", "leading_minus", "unsupported_negative_amount_notation"),
        ("0,00-", None, "unsupported_negative_amount_notation"),
    ],
)
def test_negative_eligibility_reports_every_page_before_parsing(
    reader, tmp_path, amount, notation, reason
):
    source = tmp_path / "reversal.pdf"
    layout = write_negative_grid_pdf(source, amount=amount, pages=3)
    if notation:
        layout.update(
            negative_amount_notation=notation, negative_amount_semantics="signed_side"
        )

    rows, diag = reader(source, layout)

    assert rows == []
    assert diag["accepted"] is False
    assert diag["candidate_row_count"] == 0
    assert diag["negative_amount_eligibility"]["page_count"] == 3
    assert diag["negative_amount_eligibility"]["issue_count"] == 6
    assert [r["source_page"] for r in diag["rejected_rows"]] == [1, 1, 2, 2, 3, 3]
    assert {r["reason"] for r in diag["rejected_rows"]} == {reason}
    assert diag["rejected_rows"][0]["source_row"] == 2
    assert diag["rejected_rows"][0]["amount_text"] == amount


@pytest.mark.parametrize(
    "amount,total,opening",
    [
        ("1.234,56-", "765,44", "2000"),
        ("25,88-", "25,88-", "0"),
    ],
)
def test_reviewed_negatives_handle_grouped_amounts_and_negative_footers(
    reader, tmp_path, amount, total, opening
):
    source = tmp_path / "reversal.pdf"
    layout = write_negative_grid_pdf(source, amount=amount, total=total)
    layout["running_totals"].update(opening_debit=opening, opening_credit=opening)
    layout.update(
        negative_amount_notation="trailing_minus",
        negative_amount_semantics="signed_side",
    )

    rows, diag = reader(source, layout)

    assert diag["accepted"], diag
    assert len(rows) == 2
    assert diag["running_total_controls"][0]["matched"] is True


@pytest.mark.parametrize("semantics", ["signed_side", "opposite_side"])
def test_same_source_side_reversal_balances_after_review(reader, tmp_path, semantics):
    source = tmp_path / "reversal.pdf"
    layout = write_negative_grid_pdf(
        source, total="100,00", counterpart="25,88", same_side=True
    )
    layout.update(
        negative_amount_notation="trailing_minus", negative_amount_semantics=semantics
    )

    rows, diag = reader(source, layout)

    assert diag["accepted"], diag
    assert len(rows) == 2
    assert rows[1]["debit"] == "25.88"
    assert rows[1]["credit"] == "0"


@pytest.mark.parametrize(
    "options",
    [
        {"negative_amount_notation": "trailing_minus"},
        {"negative_amount_semantics": "signed_side"},
        {
            "negative_amount_notation": "parentheses",
            "negative_amount_semantics": "signed_side",
        },
        {
            "negative_amount_notation": "trailing_minus",
            "negative_amount_semantics": "automatic",
        },
    ],
)
def test_negative_policy_requires_two_explicit_supported_choices(
    reader, tmp_path, options
):
    source = tmp_path / "reversal.pdf"
    layout = write_negative_grid_pdf(source)
    layout.update(options)

    with pytest.raises(ValueError, match="negative_amount_"):
        reader(source, layout)


@pytest.mark.parametrize(
    "amount,reason",
    [
        ("100,00-", "unsupported_negative_amount_notation"),
        ("-100,00", "negative_amount_side_requires_review"),
    ],
)
def test_legacy_negative_diagnostics_do_not_enable_unreviewed_postings(
    reader, tmp_path, amount, reason
):
    from tests.plugins.test_journal_sampling_plugin import (
        _write_registration_journal_pdf,
    )

    source = tmp_path / "legacy.pdf"
    layout = _write_registration_journal_pdf(source, credit=amount)

    rows, diag = reader(source, layout)

    assert rows == []
    assert reason in [r["reason"] for r in diag["rejected_rows"]]


@pytest.mark.parametrize(
    "total,counterpart,reason",
    [
        ("74,13", "25,88-", "running_total_does_not_match_postings"),
        ("74,12", "25,87-", "registration_debit_credit_do_not_balance"),
        ("74,12", "-25,88-", "posting_requires_registration_account_and_amount"),
    ],
)
def test_negative_policy_does_not_relax_completeness_controls(
    reader, tmp_path, total, counterpart, reason
):
    source = tmp_path / "reversal.pdf"
    layout = write_negative_grid_pdf(source, total=total, counterpart=counterpart)
    layout.update(
        negative_amount_notation="trailing_minus",
        negative_amount_semantics="opposite_side",
    )

    rows, diag = reader(source, layout)

    assert rows == []
    assert reason in [r["reason"] for r in diag["rejected_rows"]]


def test_recovery_retains_all_negative_locations_with_bounded_projection(
    recovery, tmp_path
):
    source = tmp_path / "reversal.pdf"
    layout = write_negative_grid_pdf(source, pages=26)
    out = tmp_path / "out"

    result = recovery(
        source,
        out,
        "trial",
        currency="EUR",
        layout=layout,
        reason="Review printed reversal notation",
    )

    saved = json.loads((out / "pdf_recovery/attempt-01.json").read_text())
    assert saved["diagnostics"]["negative_amount_eligibility"]["issue_count"] == 52
    assert len(saved["diagnostics"]["negative_amount_eligibility"]["issues"]) == 52
    assert len(result["diagnostics"]["negative_amount_eligibility"]["issues"]) == 50
    assert (
        result["diagnostics"]["negative_amount_eligibility"]["issues_truncated"] is True
    )
    assert result["status"] == "revise_layout"


def test_grid_removes_only_rules_and_excludes_totals(reader, tmp_path):
    source = tmp_path / "grid.pdf"
    layout = write_grid_pdf(source, pages=1)

    rows, diag = reader(source, layout)

    assert diag["accepted"], diag
    assert len(rows) == 3
    assert rows[0]["account"] == "2.04.001 ABCDEF"
    assert rows[0]["line_desc"] == "Example! punctuation Invoice continuation"
    assert [r["debit"] for r in rows] == ["32.94", "0", "0"]
    assert [r["credit"] for r in rows] == ["0", "27.00", "5.94"]
    assert diag["running_total_controls"][0]["matched"] is True
    assert diag["candidate_row_count"] == 3


def test_grid_retains_registration_across_three_pages(reader, tmp_path):
    # A dedicated three-page registration checks state without new headers.
    from reportlab.pdfgen import canvas

    from tests.plugins.journal_pdf_fixtures import POSITIONS, grid_layout

    source = tmp_path / "continued.pdf"
    pdf = canvas.Canvas(str(source), pagesize=(600, 800))
    for index, amount in enumerate(("100,00", "40,00", "60,00")):
        pdf.setFont("Courier", 8)
        header = (
            "1 ---- 01/01/2024 ----"
            if index == 0
            else "seguito registrazione del 01/01/2024"
        )
        pdf.drawString(20, 750, "+----+ " + header + " ----+----+")
        for x in POSITIONS:
            pdf.drawString(x, 720, "!")
        pdf.drawString(24.8 if index == 0 else 101.6, 720, "1.01.001")
        pdf.drawString(178.4, 720, "Posting")
        pdf.drawRightString(480 if index == 0 else 562, 720, amount)
        pdf.drawString(178.4, 680, "TOTALI PROGRESSIVI")
        pdf.drawRightString(480, 680, "100,00")
        pdf.drawRightString(562, 680, ("0,00", "40,00", "100,00")[index])
        pdf.showPage()
    pdf.save()

    rows, diag = reader(source, grid_layout())

    assert diag["accepted"], diag
    assert [r["movement_number"] for r in rows] == ["1", "1", "1"]
    assert [r["source_page"] for r in rows] == [1, 2, 3]
    assert len(diag["running_total_controls"]) == 3


@pytest.mark.parametrize(
    "issue,reason",
    [
        ("malformed_header", "unrecognized_decorated_registration_line"),
        ("unbalanced", "registration_debit_credit_do_not_balance"),
        ("wrong_total", "running_total_does_not_match_postings"),
        ("shift", "reviewed_rule_positions_not_present_on_page"),
        ("orphan", "continuation_without_matching_registration"),
        ("unassigned_money", "monetary_value_outside_reviewed_bands"),
        ("continuation_date", "continuation_without_matching_registration"),
        ("missing_continuation", "posting_without_page_continuation"),
    ],
)
def test_grid_failure_withholds_all_postings(reader, tmp_path, issue, reason):
    source = tmp_path / "grid.pdf"
    pages = (
        1
        if issue
        in {
            "orphan",
            "malformed_header",
            "unbalanced",
            "wrong_total",
            "unassigned_money",
        }
        else 2
    )
    layout = write_grid_pdf(source, pages=pages, issue=issue)

    rows, diag = reader(source, layout)

    assert rows == []
    assert not diag["accepted"]
    assert reason in [r["reason"] for r in diag["rejected_rows"]]
    assert len(diag["rejected_rows"]) <= 50
    assert diag["reason"] == "registration_pdf_incomplete_or_unbalanced"


@pytest.mark.parametrize(
    "key,value",
    [
        ("rule_characters", None),
        ("rule_characters", {"text": "A", "x0": ["20", "96.8"], "tolerance": "0.5"}),
        ("rule_characters", {"text": "!", "x0": [20, "96.8"], "tolerance": "0.5"}),
        ("rule_characters", {"text": "!", "x0": ["20", "20"], "tolerance": "0.5"}),
        ("rule_characters", {"text": "!", "x0": ["20", "96.8"], "tolerance": "20"}),
        ("border_art", True),
        (
            "running_totals",
            {
                "labels": ["TOTALI"],
                "opening_debit": "NaN",
                "opening_credit": "0",
                "required_each_page": True,
            },
        ),
    ],
)
def test_invalid_opt_in_configuration_is_rejected(reader, tmp_path, key, value):
    source = tmp_path / "grid.pdf"
    layout = write_grid_pdf(source, pages=1)
    layout[key] = value
    with pytest.raises(ValueError):
        reader(source, layout)


@pytest.mark.parametrize(
    "variant",
    ["valid", "unbalanced", "wrong_continuation", "unassigned", "no_layout", "grid"],
)
def test_legacy_reader_matches_pinned_v2_records_and_diagnostics(
    reader, tmp_path, variant
):
    import types

    from tests.plugins.test_journal_sampling_plugin import (
        _write_registration_journal_pdf,
    )

    # Snapshot from f7344305f, not mutable HEAD and not dependent on Git in CI.
    snapshot = Path(__file__).parent / "fixtures/registration_reader_v2.py.txt"
    baseline = types.ModuleType("pinned_registration_reader_v2")
    exec(compile(snapshot.read_text(), str(snapshot), "exec"), baseline.__dict__)
    source = tmp_path / "journal.pdf"
    layout = _write_registration_journal_pdf(
        source,
        credit="99,00" if variant == "unbalanced" else "100,00",
        continuation_date=(
            "02/01/2024" if variant == "wrong_continuation" else "01/01/2024"
        ),
        credit_x=590 if variant == "unassigned" else 500,
    )
    if variant == "no_layout":
        layout = None
    if variant == "grid":
        layout = write_grid_pdf(source, pages=1)
        for key in ("rule_characters", "border_art", "running_totals"):
            layout.pop(key)

    assert reader(source, layout) == baseline.read_registration_pdf(source, layout)


def test_agent_can_inspect_revise_freeze_and_replay(recovery, reader, tmp_path):
    source = tmp_path / "grid.pdf"
    layout = write_grid_pdf(source, pages=1)
    out = tmp_path / "normalization"
    evidence = recovery(
        source, out, "inspect", currency="EUR", pages=[1], region=[15, 90, 180, 220]
    )
    assert evidence["status"] == "evidence_only"
    assert evidence["evidence"]["sampled_pages"][0]["characters"]
    original = copy.deepcopy(layout)
    original.pop("running_totals")
    failed = recovery(
        source,
        out,
        "trial",
        currency="EUR",
        layout=original,
        reason="Test separators and decorated headers",
    )
    assert failed["status"] == "revise_layout"
    assert failed["qualified"] is False
    before = (out / "pdf_recovery/attempt-01.json").read_bytes()
    succeeded = recovery(
        source,
        out,
        "trial",
        currency="EUR",
        layout=layout,
        reason="Footer has two cumulative amounts; retain as controls",
    )
    assert succeeded["status"] == "ready_to_freeze"
    frozen = recovery(source, out, "freeze", currency="EUR", layout=layout)
    assert frozen["status"] == "frozen_requires_mapping_review"
    assert frozen["qualified"] is False
    assert (out / "pdf_recovery/attempt-01.json").read_bytes() == before
    captured = json.loads(Path(frozen["layout_path"]).read_text())
    assert reader(source, captured)[1]["accepted"]
    assert recovery(source, out, "freeze", currency="EUR", layout=layout) == frozen


def test_recovery_requires_successful_exact_recipe_and_rejects_stale_source(
    recovery, tmp_path
):
    source = tmp_path / "grid.pdf"
    layout = write_grid_pdf(source, pages=1)
    out = tmp_path / "out"
    with pytest.raises(ValueError, match="latest successful"):
        recovery(source, out, "freeze", currency="EUR", layout=layout)
    recovery(
        source, out, "trial", currency="EUR", layout=layout, reason="Reviewed geometry"
    )
    altered = copy.deepcopy(layout)
    altered["body"][0] = "21"
    with pytest.raises(ValueError, match="exact latest"):
        recovery(source, out, "freeze", currency="EUR", layout=altered)
    with source.open("ab") as stream:
        stream.write(b"\n%changed source")
    with pytest.raises(ValueError, match="stale"):
        recovery(source, out, "freeze", currency="EUR", layout=layout)


@pytest.mark.parametrize("prior_attempts", [4, 100])
def test_recovery_accepts_new_evidence_after_prior_failures_and_keeps_history(
    recovery, tmp_path, prior_attempts
):
    source = tmp_path / "grid.pdf"
    layout = write_grid_pdf(source, pages=1)
    out = tmp_path / "out"
    invalid = copy.deepcopy(layout)
    for number in range(prior_attempts):
        invalid["rule_characters"]["tolerance"] = str(2 + number)
        recovery(
            source,
            out,
            "trial",
            currency="EUR",
            layout=invalid,
            reason="Investigating rule geometry",
        )
    retained = (out / "pdf_recovery/attempt-01.json").read_bytes()

    result = recovery(
        source,
        out,
        "trial",
        currency="EUR",
        layout=layout,
        reason="Use the inspected source's complete physical layout",
    )

    assert result["status"] == "ready_to_freeze"
    assert result["qualified"] is False
    assert (
        len(list((out / "pdf_recovery").glob("attempt-*.json"))) == prior_attempts + 1
    )
    assert (out / "pdf_recovery/attempt-01.json").read_bytes() == retained


def test_recovery_can_inspect_more_than_twelve_regions_without_resetting_history(
    recovery, tmp_path
):
    source = tmp_path / "grid.pdf"
    write_grid_pdf(source, pages=1)
    out = tmp_path / "out"
    for _ in range(12):
        recovery(source, out, "inspect", currency="EUR", pages=[1])
    retained = (out / "pdf_recovery/inspection-01.json").read_bytes()

    result = recovery(source, out, "inspect", currency="EUR", pages=[1])

    assert result["status"] == "evidence_only"
    assert len(list((out / "pdf_recovery").glob("inspection-*.json"))) == 13
    assert (out / "pdf_recovery/inspection-01.json").read_bytes() == retained


def test_recovery_does_not_repeat_an_identical_recipe(recovery, tmp_path):
    source = tmp_path / "grid.pdf"
    layout = write_grid_pdf(source, pages=1)
    recovery(
        source,
        tmp_path / "out",
        "trial",
        currency="EUR",
        layout=layout,
        reason="Initial review",
    )
    with pytest.raises(ValueError, match="already tried"):
        recovery(
            source,
            tmp_path / "out",
            "trial",
            currency="EUR",
            layout=layout,
            reason="retry",
        )


def test_inspection_renders_all_requested_pages(recovery, tmp_path):
    source = tmp_path / "grid.pdf"
    write_grid_pdf(source)
    evidence = recovery(
        source, tmp_path / "out", "inspect", currency="EUR", pages=[1, 2], render=True
    )
    assert all(
        Path(p["render"]).is_file() for p in evidence["evidence"]["sampled_pages"]
    )


@pytest.mark.parametrize("semantics", [None, "signed_side", "opposite_side"])
def test_recovered_layout_passes_managed_normalization_replay_and_sampling(
    tmp_path, semantics
):
    from tests.plugins.test_journal_sampling_plugin import (
        _approve_suggested_recipe,
        _running_customer_output,
        load_core,
    )

    core = load_core()
    source = tmp_path / "grid.pdf"
    layout = (
        write_negative_grid_pdf(source)
        if semantics
        else write_grid_pdf(source, pages=1)
    )
    if semantics:
        layout.update(
            negative_amount_notation="trailing_minus",
            negative_amount_semantics=semantics,
        )
    context_path, output = _running_customer_output(tmp_path, source_path=source)
    context = core.load_client_engagement_context(context_path)
    bound = Path(context["input_bindings"][0]["path"])
    normalization = output / "normalization"
    recipe = output / "proposed.json"
    recipe.write_text(
        json.dumps(
            {
                "files": {
                    bound.name: {
                        "parser": "registration_pdf",
                        "layout": layout,
                        "currency": "EUR",
                    }
                }
            }
        )
    )
    result = core.recover_pdf_layout(
        bound,
        normalization,
        recipe,
        client_engagement=context,
        action="trial",
        currency="EUR",
        reason="Reviewed grid and cumulative footer",
    )
    assert result["status"] == "ready_to_freeze"
    frozen = core.recover_pdf_layout(
        bound,
        normalization,
        recipe,
        client_engagement=context,
        action="freeze",
        currency="EUR",
    )
    layout = json.loads(Path(frozen["layout_path"]).read_text())
    recipe.write_text(
        json.dumps(
            {
                "files": {
                    bound.name: {
                        "parser": "registration_pdf",
                        "layout": layout,
                        "currency": "EUR",
                    }
                }
            }
        )
    )
    core.inspect_path(bound, normalization, recipe, client_engagement=context)
    reviewed = normalization / "suggested_recipe.json"
    _approve_suggested_recipe(reviewed)
    normalized = core.normalize_path(
        bound, normalization, reviewed, client_engagement=context
    )
    sample = core.run_sample(
        normalization / "normalized_journal.csv",
        output / "sample",
        method="random",
        size=1,
        client_engagement=context,
    )

    assert normalized.frame.height == (2 if semantics else 3)
    if semantics:
        assert normalized.frame["amount_signed"].cast(str).to_list() == [
            "-25.88",
            "25.88",
        ]
    assert sample.frame.height == 1
    assert (normalization / "pdf_recovery/freeze_receipt.json").is_file()


def test_managed_recovery_rejects_unbound_source_before_writes(tmp_path):
    from tests.plugins.test_journal_sampling_plugin import (
        _running_customer_output,
        load_core,
    )

    core = load_core()
    source = tmp_path / "grid.pdf"
    write_grid_pdf(source, pages=1)
    context_path, output = _running_customer_output(tmp_path, source_path=source)
    context = core.load_client_engagement_context(context_path)
    with pytest.raises(ValueError, match="exact journal receipt"):
        core.recover_pdf_layout(
            source,
            output / "normalization",
            None,
            client_engagement=context,
            action="inspect",
            currency="EUR",
        )
    assert not (output / "normalization/pdf_recovery").exists()


@pytest.mark.parametrize("mutate", [False, True])
@pytest.mark.parametrize("semantics", [None, "signed_side", "opposite_side"])
def test_ruled_layout_bank_mapping_receipt_seals_recovery_options(
    tmp_path, mutate, semantics
):
    from tests.plugins.test_journal_bank_reconciliation_plugin import (
        _attach_current_mapping_receipt,
        _save_csv,
        _seal_relationship_recipe,
        load_core,
    )

    core = load_core()
    journal, bank = tmp_path / "grid.pdf", tmp_path / "bank.csv"
    layout = (
        write_negative_grid_pdf(journal)
        if semantics
        else write_grid_pdf(journal, pages=1)
    )
    if semantics:
        layout.update(
            negative_amount_notation="trailing_minus",
            negative_amount_semantics=semantics,
        )
    _save_csv(
        bank,
        [
            ["Date", "Amount", "Description"],
            (
                ["2023-01-01", "-25.88", "OPS! SRLS"]
                if semantics
                else ["2024-01-01", "32.94", "Example punctuation"]
            ),
        ],
    )
    proposed = tmp_path / "proposed.json"
    proposed.write_text(
        json.dumps(
            {"journal": {"files": {journal.name: {"pdf_registration_layout": layout}}}}
        )
    )
    inspection = tmp_path / "inspection"
    core.inspect_inputs(bank, journal, inspection, proposed)
    recipe_path = inspection / "suggested_recipe.json"
    recipe = json.loads(recipe_path.read_text())
    receipts = json.loads((inspection / "input_receipts.json").read_text())["receipts"]
    _attach_current_mapping_receipt(
        core,
        recipe,
        receipts,
        side="journal",
        source_path=journal,
        decision_id="decision.mapping.ruled_pdf",
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
    if mutate:
        changed = json.loads(sealed.read_text())
        changed_layout = changed["journal"]["files"][journal.name][
            "pdf_registration_layout"
        ]
        if semantics:
            changed_layout["negative_amount_semantics"] = (
                "opposite_side" if semantics == "signed_side" else "signed_side"
            )
        else:
            changed_layout["rule_characters"]["tolerance"] = "0.6"
        sealed.write_text(json.dumps(changed))
        with pytest.raises(ValueError):
            core.run_reconciliation(
                bank,
                journal,
                tmp_path / "results",
                sealed,
                tolerance="0",
                date_window_days=0,
            )
    else:
        result = core.run_reconciliation(
            bank,
            journal,
            tmp_path / "results",
            sealed,
            tolerance="0",
            date_window_days=0,
        )
        assert result.matches.height == 1
        assert result.unmatched_journal.height == (1 if semantics else 2)


def test_freeze_rejects_changed_replay_results(recovery, monkeypatch, tmp_path):
    import vera_journal_pdf

    source = tmp_path / "grid.pdf"
    layout = write_grid_pdf(source, pages=1)
    recovery(
        source,
        tmp_path / "out",
        "trial",
        currency="EUR",
        layout=layout,
        reason="Reviewed rules",
    )
    original = vera_journal_pdf.read_registration_pdf

    def changed(*args, **kwargs):
        rows, diag = original(*args, **kwargs)
        rows[0]["account"] = "DIFFERENT"
        return rows, diag

    monkeypatch.setattr(vera_journal_pdf, "read_registration_pdf", changed)
    with pytest.raises(ValueError, match="Fresh PDF replay differs"):
        recovery(source, tmp_path / "out", "freeze", currency="EUR", layout=layout)
    assert not (tmp_path / "out/pdf_recovery/frozen_layout.json").exists()


def test_recovery_returns_bounded_controls_but_retains_full_evidence(
    recovery, tmp_path
):
    source = tmp_path / "grid.pdf"
    layout = write_grid_pdf(source, pages=8)
    result = recovery(
        source,
        tmp_path / "out",
        "trial",
        currency="EUR",
        layout=layout,
        reason="Reviewed page geometry and cumulative controls",
    )
    assert result["status"] == "ready_to_freeze"
    assert result["diagnostics"]["running_total_control_count"] == 8
    assert len(result["diagnostics"]["running_total_controls"]) == 3
    retained = json.loads((tmp_path / "out/pdf_recovery/attempt-01.json").read_text())
    assert len(retained["diagnostics"]["running_total_controls"]) == 8


def test_reviewed_ignore_label_cannot_hide_a_posting(reader, tmp_path):
    source = tmp_path / "grid.pdf"
    layout = write_grid_pdf(source, pages=1)
    layout["ignored_line_prefixes"] = ["2.04.001 ABCDEF Example! punctuation 32,94"]
    rows, diag = reader(source, layout)
    assert rows == []
    assert "monetary_line_cannot_be_ignored" in [
        r["reason"] for r in diag["rejected_rows"]
    ]


def test_invalid_render_region_preserves_attempt_and_allows_recovery(
    recovery, tmp_path
):
    source = tmp_path / "grid.pdf"
    write_grid_pdf(source, pages=1)
    invalid = recovery(
        source,
        tmp_path / "out",
        "inspect",
        currency="EUR",
        pages=[1],
        region=[0, 0, 999, 999],
        render=True,
    )
    assert invalid["status"] == "invalid_inspection"
    result = recovery(
        source,
        tmp_path / "out",
        "inspect",
        currency="EUR",
        pages=[1],
        render=True,
    )
    assert result["status"] == "evidence_only"
    assert Path(result["evidence"]["sampled_pages"][0]["render"]).is_file()
    assert len(list((tmp_path / "out/pdf_recovery").glob("inspection-*.json"))) == 2


@pytest.mark.parametrize("host", ["source", "codex", "cowork"])
@pytest.mark.parametrize(
    "workflow", ["journal-sampling", "journal-bank-reconciliation"]
)
def test_managed_host_recovery_entrypoint(tmp_path, monkeypatch, host, workflow):
    from tests.plugins import test_journal_bank_review_receipts as harness
    from tests.plugins.test_journal_sampling_plugin import (
        _running_customer_output,
        load_core,
    )

    root = ROOT / "plugins/vera"
    if host != "source":
        filename = "vera-plugin.zip" if host == "codex" else "vera-claude-plugin.zip"
        with ZipFile(ROOT / "plugin_packages/vera" / filename) as archive:
            archive.extractall(tmp_path / "package")
        root = next(
            (tmp_path / "package").rglob("scripts/managed_python_runtime.py")
        ).parents[1]
    environment = harness._runtime_environment(root, tmp_path)
    if workflow == "journal-sampling":
        source = tmp_path / "journal.pdf"
        layout = write_negative_grid_pdf(source)
        layout.update(
            negative_amount_notation="trailing_minus",
            negative_amount_semantics="opposite_side",
        )
        context, output = _running_customer_output(tmp_path, source_path=source)
        hydrated = load_core().load_client_engagement_context(context)
        bound = Path(hydrated["input_bindings"][0]["path"])
        output = output / "normalization"
        proposed = {
            "files": {bound.name: {"parser": "registration_pdf", "layout": layout}}
        }
        script, inputs = "inspect_journal.py", [bound]
    else:
        original = harness._write_pdf_table
        layouts = []

        def write_source(path, rows):
            if path.name == "journal.pdf":
                layout = write_negative_grid_pdf(path)
                layout.update(
                    negative_amount_notation="trailing_minus",
                    negative_amount_semantics="opposite_side",
                )
                layouts.append(layout)
            else:
                original(path, rows)

        monkeypatch.setattr(harness, "_write_pdf_table", write_source)
        case = harness._case(tmp_path)
        context, output = Path(case["context_path"]), Path(case["output_dir"])
        sources = {
            item["role"]: Path(item["path"])
            for item in case["context"]["input_bindings"]
        }
        bound = sources["journal"]
        proposed = {
            "journal": {"files": {bound.name: {"pdf_registration_layout": layouts[0]}}}
        }
        script, inputs = "inspect_inputs.py", [sources["source"], bound]
    output.mkdir(parents=True, exist_ok=True)
    recipe = output / "proposed.json"
    recipe.write_text(json.dumps(proposed))
    for action in ("inspect", "trial", "freeze"):
        result = subprocess.run(
            [
                sys.executable,
                str(root / "scripts/managed_python_runtime.py"),
                "--module",
                workflow,
                "run",
                f"scripts/{script}",
                *map(str, inputs),
                "--output-dir",
                str(output),
                "--client-engagement",
                str(context),
                "--pdf-recovery",
                action,
                "--pdf-currency",
                "EUR",
                "--recipe",
                str(recipe),
                "--pdf-reason",
                "Reviewed glyph coordinates, continuation and totals",
            ],
            capture_output=True,
            text=True,
            env=environment,
            cwd=root,
            timeout=90,
            check=False,
        )
        assert result.returncode == 0, result.stderr
    receipt = json.loads((output / "pdf_recovery/freeze_receipt.json").read_text())
    assert receipt["status"] == "frozen_requires_mapping_review"
    assert receipt["qualified"] is False
    trial = json.loads((output / "pdf_recovery/attempt-01.json").read_text())
    assert trial["diagnostics"]["accepted"] is True
