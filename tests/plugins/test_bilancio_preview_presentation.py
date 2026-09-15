"""Check the native accounts preview as a readable, current review document."""

from __future__ import annotations

import importlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
from lxml import etree

from tests.plugins.test_bilancio_xbrl_it_plugin import _prepared_case, xbrl_case

_preview_text_module = importlib.import_module("accounts_preview_text")
preview_check_message = _preview_text_module.preview_check_message
preview_text = _preview_text_module.preview_text
preview_reason = _preview_text_module.preview_reason


def test_all_shipped_rule_pack_questions_have_italian_display_text():
    root = Path(__file__).resolve().parents[2] / "plugins/bilancio-xbrl-it/rulepacks"

    def questions(value):
        if isinstance(value, dict):
            if "question_id" in value and "title" in value:
                yield value
            for child in value.values():
                yield from questions(child)
        elif isinstance(value, list):
            for child in value:
                yield from questions(child)

    shipped = [
        question
        for path in root.rglob("*.json")
        for question in questions(json.loads(path.read_text()))
    ]
    assert len({q["title"] for q in shipped}) == 27
    for question in shipped:
        assert preview_text(question["title"], "it") != question["title"]
        assert (
            preview_text(question["evidence_requested"], "it")
            != question["evidence_requested"]
        )
        assert preview_text(question["title"], "en") == question["title"]


@pytest.mark.parametrize("language", ["it", "en"])
def test_preview_retains_authored_text_and_unknown_check_subjects(language):
    authored = "Reviewer-specific assessment: <untrusted source>"
    case = {"questionnaire": []}

    assert preview_text(authored, language) == authored
    assert preview_check_message({"message": authored}, case, language) == authored
    assert preview_reason(authored, language) == authored
    assert (
        preview_reason("schedule NEW_TYPE is present or reviewer-triggered", language)
        == "schedule NEW_TYPE is present or reviewer-triggered"
    )
    assert "ANSWER:new_subject" in preview_check_message(
        {"message": "Triggered disclosure is incomplete: ANSWER:new_subject"},
        case,
        language,
    )


@pytest.mark.parametrize(
    ("language", "expected", "manual", "negative"),
    [
        ("it", "Criteri di valutazione applicati", "leasing finanziari", "Mancano 11"),
        (
            "en",
            "Accounting policies applied",
            "finance leases",
            "11 annual confirmations",
        ),
    ],
)
def test_preview_check_subjects_use_current_question_titles(
    language, expected, manual, negative
):
    case = {
        "questionnaire": [
            {
                "answer_key": "accounting_policies",
                "title": "Accounting policies applied",
            }
        ]
    }

    result = preview_check_message(
        {
            "message": "Triggered disclosure is incomplete: ANSWER:accounting_policies, NARRATIVE_SECTION:POLICIES"
        },
        case,
        language,
    )

    assert expected in result
    assert "ANSWER:" not in result
    assert "NARRATIVE_SECTION:" not in result
    assert manual in preview_check_message(
        {
            "message": "Disclosure applicability requires professional decisions for: FINANCE_LEASES_PRESENT"
        },
        case,
        language,
    )
    assert negative in preview_check_message(
        {"message": "11 annual negative confirmations are missing"},
        case,
        language,
    )


@pytest.mark.parametrize(
    ("language", "expected"), [("it", "patrimonio netto"), ("en", "equity")]
)
def test_preview_explains_native_disclosure_reasons(language, expected):
    reason = "always applicable for the selected form; schedule EQUITY is present or reviewer-triggered"

    result = preview_reason(reason, language)

    assert expected in result
    assert "always applicable" not in result
    assert "EQUITY" not in result
    assert "CLIENT.LINE" in preview_reason(
        "statement line CLIENT.LINE is non-zero", language
    )
    assert "EMPLOYEES_OR_BODIES_PRESENT" not in preview_reason(
        "reviewer trigger EMPLOYEES_OR_BODIES_PRESENT", language
    )


def test_preview_shows_exact_source_cell_and_requested_evidence(tmp_path):
    case = _prepared_case(tmp_path)
    case["questionnaire"] = [
        {
            "title": "Current and deferred taxes",
            "state": "OPEN",
            "evidence_requested": "Tax computation",
            "reason": "Client has not supplied it.",
        }
    ]

    result = xbrl_case.render_preview_html(case).decode()

    anchor = case["trial_balance"]["source_anchors"][0]
    document = case["source_documents"][0]
    assert document["file_name"] in result
    assert f'{anchor["column"]}{anchor["row"]}' in result
    assert "Riferimenti alle fonti" in result
    assert "Calcolo delle imposte" in result
    assert "Client has not supplied it." in result
    assert "decisioni mancanti 0" not in result


@pytest.mark.parametrize(
    ("section", "value", "multiplier", "displayed"),
    [
        ("LIABILITIES_EQUITY", "-3500", "-1", "3.500,00"),
        ("INCOME_STATEMENT", "5000", "1", "5.000,00"),
        ("INCOME_RESULT", "-1000", "1", "-1.000,00"),
        ("ASSETS", "-100", "1", "-100,00"),
    ],
)
def test_preview_uses_reviewed_sign_without_turning_losses_positive(
    tmp_path, section, value, multiplier, displayed
):
    case = _prepared_case(tmp_path)
    case["statements"]["facts"] = [
        {
            "statement_section": section,
            "key": "Reviewed item",
            "current_value": value,
            "prior_value": None,
            "currency": "EUR",
            "xbrl_sign_multiplier": multiplier,
        }
    ]
    before = deepcopy(case)

    document = etree.HTML(xbrl_case.render_preview_html(case))

    assert document.xpath(
        '//section[@aria-labelledby="statements-heading"]//tbody/tr/td[3]/text()'
    ) == [displayed]
    assert case == before


@pytest.mark.parametrize("language", ["it", "en"])
def test_preview_uses_readable_statutory_footnote_labels(tmp_path, language):
    case = _prepared_case(tmp_path)
    case["output_language"] = language
    case["micro_reporting"] = {
        "footer_items": [
            {"key": "director_auditor_compensation", "status": "PRESENT", "value": "0"}
        ]
    }

    document = xbrl_case.render_preview_html(case).decode()

    assert "director_auditor_compensation" not in document
    assert (
        "Compensi ad amministratori e revisori"
        if language == "it"
        else "Director and auditor compensation"
    ) in document


@pytest.mark.parametrize(
    ("language", "heading", "section", "amount", "empty"),
    [
        ("it", "Prospetti", "Attivo", "1.234,50", "Nessun prospetto di dettaglio"),
        ("en", "Statements", "Assets", "1,234.50", "No supporting schedules"),
    ],
)
def test_preview_localizes_navigation_and_preserves_source_labels(
    tmp_path, language, heading, section, amount, empty
):
    case = _prepared_case(tmp_path)
    case["output_language"] = language
    case["statements"]["facts"] = [
        {
            "statement_section": "ASSETS",
            "key": "Banca <source>",
            "current_value": "1234.50",
            "prior_value": None,
            "currency": "EUR",
            "source_refs": ["src_0000001"],
        }
    ]
    before = deepcopy(case)

    result = xbrl_case.render_preview_html(case)

    root = etree.HTML(result)
    assert root.get("lang") == language
    assert root.xpath(f'//h2[@id="statements-heading" and text()="{heading}"]')
    assert section in " ".join(root.xpath("//td//text()"))
    assert amount in " ".join(root.xpath("//td//text()"))
    assert "Banca &lt;source&gt;" in result.decode()
    assert empty in result.decode()
    assert not root.xpath("//table[not(tbody/tr)]")
    assert case == before


def test_new_preview_shows_current_checks_without_a_stale_preview_warning(tmp_path):
    case = _prepared_case(tmp_path)
    case = xbrl_case.run_validation(case, "fixture", case["revision_id"])
    assert "REVIEW.PREVIEW_REQUIRED" in {
        issue["rule_id"] for issue in case["validation"]["issues"]
    }
    case["validation"]["issues"].append(
        {
            "rule_id": "STALE.SENTINEL",
            "message": "Obsolete check from a previous version",
            "severity": "BLOCKER",
            "review_status": "UNREVIEWED",
        }
    )

    result = xbrl_case.create_preview(
        case, tmp_path / "current.html", "fixture", case["revision_id"]
    )

    preview = (tmp_path / "current.html").read_text()
    assert "STALE.SENTINEL" not in preview
    assert "REVIEW.PREVIEW_REQUIRED" not in preview
    assert "DISCLOSURE.NEGATIVE_CONFIRMATIONS" in preview
    assert result["validation"] is None
    assert result["approval"] is None
    validation = xbrl_case.validate_case(result)
    assert not any(
        issue["rule_id"].startswith("REVIEW.PREVIEW_") for issue in validation["issues"]
    )
    assert validation["blockers"] > 0
